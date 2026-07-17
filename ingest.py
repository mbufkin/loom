#!/usr/bin/env python3
"""
ingest.py — Documents only in. Models organize units + infer calendars → YAML.

You provide: raw curriculum files in sources/
Models produce: manifest.yaml, units/*/calendar.yaml

Then run_project.py audits and renders PDFs. No manual YAML editing required.

school-calendar.yaml is provided by the human (or shared template), not inferred
by this stage — rollup.py reads it to produce dated pacing plans.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from audit_lib import (
    BASE_DIR,
    atomic_write,
    iter_source_files,
    load_config,
    log,
    model_chat,
    parse_model_json,
    project_dir,
    scrub_document,
    validate_slug_id,
)
from schema_validate import raise_on_errors, validate_ingest_plan

ORGANIZER_RULES = """
You are a curriculum document organizer and auditor. READ-ONLY.

Tasks:
1. Group every source file into exactly one curriculum unit (no file left unassigned).
2. Infer the instructional calendar for each unit from document text (days, weeks, phases).
3. Define expected artifact types per day (lesson_content, exit_ticket, etc.).

RULES:
- Use ONLY evidence from the catalog below. Cite source_file when inferring calendar length.
- NEVER invent lesson content or write curriculum materials.
- unit_id: lowercase slug (e.g. engineering, health-science).
- Calendar days: id d1, d2, ...; label from document headings when available.
- If documents mention "Estimated Day(s): N", use N for unit_length_days.
- If documents mention Day 1, Day 2, Day 3, create that many days.
- unit_supporting: artifact types that span the unit (lesson_plan, quiz, answer_key, rubric, worksheet).
- school_calendar_hint: optional top-level year/semester notes found in documents (or null).
"""

ORGANIZE_SCHEMA = """
Respond with ONLY valid JSON (no markdown fences):
{
  "school_calendar_hint": {
    "school_year": "string or null",
    "notes": "string or null",
    "grading_periods": []
  },
  "units": [
    {
      "unit_id": "slug",
      "title": "Human Title",
      "source_files": ["relative/path/from/sources/filename.ext"],
      "calendar": {
        "unit_length_days": 3,
        "days": [
          {"id": "d1", "label": "Day 1 — topic", "expected": ["lesson_content", "exit_ticket"]}
        ],
        "unit_supporting": ["lesson_plan", "quiz"]
      }
    }
  ]
}
Every catalog file must appear in exactly one unit's source_files.
"""


def model_call(
    cfg: dict, role: str, messages: list, step: str, temperature: float = 0.1
) -> dict:
    return model_chat(cfg, role, messages, step, temperature=temperature)


def parse_json(text: str, *, step: str = "ingest") -> dict:
    return parse_model_json(text, context=step)


def extract_content(response: dict) -> str:
    return response["choices"][0]["message"]["content"]


def build_catalog(sources: Path) -> tuple[list[dict], list[Path]]:
    paths = iter_source_files(sources)
    if not paths:
        raise FileNotFoundError(
            f"No curriculum files in {sources}. "
            f"Supported: pdf, docx, pptx, xlsx, odt, txt, md, html, rtf, doc (with antiword)"
        )
    records = []
    failed = []
    for p in paths:
        rel = p.relative_to(sources).as_posix()
        ev = scrub_document(p)
        ev["source_file"] = rel  # preserve subfolder path for manifest
        if ev.get("extraction_error"):
            failed.append(f"{p.name}: {ev['extraction_error']}")
        records.append(ev)
    if failed:
        log(f"WARN: {len(failed)} file(s) could not be extracted:")
        for f in failed[:10]:
            log(f"  - {f}")
    usable = [r for r in records if r.get("char_count_clean", 0) > 0]
    if not usable:
        raise FileNotFoundError("No documents produced extractable text")
    return usable, paths


def catalog_block(records: list[dict]) -> str:
    lines = []
    for r in records:
        lines.append(
            f"- {r['source_file']} | fmt={r.get('source_format','?')} | type={r['doc_type']} | "
            f"days={r['day_hints']} | len_hint={r.get('unit_length_days_hint')} | "
            f"title={r['title'][:80]!r}\n"
            f"  excerpt: {r['excerpt_head'][:200]!r}"
        )
    return "\n".join(lines)


def analyst_organize(cfg: dict, records: list[dict]) -> dict:
    prompt = f"""{ORGANIZER_RULES}

DOCUMENT CATALOG ({len(records)} files):
{catalog_block(records)}

{ORGANIZE_SCHEMA}
"""
    resp = model_call(
        cfg, "analyst", [{"role": "user", "content": prompt}], "ingest-analyst"
    )
    return parse_json(extract_content(resp), step="ingest-analyst")


def verifier_organize(cfg: dict, records: list[dict], draft: dict) -> dict:
    prompt = f"""{ORGANIZER_RULES}

Verify and correct the Analyst's organization. Every catalog file must be assigned once.
Remove calendar days not supported by document excerpts. Fix unit groupings if wrong.

CATALOG:
{catalog_block(records)}

ANALYST OUTPUT:
{json.dumps(draft, indent=2)}

{ORGANIZE_SCHEMA}
"""
    resp = model_call(
        cfg,
        "verifier",
        [{"role": "user", "content": prompt}],
        "ingest-verifier",
        temperature=0.0,
    )
    return parse_json(extract_content(resp), step="ingest-verifier")


def validate_coverage(records: list[dict], plan: dict) -> list[str]:
    """Deterministic check: all files assigned exactly once."""
    errors = []
    catalog = {r["source_file"] for r in records}
    assigned = []
    for u in plan.get("units", []):
        assigned.extend(u.get("source_files", []))
    assigned_set = set(assigned)
    missing = catalog - assigned_set
    extra = assigned_set - catalog
    dupes = [f for f in assigned if assigned.count(f) > 1]
    if missing:
        errors.append(
            f"unassigned files: {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )
    if extra:
        errors.append(f"unknown files in plan: {sorted(extra)[:5]}")
    if dupes:
        errors.append(f"duplicate assignments: {sorted(set(dupes))[:5]}")
    if not plan.get("units"):
        errors.append("no units in plan")
    return errors


def write_yaml_files(project_id: str, sources: Path, plan: dict) -> None:
    root = project_dir(project_id)
    units_dir = root / "units"
    units_dir.mkdir(parents=True, exist_ok=True)

    manifest_units = {}
    for u in plan["units"]:
        uid = u["unit_id"]
        cal = u["calendar"]
        cal_doc = {
            "unit_id": uid,
            "title": u.get("title", uid),
            "unit_length_days": cal.get("unit_length_days", len(cal.get("days", []))),
            "days": cal.get("days", []),
            "unit_supporting": cal.get("unit_supporting", []),
        }
        cal_path = units_dir / uid / "calendar.yaml"
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cal_path, "w") as f:
            yaml.dump(cal_doc, f, default_flow_style=False, sort_keys=False)
        manifest_units[uid] = {
            "title": u.get("title", uid),
            "calendar": f"units/{uid}/calendar.yaml",
            "documents": sorted(u.get("source_files", [])),
        }

    manifest = {
        "project": {"id": project_id, "name": plan.get("project_name", project_id)},
        "sources_dir": str(sources.resolve()),
        "units": manifest_units,
        "generated_by": "ingest.py",
    }
    with open(root / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    hint = plan.get("school_calendar_hint") or {}
    school_cal = {
        "school_year": hint.get("school_year"),
        "notes": hint.get("notes"),
        "grading_periods": hint.get("grading_periods", []),
        "units": [
            {"unit_id": u["unit_id"], "title": u.get("title")} for u in plan["units"]
        ],
    }
    with open(root / "school-calendar.yaml", "w") as f:
        yaml.dump(school_cal, f, default_flow_style=False, sort_keys=False)


def ingest(project_id: str, sources: Path, skip_models: bool = False) -> Path:
    root = project_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    ingest_dir = root / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = ingest_dir / ".raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    records, _paths = build_catalog(sources)
    atomic_write(ingest_dir / "catalog.json", json.dumps(records, indent=2))
    log(f"catalog: {len(records)} documents from {sources}")

    if skip_models:
        # Deterministic fallback: one unit per unique top-level token in filename
        plan = _deterministic_plan(records)
    else:
        cfg = load_config()
        log("Analyst organizing documents + inferring calendars...")
        draft = analyst_organize(cfg, records)
        atomic_write(raw_dir / "organize-analyst.json", json.dumps(draft, indent=2))
        log("Verifier validating organization...")
        final = verifier_organize(cfg, records, draft)
        atomic_write(raw_dir / "organize-verifier.json", json.dumps(final, indent=2))
        plan = final

    errors = validate_coverage(records, plan)
    errors.extend(validate_ingest_plan(plan))
    raise_on_errors(errors, "Ingest validation")

    write_yaml_files(project_id, sources, plan)
    log(f"wrote manifest.yaml + {len(plan['units'])} unit calendars → {root}")
    return root


def _deterministic_plan(records: list[dict]) -> dict:
    """Offline fallback: one unit 'curriculum' with all docs, calendar from day hints."""
    max_day = 1
    for r in records:
        if r.get("day_hints"):
            max_day = max(max_day, max(r["day_hints"]))
        if r.get("unit_length_days_hint"):
            max_day = max(max_day, r["unit_length_days_hint"])
    days = [
        {
            "id": f"d{d}",
            "label": f"Day {d}",
            "expected": ["lesson_content", "exit_ticket"],
        }
        for d in range(1, max_day + 1)
    ]
    return {
        "school_calendar_hint": None,
        "units": [
            {
                "unit_id": "curriculum",
                "title": "Curriculum",
                "source_files": [r["source_file"] for r in records],
                "calendar": {
                    "unit_length_days": max_day,
                    "days": days,
                    "unit_supporting": [
                        "lesson_plan",
                        "quiz",
                        "answer_key",
                        "rubric",
                        "worksheet",
                    ],
                },
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Organize docs + infer calendars → YAML"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--sources", type=Path, help="Folder of curriculum files (any supported type)"
    )
    parser.add_argument("--skip-models", action="store_true")
    args = parser.parse_args()

    sources = args.sources or (project_dir(args.project) / "sources")
    if not sources.is_dir():
        log(f"ERROR: sources not found: {sources}")
        log("Create projects/<id>/sources/ and drop curriculum documents there.")
        return 2

    try:
        validate_slug_id(args.project, "project id")
        ingest(args.project, sources, skip_models=args.skip_models)
    except ValueError as e:
        log(f"ERROR: {e}")
        return 2
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
