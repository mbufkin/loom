#!/usr/bin/env python3
"""P1 × D graphing experiment: code-first propose → local model repair → score vs gold.

Usage:
  LOOM_CONFIG=config.yaml .venv/bin/python experiments/graphing/run_pd.py \
      --project lab-dallas-ag --gold projects/lab-dallas-ag/graph/HAS-PART.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_lib import extract_content, load_config, log, model_chat, parse_model_json  # noqa: E402
from code_first import propose_graph  # noqa: E402
from score_haspart import score  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"

REPAIR_SCHEMA = """
Respond with ONLY valid JSON (no markdown fences) shaped like:
{
  "project_id": "...",
  "nodes": [ {"id":"...", "type":"Course|LessonGrouping|Lesson|Activity|Assessment|Material", ...} ],
  "edges": [ {"rel":"hasPart|spanIn|describes|uses", "from":"...", "to":"..."} ],
  "coverage": {"source_files": ["..."] }
}

Rules for repair:
- Keep EVERY source file as a Material (no drops).
- Lesson nodes use span.paragraphs and/or span.element_ids into multi-day Materials.
- Exit-ticket FILES become Assessment nodes hasPart of the matching Day lesson (d1/d2/d3).
- lesson_plan Materials describe each Lesson.
- Do not invent filenames. unit_id / lesson ids: hyphen slugs (d1 not day1 only — prefer lesson:<unit>:dN).
- unit_length / lesson count should follow Day headers in content when calendar disagrees.
"""


def repair_with_model(cfg: dict, proposal: dict, project_id: str) -> dict:
    # compact proposal for prompt: drop huge fields
    compact = {
        "project_id": proposal.get("project_id"),
        "nodes": proposal.get("nodes"),
        "edges": proposal.get("edges"),
        "coverage": proposal.get("coverage"),
    }
    prompt = f"""You repair a code-proposed curriculum hasPart graph.

Project: {project_id}
The proposal below was built with Day-header heuristics. Fix mistakes:
- wrong lesson count vs Day 1/2/3 markers
- exit tickets not under the right lesson
- missing describes from lesson_plan
- missing Materials for any listed source file

PROPOSAL_JSON:
{json.dumps(compact, indent=2)[:120000]}

{REPAIR_SCHEMA}
"""
    resp = model_chat(
        cfg,
        "analyst",
        [{"role": "user", "content": prompt}],
        f"graph-pd-repair-{project_id}",
        temperature=0.1,
    )
    return parse_model_json(extract_content(resp), context=f"graph-pd-{project_id}")


def run_one(project_id: str, gold_path: Path, *, skip_model: bool = False) -> dict:
    cfg = load_config()
    models = cfg.get("models") or {}
    out_dir = OUT / f"P1xD_{project_id}_{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"P1×D propose {project_id} model={models.get('analyst_model')}")
    proposal = propose_graph(project_id)
    (out_dir / "propose.json").write_text(json.dumps(proposal, indent=2) + "\n")

    sources = ROOT / "projects" / project_id / "sources"
    propose_score = score(out_dir / "propose.json", gold_path, sources)
    (out_dir / "score_propose.json").write_text(json.dumps(propose_score, indent=2) + "\n")
    log(f"propose score: pass={propose_score['pass_provisional']} { {k: propose_score[k] for k in ['material_coverage','lesson_mean_iou','assessment_attach','edge_f1','n_pred_lessons','n_gold_lessons']} }")

    if skip_model:
        final = proposal
        stage = "propose_only"
    else:
        log("model repair…")
        try:
            final = repair_with_model(cfg, proposal, project_id)
            # ensure required keys
            if "nodes" not in final:
                raise ValueError("repair missing nodes")
            stage = "repaired"
        except Exception as e:
            log(f"repair FAILED ({e}); keeping propose")
            final = proposal
            stage = f"repair_failed:{e}"
            (out_dir / "repair_error.txt").write_text(str(e))

    (out_dir / "final.json").write_text(json.dumps(final, indent=2) + "\n")
    final_score = score(out_dir / "final.json", gold_path, sources)
    (out_dir / "score_final.json").write_text(json.dumps(final_score, indent=2) + "\n")

    row = {
        "project_id": project_id,
        "method": "P1xD",
        "placement": "P1",
        "analyst_model": models.get("analyst_model"),
        "analyst_url": models.get("analyst_url"),
        "stage": stage,
        "out_dir": str(out_dir),
        "propose": propose_score,
        "final": final_score,
    }
    (out_dir / "SUMMARY.json").write_text(json.dumps(row, indent=2) + "\n")

    results_md = OUT / "RESULTS.md"
    if not results_md.exists():
        results_md.write_text("# Graphing P1×D results\n\n", encoding="utf-8")
    with results_md.open("a", encoding="utf-8") as f:
        f.write(
            f"## {time.strftime('%Y-%m-%d %H:%M')} {project_id} ({stage})\n\n"
            f"- model: `{models.get('analyst_model')}`\n"
            f"- propose: cov={propose_score['material_coverage']} lesson_iou={propose_score['lesson_mean_iou']} "
            f"assess={propose_score['assessment_attach']} edge_f1={propose_score['edge_f1']} "
            f"lessons={propose_score['n_pred_lessons']}/{propose_score['n_gold_lessons']} "
            f"pass={propose_score['pass_provisional']}\n"
            f"- final:   cov={final_score['material_coverage']} lesson_iou={final_score['lesson_mean_iou']} "
            f"assess={final_score['assessment_attach']} edge_f1={final_score['edge_f1']} "
            f"lessons={final_score['n_pred_lessons']}/{final_score['n_gold_lessons']} "
            f"pass={final_score['pass_provisional']}\n"
            f"- dir: `{out_dir}`\n\n"
        )
    log(
        f"final score: pass={final_score['pass_provisional']} "
        f"{ {k: final_score[k] for k in ['material_coverage','lesson_mean_iou','assessment_attach','edge_f1','n_pred_lessons','n_gold_lessons']} }"
    )
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", action="append", required=True)
    ap.add_argument("--gold", action="append", required=True, type=Path)
    ap.add_argument("--skip-model", action="store_true")
    args = ap.parse_args()
    if len(args.project) != len(args.gold):
        ap.error("provide matching --project and --gold pairs")
    rows = []
    for pid, gold in zip(args.project, args.gold):
        rows.append(run_one(pid, gold, skip_model=args.skip_model))
    print(json.dumps(rows, indent=2))
    # exit 0 if all final pass_provisional
    return 0 if all(r["final"]["pass_provisional"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
