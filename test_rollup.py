#!/usr/bin/env python3
"""Tests for rollup.py (structural pacing inference, no models).

Runs against the synthetic corpus in tests/fixtures/data-root, not a real
district's curriculum. Two reasons, both learned the hard way:

  * These tests used to read a live district tree committed under projects/.
    That is what made the program and its data share a directory, which in turn
    meant shipping the program shipped somebody's curriculum.
  * `test_rollup_writes_artifacts` shells out to `rollup.py --force`, which
    writes pacing-plan.yaml and output/ next to its inputs. Pointed at a
    committed tree, running the suite silently rewrote a tracked file — and on
    Windows, where the default text encoding is cp1252 rather than UTF-8, it
    corrupted the em-dashes in it. A test that mutates its own fixture is a
    test that only passes once.

So each test gets a throwaway copy of the fixture, and both this process and
any subprocess are pointed at it via LOOM_HOME / audit_lib.DATA_DIR.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import audit_lib
from audit_lib import load_yaml, project_dir
from rollup import (
    collect_blocked_dates,
    enumerate_instructional_days,
    grading_period_for,
    map_units_to_year,
)

#: The synthetic curriculum under test. See tests/fixtures/data-root/README.md
#: for the properties the assertions below rely on.
FIXTURE_DATA_ROOT = BASE / "tests" / "fixtures" / "data-root"
PROJECT = "sample-cte-demo"


class _IsolatedDataRoot:
    """Context manager giving each test a private, writable copy of the corpus.

    Sets LOOM_HOME as well as audit_lib.DATA_DIR because `rollup.py` runs as a
    subprocess in one of these tests: the in-process override does not reach a
    fresh interpreter, but the environment variable does. That is exactly what
    LOOM_HOME is for.
    """

    def __enter__(self) -> Path:
        self._tmp = Path(tempfile.mkdtemp(prefix="loom-rollup-"))
        self._root = self._tmp / "data"
        shutil.copytree(FIXTURE_DATA_ROOT, self._root)
        self._saved_env = os.environ.get("LOOM_HOME")
        self._saved_data_dir = audit_lib.DATA_DIR
        os.environ["LOOM_HOME"] = str(self._root)
        audit_lib.DATA_DIR = self._root
        return self._root

    def __exit__(self, *exc: object) -> None:
        audit_lib.DATA_DIR = self._saved_data_dir
        if self._saved_env is None:
            os.environ.pop("LOOM_HOME", None)
        else:
            os.environ["LOOM_HOME"] = self._saved_env
        shutil.rmtree(self._tmp, ignore_errors=True)


def _school_calendar() -> dict:
    return load_yaml(project_dir(PROJECT) / "school-calendar.yaml")


def test_blocked_dates_include_winter_break():
    with _IsolatedDataRoot():
        blocked = collect_blocked_dates(_school_calendar())
        # Inside a {begin, end} holiday span …
        assert date(2030, 12, 25) in blocked
        # … and a standalone {date, name} holiday.
        assert date(2030, 9, 2) in blocked
        # The separate fall_break block is honored too.
        assert date(2030, 10, 13) in blocked


def test_instructional_days_skip_weekends():
    with _IsolatedDataRoot():
        days = enumerate_instructional_days(_school_calendar())
        assert len(days) > 150
        assert all(d.weekday() < 5 for d in days)
        # Both boundaries are weekdays and neither is blocked, so the walk
        # should include the first and last day of class themselves.
        assert days[0] == date(2030, 8, 5)
        assert days[-1] == date(2031, 5, 23)


def test_grading_period_lookup():
    with _IsolatedDataRoot():
        cal = _school_calendar()
        assert grading_period_for(date(2030, 8, 5), cal) == "q1"
        assert grading_period_for(date(2030, 10, 15), cal) == "q2"
        # A weekday belonging to no grading period: q1 ends Oct 10 and q2 opens
        # Oct 15, with fall break in between. Asserting on a weekday matters —
        # a weekend would return None for the wrong reason.
        assert grading_period_for(date(2030, 10, 11), cal) is None


def test_map_units_sequential_no_overlap():
    with _IsolatedDataRoot():
        root = project_dir(PROJECT)
        manifest = load_yaml(root / "manifest.yaml")
        school_cal = load_yaml(root / "school-calendar.yaml")
        mapped = map_units_to_year(manifest, school_cal, root)

        assert mapped["dated_mode"] is True
        assert len(mapped["units"]) == len(manifest["units"])
        # Six units of two days each, placed sequentially.
        assert mapped["instructional_days_consumed"] == 12
        assert not mapped["warnings"]

        dates_used = [p["date"] for p in mapped["flat_map"]]
        assert len(dates_used) == len(set(dates_used)), "each date assigned once"


def test_rollup_writes_artifacts():
    with _IsolatedDataRoot():
        rc = subprocess.call(
            [sys.executable, str(BASE / "rollup.py"), "--project", PROJECT, "--force"]
        )
        assert rc == 0

        root = project_dir(PROJECT)
        assert (root / "pacing-plan.yaml").is_file()
        pacing = load_yaml(root / "pacing-plan.yaml")
        assert pacing["source"] == "inferred_from_documents"
        assert pacing["mode"] == "dated"
        assert pacing["summary"]["units_placed"] == len(pacing["units"])

        year_path = root / "output" / "03-year-calendar-map.json"
        assert year_path.is_file()
        year = json.loads(year_path.read_text(encoding="utf-8"))
        assert year["placements"]
        assert year["year_at_a_glance"]["grading_period_columns"]


if __name__ == "__main__":
    tests = [
        test_blocked_dates_include_winter_break,
        test_instructional_days_skip_weekends,
        test_grading_period_lookup,
        test_map_units_sequential_no_overlap,
        test_rollup_writes_artifacts,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print("ALL ROLLUP TESTS PASSED")
