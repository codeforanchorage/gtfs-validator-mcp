"""GTFS Validator MCP Server.

Exposes tools for validating GTFS feeds from GitHub repos using
MobilityData and Etalab validators, diffing current vs incoming feeds,
and applying city-specific validation rules.
"""

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from validators import mobilitydata, etalab
from gtfs_diff import diff_feeds

# --- Configuration ---
CITIES_DIR = Path(__file__).parent / "cities"
CACHE_DIR = Path(__file__).parent / "cache"

mcp = FastMCP("GTFS Validator")


# --- Helpers ---

def _load_city_config(city: str) -> dict | None:
    """Load a city config JSON file."""
    config_path = CITIES_DIR / f"{city.lower()}.json"
    if not config_path.exists():
        return None
    with open(config_path) as f:
        return json.load(f)


def _list_available_cities() -> list[str]:
    """List all available city config files."""
    if not CITIES_DIR.exists():
        return []
    return [p.stem for p in CITIES_DIR.glob("*.json")]


def _download_github_directory(repo: str, path: str, dest_dir: str) -> str:
    """Download a directory from a GitHub repo into dest_dir.

    Uses the GitHub API to list contents then downloads each file.
    Returns the local directory path.
    """
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    local_dir = os.path.join(dest_dir, os.path.basename(path))
    os.makedirs(local_dir, exist_ok=True)

    with httpx.Client(timeout=60) as client:
        resp = client.get(api_url)
        resp.raise_for_status()
        contents = resp.json()

        for item in contents:
            if item["type"] == "file":
                file_resp = client.get(item["download_url"])
                file_resp.raise_for_status()
                file_path = os.path.join(local_dir, item["name"])
                with open(file_path, "wb") as f:
                    f.write(file_resp.content)

    return local_dir


def _zip_directory(dir_path: str, zip_path: str) -> str:
    """Zip a directory of GTFS files for validator input."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in os.listdir(dir_path):
            filepath = os.path.join(dir_path, file)
            if os.path.isfile(filepath):
                zf.write(filepath, file)
    return zip_path


def _fetch_and_zip_feed(repo: str, path: str, work_dir: str, label: str) -> tuple[str, str]:
    """Download a GTFS feed from GitHub and zip it.

    Returns (directory_path, zip_path).
    """
    feed_dir = _download_github_directory(repo, path, work_dir)
    zip_path = os.path.join(work_dir, f"{label}.zip")
    _zip_directory(feed_dir, zip_path)
    return feed_dir, zip_path


def _download_and_unzip_url(url: str, work_dir: str, label: str) -> tuple[str, str]:
    """Download a GTFS zip from a URL and unzip it.

    Returns (directory_path, zip_path).
    """
    zip_path = os.path.join(work_dir, f"{label}.zip")
    feed_dir = os.path.join(work_dir, label)
    os.makedirs(feed_dir, exist_ok=True)

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            f.write(resp.content)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(feed_dir)

    return feed_dir, zip_path


# --- MCP Tools ---

@mcp.tool()
def list_cities() -> str:
    """List all cities with GTFS validation configs available."""
    cities = _list_available_cities()
    configs = []
    for city in cities:
        config = _load_city_config(city)
        configs.append({
            "id": city,
            "city": config.get("city"),
            "agency": config.get("agency"),
            "repo": config.get("repo"),
        })
    return json.dumps({"cities": configs}, indent=2)


@mcp.tool()
def get_config(city: str) -> str:
    """Get the full validation config for a city.

    Args:
        city: City identifier (e.g. 'anchorage')
    """
    config = _load_city_config(city)
    if config is None:
        return json.dumps({"error": f"No config found for city: {city}"})
    return json.dumps(config, indent=2)


@mcp.tool()
def validate_url(url: str, city: str = "") -> str:
    """Validate a GTFS zip from any URL before committing it to a repo.

    Downloads the zip, runs both validators, and optionally applies
    city-specific rules if a city is specified. Useful for checking a
    transit agency's published feed before importing it.

    Args:
        url: Direct URL to a GTFS zip file
        city: Optional city identifier to apply city-specific rules (e.g. 'anchorage')
    """
    config = _load_city_config(city) if city else None

    with tempfile.TemporaryDirectory() as work_dir:
        try:
            feed_dir, zip_path = _download_and_unzip_url(url, work_dir, "feed")
        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"Failed to download: {e.response.status_code} {url}"})
        except Exception as e:
            return json.dumps({"error": f"Failed to download/unzip: {str(e)}"})

        # Pass 1: MobilityData
        pass1 = mobilitydata.run(zip_path)

        # Pass 2: Etalab
        pass2 = etalab.run(zip_path)

        # Pass 3: City-specific rules (if city provided)
        city_checks = _run_city_checks(feed_dir, config) if config else []

        # Basic file inventory
        gtfs_files = [f for f in os.listdir(feed_dir) if f.endswith(".txt")]

        result = {
            "source_url": url,
            "city": config["city"] if config else None,
            "files_found": sorted(gtfs_files),
            "pass_1_mobilitydata": {
                "summary": pass1.get("summary"),
                "notices": pass1.get("notices", []),
                "error": pass1.get("error"),
            },
            "pass_2_etalab": {
                "summary": pass2.get("summary"),
                "issues": pass2.get("issues", []),
                "error": pass2.get("error"),
            },
            "pass_3_city_rules": city_checks,
            "overall_summary": _combine_summaries(pass1, pass2, city_checks),
        }

    return json.dumps(result, indent=2)


@mcp.tool()
def validate(city: str, feed: str = "incoming") -> str:
    """Validate a GTFS feed using both MobilityData and Etalab validators.

    Runs two passes:
      Pass 1: MobilityData canonical validator (spec compliance)
      Pass 2: Etalab transport-validator (practical checks)

    Then applies city-specific rules from the city config.

    Args:
        city: City identifier (e.g. 'anchorage')
        feed: Which feed to validate - 'current' or 'incoming' (default: 'incoming')
    """
    config = _load_city_config(city)
    if config is None:
        return json.dumps({"error": f"No config found for city: {city}"})

    repo = config["repo"]
    feed_path = config["current_path"] if feed == "current" else config["incoming_path"]

    with tempfile.TemporaryDirectory() as work_dir:
        # Download and zip the feed
        feed_dir, zip_path = _fetch_and_zip_feed(repo, feed_path, work_dir, feed)

        # Pass 1: MobilityData
        pass1 = mobilitydata.run(zip_path)

        # Pass 2: Etalab
        pass2 = etalab.run(zip_path)

        # Pass 3: City-specific rule checks on the raw files
        city_checks = _run_city_checks(feed_dir, config)

        result = {
            "city": config["city"],
            "feed": feed,
            "repo": repo,
            "path": feed_path,
            "pass_1_mobilitydata": {
                "summary": pass1.get("summary"),
                "notices": pass1.get("notices", []),
                "error": pass1.get("error"),
            },
            "pass_2_etalab": {
                "summary": pass2.get("summary"),
                "issues": pass2.get("issues", []),
                "error": pass2.get("error"),
            },
            "pass_3_city_rules": city_checks,
            "overall_summary": _combine_summaries(pass1, pass2, city_checks),
        }

    return json.dumps(result, indent=2)


@mcp.tool()
def diff(city: str) -> str:
    """Diff the current vs incoming GTFS feed for a city.

    Compares files, routes, stops (with geographic drift detection),
    trips, calendars, and fares. Applies city-specific thresholds.

    Args:
        city: City identifier (e.g. 'anchorage')
    """
    config = _load_city_config(city)
    if config is None:
        return json.dumps({"error": f"No config found for city: {city}"})

    repo = config["repo"]

    with tempfile.TemporaryDirectory() as work_dir:
        current_dir = _download_github_directory(repo, config["current_path"], work_dir)
        incoming_dir = _download_github_directory(repo, config["incoming_path"], work_dir)

        result = diff_feeds(current_dir, incoming_dir, config)
        result["city"] = config["city"]
        result["repo"] = repo

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def validate_and_diff(city: str) -> str:
    """Run full validation on incoming feed AND diff against current.

    This is the all-in-one tool that runs:
      1. MobilityData validation on incoming
      2. Etalab validation on incoming
      3. City-specific rule checks
      4. Diff current vs incoming

    Args:
        city: City identifier (e.g. 'anchorage')
    """
    config = _load_city_config(city)
    if config is None:
        return json.dumps({"error": f"No config found for city: {city}"})

    repo = config["repo"]

    with tempfile.TemporaryDirectory() as work_dir:
        # Download both feeds
        current_dir = _download_github_directory(repo, config["current_path"], work_dir)
        incoming_dir = _download_github_directory(repo, config["incoming_path"], work_dir)

        # Zip incoming for validators
        incoming_zip = os.path.join(work_dir, "incoming.zip")
        _zip_directory(incoming_dir, incoming_zip)

        # Validation passes
        pass1 = mobilitydata.run(incoming_zip)
        pass2 = etalab.run(incoming_zip)
        city_checks = _run_city_checks(incoming_dir, config)

        # Diff
        diff_result = diff_feeds(current_dir, incoming_dir, config)

        result = {
            "city": config["city"],
            "repo": repo,
            "validation": {
                "pass_1_mobilitydata": {
                    "summary": pass1.get("summary"),
                    "notices": pass1.get("notices", []),
                    "error": pass1.get("error"),
                },
                "pass_2_etalab": {
                    "summary": pass2.get("summary"),
                    "issues": pass2.get("issues", []),
                    "error": pass2.get("error"),
                },
                "pass_3_city_rules": city_checks,
                "overall_summary": _combine_summaries(pass1, pass2, city_checks),
            },
            "diff": diff_result,
        }

    return json.dumps(result, indent=2, default=str)


# --- Internal helpers ---

def _run_city_checks(feed_dir: str, config: dict) -> list:
    """Run city-specific validation rules on raw GTFS files."""
    import csv

    rules = config.get("rules", {})
    violations = []

    def count_rows(filename):
        path = os.path.join(feed_dir, filename)
        if not os.path.exists(path):
            return -1
        with open(path, "r", encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)

    # Agency count
    expected = rules.get("expected_agency_count")
    if expected is not None:
        actual = count_rows("agency.txt")
        if actual != expected:
            violations.append({
                "rule": "expected_agency_count",
                "severity": "error",
                "expected": expected,
                "actual": actual,
                "message": f"Expected {expected} agency(ies), found {actual}",
            })

    # Fare count
    expected_fares = rules.get("expected_fare_count")
    if expected_fares is not None:
        actual = count_rows("fare_attributes.txt")
        if actual != expected_fares:
            violations.append({
                "rule": "expected_fare_count",
                "severity": "error",
                "expected": expected_fares,
                "actual": actual,
                "message": f"Expected {expected_fares} fare(s), found {actual}",
            })

    # Fare not empty
    if rules.get("fare_must_not_be_empty"):
        actual = count_rows("fare_attributes.txt")
        if actual == 0:
            violations.append({
                "rule": "fare_must_not_be_empty",
                "severity": "error",
                "message": "fare_attributes.txt has no data rows",
            })

    # Required files
    for filename in rules.get("required_files", []):
        if not os.path.exists(os.path.join(feed_dir, filename)):
            violations.append({
                "rule": "required_files",
                "severity": "error",
                "message": f"Required file missing: {filename}",
            })

    return violations


def _combine_summaries(pass1: dict, pass2: dict, city_checks: list) -> dict:
    """Combine results from all passes into one overall summary."""
    p1 = pass1.get("summary", {})
    p2 = pass2.get("summary", {})

    city_errors = sum(1 for c in city_checks if c.get("severity") == "error")
    city_warnings = sum(1 for c in city_checks if c.get("severity") == "warning")

    total_errors = p1.get("errors", 0) + p2.get("errors", 0) + city_errors
    total_warnings = p1.get("warnings", 0) + p2.get("warnings", 0) + city_warnings

    return {
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "pass_1_errors": p1.get("errors", 0),
        "pass_1_warnings": p1.get("warnings", 0),
        "pass_2_errors": p2.get("errors", 0),
        "pass_2_warnings": p2.get("warnings", 0),
        "city_rule_errors": city_errors,
        "city_rule_warnings": city_warnings,
        "has_blockers": total_errors > 0,
    }


# --- Entry point ---

if __name__ == "__main__":
    import sys
    import uvicorn
    print("Starting GTFS Validator MCP Server on port 8080...", file=sys.stderr)
    app = mcp.sse_app()
    uvicorn.run(app, host="0.0.0.0", port=8080, server_header=False, proxy_headers=True, forwarded_allow_ips="*")
