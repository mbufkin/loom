#!/usr/bin/env python3
"""Pack P1×D graphing results into a single JSON for the local viz site.

Best practice: keep the browser dumb — normalize scores, lesson spans, and
HAS-PART graphs here so index.html only renders. Re-run this after new runs.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "experiments" / "graphing" / "results"
OUT = Path(__file__).resolve().parent / "data.json"

# Gold graphs are the ground-truth HAS-PART trees each run is scored against.
GOLD_BY_PROJECT = {
    "lab-dallas-ag": ROOT / "projects" / "lab-dallas-ag" / "graph" / "HAS-PART.json",
    "lab-arts-av": ROOT / "projects" / "lab-arts-av" / "graph" / "HAS-PART.json",
}


def _lessons(graph: dict) -> list[dict]:
    """Extract lesson nodes with the span fields that explain IoU collapse."""
    out = []
    for n in graph.get("nodes") or []:
        if n.get("type") != "Lesson":
            continue
        span = n.get("span") or {}
        out.append(
            {
                "id": n.get("id"),
                "name": n.get("name") or n.get("id"),
                "paragraphs": span.get("paragraphs") or [],
                "element_ids": span.get("element_ids") or [],
                "source_file": span.get("source_file") or n.get("source_file"),
            }
        )
    return sorted(out, key=lambda x: x["id"] or "")


def _slim_graph(graph: dict) -> dict:
    """Keep only what the SVG layout needs — ids, types, names, edges."""
    nodes = []
    for n in graph.get("nodes") or []:
        nodes.append(
            {
                "id": n.get("id"),
                "type": n.get("type"),
                "name": n.get("name") or n.get("id"),
                "role": n.get("role"),
                "element_ids": (n.get("span") or {}).get("element_ids")
                or n.get("element_ids")
                or [],
                "paragraphs": (n.get("span") or {}).get("paragraphs") or [],
            }
        )
    edges = [
        {"rel": e.get("rel"), "from": e.get("from"), "to": e.get("to")}
        for e in graph.get("edges") or []
    ]
    return {"nodes": nodes, "edges": edges}


def _score_blob(score: dict | None) -> dict:
    if not score:
        return {}
    return {
        "pass": score.get("pass_provisional"),
        "material_coverage": score.get("material_coverage"),
        "lesson_mean_iou": score.get("lesson_mean_iou"),
        "assessment_attach": score.get("assessment_attach"),
        "edge_f1": score.get("edge_f1"),
        "n_gold_lessons": score.get("n_gold_lessons"),
        "n_pred_lessons": score.get("n_pred_lessons"),
        "lesson_pairs": score.get("lesson_pairs") or [],
        "assessment_attach_counts": score.get("assessment_attach_counts") or {},
    }


def _break_story(project: str, stage: str, propose: dict, final: dict) -> str | None:
    """One-line diagnosis when final regresses vs propose (the repaired failure)."""
    ps, fs = propose.get("score") or {}, final.get("score") or {}
    if stage != "repaired":
        if ps.get("pass") is False:
            return "Propose failed provisional gates (IoU / assessment / coverage)."
        return None
    if ps.get("pass") and fs.get("pass") is False:
        # Surface the span collapse that caused the dallas-ag break.
        diffs = []
        p_lessons = {l["id"]: l for l in propose.get("lessons") or []}
        for fl in final.get("lessons") or []:
            pl = p_lessons.get(fl["id"])
            if not pl:
                continue
            pe, fe = len(pl["element_ids"]), len(fl["element_ids"])
            if fe < pe:
                diffs.append(f"{fl['id']}: {pe}→{fe} elements, paras {pl['paragraphs']}→{fl['paragraphs']}")
        detail = "; ".join(diffs) if diffs else "final metrics collapsed"
        return f"Model repair wrecked a good propose — {detail}."
    return None


def main() -> None:
    gold_cache = {
        pid: _slim_graph(json.loads(path.read_text(encoding="utf-8")))
        for pid, path in GOLD_BY_PROJECT.items()
        if path.exists()
    }
    gold_lessons = {
        pid: _lessons(json.loads(path.read_text(encoding="utf-8")))
        for pid, path in GOLD_BY_PROJECT.items()
        if path.exists()
    }

    runs = []
    for d in sorted(RESULTS.glob("P1xD_*"), key=lambda p: p.name):
        summary = json.loads((d / "SUMMARY.json").read_text(encoding="utf-8"))
        propose_g = json.loads((d / "propose.json").read_text(encoding="utf-8"))
        final_g = json.loads((d / "final.json").read_text(encoding="utf-8"))
        propose = {
            "graph": _slim_graph(propose_g),
            "lessons": _lessons(propose_g),
            "score": _score_blob(summary.get("propose")),
        }
        final = {
            "graph": _slim_graph(final_g),
            "lessons": _lessons(final_g),
            "score": _score_blob(summary.get("final")),
        }
        project = summary.get("project_id") or d.name
        stage = summary.get("stage") or "unknown"
        runs.append(
            {
                "id": d.name,
                "project": project,
                "stage": stage,
                "method": summary.get("method"),
                "model": summary.get("analyst_model"),
                "out_dir": summary.get("out_dir"),
                "propose": propose,
                "final": final,
                "gold_lessons": gold_lessons.get(project, []),
                "break_story": _break_story(project, stage, propose, final),
                "highlight": bool(
                    stage == "repaired"
                    and propose["score"].get("pass")
                    and final["score"].get("pass") is False
                ),
            }
        )

    payload = {
        "title": "P1×D HAS-PART graph lab",
        "generated_from": str(RESULTS),
        "gold": gold_cache,
        "runs": runs,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(runs)} runs)")


if __name__ == "__main__":
    main()
