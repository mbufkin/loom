#!/usr/bin/env python3
"""Assemble HAS-PART from precomputed narrow-step JSON (no model calls).

Used when an external reviewer (e.g. Cursor Agent + Grok) writes per-doc
role / lessons / assessment JSON; this script owns merge + rebuild + optional
gold score — same code path as graph_phase.py.

Usage:
  python3 tools/graph_assemble_from_steps.py \\
    --project bluebonnet-g5-m1-graph-test \\
    --unit place-value-decimals \\
    --steps-dir /path/to/steps \\
    --gold projects/bluebonnet-g5-m1-graph-test/graph-gold/HAS-PART.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_lib import log, project_dir  # noqa: E402
from graph_assemble import (  # noqa: E402
    load_unit_slice,
    merge_narrow_step_findings,
    rebuild_multi,
)
from graph_inventory import build_provisional, gate_a, lesson_ids_in  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument(
        "--steps-dir",
        type=Path,
        required=True,
        help="Dir with 01-role-*.json, 02-lessons-*.json, 03-assess-*.json per source",
    )
    ap.add_argument("--gold", type=Path, help="Optional HAS-PART gold for score_haspart")
    ap.add_argument(
        "--out-dir",
        type=Path,
        help="Unit output dir (default: projects/<id>/graph/units/<unit>)",
    )
    ap.add_argument(
        "--model-label",
        default="cursor-grok-narrow-steps",
        help="Stored on findings/HAS-PART for A/B compare",
    )
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    root = project_dir(args.project)
    manifest = root / "manifest.yaml"
    slice_ = load_unit_slice(manifest, unit_id=args.unit)
    sources = list(slice_.documents)
    steps = Path(args.steps_dir)

    roles: dict[str, dict] = {}
    lessons: dict[str, dict] = {}
    assesses: dict[str, dict] = {}
    for sf in sources:
        stem = Path(sf).stem
        for kind, bucket in (
            ("01-role", roles),
            ("02-lessons", lessons),
            ("03-assess", assesses),
        ):
            # Allow exact stem or truncated stem filenames
            matches = sorted(steps.glob(f"{kind}-{stem}*.json"))
            if not matches:
                matches = sorted(steps.glob(f"{kind}-*.json"))
                matches = [p for p in matches if stem[:40] in p.stem]
            if not matches:
                # Soft-skip: allow assemble when a doc was stubbed/absent
                # (empty evidence). Keep Material inventoriable with no lessons.
                if kind == "01-role":
                    data = {
                        "source_file": sf,
                        "role": "other",
                        "notes": "soft-skip: missing step JSON",
                    }
                elif kind == "02-lessons":
                    data = {
                        "source_file": sf,
                        "covers_lesson_numbers": [],
                        "citations": [],
                        "notes": "soft-skip: missing step JSON",
                    }
                else:
                    data = {
                        "source_file": sf,
                        "is_assessment_bearing": False,
                        "assessment_lesson_numbers": [],
                        "assessment_name": None,
                        "citations": [],
                        "notes": "soft-skip: missing step JSON",
                    }
                bucket[sf] = data
                continue
            data = json.loads(matches[0].read_text(encoding="utf-8"))
            data["source_file"] = sf
            bucket[sf] = data

    out_dir = Path(args.out_dir) if args.out_dir else (root / "graph" / "units" / args.unit)
    if out_dir.exists() and not args.force and (out_dir / "HAS-PART.json").is_file():
        raise SystemExit(f"{out_dir} exists; pass --force")
    out_dir.mkdir(parents=True, exist_ok=True)

    provisional = build_provisional(slice_.project_id, args.unit, sources)
    gate = gate_a(provisional, sources)
    if not gate.ok:
        raise SystemExit(gate.message)

    findings = merge_narrow_step_findings(
        slice_.project_id,
        args.unit,
        sources,
        roles,
        lessons,
        assesses,
        spine_policy=slice_.spine_policy,
        model_label=args.model_label,
    )
    final = rebuild_multi(provisional, findings)
    final["method"] = f"graph-assemble-from-steps+{args.model_label}"
    final["model"] = args.model_label
    final["stage"] = "rebuilt"

    (out_dir / "HAS-PART.provisional.json").write_text(
        json.dumps(provisional, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "review-findings.json").write_text(
        json.dumps(findings, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "HAS-PART.json").write_text(
        json.dumps(final, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "project_id": slice_.project_id,
        "unit_id": args.unit,
        "n_lessons": len(lesson_ids_in(final)),
        "n_assessment_files": sum(
            1 for f in findings["findings"] if f["action"] == "attach_assessment"
        ),
        "out_dir": str(out_dir),
        "step_summary": {
            sf: {
                "role": roles[sf].get("role"),
                "lessons": lessons[sf].get("covers_lesson_numbers"),
                "assessment": assesses[sf].get("is_assessment_bearing"),
            }
            for sf in sources
        },
    }

    if args.gold and args.gold.is_file():
        sys.path.insert(0, str(ROOT / "experiments" / "graphing"))
        from score_haspart import score  # noqa: E402

        sc = score(out_dir / "HAS-PART.json", args.gold, root / "sources")
        summary["score_vs_gold"] = {
            "pass_provisional": sc.get("pass_provisional"),
            "n_pred_lessons": sc.get("n_pred_lessons"),
            "n_gold_lessons": sc.get("n_gold_lessons"),
            "lesson_mean_iou": sc.get("lesson_mean_iou"),
            "assessment_attach": sc.get("assessment_attach"),
            "edge_f1": sc.get("edge_f1"),
        }
        (out_dir / "score_final.json").write_text(
            json.dumps(sc, indent=2) + "\n", encoding="utf-8"
        )

    (out_dir / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if summary.get("score_vs_gold"):
        return 0 if summary["score_vs_gold"].get("pass_provisional") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
