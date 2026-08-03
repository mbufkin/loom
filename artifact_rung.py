#!/usr/bin/env python3
"""
artifact_rung.py — the NON-lesson artifact rung of the curriculum waterfall.

Path A reviews lesson plans. This rung reviews everything else — quizzes, exit
tickets, rubrics, worksheets, answer keys, projects, slides, and unknown types —
so a curriculum's ~80% non-lesson documents get a real review instead of a stub.

It mirrors lesson_rung.py exactly one artifact at a time:
  1. enumerate every NON-lesson doc from the Layer 0 ledger, map it to its unit;
  2. run the DETERMINISTIC PresenceScorer from that doc's per-type spec (gates);
  3. optionally run the model AlignmentScorer (advisory) against the unit's anchor
     (lesson objective -> cited TEKS -> "cannot assess", rolled up as a lesson gap);
  4. roll up per unit and emit layer_artifact/ARTIFACT-RUNG.json (+ .md) — the stable
     hand-off unit_rung.py consumes (deterministic gaps GATE, alignment ADVISES).

Unknown/`other` types get the generic fallback spec and are appended to
_loom_feedback.yaml (the feedback nursery) so a future dedicated Path can be grown —
curriculum-agnostic by construction, no per-curriculum code.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import artifact_scorers  # noqa: F401 — import registers the presence/alignment scorers
from artifact_scorers import ANCHOR_OBJECTIVE, ANCHOR_TEKS
from audit_lib import (
    atomic_write,
    classify_doc_type,
    doc_id_from_filename,
    load_config,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)
from lesson_scoring import ArtifactInput, LessonElement, build_scorer

# Doc roles that ARE lessons (reviewed by the lesson rung / Path A) and so are NOT
# artifacts. teacher_edition_multi_lesson is a lesson CONTAINER fanned by te_prepass
# — also not a standalone artifact. Everything else is an artifact this rung reviews.
LESSON_ROLES = {"lesson_plan", "lesson_content", "teacher_edition_multi_lesson"}

PRESENCE_SCORER = "artifact_presence"
ALIGNMENT_SCORER = "artifact_alignment"

# A permissive cited-standard detector for the TEKS fallback anchor. We are not
# validating the code, only detecting that the lesson names a standard we can use as
# the alignment target when it has no prose objective. Matches "TEKS 130.362",
# "§130.42(c)(1)(A)", "126.6(c)(2)" etc. Curriculum-agnostic (any dotted-number
# standard or explicit TEKS/standard mention).
_TEKS_RE = re.compile(
    r"(?:TEKS|standard[s]?)\b[^.\n]{0,60}|§?\s*\d{2,3}\.\d{1,3}[A-Za-z]?(?:\([^)]*\))*",
    re.IGNORECASE,
)


# --- anchor resolution (shared) ---------------------------------------------


def _find_teks(elements: list[LessonElement]) -> str | None:
    """First cited-standard mention across a lesson's elements, or None."""
    for el in elements:
        m = _TEKS_RE.search(el.excerpt or "")
        if m:
            snippet = (el.excerpt or "")[max(0, m.start() - 20) : m.end() + 80].strip()
            return snippet
    return None


def resolve_unit_anchors(project_id: str, lessons=None) -> dict[str, dict]:
    """Per-unit alignment anchor, resolved the way a human reviewer would:

      1. the unit's lesson OBJECTIVE (a standards_objectives element) — preferred;
      2. else a cited TEKS/standard found anywhere in the unit's lesson text;
      3. else NONE — recorded so the artifact rung can emit "cannot assess alignment"
         and roll it up as a lesson-level gap (the lesson has no objective/standard).

    Pure w.r.t. the model (reads only Layer 0 elements). Returns unit_id -> anchor
    dict {kind, text, lesson_id, element_id?}. A unit with no lessons gets no entry
    (its artifacts then resolve to the NONE anchor -> lesson gap)."""
    if lessons is None:
        from lesson_bakeoff import enumerate_lessons

        lessons = enumerate_lessons(project_id)

    anchors: dict[str, dict] = {}
    for le in lessons:
        uid = le.unit_id
        # Keep the first strong OBJECTIVE anchor per unit; don't let a later weaker
        # TEKS anchor overwrite it.
        if anchors.get(uid, {}).get("kind") == ANCHOR_OBJECTIVE:
            continue
        obj = le.elements_of_type("standards_objectives")
        if obj and (obj[0].excerpt or "").strip():
            anchors[uid] = {
                "kind": ANCHOR_OBJECTIVE,
                "text": obj[0].excerpt.strip(),
                "lesson_id": le.lesson_id,
                "element_id": obj[0].element_id,
            }
            continue
        if uid not in anchors:
            teks = _find_teks(le.elements)
            if teks:
                anchors[uid] = {
                    "kind": ANCHOR_TEKS,
                    "text": teks,
                    "lesson_id": le.lesson_id,
                }
    return anchors


# --- enumeration ------------------------------------------------------------


def enumerate_artifacts(project_id: str) -> list[ArtifactInput]:
    """One ArtifactInput per NON-lesson document from the Layer 0 ledger, mapped to
    its unit via the manifest and carrying its classified doc_type. Deterministic +
    offline (mirrors lesson_bakeoff.enumerate_lessons)."""
    root = project_dir(project_id)
    manifest = load_yaml(root / "manifest.yaml")
    ledger_path = root / "layer0" / "ledger.json"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"no Layer 0 ledger at {ledger_path} — run layer0 first")
    ledger = json.loads(ledger_path.read_text())

    doc_unit: dict[str, str] = {}
    for uid, unit in (manifest.get("units") or {}).items():
        for rel in unit.get("documents") or unit.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)

    by_doc: dict[str, list[dict]] = defaultdict(list)
    for el in ledger:
        by_doc[el["doc_id"]].append(el)

    from synthesize import readable_title_from_filename

    artifacts: list[ArtifactInput] = []
    for doc_id, els in by_doc.items():
        source_file = els[0].get("source_file", doc_id)
        dtype = classify_doc_type(source_file)
        # Lessons (and TE containers) are reviewed by the lesson rung — never
        # double-reviewed here (this is the lesson_content contradiction fix).
        if dtype in LESSON_ROLES:
            continue
        elements = [
            LessonElement(
                e["element_id"], e.get("element_type", ""), e.get("excerpt", "")
            )
            for e in els
        ]
        artifacts.append(
            ArtifactInput(
                project_id=project_id,
                lesson_id=doc_id,
                unit_id=doc_unit.get(doc_id, "(unlinked)"),
                title=readable_title_from_filename(source_file),
                elements=elements,
                doc_type=dtype,
                # sources/<basename> — served by the review API so the UI can show
                # the raw document beneath its per-doc review.
                source_file=f"sources/{source_file}" if source_file else None,
            )
        )
    artifacts.sort(key=lambda a: (a.unit_id, a.doc_type, a.title))
    return artifacts


# --- per-doc + per-unit rollup ----------------------------------------------


def artifact_record(artifact: ArtifactInput, presence, alignment=None) -> dict:
    """One artifact's rung record: role, unit, presence verdicts + gate, and (when
    run) the advisory alignment block. Every verdict keeps its cited evidence."""
    rec = {
        "doc_id": artifact.lesson_id,
        "unit_id": artifact.unit_id,
        "title": artifact.title,
        "source_file": artifact.source_file,
        "role": presence.summary.get("role", artifact.doc_type),
        "doc_type": artifact.doc_type,
        "is_fallback": presence.summary.get("is_fallback", False),
        "nursery": presence.summary.get("nursery", False),
        "presence": {
            "gate_pass": presence.summary.get("gate_pass", False),
            "coverage": presence.summary.get("coverage"),
            # Required parts not fully present — the structural gaps that gate.
            "missing_required": presence.summary.get("missing_required", []),
            "criteria": [c.to_dict() for c in presence.criteria],
        },
    }
    if alignment is not None:
        rec["alignment"] = {
            "applicable": alignment.summary.get("applicable", False),
            "cannot_assess": alignment.summary.get("cannot_assess", False),
            "skipped": alignment.summary.get("skipped", False),
            "mean_band": alignment.summary.get("mean_band"),
            "max_band": alignment.summary.get("max_band"),
            "anchor_kind": alignment.summary.get("anchor_kind"),
            "error": alignment.error,
            "criteria": [c.to_dict() for c in alignment.criteria],
        }
    return rec


def rollup_units(records: list[dict]) -> dict:
    """Compose per-artifact records into a per-unit summary — the hand-off the unit
    rung reads. Pure (no I/O). Deterministic presence drives the gate signals; any
    alignment is carried as advisory only."""
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_unit[r["unit_id"]].append(r)

    units: dict[str, dict] = {}
    for uid, rows in sorted(by_unit.items()):
        n = len(rows)
        gate_pass = sum(1 for r in rows if r["presence"]["gate_pass"])
        # Deterministic structural gaps: artifacts that failed their presence gate,
        # named by role + what they lack. These are what GATE the unit band.
        gaps = [
            {
                "doc_id": r["doc_id"],
                "role": r["role"],
                "title": r["title"],
                "missing_required": r["presence"]["missing_required"],
            }
            for r in rows
            if not r["presence"]["gate_pass"]
        ]
        cannot_assess = sum(
            1 for r in rows if r.get("alignment", {}).get("cannot_assess")
        )
        role_counts: dict[str, int] = defaultdict(int)
        for r in rows:
            role_counts[r["role"]] += 1
        units[uid] = {
            "artifact_count": n,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / n, 3) if n else 0.0,
            "roles": dict(role_counts),
            "deterministic_gaps": gaps,
            "has_artifact_gap": bool(gaps),
            "cannot_assess_alignment": cannot_assess,
            "documents": rows,
        }
    return units


def _nursery_entries(records: list[dict]) -> list[dict]:
    """Feedback-nursery tickets for unknown/`other` (fallback) types — one per doc,
    the "grow a real Path for this type" signal, matching route.append_feedback's
    shape."""
    entries = []
    for r in records:
        if r.get("nursery"):
            entries.append(
                {
                    "doc_id": r["doc_id"],
                    "doc_type": r["doc_type"],
                    "suggested_pattern": (
                        f"No dedicated review spec for type '{r['doc_type']}'; scored "
                        f"with the generic fallback. Add workflows/rubrics/artifacts/"
                        f"{r['doc_type']}.yaml to grow a real Path."
                    ),
                    "reason": "weak_or_unknown_type",
                }
            )
    return entries


# --- build ------------------------------------------------------------------


def score_artifacts(
    project_id: str, doc_ids: set[str] | None = None, with_model: bool = False
) -> list[dict]:
    """Score non-lesson artifacts and return their per-doc records. When `doc_ids` is
    given, only those docs are scored (so the router paths B/C can score just their
    own routed subset while reusing the exact same engine as the rung). Presence
    always runs (deterministic); alignment runs only with_model (advisory).

    Shared by build_artifact_rung and workflows/quiz.py + general.py so there is ONE
    engine — no divergent per-path logic."""
    artifacts = enumerate_artifacts(project_id)
    if doc_ids is not None:
        artifacts = [a for a in artifacts if a.lesson_id in doc_ids]
    anchors = resolve_unit_anchors(project_id)
    presence = build_scorer(PRESENCE_SCORER)
    aligner = build_scorer(ALIGNMENT_SCORER) if with_model else None
    cfg = load_config() if with_model else None

    records: list[dict] = []
    for art in artifacts:
        art.anchor = anchors.get(art.unit_id)
        pres = presence.score(art, None)
        align = aligner.score(art, cfg) if aligner else None
        records.append(artifact_record(art, pres, align))
    return records


def build_artifact_rung(project_id: str, with_model: bool = False) -> Path:
    """Score every non-lesson artifact and write ARTIFACT-RUNG.json (+ .md). Presence
    always runs (deterministic); alignment runs only with_model (advisory)."""
    records = score_artifacts(project_id, doc_ids=None, with_model=with_model)
    units = rollup_units(records)
    total = len(records)
    gate_pass = sum(1 for r in records if r["presence"]["gate_pass"])
    role_totals: dict[str, int] = defaultdict(int)
    for r in records:
        role_totals[r["role"]] += 1

    # Feedback nursery: append unknown/other types so a future Path can be grown.
    nursery = _nursery_entries(records)
    if nursery:
        from route import append_feedback

        append_feedback(project_id, nursery)

    artifact = {
        "project_id": project_id,
        "presence_scorer": PRESENCE_SCORER,
        "alignment_scorer": ALIGNMENT_SCORER if with_model else None,
        "with_model": with_model,
        "summary": {
            "artifact_count": total,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / total, 3) if total else 0.0,
            "unit_count": len(units),
            "roles": dict(sorted(role_totals.items())),
            "nursery_count": len(nursery),
        },
        "units": units,
        "artifacts": records,
    }

    out_dir = project_dir(project_id) / "layer_artifact"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "ARTIFACT-RUNG.json"
    atomic_write(dest, json.dumps(artifact, indent=2))
    atomic_write(out_dir / "ARTIFACT-RUNG.md", _render_md(project_id, artifact))
    log(
        f"artifact-rung → {dest} ({total} artifacts, {gate_pass} passed presence "
        f"gate, {len(units)} units, {len(nursery)} nursery tickets)"
    )
    return dest


def _render_md(project_id: str, artifact: dict) -> str:
    s = artifact["summary"]
    roles = "  ·  ".join(f"{k}×{v}" for k, v in s["roles"].items()) or "(none)"
    md = [
        "# Artifact rung (Paths B/C — non-lesson review)",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Artifacts:** {s['artifact_count']}  ·  "
        f"**Passed presence gate:** {s['gate_pass_count']} "
        f"({s['gate_pass_rate']:.0%})  ·  **Units:** {s['unit_count']}",
        f"**Roles:** {roles}  ",
        f"**Feedback-nursery tickets (unknown types):** {s['nursery_count']}",
        "",
        "Deterministic presence GATES the unit band; model alignment (with `--with-model`) "
        "ADVISES only. Per-doc, evidence-cited detail is in `ARTIFACT-RUNG.json`.",
        "",
        "| Unit | Artifacts | Presence gate | Structural gaps | Cannot-assess |",
        "|---|---|---|---|---|",
    ]
    for uid, u in artifact["units"].items():
        gaps = len(u["deterministic_gaps"])
        md.append(
            f"| {uid} | {u['artifact_count']} | "
            f"{u['gate_pass_count']}/{u['artifact_count']} | {gaps} | "
            f"{u['cannot_assess_alignment']} |"
        )
    return "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Artifact rung (Paths B/C non-lesson review; feeds the unit rung)"
    )
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--with-model",
        action="store_true",
        help="also run the advisory alignment audit (one model call per artifact)",
    )
    args = ap.parse_args()
    validate_slug_id(args.project, "project id")
    try:
        build_artifact_rung(args.project, with_model=args.with_model)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
