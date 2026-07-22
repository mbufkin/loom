#!/usr/bin/env python3
"""
artifact_scorers.py — the Path B/C review scorers for NON-lesson artifacts.

Two scorers, mirroring the lesson rung's split of labor:

  PresenceScorer  (deterministic, GATES)  — reads a per-type spec
                  (workflows/rubrics/artifacts/<role>.yaml) and decides
                  PRESENT / PARTIAL / MISSING for each structural part from the
                  artifact's own Layer 0 elements. No model call — completeness is a
                  fact. Its `gate_pass` is the deterministic signal the unit rung can
                  hard-gate on (a quiz with no items, an answer key with no answers).

  AlignmentScorer (model, ADVISES only)    — resolves nothing itself; it consumes the
                  anchor the artifact rung already resolved (unit objective -> cited
                  TEKS -> none) and judges, with EVIDENCE-BOUND citations, whether the
                  artifact serves that objective. Auditor-only: it never asserts a
                  student's answer is correct, and an uncited band is downgraded to
                  needs-review. When there is no anchor it emits an honest
                  "cannot assess alignment" that the rung rolls up as a lesson gap.

Both reuse the document-agnostic Scorer/CriterionResult/Evidence/ScorerResult schema
from lesson_scoring.py verbatim — an artifact is just a LessonInput with a doc_type.
"""

from __future__ import annotations

from lesson_scoring import (
    ArtifactInput,
    CriterionResult,
    Evidence,
    Scorer,
    ScorerResult,
    presence_result,
    register_scorer,
    summarize_bands,
)
from rubrics import load_artifact_spec

# Anchor "kinds" the artifact rung emits (see artifact_rung.resolve_anchor). Kept as
# constants so the scorer and the resolver never drift on the string.
ANCHOR_OBJECTIVE = "objective"
ANCHOR_TEKS = "teks"
ANCHOR_NONE = "none"

ALIGNMENT_PREAMBLE = (
    "You are a curriculum alignment auditor. READ-ONLY. You judge only whether the "
    "ARTIFACT below serves the stated ANCHOR (the lesson's objective or standard). "
    "You NEVER rewrite content and you NEVER assert whether any student answer is "
    "correct — you audit alignment, not correctness. For every band you MUST quote a "
    "verbatim excerpt from the ARTIFACT elements and give its id; if nothing supports "
    "a criterion, assign band 0 with an empty quote. An honest 0 is correct."
)


# --- deterministic presence (Phase 1) ---------------------------------------


class PresenceScorer(Scorer):
    scorer_id = "artifact_presence"
    name = "Artifact presence gate (deterministic, per-type spec)"

    def score(self, artifact: ArtifactInput, cfg: dict | None = None) -> ScorerResult:
        spec, is_fallback = load_artifact_spec(artifact.doc_type)
        res = presence_result(artifact, spec, self.scorer_id)
        # Carry the spec's identity forward so the rung can group by role, drive the
        # feedback nursery for unknown types, and cite which spec judged the doc.
        res.summary["role"] = spec.get("role", artifact.doc_type or "other")
        res.summary["spec_id"] = spec["rubric_id"]
        res.summary["is_fallback"] = is_fallback
        res.summary["nursery"] = bool(spec.get("nursery")) or is_fallback
        return res


# --- model alignment (Phase 2, advisory) ------------------------------------


def _alignment_candidates(artifact: ArtifactInput, align: dict) -> list:
    """Elements the alignment rubric may cite: the union of every criterion's
    reads_from types (fallback to all elements), capped so the prompt stays bounded."""
    wanted: set[str] = set()
    for c in align.get("criteria", []):
        wanted.update(c.get("reads_from") or [])
    els = artifact.elements_of_type(*wanted) if wanted else list(artifact.elements)
    if not els:
        els = list(artifact.elements)
    return els[:40]


def _build_alignment_prompt(
    artifact: ArtifactInput, align: dict, anchor: dict, candidates: list
) -> str:
    scale = "\n".join(f"  {k}: {v}" for k, v in (align.get("band_scale") or {}).items())
    crit_block = "\n".join(
        f"- {c['id']}: {c.get('label', c['id'])} — {c.get('description', '').strip()}"
        for c in align["criteria"]
    )
    cand_block = (
        "\n\n".join(
            f'[{el.element_id}] ({el.element_type})\n"""\n{(el.excerpt or "")[:600]}\n"""'
            for el in candidates
        )
        or "(no candidate elements for this artifact)"
    )
    ids = ", ".join(c["id"] for c in align["criteria"])
    anchor_kind = "objective" if anchor.get("kind") == ANCHOR_OBJECTIVE else "standard (TEKS)"
    return f"""{ALIGNMENT_PREAMBLE}

ANCHOR ({anchor_kind}) — the target this artifact should serve:
\"\"\"
{(anchor.get('text') or '').strip()[:800]}
\"\"\"

RUBRIC: {align.get('title', 'artifact alignment')}
BAND SCALE:
{scale}

CRITERIA to score (one band each):
{crit_block}

ARTIFACT: {artifact.title} (type: {artifact.doc_type})
ARTIFACT ELEMENTS (cite by id):
{cand_block}

Respond with ONLY valid JSON (no markdown fences):
{{
  "scores": [
    {{"criterion_id": "<one of: {ids}>", "band": <int>,
      "evidence_element_id": "<id from artifact elements, or empty>",
      "evidence_quote": "<verbatim excerpt from that element, or empty>",
      "note": "<one short sentence: what aligns or what is off-target>"}}
  ]
}}
One entry per criterion above."""


class AlignmentScorer(Scorer):
    scorer_id = "artifact_alignment"
    name = "Artifact alignment audit (model, advisory, evidence-bound)"

    def score(self, artifact: ArtifactInput, cfg: dict | None = None) -> ScorerResult:
        spec, _ = load_artifact_spec(artifact.doc_type)
        align = spec.get("alignment")
        base = ScorerResult(
            scorer_id=self.scorer_id,
            rubric_id=spec["rubric_id"],
            rubric_version=spec["version"],
            scoring="band",
            lesson_id=artifact.lesson_id,
        )

        # This type has no alignment half (e.g. the generic fallback): nothing to
        # advise on, and we won't invent criteria. Honest empty, not an error.
        if not align:
            base.summary = {"advisory": True, "applicable": False}
            return base

        crits_spec = align["criteria"]
        max_band = max((align.get("band_scale") or {0: ""}).keys())

        def _flat(note: str) -> ScorerResult:
            base.criteria = [
                CriterionResult(c["id"], c.get("label", c["id"]), "band", note=note)
                for c in crits_spec
            ]
            return base

        # No anchor -> cannot assess alignment. This is a real, honest signal that the
        # rung rolls UP as a lesson-level gap (the lesson has no objective/standard).
        anchor = artifact.anchor or {"kind": ANCHOR_NONE}
        if anchor.get("kind") == ANCHOR_NONE or not (anchor.get("text") or "").strip():
            res = _flat("cannot assess alignment — lesson lacks an objective/standard")
            res.summary = {"advisory": True, "applicable": True, "cannot_assess": True}
            return res

        # Offline / no model config -> advisory simply not produced this run.
        if cfg is None:
            res = _flat("skipped — model offline (advisory)")
            res.error = "no model config (offline) — alignment advisory skipped"
            res.summary = {"advisory": True, "applicable": True, "skipped": True}
            return res

        candidates = _alignment_candidates(artifact, align)
        valid_ids = {el.element_id: el for el in candidates}
        prompt = _build_alignment_prompt(artifact, align, anchor, candidates)
        try:
            from layer1 import call_and_parse_with_retry

            data = call_and_parse_with_retry(
                cfg,
                "analyst",
                prompt,
                f"artifact-align-{artifact.lesson_id}",
            )
        except Exception as e:  # noqa: BLE001 — any model/parse failure degrades cleanly
            res = _flat("error")
            res.error = f"model call failed: {e}"
            res.cost = {"model_calls": 1}
            res.summary = {"advisory": True, "applicable": True, "skipped": True}
            return res

        scored = {s.get("criterion_id"): s for s in (data.get("scores") or [])}
        crits: list[CriterionResult] = []
        for c in crits_spec:
            s = scored.get(c["id"]) or {}
            band = s.get("band")
            band = int(band) if isinstance(band, (int, float)) else None
            eid = (s.get("evidence_element_id") or "").strip()
            quote = (s.get("evidence_quote") or "").strip()
            note = (s.get("note") or "").strip()
            evidence: list[Evidence] = []
            # Trust a band only if it cites a real candidate id + quote; otherwise
            # downgrade to needs-review (never invent authority) — same guard the
            # lesson band scorers use.
            if eid in valid_ids and quote:
                evidence = [Evidence(eid, quote)]
            elif band:
                note = (note + " ").strip() + "[unevidenced band — needs review]"
            crits.append(
                CriterionResult(
                    c["id"], c.get("label", c["id"]), "band",
                    band=band, evidence=evidence, note=note,
                )
            )
        base.criteria = crits
        base.summary = {
            **summarize_bands(crits, max_band=max_band),
            "advisory": True,
            "applicable": True,
            "anchor_kind": anchor.get("kind"),
        }
        base.cost = {"model_calls": 1}
        return base


register_scorer(PresenceScorer)
register_scorer(AlignmentScorer)
