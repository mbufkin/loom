"""Build calendar coverage matrices for PDF and markdown reports."""

from __future__ import annotations

from typing import Any


def _find_on_day(by_slot: dict, day_id: str, role: str) -> dict | None:
    for p in by_slot.get(day_id, []):
        if p.get("role") == role:
            return p
    return None


def _find_supporting(by_slot: dict, role: str) -> dict | None:
    for p in by_slot.get("unit_supporting", []):
        if p.get("role") == role:
            return p
    return None


def build_coverage_matrix(calendar: dict, gap_report: dict) -> dict[str, Any]:
    """
    Calendar-first structure for reports.
    Each day column shows expected artifacts with present / missing / misplaced.
    """
    by_slot = gap_report.get("placements_by_slot", {})
    missing_set = {
        (m["day_id"], m["expected"]) for m in gap_report.get("missing_slots", [])
    }

    days = []
    day_columns = []
    for day in calendar.get("days", []):
        day_id = day["id"]
        cells = []
        for expected in day.get("expected", []):
            on_day = _find_on_day(by_slot, day_id, expected)
            if on_day:
                status = "present"
                detail = on_day
            else:
                supporting = _find_supporting(by_slot, expected)
                if supporting and (day_id, expected) in missing_set:
                    status = "misplaced"
                    detail = supporting
                else:
                    status = "missing"
                    detail = None
            cells.append(
                {
                    "artifact": expected,
                    "status": status,
                    "placement": detail,
                }
            )
        present_n = sum(1 for c in cells if c["status"] == "present")
        expected_n = len(cells)
        day_columns.append(
            {
                "id": day_id,
                "label": day.get("label", day_id),
                "cells": cells,
                "coverage_pct": (
                    round(100 * present_n / expected_n) if expected_n else 100
                ),
                "present": present_n,
                "expected": expected_n,
            }
        )
        days.append(day_id)

    supporting_rows = []
    for role in calendar.get("unit_supporting", []):
        items = [p for p in by_slot.get("unit_supporting", []) if p.get("role") == role]
        supporting_rows.append(
            {
                "artifact": role,
                "status": "present" if items else "absent",
                "placements": items,
            }
        )

    total_expected = sum(d["expected"] for d in day_columns)
    total_present = sum(d["present"] for d in day_columns)
    unit_coverage = (
        round(100 * total_present / total_expected) if total_expected else 100
    )

    return {
        "title": calendar.get("title", calendar.get("unit_id", "")),
        "unit_length_days": calendar.get("unit_length_days", len(day_columns)),
        "day_columns": day_columns,
        "supporting_rows": supporting_rows,
        "unit_coverage_pct": unit_coverage,
        "missing_slots": gap_report.get("missing_slots", []),
        "unplaced_documents": gap_report.get("unplaced_documents", []),
        "placement_count": gap_report.get("placement_count", 0),
    }
