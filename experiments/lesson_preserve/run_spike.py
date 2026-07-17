#!/usr/bin/env python3
"""
run_spike.py — Lesson preserve spike CLI (side only; not in run_project).

  python3 experiments/lesson_preserve/run_spike.py --project dallas-career-2026
  python3 experiments/lesson_preserve/run_spike.py --project dallas-career-2026 \
      --units financial-literacy,engineering,professional-preparedness
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Repo root on path when run as script
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audit_lib import (  # noqa: E402
    atomic_write,
    doc_id_from_filename,
    load_manifest,
    log,
    project_dir,
    validate_slug_id,
)
from experiments.lesson_preserve.emit import (  # noqa: E402
    spike_out_root,
    write_unit_outputs,
)
from experiments.lesson_preserve.meeting import (  # noqa: E402
    derive_meeting_span,
    signal_expects_lesson_plan,
)
from experiments.lesson_preserve.organize import organize_unit  # noqa: E402
from experiments.lesson_preserve.path_a_modes import (  # noqa: E402
    resolve_mode_with_signal,
)


def _title_map(manifest: dict) -> dict[str, str]:
    try:
        from synthesize import readable_title_from_filename
    except Exception:

        def readable_title_from_filename(name: str) -> str:  # type: ignore
            return Path(name).name

    out: dict[str, str] = {}
    for u in (manifest.get("units") or {}).values():
        for rel in u.get("documents") or []:
            did = doc_id_from_filename(rel)
            out[did] = readable_title_from_filename(rel)
    return out


def run_spike(project_id: str, unit_ids: list[str] | None = None) -> Path:
    validate_slug_id(project_id, "project_id")
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    title_map = _title_map(manifest)
    units = manifest.get("units") or {}
    if unit_ids:
        unknown = [u for u in unit_ids if u not in units]
        if unknown:
            raise KeyError(f"Unknown unit(s): {unknown}")
        selected = unit_ids
    else:
        selected = sorted(units.keys())

    out_root = spike_out_root(project_id)
    out_root.mkdir(parents=True, exist_ok=True)

    organization: dict[str, Any] = {"project_id": project_id, "units": {}}
    index: dict[str, Any] = {"project_id": project_id, "units": {}}

    for uid in selected:
        u = units[uid]
        title = u.get("title") or uid
        docs = list(u.get("documents") or [])
        org = organize_unit(
            project_id,
            uid,
            title=title,
            documents=docs,
            title_map=title_map,
        )
        doc_ids = {doc_id_from_filename(r) for r in docs}
        meeting = derive_meeting_span(project_id, uid, doc_ids)
        expects, reasons = signal_expects_lesson_plan(project_id, uid)
        org = resolve_mode_with_signal(org, expects_lp=expects, expect_reasons=reasons)

        summary = write_unit_outputs(
            project_id,
            org,
            meeting,
            title_map=title_map,
            manifest=manifest,
        )
        organization["units"][uid] = {
            "title": title,
            "doc_count": org["doc_count"],
            "lesson_plan_count": org["lesson_plan_count"],
            "path_a_mode": org["path_a_mode"],
            "path_order": org["path_order"],
            "inventory": org["inventory"],
            "expects_lesson_plan": org.get("expects_lesson_plan"),
            "expect_reasons": org.get("expect_reasons"),
        }
        index["units"][uid] = {
            "title": title,
            "lesson_plan_count": summary["lesson_plan_count"],
            "path_a_mode": summary["path_a_mode"],
            "lesson_plans": [
                {
                    "doc_id": p.get("doc_id"),
                    "title": p.get("title"),
                    "source_file": p.get("source_file"),
                    "preserved_path": p.get("preserved_path"),
                    "detect_reasons": p.get("detect_reasons"),
                }
                for p in summary["lesson_plans"]
            ],
            "meeting_count": summary["meeting_count"],
            "meeting_source": summary["meeting_source"],
            "gap_plate": summary["gap_plate"],
            "path_a_depth": summary.get("path_a_depth"),
        }
        log(
            f"spike {uid}: mode={summary['path_a_mode']} "
            f"lp={summary['lesson_plan_count']} meeting={summary['meeting_count']}"
        )

    atomic_write(
        out_root / "organization.json",
        json.dumps(organization, indent=2, ensure_ascii=False),
    )
    atomic_write(
        out_root / "lesson_plans_index.json",
        json.dumps(index, indent=2, ensure_ascii=False),
    )
    log(f"spike done → {out_root}")
    return out_root


def main() -> None:
    p = argparse.ArgumentParser(description="Lesson preserve spike (side only)")
    p.add_argument("--project", required=True)
    p.add_argument(
        "--units",
        default="",
        help="Comma-separated unit ids (default: all)",
    )
    args = p.parse_args()
    units = [u.strip() for u in args.units.split(",") if u.strip()] or None
    run_spike(args.project, units)


if __name__ == "__main__":
    main()
