"""Wrapper for the Etalab transport-validator (Rust binary)."""

import json
import subprocess
from pathlib import Path


BIN_PATH = Path(__file__).parent.parent / "bin" / "transport-validator"


def run(gtfs_zip_path: str) -> dict:
    """Run the Etalab transport-validator on a GTFS zip file.

    Returns a dict with:
      - summary: high-level counts by severity
      - issues: list of individual validation issues
    """
    if not BIN_PATH.exists():
        return {"error": f"Etalab binary not found at {BIN_PATH}. Run setup.sh first."}

    cmd = [
        str(BIN_PATH),
        "--input", gtfs_zip_path,
        "--output-format", "json",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0 and not result.stdout:
        return {
            "error": "Etalab validator failed",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "returncode": result.returncode,
        }

    try:
        raw_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "error": "Failed to parse Etalab JSON output",
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }

    return _parse_output(raw_output)


def _parse_output(raw_output) -> dict:
    """Parse the Etalab validator JSON output into a structured result."""
    issues = []
    summary = {"errors": 0, "warnings": 0, "infos": 0}

    # Etalab output can be a list of validations or a single object
    validations = raw_output if isinstance(raw_output, list) else raw_output.get("validations", [raw_output])

    for validation in validations:
        severity = validation.get("severity", "Information").lower()
        issue_type = validation.get("issue_type", "unknown")
        object_id = validation.get("object_id", "")
        object_name = validation.get("object_name", "")
        related_objects = validation.get("related_objects", [])

        if severity in ("fatal", "error"):
            summary["errors"] += 1
            severity = "error"
        elif severity == "warning":
            summary["warnings"] += 1
        else:
            summary["infos"] += 1
            severity = "info"

        issues.append({
            "issue_type": issue_type,
            "severity": severity,
            "object_id": object_id,
            "object_name": object_name,
            "related_objects": related_objects[:3],
            "details": validation.get("details", ""),
        })

    return {
        "validator": "Etalab",
        "summary": summary,
        "issues": issues,
    }
