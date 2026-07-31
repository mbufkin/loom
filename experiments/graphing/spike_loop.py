#!/usr/bin/env python3
"""ledger-mini spike: provisional HAS-PART → review → batch rebuild.

Implements experiments/graphing/SPIKE.md (Gate A, soft-queue, belonging,
batch rebuild, per-source flat graph/.raw/ decision JSON).

No production wiring. No LLM required — decisions are code-first heuristics
that still write the flat per-doc choice log (model=code-first-spike-v0).

Usage:
  python3 experiments/graphing/spike_loop.py
  python3 experiments/graphing/spike_loop.py --project-root projects/_fixtures/ledger-mini
"""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = ROOT / "projects" / "_fixtures" / "ledger-mini"
MODEL_ID = "code-first-spike-v0"


# ---------------------------------------------------------------------------
# Roles / ids — educational: filename heuristics stand in for model choice so
# the flat JSON still shows a clear provisional → rebuild before/after.
# ---------------------------------------------------------------------------


def _stem(source_file: str) -> str:
    return Path(source_file).stem


def _doc_id(source_file: str) -> str:
    m = re.match(r"doc_([a-f0-9]+)_", source_file, re.I)
    return m.group(1) if m else _stem(source_file)


def invent_role(source_file: str) -> str:
    name = source_file.lower()
    if "exit_ticket" in name or "exit-ticket" in name:
        return "exit_ticket"
    if "slide" in name:
        return "slides"
    if "lesson_plan" in name or "lesson-plan" in name or "plan" in name:
        return "lesson_plan"
    return "other"


def material_id(source_file: str) -> str:
    return f"material:{_doc_id(source_file)}"


# ---------------------------------------------------------------------------
# Gate A — inventory completeness
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    ok: bool
    missing_materials: list[str] = field(default_factory=list)
    orphan_sources: list[str] = field(default_factory=list)
    message: str = ""


def list_sources(sources_dir: Path) -> list[str]:
    return sorted(
        p.name
        for p in sources_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )


def gate_a(graph: dict, sources: list[str]) -> GateResult:
    """Hard pass: every source is a Material; no orphan source files."""
    mats = {
        n.get("source_file")
        for n in graph.get("nodes") or []
        if n.get("type") == "Material" and n.get("source_file")
    }
    missing = [s for s in sources if s not in mats]
    # Orphans = Material source_files not on disk (shouldn't invent extras).
    orphans = sorted(m for m in mats if m not in sources)
    ok = not missing and not orphans
    msg = "Gate A pass" if ok else f"Gate A fail missing={missing} orphans={orphans}"
    return GateResult(ok=ok, missing_materials=missing, orphan_sources=orphans, message=msg)


# ---------------------------------------------------------------------------
# Provisional graph (organization v0) — Materials only under unit; no Lessons
# ---------------------------------------------------------------------------


def build_provisional(project_id: str, unit_id: str, sources: list[str]) -> dict:
    course_id = f"course:{project_id}"
    unit_node = f"unit:{unit_id}"
    nodes: list[dict[str, Any]] = [
        {"id": course_id, "type": "Course", "name": project_id},
        {
            "id": unit_node,
            "type": "LessonGrouping",
            "name": unit_id,
            "groupName": "unit",
        },
    ]
    edges: list[dict[str, str]] = [
        {"rel": "hasPart", "from": course_id, "to": unit_node},
    ]
    for src in sources:
        mid = material_id(src)
        nodes.append(
            {
                "id": mid,
                "type": "Material",
                "role": invent_role(src),  # hint only; rebuild may refine
                "name": src,
                "source_file": src,
            }
        )
        # Inventory hang under unit — not a Lesson home (Lessons come later).
        edges.append({"rel": "hasPart", "from": unit_node, "to": mid})

    return {
        "project_id": project_id,
        "unit_id": unit_id,
        "stage": "provisional",
        "model": MODEL_ID,
        "method": "spike-loop-v0",
        "nodes": nodes,
        "edges": edges,
        "coverage": {"source_files": list(sources)},
    }


def lesson_ids_in(graph: dict) -> list[str]:
    return sorted(n["id"] for n in graph.get("nodes") or [] if n.get("type") == "Lesson")


def materials_needing_queue(graph: dict) -> list[str]:
    """Soft-queue: Materials with no Lesson yet wait at the back of the line."""
    if lesson_ids_in(graph):
        return []
    return sorted(
        n["source_file"]
        for n in graph.get("nodes") or []
        if n.get("type") == "Material" and n.get("source_file")
    )


# ---------------------------------------------------------------------------
# Review findings (minimal spike input) — what Path review would record
# ---------------------------------------------------------------------------


def default_review_findings(project_id: str, unit_id: str, sources: list[str]) -> dict:
    """Deterministic findings for ledger-mini: one Lesson; exit ticket → Assessment."""
    lesson_id = f"lesson:{unit_id}:d1"
    findings = []
    for src in sources:
        role = invent_role(src)
        if role == "exit_ticket":
            findings.append(
                {
                    "source_file": src,
                    "action": "attach_assessment",
                    "lesson_id": lesson_id,
                    "role": role,
                    "node_type": "Assessment",
                }
            )
        else:
            findings.append(
                {
                    "source_file": src,
                    "action": "attach_material",
                    "lesson_id": lesson_id,
                    "role": role,
                    "node_type": "Material",
                    "edge": "describes" if role == "lesson_plan" else "spanIn",
                }
            )
    return {
        "project_id": project_id,
        "unit_id": unit_id,
        "lesson_id": lesson_id,
        "create_lesson": {
            "id": lesson_id,
            "type": "Lesson",
            "name": "Day 1",
        },
        "findings": findings,
        "note": "Spike findings: simulated unit review close (all Materials reviewed).",
    }


# ---------------------------------------------------------------------------
# Batch rebuild — Materials inventory stable; org/edges/roles may change
# ---------------------------------------------------------------------------


def rebuild(provisional: dict, findings: dict) -> dict:
    """Apply review findings onto provisional graph. Stable: Material per source_file."""
    graph = deepcopy(provisional)
    graph["stage"] = "rebuilt"
    unit_id = findings["unit_id"]
    unit_node = f"unit:{unit_id}"
    lesson = findings["create_lesson"]
    lesson_id = lesson["id"]

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    if lesson_id not in nodes_by_id:
        graph["nodes"].append(dict(lesson))
        graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": lesson_id})

    # Drop unit→Material inventory edges; rebuild hangs materials via lesson edges.
    graph["edges"] = [
        e
        for e in graph["edges"]
        if not (
            e.get("rel") == "hasPart"
            and e.get("from") == unit_node
            and str(e.get("to", "")).startswith("material:")
        )
    ]

    for f in findings.get("findings") or []:
        src = f["source_file"]
        mid = material_id(src)
        mat = nodes_by_id.get(mid)
        if not mat:
            raise ValueError(f"rebuild refuses to invent Material for {src}")
        mat["role"] = f.get("role") or mat.get("role")

        if f.get("action") == "attach_assessment":
            aid = f"assessment:{_doc_id(src)}:exit-ticket"
            if aid not in nodes_by_id:
                anode = {
                    "id": aid,
                    "type": "Assessment",
                    "name": "Exit ticket",
                    "source_file": src,
                    "material_id": mid,
                }
                graph["nodes"].append(anode)
                nodes_by_id[aid] = anode
            # Non-negotiable belonging: Lesson hasPart → Assessment
            graph["edges"].append({"rel": "hasPart", "from": lesson_id, "to": aid})
            # Material remains inventory; Assessment references its file via material_id
            graph["edges"].append({"rel": "uses", "from": aid, "to": mid})
        else:
            edge_rel = f.get("edge") or "hasPart"
            if edge_rel == "hasPart":
                graph["edges"].append({"rel": "hasPart", "from": lesson_id, "to": mid})
            elif edge_rel == "spanIn":
                # spanIn: Lesson → Material (matches code_first / P1×D polarity)
                graph["edges"].append({"rel": "spanIn", "from": lesson_id, "to": mid})
                # Keep Material under unit for inventory discoverability
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
            else:
                # describes: Material → Lesson (plan describes the Lesson)
                graph["edges"].append({"rel": edge_rel, "from": mid, "to": lesson_id})
                # Keep Material under unit for inventory discoverability
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})

    # Deduplicate edges
    seen = set()
    uniq = []
    for e in graph["edges"]:
        key = (e.get("rel"), e.get("from"), e.get("to"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    graph["edges"] = uniq
    return graph


# ---------------------------------------------------------------------------
# Soft-queue review order
# ---------------------------------------------------------------------------


def review_order(provisional: dict, findings: dict) -> list[str]:
    """Materials without a Lesson are at the back until a Lesson will exist.

    For the spike, findings create the Lesson at rebuild — so during review we
    still *record* findings for all sources, but the order lists queued items last.
    """
    queued = set(materials_needing_queue(provisional))
    sources = list((provisional.get("coverage") or {}).get("source_files") or [])
    ready = [s for s in sources if s not in queued]
    back = [s for s in sources if s in queued]
    # When no Lessons yet, everything is queued — process in filename order as
    # the "back of the line" batch once findings introduce a Lesson at rebuild.
    return ready + back if ready else back


# ---------------------------------------------------------------------------
# Per-source flat decision JSON (core + before/after)
# ---------------------------------------------------------------------------


def _choice_for(source_file: str, graph: dict, *, queued: bool) -> dict[str, Any]:
    mid = material_id(source_file)
    mat = next((n for n in graph.get("nodes") or [] if n.get("id") == mid), None)
    role = (mat or {}).get("role") or invent_role(source_file)
    lessons = lesson_ids_in(graph)
    lesson_id = None if queued or not lessons else lessons[0]

    # Assessment belonging?
    assessment = next(
        (
            n
            for n in graph.get("nodes") or []
            if n.get("type") == "Assessment" and n.get("source_file") == source_file
        ),
        None,
    )
    node_type = "Assessment" if assessment else "Material"
    edges_proposed = [
        e
        for e in graph.get("edges") or []
        if e.get("from") in {mid, (assessment or {}).get("id")}
        or e.get("to") in {mid, (assessment or {}).get("id")}
    ]
    if assessment and lesson_id:
        # Prefer the Lesson hasPart Assessment edge in the flat summary
        belong = [
            e
            for e in graph.get("edges") or []
            if e.get("rel") == "hasPart"
            and e.get("from") == lesson_id
            and e.get("to") == assessment["id"]
        ]
        if belong:
            edges_proposed = belong + [e for e in edges_proposed if e not in belong]

    return {
        "role": role,
        "node_type": node_type,
        "lesson_id": lesson_id,
        "edges_proposed": edges_proposed,
        "queued": queued and lesson_id is None,
    }


def write_raw_decisions(
    raw_dir: Path,
    sources: list[str],
    provisional: dict,
    rebuilt: dict | None,
    *,
    review_queue: list[str],
) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    queued_set = set(review_queue)
    ts = datetime.now(timezone.utc).isoformat()
    paths = []
    for src in sources:
        # At provisional stage everyone without a Lesson is queued.
        prov_queued = src in queued_set or not lesson_ids_in(provisional)
        record = {
            "source_file": src,
            "stage": "rebuild" if rebuilt else "provisional",
            "provisional_choice": _choice_for(src, provisional, queued=prov_queued),
            "rebuild_choice": (
                _choice_for(src, rebuilt, queued=False) if rebuilt else None
            ),
            "model": MODEL_ID,
            "prompt_ref": "experiments/graphing/spike_loop.py",
            "ts": ts,
        }
        out = raw_dir / f"{_stem(src)}.json"
        out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        paths.append(out)
    return paths


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_spike(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    sources_dir = project_root / "sources"
    if not sources_dir.is_dir():
        raise FileNotFoundError(f"missing sources dir: {sources_dir}")

    manifest_path = project_root / "manifest.yaml"
    project_id = project_root.name
    unit_id = "plants"
    if manifest_path.exists():
        text = manifest_path.read_text(encoding="utf-8")
        m = re.search(r"^\s*id:\s*(\S+)", text, re.M)
        if m:
            project_id = m.group(1)
        um = re.search(r"^units:\n\s+(\S+):", text, re.M)
        if um:
            unit_id = um.group(1).rstrip(":")

    sources = list_sources(sources_dir)
    graph_dir = project_root / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)

    provisional = build_provisional(project_id, unit_id, sources)
    gate = gate_a(provisional, sources)
    if not gate.ok:
        raise SystemExit(f"provisional blocked: {gate.message}")

    queue = materials_needing_queue(provisional)
    order = review_order(provisional, {})
    findings = default_review_findings(project_id, unit_id, sources)

    # Batch rebuild only after all Materials "reviewed" (spike: findings cover all).
    reviewed = {f["source_file"] for f in findings["findings"]}
    if reviewed != set(sources):
        raise SystemExit("unit review incomplete — not all Materials have findings")

    rebuilt = rebuild(provisional, findings)

    (graph_dir / "HAS-PART.provisional.json").write_text(
        json.dumps(provisional, indent=2) + "\n", encoding="utf-8"
    )
    (graph_dir / "HAS-PART.json").write_text(
        json.dumps(rebuilt, indent=2) + "\n", encoding="utf-8"
    )
    (graph_dir / "review-findings.json").write_text(
        json.dumps(findings, indent=2) + "\n", encoding="utf-8"
    )

    raw_paths = write_raw_decisions(
        graph_dir / ".raw",
        sources,
        provisional,
        rebuilt,
        review_queue=queue,
    )

    summary = {
        "project_id": project_id,
        "unit_id": unit_id,
        "gate_a": gate.message,
        "soft_queue": queue,
        "review_order": order,
        "n_sources": len(sources),
        "provisional_lessons": lesson_ids_in(provisional),
        "rebuilt_lessons": lesson_ids_in(rebuilt),
        "raw_files": [str(p.relative_to(project_root)) for p in raw_paths],
        "out": {
            "provisional": str(
                (graph_dir / "HAS-PART.provisional.json").relative_to(project_root)
            ),
            "rebuilt": str((graph_dir / "HAS-PART.json").relative_to(project_root)),
            "findings": str(
                (graph_dir / "review-findings.json").relative_to(project_root)
            ),
        },
    }
    (graph_dir / "SPIKE-SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Path to ledger-mini (or copy) with sources/",
    )
    args = ap.parse_args()
    summary = run_spike(args.project_root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
