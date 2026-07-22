#!/usr/bin/env python3
"""
rubrics.py — load + validate the versioned lesson-evaluation rubrics that the
lesson-rung bake-off scorers consume (see workflows/rubrics/*.yaml).

Design discipline (mirrors layer2.LAYER2_TAXONOMY_VERSION): a rubric is a
VERSIONED DATA INPUT, never hardcoded logic. Each rubric declares a `scoring`
mode the scorer honors:
  - "presence": each criterion is PRESENT / PARTIAL / MISSING (deterministic).
  - "band":     each criterion gets a 0-N band and MUST cite verbatim evidence.

The curriculum's-own rubric is per-project: workflows/rubrics/curriculum_own/
<project_id>.yaml. When a project has none, the harness falls back to the
subject-agnostic completeness gate so it never hard-fails on a new corpus.
"""

from __future__ import annotations

from pathlib import Path

from audit_lib import load_yaml

BASE = Path(__file__).resolve().parent
RUBRICS_DIR = BASE / "workflows" / "rubrics"
CURRICULUM_OWN_DIR = RUBRICS_DIR / "curriculum_own"
# Per-artifact-type review specs (Paths B/C). One YAML per universal role, keyed by
# doc_type; unknown types fall back to _fallback.yaml so a new corpus never crashes.
ARTIFACTS_DIR = RUBRICS_DIR / "artifacts"
ARTIFACT_FALLBACK = "_fallback"

# The scorers reference these by id; kept explicit so a typo fails loudly rather
# than silently skipping a method in the bake-off.
COMPLETENESS_RUBRIC = "completeness_core8"
UBD_RUBRIC = "ubd_alignment"
QUALITY_RUBRIC = "quality_dimensions"

VALID_SCORING = {"presence", "band"}


class RubricError(ValueError):
    """A rubric file is missing or malformed — surfaced loudly, never swallowed."""


def _validate(rubric: dict, source: Path) -> dict:
    """Fail fast on the handful of invariants every scorer relies on, so a bad
    edit to a YAML is caught at load time with a pointer to the file, not as a
    confusing KeyError deep inside a scorer."""
    for key in ("version", "rubric_id", "scoring", "criteria"):
        if not rubric.get(key):
            raise RubricError(f"{source}: missing required key '{key}'")
    if rubric["scoring"] not in VALID_SCORING:
        raise RubricError(
            f"{source}: scoring '{rubric['scoring']}' not in {sorted(VALID_SCORING)}"
        )
    if not isinstance(rubric["criteria"], list) or not rubric["criteria"]:
        raise RubricError(f"{source}: 'criteria' must be a non-empty list")
    seen: set[str] = set()
    for c in rubric["criteria"]:
        cid = c.get("id")
        if not cid:
            raise RubricError(f"{source}: a criterion is missing 'id'")
        if cid in seen:
            raise RubricError(f"{source}: duplicate criterion id '{cid}'")
        seen.add(cid)
    if rubric["scoring"] == "band" and not rubric.get("band_scale"):
        raise RubricError(f"{source}: band-scored rubric must define 'band_scale'")
    return rubric


def load_rubric(rubric_id: str) -> dict:
    """Load + validate one shared rubric by id (filename without .yaml)."""
    path = RUBRICS_DIR / f"{rubric_id}.yaml"
    if not path.is_file():
        raise RubricError(f"no rubric '{rubric_id}' at {path}")
    return _validate(load_yaml(path) or {}, path)


def load_curriculum_own(project_id: str) -> dict | None:
    """The project's own-template rubric (scorer S3), or None if it has none yet
    (harness then falls back to the completeness gate — graceful, not a crash)."""
    path = CURRICULUM_OWN_DIR / f"{project_id}.yaml"
    if not path.is_file():
        return None
    return _validate(load_yaml(path) or {}, path)


def _validate_alignment(spec: dict, source: Path) -> None:
    """An artifact spec MAY carry an optional `alignment` block (the model, advisory
    half of the review). When present it must be a well-formed band rubric so the
    AlignmentScorer can trust it — same discipline as the shared band rubrics."""
    align = spec.get("alignment")
    if align is None:
        return
    if not align.get("band_scale"):
        raise RubricError(f"{source}: alignment block must define 'band_scale'")
    crits = align.get("criteria")
    if not isinstance(crits, list) or not crits:
        raise RubricError(f"{source}: alignment.criteria must be a non-empty list")
    seen: set[str] = set()
    for c in crits:
        cid = c.get("id")
        if not cid:
            raise RubricError(f"{source}: an alignment criterion is missing 'id'")
        if cid in seen:
            raise RubricError(f"{source}: duplicate alignment criterion id '{cid}'")
        seen.add(cid)


def load_artifact_spec(doc_type: str) -> tuple[dict, bool]:
    """Load the per-type review spec for a non-lesson artifact by its universal role
    (doc_type). Returns (spec, is_fallback). Unknown/`other` types resolve to the
    generic `_fallback.yaml` so any curriculum flows through with zero new code — the
    fallback also drives the feedback nursery (see artifact_rung). The presence half
    is validated as a normal presence rubric; the optional alignment half is checked
    too so a malformed spec fails at load, not mid-run."""
    name = (doc_type or "").strip() or ARTIFACT_FALLBACK
    path = ARTIFACTS_DIR / f"{name}.yaml"
    # A type is "fallback" (-> nursery) when it has no dedicated spec, OR when it is
    # the catch-all/empty type itself. Either way it should grow a future Path.
    is_fallback = name == ARTIFACT_FALLBACK
    if not path.is_file():
        path = ARTIFACTS_DIR / f"{ARTIFACT_FALLBACK}.yaml"
        is_fallback = True
    if not path.is_file():
        raise RubricError(f"no artifact spec for '{doc_type}' and no _fallback at {path}")
    spec = _validate(load_yaml(path) or {}, path)
    _validate_alignment(spec, path)
    return spec, is_fallback


def list_artifact_specs() -> list[str]:
    """doc_types that have a dedicated spec (excludes the leading-underscore fallback)."""
    if not ARTIFACTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in ARTIFACTS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def list_rubrics() -> list[str]:
    """Rubric ids available in the shared dir (excludes per-project own rubrics)."""
    if not RUBRICS_DIR.is_dir():
        return []
    return sorted(p.stem for p in RUBRICS_DIR.glob("*.yaml"))


def criteria_ids(rubric: dict) -> list[str]:
    return [c["id"] for c in rubric.get("criteria", [])]
