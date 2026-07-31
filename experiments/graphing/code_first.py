#!/usr/bin/env python3
"""Deterministic HAS-PART proposal (Option D first half).

Educational note: heuristics only propose structure from Day headers, filenames,
and doc_type priors. The model repair pass may confirm/split/merge — this module
must stay pure and testable without a model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from audit_lib import scrub_document

DAY_HEADER_RE = re.compile(r"^\s*Day\s*([1-9]\d*)\b", re.I | re.M)
EXIT_DAY_RE = re.compile(r"Exit\s*Ticket\s*[-–—:]?\s*Day\s*([1-9]\d*)", re.I)
DAY_IN_NAME_RE = re.compile(r"Day[_\s-]*([1-9]\d*)", re.I)


def _paras(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def _doc_id_from_name(name: str) -> str:
    m = re.match(r"doc_([0-9a-f]+)_", name)
    return m.group(1) if m else Path(name).stem


def _guess_role(name: str, doc_type: str | None) -> str:
    n = name.lower()
    dt = (doc_type or "").lower()
    if "exit_ticket" in n or "exit-ticket" in n or dt == "exit_ticket":
        return "exit_ticket"
    if "rubric" in n or dt == "rubric":
        return "rubric"
    if "lesson_plan" in n or "lesson-plan" in n or dt == "lesson_plan":
        return "lesson_plan"
    if "notes" in n or dt in {"worksheet", "project_work"}:
        return "worksheet"
    if "slide" in n or dt in {"lesson_content", "presentation"}:
        return "lesson_content"
    if dt and dt != "other":
        return dt
    return "other"


def day_spans_from_text(text: str) -> list[dict[str, Any]]:
    """Return [{day, start_para, end_para}] using blank-line paragraph indices (1-based)."""
    paras = _paras(text)
    starts: list[tuple[int, int]] = []  # (day, para_idx)
    for i, p in enumerate(paras, 1):
        # header at start of paragraph
        m = DAY_HEADER_RE.match(p.split("\n", 1)[0].strip() + "\n")
        if not m:
            m = re.match(r"^\s*Day\s*([1-9]\d*)\b", p, re.I)
        if m:
            # skip "Exit Ticket - Day N" as lesson starts (those are assessments)
            first = p.split("\n", 1)[0]
            if re.search(r"Exit\s*Ticket", first, re.I):
                continue
            starts.append((int(m.group(1)), i))
    if not starts:
        return []
    # unique by day keeping first
    seen = {}
    for day, idx in starts:
        seen.setdefault(day, idx)
    ordered = sorted(seen.items(), key=lambda x: x[1])
    spans = []
    for i, (day, start) in enumerate(ordered):
        end = (ordered[i + 1][1] - 1) if i + 1 < len(ordered) else len(paras)
        spans.append({"day": day, "start_para": start, "end_para": end})
    return spans


def elements_in_span(ledger_rows: list[dict], start: int, end: int) -> list[str]:
    out = []
    for e in ledger_rows:
        s = e.get("excerpt_start_paragraph")
        t = e.get("excerpt_end_paragraph")
        if s is None:
            continue
        t = t if t is not None else s
        # overlap with [start,end]
        if t < start or s > end:
            continue
        out.append(e["element_id"])
    return out


def load_ledger_for_project(project_root: Path, source_names: set[str]) -> dict[str, list[dict]]:
    """Prefer project layer0 ledger; fall back to dallas-career-2026 ledger by filename."""
    candidates = [
        project_root / "layer0" / "ledger.json",
        Path("projects/dallas-career-2026/layer0/ledger.json"),
        Path("projects/lab-dallas-career/layer0/ledger.json"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        by: dict[str, list[dict]] = {}
        for e in rows:
            sf = e.get("source_file")
            if sf in source_names:
                by.setdefault(sf, []).append(e)
        if by:
            return by
    return {}


def propose_graph(project_id: str, project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path("projects") / project_id
    sources = root / "sources"
    manifest = {}
    man_path = root / "manifest.yaml"
    if man_path.is_file():
        import yaml

        manifest = yaml.safe_load(man_path.read_text(encoding="utf-8")) or {}

    units = manifest.get("units") or {}
    if not units:
        unit_id = "unit"
        unit_title = project_id
        doc_names = sorted(p.name for p in sources.glob("*") if p.is_file())
        unit_docs = {unit_id: doc_names}
    else:
        unit_docs = {
            uid: list(u.get("documents") or []) for uid, u in units.items()
        }
        # titles
        unit_id = next(iter(units))
        unit_title = (units[unit_id] or {}).get("title") or unit_id

    all_names = set()
    for docs in unit_docs.values():
        all_names.update(docs)
    # also any files on disk
    if sources.is_dir():
        all_names.update(p.name for p in sources.glob("*") if p.is_file())

    ledger_by = load_ledger_for_project(root, all_names)

    nodes: list[dict] = [
        {"id": f"course:{project_id}", "type": "Course", "name": project_id},
    ]
    edges: list[dict] = []

    # one unit for labs (first / only)
    for uid, docs in unit_docs.items():
        utitle = (units.get(uid) or {}).get("title") or uid
        unit_node = f"unit:{uid}"
        nodes.append(
            {
                "id": unit_node,
                "type": "LessonGrouping",
                "name": utitle,
                "groupName": "unit",
            }
        )
        edges.append(
            {"rel": "hasPart", "from": f"course:{project_id}", "to": unit_node}
        )

        # scrub each doc
        meta = []
        for name in sorted(docs):
            path = sources / name
            if not path.is_file():
                continue
            ev = scrub_document(path)
            role = _guess_role(name, ev.get("doc_type"))
            text = ev.get("content_clean") or path.read_text(errors="replace")
            meta.append(
                {
                    "name": name,
                    "doc_id": _doc_id_from_name(name),
                    "role": role,
                    "doc_type": ev.get("doc_type"),
                    "text": text,
                    "spans": day_spans_from_text(text),
                }
            )

        # Materials for every file
        for m in meta:
            mid = f"material:{m['doc_id']}"
            nodes.append(
                {
                    "id": mid,
                    "type": "Material",
                    "role": m["role"],
                    "name": m["name"],
                    "source_file": m["name"],
                    "doc_id": m["doc_id"],
                }
            )
            edges.append({"rel": "hasPart", "from": unit_node, "to": mid})

        # Choose primary multi-day content: prefer lesson_content with day spans, else any with spans
        content_candidates = [m for m in meta if m["spans"] and m["role"] in {"lesson_content", "other", "presentation"}]
        if not content_candidates:
            content_candidates = [m for m in meta if m["spans"]]
        primary = max(content_candidates, key=lambda m: len(m["spans"])) if content_candidates else None

        lessons: dict[int, str] = {}
        if primary:
            rows = ledger_by.get(primary["name"], [])
            # Include lead-in paragraphs before the first Day header (title blocks).
            spans = list(primary["spans"])
            if spans and spans[0]["start_para"] > 1:
                spans[0] = {
                    **spans[0],
                    "start_para": 1,
                }
            for sp in spans:
                day = sp["day"]
                lid = f"lesson:{uid}:d{day}"
                lessons[day] = lid
                eids = elements_in_span(rows, sp["start_para"], sp["end_para"])
                # Next day's header element often overlaps the boundary — drop
                # elements whose excerpt starts with "Day {next}".
                next_days = {s["day"] for s in spans if s["day"] != day}
                filtered = []
                by_id = {e["element_id"]: e for e in rows}
                for eid in eids:
                    ex = (by_id.get(eid) or {}).get("excerpt") or ""
                    first = ex.strip().split("\n", 1)[0]
                    mday = re.match(r"^\s*Day\s*([1-9]\d*)\b", first, re.I)
                    if mday and int(mday.group(1)) in next_days:
                        continue
                    filtered.append(eid)
                eids = filtered
                nodes.append(
                    {
                        "id": lid,
                        "type": "Lesson",
                        "name": f"Day {day}",
                        "span": {
                            "source_file": primary["name"],
                            "doc_id": primary["doc_id"],
                            "paragraphs": [sp["start_para"], sp["end_para"]],
                            "element_ids": eids,
                        },
                    }
                )
                edges.append({"rel": "hasPart", "from": unit_node, "to": lid})
                edges.append(
                    {"rel": "spanIn", "from": lid, "to": f"material:{primary['doc_id']}"}
                )
                # In-deck assessments (no separate exit-ticket file)
                for eid in eids:
                    e = by_id.get(eid) or {}
                    if e.get("element_type") != "assessment_checkpoint":
                        continue
                    aid = f"assessment:{uid}:d{day}:{eid}"
                    nodes.append(
                        {
                            "id": aid,
                            "type": "Assessment",
                            "name": (e.get("excerpt") or "checkpoint")[:80],
                            "element_ids": [eid],
                            "embedded_in": primary["name"],
                        }
                    )
                    edges.append({"rel": "hasPart", "from": lid, "to": aid})

        # lesson plans describe all lessons
        for m in meta:
            if m["role"] != "lesson_plan":
                continue
            for lid in lessons.values():
                edges.append(
                    {
                        "rel": "describes",
                        "from": f"material:{m['doc_id']}",
                        "to": lid,
                    }
                )

        # exit tickets → Assessment under matching day
        for m in meta:
            if m["role"] != "exit_ticket":
                continue
            day = None
            mm = DAY_IN_NAME_RE.search(m["name"]) or EXIT_DAY_RE.search(m["text"][:400])
            if mm:
                day = int(mm.group(1))
            aid = f"assessment:d{day}:exit-ticket" if day else f"assessment:{m['doc_id']}"
            # avoid dup ids
            if any(n.get("id") == aid for n in nodes):
                aid = f"assessment:{m['doc_id']}"
            nodes.append(
                {
                    "id": aid,
                    "type": "Assessment",
                    "name": f"Exit Ticket Day {day}" if day else m["name"],
                    "source_file": m["name"],
                    "doc_id": m["doc_id"],
                    "span": {
                        "element_ids": [e["element_id"] for e in ledger_by.get(m["name"], [])]
                    },
                }
            )
            if day and day in lessons:
                edges.append({"rel": "hasPart", "from": lessons[day], "to": aid})
            else:
                edges.append({"rel": "hasPart", "from": unit_node, "to": aid})

        # rubrics: uses from last create-ish day (max day) or unit
        rubric_mats = [m for m in meta if m["role"] == "rubric"]
        if rubric_mats and lessons:
            target_day = max(lessons)
            # prefer day 2 if present (common create day)
            if 2 in lessons:
                target_day = 2
            for m in rubric_mats:
                edges.append(
                    {
                        "rel": "uses",
                        "from": lessons[target_day],
                        "to": f"material:{m['doc_id']}",
                    }
                )

        # worksheets/notes → uses from d1 if present else unit
        for m in meta:
            if m["role"] != "worksheet":
                continue
            if 1 in lessons:
                edges.append(
                    {
                        "rel": "uses",
                        "from": lessons[1],
                        "to": f"material:{m['doc_id']}",
                    }
                )

    return {
        "project_id": project_id,
        "model": "code-first-v0",
        "method": "P1xD-propose",
        "nodes": nodes,
        "edges": edges,
        "coverage": {
            "source_files_seen": len(all_names),
            "source_files": sorted(all_names),
        },
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("-o", type=Path)
    args = ap.parse_args()
    g = propose_graph(args.project)
    text = json.dumps(g, indent=2)
    if args.o:
        args.o.parent.mkdir(parents=True, exist_ok=True)
        args.o.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
