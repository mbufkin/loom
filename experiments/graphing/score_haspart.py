#!/usr/bin/env python3
"""Score a predicted HAS-PART graph against hand-built gold."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _nodes_by_type(graph: dict, typ: str) -> list[dict]:
    return [n for n in graph.get("nodes") or [] if n.get("type") == typ]


def _material_files(graph: dict) -> set[str]:
    out = set()
    for n in graph.get("nodes") or []:
        if n.get("type") == "Material" and n.get("status") != "referenced_missing":
            sf = n.get("source_file")
            if sf:
                out.add(Path(sf).name)
    return out


def _lesson_file_membership(graph: dict) -> dict[str, set[str]]:
    """lesson_id -> set of source files linked via spanIn or assessment/activity source_file."""
    id_to_node = {n["id"]: n for n in graph.get("nodes") or [] if n.get("id")}
    lesson_files: dict[str, set[str]] = defaultdict(set)
    # span on lesson node
    for n in _nodes_by_type(graph, "Lesson"):
        span = n.get("span") or {}
        sf = span.get("source_file") or n.get("source_file")
        if sf:
            lesson_files[n["id"]].add(Path(sf).name)
        for eid in span.get("element_ids") or []:
            # element id prefix is doc_id — optional
            pass
    # edges: Assessment/Activity with source_file under lesson via hasPart
    children: dict[str, list[str]] = defaultdict(list)
    for e in graph.get("edges") or []:
        if e.get("rel") == "hasPart":
            children[e["from"]].append(e["to"])
    for lid in list(lesson_files.keys()) + [n["id"] for n in _nodes_by_type(graph, "Lesson")]:
        for cid in children.get(lid, []):
            node = id_to_node.get(cid) or {}
            sf = node.get("source_file")
            if sf:
                lesson_files[lid].add(Path(sf).name)
    return dict(lesson_files)


def _lesson_element_sets(graph: dict) -> dict[str, set[str]]:
    out = {}
    for n in _nodes_by_type(graph, "Lesson"):
        span = n.get("span") or {}
        out[n["id"]] = set(span.get("element_ids") or [])
    return out


def _iou(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _match_lessons(pred: dict, gold: dict) -> list[tuple[str, str, float]]:
    """Greedy match gold lessons to pred lessons by element IoU, else file membership IoU."""
    g_els = _lesson_element_sets(gold)
    p_els = _lesson_element_sets(pred)
    g_files = _lesson_file_membership(gold)
    p_files = _lesson_file_membership(pred)
    pairs: list[tuple[str, str, float]] = []
    used: set[str] = set()
    for gid, gels in g_els.items():
        best_pid, best_rank, best_iou = None, -1.0, 0.0
        for pid, pels in p_els.items():
            if pid in used:
                continue
            # Prefer element IoU. File membership is a weak tie-breaker only when
            # both sides lack element_ids (multi-day files share one Material).
            el_score = _iou(gels, pels)
            if gels or pels:
                score = el_score
            else:
                score = _iou(g_files.get(gid, set()), p_files.get(pid, set()))
            g_day = gid.rsplit(":", 1)[-1]
            p_day = pid.rsplit(":", 1)[-1]
            rank = score + (0.05 if g_day == p_day and g_day.startswith("d") else 0.0)
            if rank > best_rank:
                best_rank, best_pid, best_iou = rank, pid, score
        if best_pid is None:
            pairs.append((gid, "", 0.0))
        else:
            used.add(best_pid)
            pairs.append((gid, best_pid, best_iou))
    return pairs


def _edge_set(graph: dict, rels: set[str] | None = None) -> set[tuple[str, str, str]]:
    out = set()
    for e in graph.get("edges") or []:
        rel = e.get("rel")
        if rels and rel not in rels:
            continue
        a, b = e.get("from"), e.get("to")
        if a and b and rel:
            out.add((rel, a, b))
    return out


def _canonicalize_edges_for_f1(pred: dict, gold: dict, lesson_map: dict[str, str]) -> tuple[set, set]:
    """Map pred lesson ids → gold lesson ids for comparable edge F1 on structural rels.

    Materials/assessments compared by source_file when present; else by id suffix heuristics.
    """
    g_nodes = {n["id"]: n for n in gold.get("nodes") or []}
    p_nodes = {n["id"]: n for n in pred.get("nodes") or []}
    # reverse lesson map pred->gold
    p_to_g_lesson = {pid: gid for gid, pid in lesson_map.items() if pid}

    def canon_id(nid: str, nodes: dict) -> str:
        if nid in p_to_g_lesson:
            return p_to_g_lesson[nid]
        n = nodes.get(nid) or {}
        sf = n.get("source_file") or (n.get("span") or {}).get("source_file")
        if sf:
            role = n.get("role") or n.get("type") or "node"
            return f"{role}:{Path(sf).name}"
        # assessment/activity without file: keep type+name
        return f"{n.get('type','?')}:{(n.get('name') or nid)}"

    def edges_canon(graph: dict, nodes: dict, is_pred: bool) -> set[tuple[str, str, str]]:
        out = set()
        for rel, a, b in _edge_set(graph, {"hasPart", "spanIn", "describes", "uses"}):
            ca = canon_id(a, nodes) if is_pred else (
                a if a in g_nodes and g_nodes[a].get("type") == "Lesson"
                else canon_id(a, nodes)
            )
            cb = canon_id(b, nodes) if is_pred else (
                b if b in g_nodes and g_nodes[b].get("type") == "Lesson"
                else canon_id(b, nodes)
            )
            # For gold, also canonicalize non-lesson to file keys
            if not is_pred:
                if g_nodes.get(a, {}).get("type") != "Lesson":
                    ca = canon_id(a, nodes)
                if g_nodes.get(b, {}).get("type") != "Lesson":
                    cb = canon_id(b, nodes)
                else:
                    cb = b  # keep gold lesson id
                if g_nodes.get(a, {}).get("type") == "Lesson":
                    ca = a
            out.add((rel, ca, cb))
        return out

    # simpler approach: structural facts we care about for T0/T1
    return edges_canon(pred, p_nodes, True), edges_canon(gold, g_nodes, False)


def score(pred_path: Path, gold_path: Path, sources_dir: Path | None = None) -> dict[str, Any]:
    pred = _load(pred_path)
    gold = _load(gold_path)

    gold_files = set(gold.get("coverage", {}).get("source_files") or [])
    if not gold_files:
        gold_files = _material_files(gold)
    pred_files = _material_files(pred)
    if sources_dir and sources_dir.is_dir():
        disk = {p.name for p in sources_dir.glob("*") if p.is_file() and p.name != ".gitkeep"}
    else:
        disk = gold_files

    material_coverage = (len(pred_files & disk) / len(disk)) if disk else 0.0

    pairs = _match_lessons(pred, gold)
    lesson_map = {gid: pid for gid, pid, _ in pairs}
    lesson_ious = [s for _, _, s in pairs]
    lesson_mean_iou = sum(lesson_ious) / len(lesson_ious) if lesson_ious else 0.0
    lesson_recall = sum(1 for s in lesson_ious if s >= 0.5) / len(lesson_ious) if lesson_ious else 0.0

    # Assessment attach: gold assessments with source_file under correct lesson
    g_nodes = {n["id"]: n for n in gold.get("nodes") or []}
    p_nodes = {n["id"]: n for n in pred.get("nodes") or []}
    g_children: dict[str, list[str]] = defaultdict(list)
    p_children: dict[str, list[str]] = defaultdict(list)
    for e in gold.get("edges") or []:
        if e.get("rel") == "hasPart":
            g_children[e["from"]].append(e["to"])
    for e in pred.get("edges") or []:
        if e.get("rel") == "hasPart":
            p_children[e["from"]].append(e["to"])

    assess_ok = 0
    assess_total = 0
    for gid, pid, _ in pairs:
        for cid in g_children.get(gid, []):
            gn = g_nodes.get(cid) or {}
            if gn.get("type") != "Assessment":
                continue
            assess_total += 1
            if not pid:
                continue
            gsf = gn.get("source_file")
            gels = set(gn.get("element_ids") or (gn.get("span") or {}).get("element_ids") or [])
            for pcid in p_children.get(pid, []):
                pn = p_nodes.get(pcid) or {}
                if pn.get("type") != "Assessment":
                    continue
                if gsf and pn.get("source_file") == gsf:
                    assess_ok += 1
                    break
                pels = set(
                    pn.get("element_ids")
                    or (pn.get("span") or {}).get("element_ids")
                    or []
                )
                if gels and pels & gels:
                    assess_ok += 1
                    break
    assess_attach = (assess_ok / assess_total) if assess_total else 1.0

    # describes: plan material describes each lesson
    def describes_pairs(graph: dict) -> set[tuple[str, str]]:
        nodes = {n["id"]: n for n in graph.get("nodes") or []}
        out = set()
        for e in graph.get("edges") or []:
            if e.get("rel") != "describes":
                continue
            a, b = nodes.get(e["from"], {}), nodes.get(e["to"], {})
            asf = a.get("source_file")
            if asf and b.get("type") == "Lesson":
                day = b["id"].rsplit(":", 1)[-1]
                out.add((Path(asf).name, day))
        return out

    g_desc = describes_pairs(gold)
    p_desc = describes_pairs(pred)
    # map pred lesson days
    desc_ok = len(g_desc & p_desc)
    desc_recall = (desc_ok / len(g_desc)) if g_desc else 1.0

    pe, ge = _canonicalize_edges_for_f1(pred, gold, {g: p for g, p, _ in pairs})
    # softer edge F1 on (rel, file_or_lesson_day) — recompute simpler
    def soft_edges(graph: dict) -> set[tuple]:
        nodes = {n["id"]: n for n in graph.get("nodes") or []}
        out = set()
        for e in graph.get("edges") or []:
            rel = e.get("rel")
            if rel not in {"hasPart", "spanIn", "describes", "uses"}:
                continue
            a, b = nodes.get(e["from"], {}), nodes.get(e["to"], {})

            def key(n: dict, nid: str) -> str:
                if n.get("type") == "Lesson":
                    return "lesson:" + nid.rsplit(":", 1)[-1]
                sf = n.get("source_file") or (n.get("span") or {}).get("source_file")
                if sf:
                    return f"{n.get('type')}:{Path(sf).name}"
                if n.get("status") == "referenced_missing":
                    return f"missing:{(n.get('name') or nid)}"
                return f"{n.get('type')}:{nid}"

            out.add((rel, key(a, e["from"]), key(b, e["to"])))
        return out

    ps, gs = soft_edges(pred), soft_edges(gold)
    tp = len(ps & gs)
    prec = tp / len(ps) if ps else 0.0
    rec = tp / len(gs) if gs else 0.0
    edge_f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0

    n_pred_lessons = len(_nodes_by_type(pred, "Lesson"))
    n_gold_lessons = len(_nodes_by_type(gold, "Lesson"))

    report = {
        "material_coverage": round(material_coverage, 3),
        "pred_materials": sorted(pred_files),
        "missing_materials": sorted(disk - pred_files),
        "extra_materials": sorted(pred_files - disk),
        "n_gold_lessons": n_gold_lessons,
        "n_pred_lessons": n_pred_lessons,
        "lesson_mean_iou": round(lesson_mean_iou, 3),
        "lesson_recall_at_0.5": round(lesson_recall, 3),
        "lesson_pairs": [
            {"gold": g, "pred": p, "iou": round(s, 3)} for g, p, s in pairs
        ],
        "assessment_attach": round(assess_attach, 3),
        "assessment_attach_counts": {"ok": assess_ok, "total": assess_total},
        "describes_recall": round(desc_recall, 3),
        "edge_precision": round(prec, 3),
        "edge_recall": round(rec, 3),
        "edge_f1": round(edge_f1, 3),
    }
    # provisional pass bar for experiments
    report["pass_provisional"] = bool(
        material_coverage >= 1.0
        and lesson_mean_iou >= 0.5
        and assess_attach >= 0.67
        and n_pred_lessons == n_gold_lessons
    )
    return report


if __name__ == "__main__":
    import argparse
    import pprint

    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--sources", type=Path)
    args = ap.parse_args()
    pprint.pp(score(args.pred, args.gold, args.sources))
