#!/usr/bin/env python3
"""HAS-PART inventory primitives for the Loom graph phase.

Educational note: Gate A + provisional Materials inventory + soft-queue +
per-doc raw decision logs are production-shaped. Filename role heuristics
(ledger-mini) lived in archived experiments/graphing/spike_loop.py — provisional
defaults role to ``other`` until narrow-steps review fills it in.

See docs/GRAPH-PHASE.md.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MODEL_ID = "graph-inventory-v0"


def _stem(source_file: str) -> str:
    return Path(source_file).stem


def _doc_id(source_file: str) -> str:
    m = re.match(r"doc_([a-f0-9]+)_", source_file, re.I)
    return m.group(1) if m else _stem(source_file)


def material_id(source_file: str) -> str:
    return f"material:{_doc_id(source_file)}"


@dataclass
class GateResult:
    ok: bool
    missing_materials: list[str] = field(default_factory=list)
    orphan_sources: list[str] = field(default_factory=list)
    message: str = ""


def list_sources(sources_dir: Path) -> list[str]:
    """Basenames of files directly under sources_dir (non-recursive)."""
    return sorted(
        p.name
        for p in sources_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )


def gate_a(graph: dict, sources: list[str]) -> GateResult:
    """Hard pass: every source is a Material; no orphan Material source_files."""
    mats = {
        n.get("source_file")
        for n in graph.get("nodes") or []
        if n.get("type") == "Material" and n.get("source_file")
    }
    missing = [s for s in sources if s not in mats]
    orphans = sorted(m for m in mats if m not in sources)
    ok = not missing and not orphans
    msg = "Gate A pass" if ok else f"Gate A fail missing={missing} orphans={orphans}"
    return GateResult(ok=ok, missing_materials=missing, orphan_sources=orphans, message=msg)


def build_provisional(
    project_id: str,
    unit_id: str,
    sources: list[str],
    *,
    role_for: Callable[[str], str] | None = None,
    method: str = "graph-inventory-v0",
) -> dict:
    """Organization v0 — Materials under unit; no Lessons yet.

    Best practice: pass ``role_for`` only for fixture heuristics. Production
    leaves role as ``other`` until review findings refine it.
    """
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
        role = role_for(src) if role_for else "other"
        nodes.append(
            {
                "id": mid,
                "type": "Material",
                "role": role,
                "name": src,
                "source_file": src,
            }
        )
        edges.append({"rel": "hasPart", "from": unit_node, "to": mid})

    return {
        "project_id": project_id,
        "unit_id": unit_id,
        "stage": "provisional",
        "model": MODEL_ID,
        "method": method,
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


def rebuild(provisional: dict, findings: dict) -> dict:
    """Apply single-lesson review findings. Stable: Material per source_file."""
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
            graph["edges"].append({"rel": "hasPart", "from": lesson_id, "to": aid})
            graph["edges"].append({"rel": "uses", "from": aid, "to": mid})
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
        else:
            edge_rel = f.get("edge") or "hasPart"
            if edge_rel == "hasPart":
                graph["edges"].append({"rel": "hasPart", "from": lesson_id, "to": mid})
            elif edge_rel == "spanIn":
                graph["edges"].append({"rel": "spanIn", "from": lesson_id, "to": mid})
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
            else:
                graph["edges"].append({"rel": edge_rel, "from": mid, "to": lesson_id})
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})

    seen: set[tuple] = set()
    uniq = []
    for e in graph["edges"]:
        key = (e.get("rel"), e.get("from"), e.get("to"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    graph["edges"] = uniq
    return graph


def review_order(provisional: dict, findings: dict) -> list[str]:
    """Materials without a Lesson are at the back until a Lesson will exist."""
    del findings  # reserved for richer Path-driven ordering
    queued = set(materials_needing_queue(provisional))
    sources = list((provisional.get("coverage") or {}).get("source_files") or [])
    ready = [s for s in sources if s not in queued]
    back = [s for s in sources if s in queued]
    return ready + back if ready else back


def _choice_for(
    source_file: str,
    graph: dict,
    *,
    queued: bool,
    role_fallback: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    mid = material_id(source_file)
    mat = next((n for n in graph.get("nodes") or [] if n.get("id") == mid), None)
    role = (mat or {}).get("role") or (role_fallback(source_file) if role_fallback else "other")
    lessons = lesson_ids_in(graph)
    lesson_id = None if queued or not lessons else lessons[0]

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
    model: str = MODEL_ID,
    prompt_ref: str = "graph_inventory.py",
    role_fallback: Callable[[str], str] | None = None,
) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    queued_set = set(review_queue)
    ts = datetime.now(timezone.utc).isoformat()
    paths = []
    for src in sources:
        prov_queued = src in queued_set or not lesson_ids_in(provisional)
        record = {
            "source_file": src,
            "stage": "rebuild" if rebuilt else "provisional",
            "provisional_choice": _choice_for(
                src, provisional, queued=prov_queued, role_fallback=role_fallback
            ),
            "rebuild_choice": (
                _choice_for(src, rebuilt, queued=False, role_fallback=role_fallback)
                if rebuilt
                else None
            ),
            "model": model,
            "prompt_ref": prompt_ref,
            "ts": ts,
        }
        out = raw_dir / f"{_stem(src)}.json"
        out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        paths.append(out)
    return paths
