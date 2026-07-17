#!/usr/bin/env python3
"""
meeting.py — meeting_count metadata only (no per-day plate split).

Derive from Estimated Day(s), Day N headers / regex_day_hints_prior, then calendar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from audit_lib import load_yaml, project_dir

ESTIMATED_RE = re.compile(r"Estimated\s+Day\(s\):\s*(\d+)", re.I)
DAY_N_RE = re.compile(r"\bDay\s*(\d+)\b", re.I)


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return [] if "ledger" in path.name else {}
    return json.loads(path.read_text(encoding="utf-8"))


def derive_meeting_span(
    project_id: str,
    unit_id: str,
    doc_ids: set[str],
) -> dict:
    """Return meeting_count + evidence; never invent instructional content."""
    root = project_dir(project_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []

    estimated = 0
    max_day_header = 0
    hint_max = 0
    for e in ledger:
        if e.get("doc_id") not in doc_ids:
            continue
        ex = e.get("excerpt") or ""
        for m in ESTIMATED_RE.finditer(ex):
            estimated = max(estimated, int(m.group(1)))
        for m in DAY_N_RE.finditer(ex):
            max_day_header = max(max_day_header, int(m.group(1)))
        hints = e.get("regex_day_hints_prior")
        if isinstance(hints, list):
            for h in hints:
                try:
                    hint_max = max(hint_max, int(h))
                except (TypeError, ValueError):
                    pass
        pos = e.get("inferred_position") or ""
        for m in DAY_N_RE.finditer(str(pos)):
            max_day_header = max(max_day_header, int(m.group(1)))

    calendar_days = 0
    cal_path = root / "units" / unit_id / "calendar.yaml"
    if cal_path.is_file():
        cal = load_yaml(cal_path)
        calendar_days = len(cal.get("days") or [])

    pacing_days = 0
    pacing_path = root / "pacing-plan.yaml"
    if pacing_path.is_file():
        pacing = load_yaml(pacing_path)
        for u in pacing.get("units") or []:
            if u.get("unit_id") == unit_id:
                pacing_days = int(u.get("unit_length_days") or 0)
                dm = u.get("day_map")
                if isinstance(dm, dict) and not pacing_days:
                    pacing_days = len(dm)
                break

    inferred_days = 0
    inf_path = root / "calendars_inferred" / "INFERRED-CALENDARS.json"
    if inf_path.is_file():
        inf = _load_json(inf_path)
        units = inf.get("units") or {}
        row = None
        if isinstance(units, dict):
            row = units.get(unit_id)
        elif isinstance(units, list):
            row = next((x for x in units if x.get("unit_id") == unit_id), None)
        if row:
            days = row.get("days") or []
            inferred_days = len(days) if isinstance(days, list) else 0

    cal_fallback = max(calendar_days, pacing_days, inferred_days)
    header_days = max(max_day_header, hint_max)
    meeting_count = max(estimated, header_days, cal_fallback)

    sources: list[str] = []
    if estimated:
        sources.append("estimated_days")
    if header_days:
        sources.append("day_headers")
    if cal_fallback:
        sources.append("calendar")

    return {
        "unit_id": unit_id,
        "meeting_count": meeting_count or None,
        "meeting_source": "+".join(sources) if sources else None,
        "evidence": {
            "estimated_days": estimated or None,
            "max_day_header": header_days or None,
            "calendar_days": calendar_days or None,
            "pacing_unit_length_days": pacing_days or None,
            "inferred_days": inferred_days or None,
        },
    }


def signal_expects_lesson_plan(project_id: str, unit_id: str) -> tuple[bool, list[str]]:
    """True when calendar/pacing implies instructional lesson material should exist."""
    root = project_dir(project_id)
    reasons: list[str] = []
    cal_path = root / "units" / unit_id / "calendar.yaml"
    if cal_path.is_file():
        cal = load_yaml(cal_path)
        for day in cal.get("days") or []:
            expected = day.get("expected") or []
            for role in expected:
                r = str(role).lower()
                if r in {"lesson_plan", "lesson_content", "direct_instruction"}:
                    reasons.append(f"calendar:{day.get('id')}:{role}")
    # Pacing length alone is a weak signal — only if calendar missing
    if not reasons:
        pacing_path = root / "pacing-plan.yaml"
        if pacing_path.is_file():
            pacing = load_yaml(pacing_path)
            for u in pacing.get("units") or []:
                if u.get("unit_id") == unit_id and int(u.get("unit_length_days") or 0) >= 1:
                    reasons.append("pacing:unit_length_days>=1")
                    break
    return (bool(reasons), reasons)
