"""Diff two GTFS feeds: current vs incoming."""

import csv
import io
import math
import os
from pathlib import Path


GTFS_FILES = [
    "agency.txt", "calendar.txt", "calendar_dates.txt",
    "fare_attributes.txt", "feed_info.txt", "routes.txt",
    "shapes.txt", "stop_times.txt", "stops.txt", "trips.txt",
]


def diff_feeds(current_dir: str, incoming_dir: str, city_config: dict) -> dict:
    """Compare two GTFS feed directories and return a structured diff."""
    result = {
        "file_summary": [],
        "routes": _diff_by_key(current_dir, incoming_dir, "routes.txt", "route_id"),
        "stops": _diff_stops(current_dir, incoming_dir, city_config),
        "trips": _diff_by_key(current_dir, incoming_dir, "trips.txt", "trip_id"),
        "calendar": _diff_by_key(current_dir, incoming_dir, "calendar.txt", "service_id"),
        "fare_attributes": _diff_by_key(current_dir, incoming_dir, "fare_attributes.txt", "fare_id"),
        "city_rule_checks": [],
    }

    # File-level summary: row counts and deltas
    for filename in GTFS_FILES:
        current_file = os.path.join(current_dir, filename)
        incoming_file = os.path.join(incoming_dir, filename)

        current_exists = os.path.exists(current_file)
        incoming_exists = os.path.exists(incoming_file)

        current_rows = _count_data_rows(current_file) if current_exists else 0
        incoming_rows = _count_data_rows(incoming_file) if incoming_exists else 0

        status = "unchanged_count"
        if not current_exists and incoming_exists:
            status = "added"
        elif current_exists and not incoming_exists:
            status = "removed"
        elif current_rows != incoming_rows:
            status = "changed"

        result["file_summary"].append({
            "file": filename,
            "status": status,
            "current_rows": current_rows,
            "incoming_rows": incoming_rows,
            "delta": incoming_rows - current_rows,
            "pct_change": _pct_change(current_rows, incoming_rows),
        })

    # City-specific rule checks
    rules = city_config.get("rules", {})
    result["city_rule_checks"] = _check_city_rules(
        current_dir, incoming_dir, result, rules
    )

    return result


def _count_data_rows(filepath: str) -> int:
    """Count non-header rows in a CSV/TXT file."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


def _read_csv(filepath: str) -> list[dict]:
    """Read a GTFS CSV file into a list of dicts."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _diff_by_key(current_dir: str, incoming_dir: str, filename: str, key_field: str) -> dict:
    """Diff two GTFS files by a key field."""
    current_rows = _read_csv(os.path.join(current_dir, filename))
    incoming_rows = _read_csv(os.path.join(incoming_dir, filename))

    current_keys = {row.get(key_field) for row in current_rows if row.get(key_field)}
    incoming_keys = {row.get(key_field) for row in incoming_rows if row.get(key_field)}

    added = sorted(incoming_keys - current_keys)
    removed = sorted(current_keys - incoming_keys)
    common = current_keys & incoming_keys

    # Check for modified rows among common keys
    current_by_key = {row[key_field]: row for row in current_rows if row.get(key_field)}
    incoming_by_key = {row[key_field]: row for row in incoming_rows if row.get(key_field)}

    modified = []
    for key in sorted(common):
        if current_by_key[key] != incoming_by_key[key]:
            changes = {}
            for field in set(list(current_by_key[key].keys()) + list(incoming_by_key[key].keys())):
                old_val = current_by_key[key].get(field, "")
                new_val = incoming_by_key[key].get(field, "")
                if old_val != new_val:
                    changes[field] = {"old": old_val, "new": new_val}
            if changes:
                modified.append({key_field: key, "changes": changes})

    return {
        "added": added[:50],
        "removed": removed[:50],
        "modified": modified[:50],
        "total_added": len(added),
        "total_removed": len(removed),
        "total_modified": len(modified),
        "total_unchanged": len(common) - len(modified),
    }


def _diff_stops(current_dir: str, incoming_dir: str, city_config: dict) -> dict:
    """Diff stops with geographic drift detection."""
    base_diff = _diff_by_key(current_dir, incoming_dir, "stops.txt", "stop_id")

    max_drift = city_config.get("rules", {}).get("max_stop_location_drift_meters", 50)

    current_stops = {
        row["stop_id"]: row
        for row in _read_csv(os.path.join(current_dir, "stops.txt"))
        if row.get("stop_id")
    }
    incoming_stops = {
        row["stop_id"]: row
        for row in _read_csv(os.path.join(incoming_dir, "stops.txt"))
        if row.get("stop_id")
    }

    drifted = []
    for stop_id in set(current_stops) & set(incoming_stops):
        try:
            lat1 = float(current_stops[stop_id].get("stop_lat", 0))
            lon1 = float(current_stops[stop_id].get("stop_lon", 0))
            lat2 = float(incoming_stops[stop_id].get("stop_lat", 0))
            lon2 = float(incoming_stops[stop_id].get("stop_lon", 0))
            dist = _haversine(lat1, lon1, lat2, lon2)
            if dist > max_drift:
                drifted.append({
                    "stop_id": stop_id,
                    "stop_name": current_stops[stop_id].get("stop_name", ""),
                    "drift_meters": round(dist, 1),
                    "old_lat": lat1, "old_lon": lon1,
                    "new_lat": lat2, "new_lon": lon2,
                })
        except (ValueError, TypeError):
            continue

    drifted.sort(key=lambda x: x["drift_meters"], reverse=True)
    base_diff["drifted_stops"] = drifted[:50]
    base_diff["total_drifted"] = len(drifted)
    return base_diff


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _pct_change(old: int, new: int) -> float | None:
    if old == 0:
        return None
    return round(((new - old) / old) * 100, 1)


def _check_city_rules(current_dir: str, incoming_dir: str, diff_result: dict, rules: dict) -> list:
    """Apply city-specific rules and return violations."""
    violations = []

    # Check expected row counts
    incoming_agencies = _count_data_rows(os.path.join(incoming_dir, "agency.txt"))
    expected = rules.get("expected_agency_count")
    if expected is not None and incoming_agencies != expected:
        violations.append({
            "rule": "expected_agency_count",
            "severity": "error",
            "message": f"Expected {expected} agency(ies), found {incoming_agencies}",
        })

    incoming_fares = _count_data_rows(os.path.join(incoming_dir, "fare_attributes.txt"))
    expected_fares = rules.get("expected_fare_count")
    if expected_fares is not None and incoming_fares != expected_fares:
        violations.append({
            "rule": "expected_fare_count",
            "severity": "error",
            "message": f"Expected {expected_fares} fare(s), found {incoming_fares}",
        })

    if rules.get("fare_must_not_be_empty") and incoming_fares == 0:
        violations.append({
            "rule": "fare_must_not_be_empty",
            "severity": "error",
            "message": "fare_attributes.txt has no data rows (header only)",
        })

    # Check required files
    for filename in rules.get("required_files", []):
        path = os.path.join(incoming_dir, filename)
        if not os.path.exists(path):
            violations.append({
                "rule": "required_files",
                "severity": "error",
                "message": f"Required file missing: {filename}",
            })

    # Check percentage change thresholds
    thresholds = {
        "trips.txt": rules.get("trip_count_change_warning_pct"),
        "stops.txt": rules.get("stop_count_change_warning_pct"),
        "routes.txt": rules.get("route_count_change_warning_pct"),
    }

    for file_info in diff_result.get("file_summary", []):
        threshold = thresholds.get(file_info["file"])
        if threshold and file_info["pct_change"] is not None:
            if abs(file_info["pct_change"]) > threshold:
                violations.append({
                    "rule": f"{file_info['file']}_count_change",
                    "severity": "warning",
                    "message": (
                        f"{file_info['file']} changed by {file_info['pct_change']}% "
                        f"({file_info['current_rows']} -> {file_info['incoming_rows']}), "
                        f"threshold is {threshold}%"
                    ),
                })

    return violations
