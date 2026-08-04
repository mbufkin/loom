#!/usr/bin/env python3
"""
route.py — Loom router: after Layer 0 (+ optional graph), map each document
to a Path A–G review lens.

Writes:
  layer0/route-map.json   — doc_id → workflow handoff
  _loom_feedback.yaml     — unknown/weak types (append)

Cascade (see docs/PATHS.md):
  1) filename / Layer-0 regex prior
  2) graph Material / Assessment roles (when HAS-PART exists)
  3) model classify — planned tip when still general/low-confidence

Nothing is placed into units here — that happens later, only for routed docs.
"""

from __future__ import annotations

import argparse
import json
import re
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

# Review lenses A–G (docs/PATHS.md)
WORKFLOW_LESSON = "lesson_plan"  # Path A — Lesson
WORKFLOW_ASSESSMENT = "quiz"  # Path B — Assessment (id kept for compat)
WORKFLOW_GENERAL = "general"  # Path C — General feedback
WORKFLOW_TEACHER = "teacher_support"  # Path D
WORKFLOW_STUDENT = "student_practice"  # Path E
WORKFLOW_STANDARDS = "standards_pacing"  # Path F
WORKFLOW_SYLLABUS = "syllabus"  # Path G

PATH_BY_WORKFLOW = {
    WORKFLOW_LESSON: "A",
    WORKFLOW_ASSESSMENT: "B",
    WORKFLOW_GENERAL: "C",
    WORKFLOW_TEACHER: "D",
    WORKFLOW_STUDENT: "E",
    WORKFLOW_STANDARDS: "F",
    WORKFLOW_SYLLABUS: "G",
}

LENS_LABEL = {
    WORKFLOW_LESSON: "Lesson",
    WORKFLOW_ASSESSMENT: "Assessment",
    WORKFLOW_GENERAL: "General feedback",
    WORKFLOW_TEACHER: "Teacher support",
    WORKFLOW_STUDENT: "Student practice",
    WORKFLOW_STANDARDS: "Standards & pacing",
    WORKFLOW_SYLLABUS: "Syllabus",
}

QUIZ_TYPES = frozenset({"quiz", "answer_key", "exit_ticket"})
LESSON_TYPES = frozenset({"lesson_plan"})
# Assessment-bearing types that are not quiz filenames
ASSESSMENT_EXTRA = frozenset({"rubric"})
STUDENT_TYPES = frozenset({"worksheet"})
# Primary type + legacy typo alias from early Path G stub naming.
SYLLABUS_TYPES = frozenset({"syllabus", "sylibuis"})
# Types that should be logged for future checklist growth inside a lens
FEEDBACK_TYPES = frozenset({"other", "flex_day", "game_activity", "lesson_content", "project_work", "presentation", "lab_activity"})

# Filename patterns when graph is missing or silent (priors only).
_TE_RE = re.compile(
    r"teacher[_\s.-]?edition|\b_te\b|educator[_\s.-]?guide|implementation[_\s.-]?guide",
    re.I,
)
_STUDENT_RE = re.compile(
    r"student[_\s.-]?edition|\bsucceed\b|\bpractice\b|\blearn\b|worksheet",
    re.I,
)
_STANDARDS_RE = re.compile(
    r"scope[_\s.-]?and[_\s.-]?sequence|pacing|standards[_\s.-]?overview|"
    r"teks[_\s.-]?summary|elps[_\s.-]?summary|program[_\s.-]?and[_\s.-]?implementation|"
    r"family[_\s.-]?guide|materials[_\s.-]?list",
    re.I,
)
# Match correct spelling first; keep "sylibuis" as typo alias only.
_SYLLABUS_RE = re.compile(r"syllabus|sylibuis", re.I)


def doc_type_to_workflow(doc_type: str) -> tuple[str, str, bool]:
    """Return (workflow_id, path, needs_feedback) from filename/prior type alone."""
    dt = (doc_type or "other").strip().lower()
    if dt in LESSON_TYPES:
        return WORKFLOW_LESSON, "A", False
    if dt in QUIZ_TYPES or dt in ASSESSMENT_EXTRA:
        return WORKFLOW_ASSESSMENT, "B", False
    if dt in SYLLABUS_TYPES:
        return WORKFLOW_SYLLABUS, "G", False
    if dt in STUDENT_TYPES:
        return WORKFLOW_STUDENT, "E", False
    needs_fb = dt in FEEDBACK_TYPES or dt == "other"
    return WORKFLOW_GENERAL, "C", needs_fb


def _load_json(path: Path) -> object:
    if not path.is_file():
        return [] if path.name.endswith(".json") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_source_key(name: str) -> str:
    """Normalize source_file / material name for graph↔ledger joins."""
    s = (name or "").strip().lower()
    if s.endswith(".pdf"):
        s = s[:-4]
    if s.endswith(".txt"):
        s = s[:-4]
    # Dallas extracts: doc_<hex>_<slug>
    if s.startswith("doc_") and len(s) > 16:
        rest = s[4:]
        if "_" in rest:
            rest = rest.split("_", 1)[1]
        s = rest
    return re.sub(r"[^a-z0-9]+", "", s)


def load_graph_routing_hints(project_id: str) -> dict[str, dict]:
    """Map normalized source keys → {role, workflow_id, reason} from HAS-PART.

    Educational note: graph runs before route. Material.role and Assessment
    nodes are stronger than filename \"other\" for Bluebonnet-style packs.
    """
    root = project_dir(project_id)
    hints: dict[str, dict] = {}
    for hp in root.joinpath("graph").rglob("HAS-PART.json"):
        try:
            data = json.loads(hp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        nodes = data.get("nodes") or []
        by_id = {n.get("id"): n for n in nodes if isinstance(n, dict) and n.get("id")}
        # Materials by role
        for n in nodes:
            if not isinstance(n, dict) or n.get("type") != "Material":
                continue
            sf = n.get("source_file") or n.get("name") or ""
            key = _norm_source_key(sf)
            if not key:
                continue
            role = (n.get("role") or "").strip().lower()
            wf = None
            if role == "teacher_edition":
                wf = WORKFLOW_TEACHER
            elif role in {"learn_student", "practice_student"}:
                wf = WORKFLOW_STUDENT
            if wf:
                hints[key] = {
                    "role": role,
                    "workflow_id": wf,
                    "reason": f"graph Material.role={role}",
                    "source_file": sf,
                }
        # Assessment nodes → linked materials via edges
        for e in data.get("edges") or []:
            if not isinstance(e, dict):
                continue
            rel = (e.get("rel") or e.get("type") or "").lower()
            frm, to = e.get("from"), e.get("to")
            a, b = by_id.get(frm) or {}, by_id.get(to) or {}
            # material → assessment or assessment involves material
            mat = None
            if a.get("type") == "Material" and b.get("type") == "Assessment":
                mat = a
            elif b.get("type") == "Material" and a.get("type") == "Assessment":
                mat = b
            elif a.get("type") == "Assessment" and rel in {"assesses", "haspart", "uses"}:
                # try other end
                mat = b if b.get("type") == "Material" else None
            if not mat:
                continue
            sf = mat.get("source_file") or mat.get("name") or ""
            key = _norm_source_key(sf)
            if not key:
                continue
            # Don't override teacher_edition with assessment
            prev = hints.get(key)
            if prev and prev.get("workflow_id") == WORKFLOW_TEACHER:
                continue
            hints[key] = {
                "role": "assessment",
                "workflow_id": WORKFLOW_ASSESSMENT,
                "reason": "graph Assessment link",
                "source_file": sf,
            }
    return hints


def filename_lens_prior(source_file: str) -> tuple[str, str] | None:
    """Optional Path D/E/F/G prior from filename when classify_doc_type is coarse."""
    name = source_file or ""
    if _SYLLABUS_RE.search(name):
        return WORKFLOW_SYLLABUS, "filename prior → syllabus"
    if _STANDARDS_RE.search(name):
        return WORKFLOW_STANDARDS, "filename prior → standards_pacing"
    if _TE_RE.search(name):
        return WORKFLOW_TEACHER, "filename prior → teacher_support"
    if _STUDENT_RE.search(name):
        return WORKFLOW_STUDENT, "filename prior → student_practice"
    return None


def resolve_workflow(
    *,
    doc_type: str,
    source_file: str,
    graph_hint: dict | None,
) -> tuple[str, str, bool, str]:
    """Cascade: lesson/quiz filename → G/F priors → graph → D/E → general.

    Returns (workflow_id, path, needs_feedback, reason).
    """
    dt = (doc_type or "other").strip().lower()

    # Hard filename wins for explicit lesson plans / quizzes (Dallas).
    if dt in LESSON_TYPES:
        return WORKFLOW_LESSON, "A", False, f"filename doc_type={dt}"
    if dt in QUIZ_TYPES:
        return WORKFLOW_ASSESSMENT, "B", False, f"filename doc_type={dt}"

    # Explicit syllabus type or name beats graph TE mis-tags.
    if dt in SYLLABUS_TYPES or _SYLLABUS_RE.search(source_file or ""):
        return (
            WORKFLOW_SYLLABUS,
            "G",
            False,
            "filename prior → syllabus"
            if _SYLLABUS_RE.search(source_file or "")
            else f"filename doc_type={dt}",
        )

    # Standards/pacing names beat graph TE mis-tags (scope/sequence ≠ teacher edition).
    if _STANDARDS_RE.search(source_file or ""):
        return (
            WORKFLOW_STANDARDS,
            "F",
            False,
            "filename prior → standards_pacing",
        )

    # Graph override (Bluebonnet TE/SE, assessments). Do not let graph steal G.
    if graph_hint and graph_hint.get("workflow_id") in PATH_BY_WORKFLOW:
        wf = graph_hint["workflow_id"]
        return (
            wf,
            PATH_BY_WORKFLOW[wf],
            False,
            graph_hint.get("reason") or "graph hint",
        )

    # Rubric → Assessment lens
    if dt in ASSESSMENT_EXTRA:
        return WORKFLOW_ASSESSMENT, "B", False, f"filename doc_type={dt}"

    # Filename D/E priors (F/G already handled above)
    prior = filename_lens_prior(source_file)
    if prior:
        wf, reason = prior
        return wf, PATH_BY_WORKFLOW[wf], False, reason

    if dt in STUDENT_TYPES:
        return WORKFLOW_STUDENT, "E", False, f"filename doc_type={dt}"

    needs_fb = dt in FEEDBACK_TYPES or dt == "other"
    return (
        WORKFLOW_GENERAL,
        "C",
        needs_fb,
        f"mapped from doc_type={dt} (general feedback lens)",
    )


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

    # Fill types from extracted source filenames when missing (Dallas-style doc_*.txt).
    # Bluebonnet-style PDF doc_ids already arrive via the ledger + source_file.
    sources = root / "sources"
    if sources.is_dir():
        for p in sources.rglob("doc_*.txt"):
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
    lines = ["# Loom unknown/weak-type feedback — read when growing lens checklists", ""]
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
    graph_hints = load_graph_routing_hints(project_id)
    routes: list[dict] = []
    feedback: list[dict] = []
    counts: Counter[str] = Counter()

    for rec in records:
        sf = rec.get("source_file") or ""
        hint = graph_hints.get(_norm_source_key(sf))
        if hint is None:
            # try doc_id / stem variants
            hint = graph_hints.get(_norm_source_key(rec["doc_id"]))
        wf, path, needs_fb, reason = resolve_workflow(
            doc_type=rec["doc_type"] or "other",
            source_file=sf,
            graph_hint=hint,
        )
        counts[wf] += 1
        entry = {
            "doc_id": rec["doc_id"],
            "doc_type": rec["doc_type"],
            "workflow_id": wf,
            "path": path,
            "lens": LENS_LABEL.get(wf, wf),
            "reason": reason,
            "feedback": needs_fb,
            "confidence": rec.get("confidence"),
            "source_file": sf,
            "element_count": len(rec.get("element_ids") or []),
            "graph_role": (hint or {}).get("role"),
        }
        routes.append(entry)
        if needs_fb:
            feedback.append(
                {
                    "doc_id": rec["doc_id"],
                    "doc_type": rec["doc_type"],
                    "suggested_pattern": (
                        f"Still on Path C (general). Prefer a checklist inside "
                        f"Lesson/Assessment/Teacher/Student/Standards rather than "
                        f"a new path letter (see docs/PATHS.md). type='{rec['doc_type']}'"
                    ),
                    "reason": "weak_or_unknown_type",
                }
            )

    # Soft validation: every ledger doc should be routed
    root = project_dir(project_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    ledger_ids = (
        {e.get("doc_id") for e in ledger if e.get("doc_id")}
        if isinstance(ledger, list)
        else set()
    )
    routed_ids = {r["doc_id"] for r in routes}
    missing = sorted(ledger_ids - routed_ids)
    if missing:
        log(f"WARN: route soft-gate — {len(missing)} ledger doc_id(s) not in route-map")

    fb_path = append_feedback(project_id, feedback)
    out = {
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lenses": LENS_LABEL,
        "counts": dict(counts),
        "unrouted_ledger_doc_ids": missing,
        "feedback_path": str(fb_path) if fb_path else None,
        "graph_hints": len(graph_hints),
        "routes": routes,
    }
    dest = root / "layer0" / "route-map.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(out, indent=2, ensure_ascii=False))
    log(
        f"route → {dest} "
        f"(A={counts[WORKFLOW_LESSON]} B={counts[WORKFLOW_ASSESSMENT]} "
        f"C={counts[WORKFLOW_GENERAL]} D={counts[WORKFLOW_TEACHER]} "
        f"E={counts[WORKFLOW_STUDENT]} F={counts[WORKFLOW_STANDARDS]} "
        f"G={counts[WORKFLOW_SYLLABUS]}; "
        f"graph_hints={len(graph_hints)} feedback={len(feedback)})"
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
    # Aliases: assessment ↔ quiz for Path B
    aliases = {workflow_id} if workflow_id else None
    if workflow_id == "assessment":
        aliases = {"assessment", "quiz"}
    elif workflow_id == "quiz":
        aliases = {"quiz", "assessment"}
    out: set[str] = set()
    for r in data.get("routes") or []:
        if aliases is not None and r.get("workflow_id") not in aliases:
            continue
        if r.get("doc_id"):
            out.add(r["doc_id"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Loom router — map docs to Path A–G review lenses"
    )
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    validate_slug_id(args.project, "project id")
    build_route_map(args.project)
    return 0


if __name__ == "__main__":
    sys.exit(main())
