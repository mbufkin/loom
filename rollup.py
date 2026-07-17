#!/usr/bin/env python3
"""
rollup.py — Structural backfill: unit calendars → year-at-a-glance pacing plan.

Reverse-inference layer (code only, no models):
  - Reads school-calendar.yaml + manifest + units/*/calendar.yaml
  - Maps each unit day (d1, d2, …) onto district instructional dates
  - Writes pacing-plan.yaml + output/03-year-calendar-map.{json,md}

Auditor charter: infers *planning maps* only — never creates lesson content.
Every output is labeled source: inferred_from_documents.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from audit_lib import atomic_write, load_yaml, log, project_dir

DISCLAIMER = (
    "Inferred projected map — reconstructed from available documents. "
    "Not official district curriculum. Does not replace missing lesson materials."
)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip())


def _date_range(begin: str, end: str) -> list[date]:
    start = _parse_date(begin)
    stop = _parse_date(end)
    out: list[date] = []
    cur = start
    while cur <= stop:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def collect_blocked_dates(school_cal: dict) -> set[date]:
    """Dates when student-facing lessons should not be scheduled."""
    blocked: set[date] = set()
    for key in (
        "professional_development",
        "teacher_workdays",
        "inclement_weather_days",
    ):
        for entry in school_cal.get(key) or []:
            if isinstance(entry, str):
                blocked.add(_parse_date(entry))
    for holiday in school_cal.get("holidays_no_school") or []:
        if isinstance(holiday, str):
            blocked.add(_parse_date(holiday))
            continue
        if holiday.get("date"):
            blocked.add(_parse_date(holiday["date"]))
        if holiday.get("begin") and holiday.get("end"):
            blocked.update(_date_range(holiday["begin"], holiday["end"]))
    fb = school_cal.get("fall_break")
    if isinstance(fb, dict) and fb.get("begin") and fb.get("end"):
        blocked.update(_date_range(fb["begin"], fb["end"]))
    return blocked


def is_instructional_day(d: date, blocked: set[date]) -> bool:
    # District calendars assume Mon–Fri instructional weeks.
    return d.weekday() < 5 and d not in blocked


def enumerate_instructional_days(school_cal: dict) -> list[date]:
    """
    Walk first_day_of_class → last_day_of_class, skipping blocked/non-weekday days.
    Returns empty list when district spine dates are absent.
    """
    first = school_cal.get("first_day_of_class")
    last = school_cal.get("last_day_of_class")
    if not first or not last:
        return []
    blocked = collect_blocked_dates(school_cal)
    start = _parse_date(first)
    end = _parse_date(last)
    days: list[date] = []
    cur = start
    while cur <= end:
        if is_instructional_day(cur, blocked):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def grading_period_for(d: date, school_cal: dict) -> str | None:
    for period in school_cal.get("grading_periods") or []:
        begin = period.get("begin")
        end = period.get("end")
        if not begin or not end:
            continue
        if _parse_date(begin) <= d <= _parse_date(end):
            return period.get("id")
    return None


def load_unit_calendar(root: Path, unit_entry: dict) -> dict:
    cal_path = root / unit_entry["calendar"]
    if not cal_path.is_file():
        raise FileNotFoundError(f"Missing unit calendar: {cal_path}")
    return load_yaml(cal_path)


def unit_length(calendar: dict) -> int:
    explicit = calendar.get("unit_length_days")
    if explicit:
        return int(explicit)
    days = calendar.get("days") or []
    return len(days) if days else 1


def map_units_to_year(
    manifest: dict,
    school_cal: dict,
    root: Path,
) -> dict[str, Any]:
    """
    Place manifest units sequentially on instructional days (or sequential indices
    when no district calendar dates exist).
    """
    instructional = enumerate_instructional_days(school_cal)
    dated_mode = bool(instructional)
    units_out: list[dict[str, Any]] = []
    flat_map: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    day_cursor = 0
    seq_cursor = 1

    for unit_id, unit_entry in manifest.get("units", {}).items():
        calendar = load_unit_calendar(root, unit_entry)
        length = unit_length(calendar)
        day_defs = calendar.get("days") or []
        day_ids = [d.get("id", f"d{i+1}") for i, d in enumerate(day_defs)]
        if not day_ids:
            day_ids = [f"d{i+1}" for i in range(length)]

        unit_record: dict[str, Any] = {
            "unit_id": unit_id,
            "title": unit_entry.get("title") or calendar.get("title") or unit_id,
            "calendar": unit_entry["calendar"],
            "unit_length_days": length,
            "source": "inferred_from_documents",
            "day_map": {},
        }

        if dated_mode:
            if day_cursor + length > len(instructional):
                warnings.append(
                    {
                        "type": "units_exceed_instructional_days",
                        "unit_id": unit_id,
                        "message": (
                            f"Not enough instructional days remaining for {unit_id} "
                            f"({length} needed, {len(instructional) - day_cursor} left)"
                        ),
                    }
                )
                unit_record["placement_status"] = "unplaced"
                units_out.append(unit_record)
                continue

            assigned = instructional[day_cursor : day_cursor + length]
            day_cursor += length
            unit_record["start_date"] = assigned[0].isoformat()
            unit_record["end_date"] = assigned[-1].isoformat()
            unit_record["grading_period_id"] = grading_period_for(
                assigned[0], school_cal
            )
            for i, day_id in enumerate(day_ids):
                if i < len(assigned):
                    iso = assigned[i].isoformat()
                    unit_record["day_map"][day_id] = iso
                    flat_map.append(
                        {
                            "unit_id": unit_id,
                            "unit_title": unit_record["title"],
                            "day_id": day_id,
                            "day_label": (
                                day_defs[i].get("label")
                                if i < len(day_defs)
                                else day_id
                            ),
                            "date": iso,
                            "grading_period_id": grading_period_for(
                                assigned[i], school_cal
                            ),
                            "instructional_day_index": instructional.index(assigned[i])
                            + 1,
                        }
                    )
        else:
            # No district dates — still infer relative unit order and day indices.
            unit_record["placement_status"] = "sequential_only"
            unit_record["start_instructional_index"] = seq_cursor
            unit_record["end_instructional_index"] = seq_cursor + length - 1
            for i, day_id in enumerate(day_ids):
                idx = seq_cursor + i
                unit_record["day_map"][day_id] = f"instructional_day_{idx}"
                flat_map.append(
                    {
                        "unit_id": unit_id,
                        "unit_title": unit_record["title"],
                        "day_id": day_id,
                        "day_label": (
                            day_defs[i].get("label") if i < len(day_defs) else day_id
                        ),
                        "date": None,
                        "instructional_day_index": idx,
                        "grading_period_id": None,
                    }
                )
            seq_cursor += length

        units_out.append(unit_record)

    return {
        "dated_mode": dated_mode,
        "instructional_days_available": len(instructional) if dated_mode else None,
        "instructional_days_consumed": day_cursor if dated_mode else seq_cursor - 1,
        "units": units_out,
        "flat_map": flat_map,
        "warnings": warnings,
    }


def build_year_at_a_glance(
    mapped: dict[str, Any],
    school_cal: dict,
) -> dict[str, Any]:
    """
    Cluster × grading-period grid: which units *start* in each nine-week window.
    Structural summary only — not official district pacing.
    """
    periods = school_cal.get("grading_periods") or []
    period_ids = [p.get("id", f"p{i}") for i, p in enumerate(periods)]
    if not period_ids:
        period_ids = ["unassigned"]

    by_period: dict[str, list[str]] = {pid: [] for pid in period_ids}
    by_period.setdefault("unassigned", [])

    for unit in mapped["units"]:
        pid = unit.get("grading_period_id") or "unassigned"
        if pid not in by_period:
            by_period[pid] = []
        by_period[pid].append(unit["unit_id"])

    columns = []
    for period in periods:
        pid = period.get("id", "")
        units_in = by_period.get(pid, [])
        columns.append(
            {
                "id": pid,
                "label": period.get("label", pid),
                "begin": period.get("begin"),
                "end": period.get("end"),
                "unit_ids": units_in,
                "unit_count": len(units_in),
            }
        )
    if not columns:
        columns.append(
            {
                "id": "sequential",
                "label": "Inferred sequence (no grading periods)",
                "unit_ids": [u["unit_id"] for u in mapped["units"]],
                "unit_count": len(mapped["units"]),
            }
        )

    rows = []
    for unit in mapped["units"]:
        span: list[str] = []
        for col in columns:
            if unit["unit_id"] in col.get("unit_ids", []):
                span.append(col["id"])
        rows.append(
            {
                "unit_id": unit["unit_id"],
                "title": unit["title"],
                "start_date": unit.get("start_date"),
                "end_date": unit.get("end_date"),
                "unit_length_days": unit["unit_length_days"],
                "grading_periods_spanned": span,
            }
        )

    return {"grading_period_columns": columns, "unit_rows": rows}


def build_pacing_plan(
    project_id: str,
    manifest: dict,
    school_cal: dict,
    mapped: dict[str, Any],
    yag: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    placed = [u for u in mapped["units"] if u.get("placement_status") != "unplaced"]
    unplaced = [
        u["unit_id"] for u in mapped["units"] if u.get("placement_status") == "unplaced"
    ]

    return {
        "project_id": project_id,
        "school_year": school_cal.get("school_year"),
        "district": school_cal.get("district"),
        "source": "inferred_from_documents",
        "disclaimer": DISCLAIMER,
        "source_school_calendar": "school-calendar.yaml",
        "generated_at": now,
        "generated_by": "rollup.py",
        "mode": "dated" if mapped["dated_mode"] else "sequential",
        "summary": {
            "units_total": len(mapped["units"]),
            "units_placed": len(placed),
            "units_unplaced": len(unplaced),
            "instructional_days_available": mapped["instructional_days_available"],
            "instructional_days_consumed": mapped["instructional_days_consumed"],
            "instructional_days_remaining": (
                (mapped["instructional_days_available"] or 0)
                - mapped["instructional_days_consumed"]
                if mapped["dated_mode"]
                else None
            ),
        },
        "year_at_a_glance": yag,
        "units": [
            {k: v for k, v in u.items() if k != "placement_status"}
            for u in mapped["units"]
        ],
        "warnings": mapped["warnings"],
    }


def render_year_map_md(pacing: dict[str, Any]) -> str:
    lines = [
        "# Year Calendar Map (inferred)",
        "",
        f"**Project:** {pacing.get('project_id')}  ",
        f"**School year:** {pacing.get('school_year') or '—'}  ",
        f"**Mode:** {pacing.get('mode')}  ",
        "",
        f"> {pacing.get('disclaimer')}",
        "",
        "## Summary",
        "",
        f"- Units placed: **{pacing['summary']['units_placed']}** / {pacing['summary']['units_total']}",
    ]
    if pacing["summary"].get("instructional_days_available") is not None:
        lines.append(
            f"- Instructional days used: **{pacing['summary']['instructional_days_consumed']}** "
            f"/ {pacing['summary']['instructional_days_available']} "
            f"({pacing['summary'].get('instructional_days_remaining', 0)} remaining)"
        )
    lines.extend(["", "## Year at a glance (units by grading period)", ""])

    yag = pacing.get("year_at_a_glance") or {}
    cols = yag.get("grading_period_columns") or []
    if cols:
        header = "| Grading period | Units starting here |"
        sep = "|----------------|----------------------|"
        lines.extend([header, sep])
        for col in cols:
            units = ", ".join(f"`{u}`" for u in col.get("unit_ids", [])) or "—"
            lines.append(f"| {col.get('label', col.get('id'))} | {units} |")
        lines.append("")

    lines.extend(
        [
            "## Unit timeline",
            "",
            "| Unit | Start | End | Days | Day map |",
            "|------|-------|-----|------|---------|",
        ]
    )
    for u in pacing.get("units", []):
        dm = ", ".join(f"{k}→{v}" for k, v in (u.get("day_map") or {}).items())
        lines.append(
            f"| {u.get('title', u['unit_id'])} | {u.get('start_date', '—')} | "
            f"{u.get('end_date', '—')} | {u.get('unit_length_days')} | {dm} |"
        )

    warnings = pacing.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for w in warnings:
            lines.append(
                f"- **{w.get('type')}** ({w.get('unit_id', '—')}): {w.get('message')}"
            )

    return "\n".join(lines) + "\n"


def rollup(project_id: str, force: bool = False) -> Path:
    root = project_dir(project_id)
    manifest_path = root / "manifest.yaml"
    school_path = root / "school-calendar.yaml"
    pacing_path = root / "pacing-plan.yaml"
    out_dir = root / "output"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    if pacing_path.is_file() and not force:
        log(f"rollup: {pacing_path} exists (use --force to regenerate)")
        return pacing_path

    manifest = load_yaml(manifest_path)
    school_cal = load_yaml(school_path) if school_path.is_file() else {}

    if not school_cal:
        log("WARN: no school-calendar.yaml — using sequential mode only")

    mapped = map_units_to_year(manifest, school_cal, root)
    yag = build_year_at_a_glance(mapped, school_cal)
    pacing = build_pacing_plan(project_id, manifest, school_cal, mapped, yag)

    atomic_write(
        pacing_path,
        yaml.dump(
            pacing, sort_keys=False, allow_unicode=True, default_flow_style=False
        ),
    )

    year_json = {
        "project_id": project_id,
        "source": "inferred_from_documents",
        "disclaimer": DISCLAIMER,
        "mode": pacing["mode"],
        "summary": pacing["summary"],
        "year_at_a_glance": yag,
        "placements": mapped["flat_map"],
        "warnings": mapped["warnings"],
    }
    atomic_write(out_dir / "03-year-calendar-map.json", json.dumps(year_json, indent=2))
    atomic_write(out_dir / "03-year-calendar-map.md", render_year_map_md(pacing))

    log(
        f"rollup: {len(mapped['units'])} units → {pacing_path.name} "
        f"({pacing['mode']}, {pacing['summary']['instructional_days_consumed']} days consumed)"
    )
    return pacing_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Roll unit calendars up to inferred year-at-a-glance pacing plan"
    )
    parser.add_argument("--project", required=True, help="Project id under projects/")
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if pacing-plan exists"
    )
    args = parser.parse_args()
    try:
        rollup(args.project, force=args.force)
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
