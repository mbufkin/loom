#!/usr/bin/env python3
"""
route.py — Loom router: after Layer 0, map each document to Path A/B/C.

Writes:
  layer0/route-map.json   — doc_id → workflow handoff
  _loom_feedback.yaml     — unknown/weak types (append)

Nothing is placed into units here — that happens later, only for routed docs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from audit_lib import (
    atomic_write,
    classify_doc_type,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)

# Filename / Layer-0 priors → Loom workflow
WORKFLOW_LESSON = "lesson_plan"
WORKFLOW_QUIZ = "quiz"
WORKFLOW_GENERAL = "general"

PATH_BY_WORKFLOW = {
    WORKFLOW_LESSON: "A",
    WORKFLOW_QUIZ: "B",
    WORKFLOW_GENERAL: "C",
}

QUIZ_TYPES = frozenset({"quiz", "answer_key", "exit_ticket"})
LESSON_TYPES = frozenset({"lesson_plan"})
# Types that should be logged for future Path growth
FEEDBACK_TYPES = frozenset({"other", "flex_day", "game_activity"})


def doc_type_to_workflow(doc_type: str) -> tuple[str, str, bool]:
    """Return (workflow_id, path, needs_feedback)."""
    dt = (doc_type or "other").strip().lower()
    if dt in LESSON_TYPES:
        return WORKFLOW_LESSON, "A", False
    if dt in QUIZ_TYPES:
        return WORKFLOW_QUIZ, "B", False
    needs_fb = dt in FEEDBACK_TYPES or dt == "other"
    return WORKFLOW_GENERAL, "C", needs_fb


def _load_json(path: Path) -> object:
    if not path.is_file():
        return [] if path.name.endswith(".json") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_doc_records(project_id: str) -> list[dict]:
    """Build Layer0→router handoff records from ledger + sources."""
    root = project_dir(project_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        ledger = []

    by_doc: dict[str, dict] = {}
    for e in ledger:
        did = e.get("doc_id")
        if not did:
            continue
        rec = by_doc.setdefault(
            did,
            {
                "doc_id": did,
                "source_file": e.get("source_file") or "",
                "doc_type": None,
                "confidence": 0.7,
                "chunk_ids": [],
                "element_ids": [],
            },
        )
        if e.get("source_file") and not rec["source_file"]:
            rec["source_file"] = e["source_file"]
        eid = e.get("element_id")
        if eid:
            rec["element_ids"].append(str(eid))
        cid = e.get("chunk_id")
        if cid:
            rec["chunk_ids"].append(str(cid))
        prior = e.get("regex_doc_type_prior")
        if prior and not rec["doc_type"]:
            rec["doc_type"] = prior
            rec["confidence"] = 0.85

    # Fill types from source filenames when missing
    sources = root / "sources"
    if sources.is_dir():
        for p in sources.glob("doc_*.txt"):
            did = doc_id_from_filename(p.name)
            dtype = classify_doc_type(p.name)
            if did not in by_doc:
                by_doc[did] = {
                    "doc_id": did,
                    "source_file": p.name,
                    "doc_type": dtype,
                    "confidence": 0.9,
                    "chunk_ids": [],
                    "element_ids": [],
                }
            else:
                if not by_doc[did].get("doc_type"):
                    by_doc[did]["doc_type"] = dtype
                    by_doc[did]["confidence"] = 0.9
                if not by_doc[did].get("source_file"):
                    by_doc[did]["source_file"] = p.name

    for rec in by_doc.values():
        if not rec.get("doc_type"):
            fname = rec.get("source_file") or rec["doc_id"]
            rec["doc_type"] = classify_doc_type(fname)
            rec["confidence"] = 0.6
        # dedupe lists
        rec["element_ids"] = sorted(set(rec["element_ids"]))
        rec["chunk_ids"] = sorted(set(rec["chunk_ids"]))

    return sorted(by_doc.values(), key=lambda r: r["doc_id"])


def append_feedback(project_id: str, entries: list[dict]) -> Path | None:
    if not entries:
        return None
    root = project_dir(project_id)
    path = root / "_loom_feedback.yaml"
    existing: list = []
    if path.is_file():
        try:
            data = load_yaml(path)
            if isinstance(data, list):
                existing = data
            elif isinstance(data, dict) and isinstance(data.get("entries"), list):
                existing = data["entries"]
        except Exception:
            existing = []
    stamp = datetime.now(timezone.utc).isoformat()
    for e in entries:
        existing.append({**e, "logged_at": stamp})
    # Write as a simple YAML list
    lines = ["# Loom unknown/weak-type feedback — read when growing new paths", ""]
    for e in existing:
        lines.append("- doc_id: " + json.dumps(e.get("doc_id")))
        lines.append("  doc_type: " + json.dumps(e.get("doc_type")))
        lines.append("  suggested_pattern: " + json.dumps(e.get("suggested_pattern")))
        lines.append("  reason: " + json.dumps(e.get("reason")))
        lines.append("  logged_at: " + json.dumps(e.get("logged_at")))
        lines.append("")
    atomic_write(path, "\n".join(lines))
    return path


def build_route_map(project_id: str) -> dict:
    records = collect_doc_records(project_id)
    routes: list[dict] = []
    feedback: list[dict] = []
    counts: Counter[str] = Counter()

    for rec in records:
        wf, path, needs_fb = doc_type_to_workflow(rec["doc_type"])
        counts[wf] += 1
        entry = {
            "doc_id": rec["doc_id"],
            "doc_type": rec["doc_type"],
            "workflow_id": wf,
            "path": path,
            "reason": f"mapped from doc_type={rec['doc_type']}",
            "feedback": needs_fb,
            "confidence": rec.get("confidence"),
            "source_file": rec.get("source_file"),
            "element_count": len(rec.get("element_ids") or []),
        }
        routes.append(entry)
        if needs_fb:
            feedback.append(
                {
                    "doc_id": rec["doc_id"],
                    "doc_type": rec["doc_type"],
                    "suggested_pattern": (
                        f"Consider a dedicated workflow for type '{rec['doc_type']}' "
                        f"(currently Path C general)."
                    ),
                    "reason": "weak_or_unknown_type",
                }
            )

    # Soft validation: every ledger doc should be routed
    root = project_dir(project_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    ledger_ids = {e.get("doc_id") for e in ledger if e.get("doc_id")} if isinstance(ledger, list) else set()
    routed_ids = {r["doc_id"] for r in routes}
    missing = sorted(ledger_ids - routed_ids)
    if missing:
        log(f"WARN: route soft-gate — {len(missing)} ledger doc_id(s) not in route-map")

    fb_path = append_feedback(project_id, feedback)
    out = {
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": dict(counts),
        "unrouted_ledger_doc_ids": missing,
        "feedback_path": str(fb_path) if fb_path else None,
        "routes": routes,
    }
    dest = root / "layer0" / "route-map.json"
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(
        f"route → {dest} "
        f"(A={counts[WORKFLOW_LESSON]} B={counts[WORKFLOW_QUIZ]} "
        f"C={counts[WORKFLOW_GENERAL]}; feedback={len(feedback)})"
    )
    return out


def load_route_map(project_id: str) -> dict:
    path = project_dir(project_id) / "layer0" / "route-map.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def routed_doc_ids(project_id: str, *, workflow_id: str | None = None) -> set[str]:
    data = load_route_map(project_id)
    out: set[str] = set()
    for r in data.get("routes") or []:
        if workflow_id and r.get("workflow_id") != workflow_id:
            continue
        if r.get("doc_id"):
            out.add(r["doc_id"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Loom router — map docs to Path A/B/C")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    validate_slug_id(args.project, "project id")
    root = project_dir(args.project)
    if not (root / "layer0" / "ledger.json").is_file() and not (root / "sources").is_dir():
        log("ERROR: need layer0/ledger.json or sources/ before routing")
        return 1
    build_route_map(args.project)
    return 0


if __name__ == "__main__":
    sys.exit(main())
