#!/usr/bin/env python3
"""
calendars.py — After unit assemble, infer day grids + year notes from materials.

Early rollup.py remains a provisional spine. This step is the authoritative
inferred calendar tagged source: inferred_from_documents.
Auditor-only: does not invent instructional content — only structures days
from evidence already present (Layer 1 findings + Path A–H inventories).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from audit_lib import (
    atomic_write,
    load_config,
    load_manifest,
    load_yaml,
    log,
    model_chat,
    project_dir,
    validate_slug_id,
)


def _load_json(path: Path):
    if not path.is_file():
        return [] if path.name.endswith(".json") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_unit_calendar_from_evidence(project_id: str, unit_id: str, unit: dict) -> dict:
    """Code-first day grid from Layer 1 findings; optional model polish later."""
    root = project_dir(project_id)
    findings = _load_json(root / "layer1" / "findings.json")
    unit_findings = [f for f in findings if f.get("unit_id") == unit_id]
    days: dict[str, list[str]] = {}
    for f in unit_findings:
        day = f.get("day_id") or "unit-level"
        role = f.get("role") or "other"
        status = f.get("status") or ""
        if status in ("FULFILLED", "DUPLICATE", "MATCH"):
            days.setdefault(day, []).append(role)

    # Preserve existing calendar day ids when present
    cal_rel = unit.get("calendar")
    existing_days = []
    if cal_rel and (root / cal_rel).is_file():
        try:
            existing_days = load_yaml(root / cal_rel).get("days") or []
        except Exception:
            existing_days = []

    day_rows = []
    if existing_days:
        for d in existing_days:
            did = d.get("id") or d.get("day_id") or "d?"
            roles = sorted(set(days.get(did, [])))
            day_rows.append(
                {
                    "id": did,
                    "expected_roles_found": roles,
                    "status": "HAS_EVIDENCE" if roles else "EMPTY",
                }
            )
    else:
        for did, roles in sorted(days.items()):
            day_rows.append(
                {
                    "id": did,
                    "expected_roles_found": sorted(set(roles)),
                    "status": "HAS_EVIDENCE",
                }
            )

    return {
        "unit_id": unit_id,
        "title": unit.get("title") or unit_id,
        "source": "inferred_from_documents",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": day_rows,
        "note": (
            "Inferred after Loom path workflows + Layer 1. "
            "Blank/EMPTY days = no fulfilled materials found — not authored content."
        ),
    }


def run_calendars(project_id: str, *, use_model: bool = False) -> Path:
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    out_dir = root / "calendars_inferred"
    out_dir.mkdir(parents=True, exist_ok=True)
    units_out = {}
    for uid, unit in (manifest.get("units") or {}).items():
        units_out[uid] = build_unit_calendar_from_evidence(project_id, uid, unit)

    # Optional short model synthesis of year pacing note (no inventing lessons)
    year_note = ""
    if use_model:
        try:
            cfg = load_config()
            summary = {
                uid: {
                    "title": u["title"],
                    "days_with_evidence": sum(
                        1 for d in u["days"] if d.get("status") == "HAS_EVIDENCE"
                    ),
                    "empty_days": sum(1 for d in u["days"] if d.get("status") == "EMPTY"),
                }
                for uid, u in units_out.items()
            }
            resp = model_chat(
                cfg,
                "analyst",
                [
                    {
                        "role": "system",
                        "content": (
                            "You summarize inferred curriculum pacing. Do not invent "
                            "lessons or days. 3-5 sentences max on which units look "
                            "thin vs stocked based on the counts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(summary, indent=2),
                    },
                ],
                step="calendars-year-note",
                temperature=0.2,
                max_tokens=400,
            )
            year_note = (resp["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            log(f"WARN: calendar year note skipped: {e}")

    payload = {
        "project_id": project_id,
        "source": "inferred_from_documents",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provisional_rollup": "pacing-plan.yaml remains provisional early spine",
        "year_note": year_note,
        "units": units_out,
    }
    dest = out_dir / "INFERRED-CALENDARS.json"
    atomic_write(dest, json.dumps(payload, indent=2, ensure_ascii=False))
    md_lines = [
        f"# Inferred calendars — `{project_id}`",
        "",
        f"**source:** `inferred_from_documents`  ",
        f"**generated:** {payload['generated_at']}",
        "",
        "Early `rollup.py` / `pacing-plan.yaml` is provisional. This file is the "
        "post-assemble evidence calendar.",
        "",
    ]
    if year_note:
        md_lines += ["## Year note", "", year_note, ""]
    for uid, u in sorted(units_out.items()):
        md_lines.append(f"## {u['title']} (`{uid}`)")
        md_lines.append("")
        for d in u.get("days") or []:
            roles = ", ".join(d.get("expected_roles_found") or []) or "—"
            md_lines.append(f"- `{d['id']}`: **{d['status']}** — {roles}")
        md_lines.append("")
    atomic_write(out_dir / "INFERRED-CALENDARS.md", "\n".join(md_lines))
    log(f"calendars → {dest} ({len(units_out)} units)")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Infer unit calendars after Loom paths + Layer 1"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--model-note",
        action="store_true",
        help="Ask model for a short year pacing note (no content invent)",
    )
    args = parser.parse_args()
    validate_slug_id(args.project, "project id")
    run_calendars(args.project, use_model=args.model_note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
