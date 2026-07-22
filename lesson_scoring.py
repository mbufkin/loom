#!/usr/bin/env python3
"""
lesson_scoring.py — common lesson-evaluation schema + pluggable scorer interface
for the lesson-rung bake-off.

Every scoring METHOD (S1 completeness gate, S2 UbD alignment, S3 curriculum's-own
rubric, S4 LLM-as-judge quality) reads the SAME LessonInput and emits the SAME
ScorerResult shape, so the harness can run them side by side and compare. Two
non-negotiable rules, enforced by the schema:

  1. Auditor-only. A scorer reports what IS or ISN'T there; it never authors,
     rewrites, or suggests lesson content (Bet 8 / docs/STRUCTURAL-FILL.md).
  2. Evidence-bound. Any non-absent verdict/band must carry >=1 verbatim cited
     excerpt from the lesson's own Layer 0 elements. A judgment with no evidence
     is invalid and is reported as needs-review, never as a confident score
     (Bet 5: never invent).

The result objects are plain, JSON-serializable dataclasses so the harness can
write one combined artifact per lesson and diff methods against a gold set.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

# Presence verdicts (for scoring == "presence" rubrics).
PRESENT = "PRESENT"
PARTIAL = "PARTIAL"
MISSING = "MISSING"
PRESENCE_VERDICTS = {PRESENT, PARTIAL, MISSING}


@dataclass
class Evidence:
    """One verbatim citation backing a verdict/band — element_id + the quote."""

    element_id: str
    excerpt: str

    def to_dict(self) -> dict:
        # Excerpts can be long; cap for the artifact but keep enough to verify.
        return {"element_id": self.element_id, "excerpt": (self.excerpt or "")[:400]}


@dataclass
class LessonElement:
    """A lesson's Layer 0 element, trimmed to what scorers actually read."""

    element_id: str
    element_type: str
    excerpt: str


@dataclass
class LessonInput:
    """Everything a scorer is allowed to look at for ONE lesson. Built by the
    harness from Layer 0 elements (+ optional Path A findings); scorers must not
    reach outside it (keeps every method reading the same evidence)."""

    project_id: str
    lesson_id: str  # doc_id — the lesson atom
    unit_id: str
    title: str
    elements: list[LessonElement] = field(default_factory=list)
    path_a: dict | None = None
    # Optional artifact-review context, ignored by the lesson scorers. `doc_type`
    # selects the per-type artifact spec (workflows/rubrics/artifacts/<type>.yaml)
    # and `anchor` is the alignment target (the unit's objective/TEKS) resolved by
    # the artifact rung. Kept on this dataclass so the SAME Scorer interface serves
    # both lessons and non-lesson artifacts — `ArtifactInput` below is an alias.
    doc_type: str = ""
    anchor: dict | None = None
    # Project-relative path to the raw source text (e.g. "sources/doc_…txt"). Pure
    # metadata (never scored) — carried so the review UI can show the actual document
    # beneath a per-doc review, like the lesson source panel.
    source_file: str | None = None

    def element_types(self) -> set[str]:
        """Every instructional-function token present across this lesson (handles
        the legacy pipe-joined compound values the same way layer2._element_types
        does, so a lesson is never unfairly judged for a since-fixed Layer 0 bug)."""
        out: set[str] = set()
        for el in self.elements:
            out.update(t for t in (el.element_type or "").split("|") if t)
        return out

    def elements_of_type(self, *types: str) -> list[LessonElement]:
        wanted = set(types)
        return [
            el
            for el in self.elements
            if wanted & {t for t in (el.element_type or "").split("|") if t}
        ]


@dataclass
class CriterionResult:
    """One rubric criterion's outcome for one lesson. Exactly one of `verdict`
    (presence rubrics) or `band` (band rubrics) is set; `evidence` backs it."""

    criterion_id: str
    label: str
    scoring: str  # "presence" | "band"
    verdict: str | None = None  # PRESENT/PARTIAL/MISSING
    band: int | None = None  # 0..N
    evidence: list[Evidence] = field(default_factory=list)
    note: str = ""

    def is_evidenced(self) -> bool:
        return bool(self.evidence)

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id,
            "label": self.label,
            "scoring": self.scoring,
            "verdict": self.verdict,
            "band": self.band,
            "evidence": [e.to_dict() for e in self.evidence],
            "note": self.note,
        }


@dataclass
class ScorerResult:
    """One scorer's full output for one lesson: per-criterion results + a small
    summary the harness compares across methods + model-cost accounting."""

    scorer_id: str
    rubric_id: str
    rubric_version: str
    scoring: str
    lesson_id: str
    criteria: list[CriterionResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    cost: dict = field(default_factory=lambda: {"model_calls": 0})
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "scorer_id": self.scorer_id,
            "rubric_id": self.rubric_id,
            "rubric_version": self.rubric_version,
            "scoring": self.scoring,
            "lesson_id": self.lesson_id,
            "criteria": [c.to_dict() for c in self.criteria],
            "summary": self.summary,
            "cost": self.cost,
            "error": self.error,
        }


class Scorer(ABC):
    """Pluggable lesson-scoring method. Subclasses set `scorer_id` / `name` and
    implement score(). The harness treats every scorer identically."""

    scorer_id: str = "base"
    name: str = "Base scorer"

    @abstractmethod
    def score(
        self, lesson: LessonInput, cfg: dict | None = None
    ) -> ScorerResult:  # pragma: no cover
        # cfg is the loaded model config; deterministic scorers ignore it, band
        # scorers use it (and degrade gracefully to an errored result when it's None).
        raise NotImplementedError


# --- registry ---------------------------------------------------------------
# A tiny registry so the harness can enumerate methods by id and a new scorer is
# one decorator away — no orchestration edits (same spirit as reports.REPORTS).
_REGISTRY: dict[str, Callable[[], Scorer]] = {}


def register_scorer(factory: Callable[[], Scorer]) -> Callable[[], Scorer]:
    """Register a zero-arg factory that builds a Scorer. Keyed by the built
    scorer's scorer_id so ids stay the single source of truth."""
    inst = factory()
    if inst.scorer_id in _REGISTRY:
        raise ValueError(f"duplicate scorer_id {inst.scorer_id!r}")
    _REGISTRY[inst.scorer_id] = factory
    return factory


def build_scorer(scorer_id: str) -> Scorer:
    if scorer_id not in _REGISTRY:
        raise KeyError(f"unknown scorer {scorer_id!r} — known: {sorted(_REGISTRY)}")
    return _REGISTRY[scorer_id]()


def available_scorers() -> list[str]:
    return sorted(_REGISTRY)


def summarize_presence(criteria: list[CriterionResult]) -> dict:
    """Shared summary for presence-scored methods: counts + a gate boolean the
    harness can compare across methods without knowing each rubric's internals."""
    present = sum(1 for c in criteria if c.verdict == PRESENT)
    partial = sum(1 for c in criteria if c.verdict == PARTIAL)
    missing = sum(1 for c in criteria if c.verdict == MISSING)
    total = len(criteria) or 1
    return {
        "present": present,
        "partial": partial,
        "missing": missing,
        "coverage": round(present / total, 3),
    }


def summarize_bands(criteria: list[CriterionResult], max_band: int = 3) -> dict:
    """Shared summary for band-scored methods: mean band + how many lacked the
    required evidence (a transparency signal, not hidden)."""
    scored = [c.band for c in criteria if c.band is not None]
    unevidenced = sum(1 for c in criteria if c.band and not c.is_evidenced())
    mean = round(sum(scored) / len(scored), 2) if scored else 0.0
    return {
        "mean_band": mean,
        "max_band": max_band,
        "unevidenced_bands": unevidenced,
        "criteria_scored": len(scored),
    }


def presence_result(subject: LessonInput, rubric: dict, scorer_id: str) -> ScorerResult:
    """Generic deterministic presence scoring, shared by the lesson completeness
    scorers (S1/S3) and the artifact presence scorer. Each criterion is decided
    PRESENT / PARTIAL / MISSING from the subject's own Layer 0 element types, with a
    keyword excerpt match as a weaker PARTIAL signal. No model call — completeness is
    a fact, not a judgment (Bet 0). `subject` is any LessonInput/ArtifactInput.

    A criterion is PRESENT when an element carries one of its `evidence_element_types`;
    PARTIAL when only a `keywords` hit is found (content hinted but not tagged as the
    real structural part); MISSING otherwise. `required: true` criteria drive the
    `gate_pass` boolean a downstream rung can trust."""
    crits: list[CriterionResult] = []
    for c in rubric["criteria"]:
        etypes = c.get("evidence_element_types") or []
        keywords = [k.lower() for k in (c.get("keywords") or [])]
        label = c.get("label", c["id"])
        matched = subject.elements_of_type(*etypes) if etypes else []
        if matched:
            crits.append(
                CriterionResult(
                    c["id"],
                    label,
                    "presence",
                    verdict=PRESENT,
                    evidence=[Evidence(matched[0].element_id, matched[0].excerpt)],
                )
            )
            continue
        kw_hit = None
        if keywords:
            for el in subject.elements:
                ex = (el.excerpt or "").lower()
                if any(k in ex for k in keywords):
                    kw_hit = el
                    break
        if kw_hit is not None:
            crits.append(
                CriterionResult(
                    c["id"],
                    label,
                    "presence",
                    verdict=PARTIAL,
                    evidence=[Evidence(kw_hit.element_id, kw_hit.excerpt)],
                    note="keyword match only; no element tagged with the expected type",
                )
            )
        else:
            crits.append(CriterionResult(c["id"], label, "presence", verdict=MISSING))

    summary = summarize_presence(crits)
    by_id = {cr.criterion_id: cr for cr in crits}
    required = [c["id"] for c in rubric["criteria"] if c.get("required")]
    summary["required_total"] = len(required)
    summary["required_present"] = sum(
        1 for r in required if by_id[r].verdict == PRESENT
    )
    # The gate a downstream rung can trust: every REQUIRED part is present. The
    # labels of the required parts that are NOT fully present are the structural
    # gaps a rung can name to a reviewer (kept here so callers don't re-derive them).
    summary["gate_pass"] = all(by_id[r].verdict == PRESENT for r in required)
    summary["missing_required"] = [
        by_id[r].label for r in required if by_id[r].verdict != PRESENT
    ]
    return ScorerResult(
        scorer_id=scorer_id,
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["version"],
        scoring="presence",
        lesson_id=subject.lesson_id,
        criteria=crits,
        summary=summary,
        cost={"model_calls": 0},
    )


# `ArtifactInput` is the same shape as a lesson input — a doc's Layer 0 elements,
# its unit, plus the optional doc_type/anchor set for the artifact review. Aliased
# (not subclassed) so scorers and helpers accept either without isinstance games.
ArtifactInput = LessonInput
