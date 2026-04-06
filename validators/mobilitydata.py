"""Wrapper for the MobilityData canonical GTFS validator (Java JAR)."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


JAR_PATH = Path(__file__).parent.parent / "bin" / "gtfs-validator.jar"


def run(gtfs_zip_path: str) -> dict:
    """Run the MobilityData validator on a GTFS zip file.

    Returns a dict with:
      - summary: high-level counts by severity
      - notices: list of individual validation notices
      - raw_report: the full parsed JSON report
    """
    if not JAR_PATH.exists():
        return {"error": f"Validator JAR not found at {JAR_PATH}. Run setup.sh first."}

    with tempfile.TemporaryDirectory() as output_dir:
        cmd = [
            "java", "-jar", str(JAR_PATH),
            "-i", gtfs_zip_path,
            "-o", output_dir,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        report_path = os.path.join(output_dir, "report.json")
        if not os.path.exists(report_path):
            return {
                "error": "Validator did not produce a report",
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
                "returncode": result.returncode,
            }

        with open(report_path) as f:
            raw_report = json.load(f)

        return _parse_report(raw_report)


def _parse_report(raw_report: dict) -> dict:
    """Parse the MobilityData JSON report into a structured result."""
    notices = []
    summary = {"errors": 0, "warnings": 0, "infos": 0}

    for notice_group in raw_report.get("notices", []):
        severity = notice_group.get("severity", "UNKNOWN").lower()
        code = notice_group.get("code", "unknown")
        total = notice_group.get("totalNotices", 0)

        if severity == "error":
            summary["errors"] += total
        elif severity == "warning":
            summary["warnings"] += total
        elif severity in ("info", "information"):
            summary["infos"] += total

        sample_notices = notice_group.get("sampleNotices", [])

        notices.append({
            "code": code,
            "severity": severity,
            "total_count": total,
            "samples": sample_notices[:5],
        })

    return {
        "validator": "MobilityData",
        "version": "7.1.0",
        "summary": summary,
        "notices": notices,
        "raw_report": raw_report,
    }
