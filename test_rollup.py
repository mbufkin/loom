#!/usr/bin/env python3
"""Tests for rollup.py (structural pacing inference, no models)."""

import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from rollup import (
    collect_blocked_dates,
    enumerate_instructional_days,
    grading_period_for,
    map_units_to_year,
    rollup,
)
from audit_lib import load_yaml, project_dir


def test_blocked_dates_include_winter_break():
    cal = load_yaml(project_dir("dallas-career-2026") / "school-calendar.yaml")
    blocked = collect_blocked_dates(cal)
    assert date(2026, 12, 25) in blocked
    assert date(2026, 9, 7) in blocked  # Labor Day


def test_instructional_days_skip_weekends():
    cal = load_yaml(project_dir("dallas-career-2026") / "school-calendar.yaml")
    days = enumerate_instructional_days(cal)
    assert len(days) > 150
    assert all(d.weekday() < 5 for d in days)
    assert days[0] == date(2026, 8, 11)


def test_grading_period_fall_1():
    cal = load_yaml(project_dir("dallas-career-2026") / "school-calendar.yaml")
    assert grading_period_for(date(2026, 8, 11), cal) == "fall-1"
    # fall-2 begins 2026-10-13 (Oct 12 is between periods / non-instructional)
    assert grading_period_for(date(2026, 10, 13), cal) == "fall-2"
    assert grading_period_for(date(2026, 10, 12), cal) is None


def test_map_units_sequential_no_overlap():
    root = project_dir("dallas-career-2026")
    manifest = load_yaml(root / "manifest.yaml")
    school_cal = load_yaml(root / "school-calendar.yaml")
    mapped = map_units_to_year(manifest, school_cal, root)
    assert mapped["dated_mode"] is True
    assert len(mapped["units"]) == len(manifest["units"])
    # 18 units, mostly 2-day modules → ~40 days consumed
    assert 35 <= mapped["instructional_days_consumed"] <= 45
    assert not mapped["warnings"]

    dates_used = [p["date"] for p in mapped["flat_map"]]
    assert len(dates_used) == len(
        set(dates_used)
    ), "each instructional date assigned once"


def test_rollup_writes_artifacts():
    rc = __import__("subprocess").call(
        [
            sys.executable,
            str(BASE / "rollup.py"),
            "--project",
            "dallas-career-2026",
            "--force",
        ]
    )
    assert rc == 0
    root = project_dir("dallas-career-2026")
    assert (root / "pacing-plan.yaml").is_file()
    pacing = load_yaml(root / "pacing-plan.yaml")
    assert pacing["source"] == "inferred_from_documents"
    assert pacing["mode"] == "dated"
    assert pacing["summary"]["units_placed"] == len(pacing["units"])
    assert (root / "output" / "03-year-calendar-map.json").is_file()
    year = json.loads((root / "output" / "03-year-calendar-map.json").read_text())
    assert year["placements"]
    assert year["year_at_a_glance"]["grading_period_columns"]


if __name__ == "__main__":
    tests = [
        test_blocked_dates_include_winter_break,
        test_instructional_days_skip_weekends,
        test_grading_period_fall_1,
        test_map_units_sequential_no_overlap,
        test_rollup_writes_artifacts,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print("ALL ROLLUP TESTS PASSED")
