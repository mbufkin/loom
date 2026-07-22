# Artifact alignment — deferred (do not surface as a claim yet)

**Status:** built, wired, and producing output — but intentionally **not** presented
as a verdict in the UI. Presence/completeness (deterministic) is the only artifact
signal we currently stand behind.

**Date:** 2026-07-21

## Why this note exists

Paths B/C now review non-lesson artifacts (exit tickets, quizzes, rubrics, worksheets,
projects, slides, …) via two scorers in `artifact_scorers.py`:

- **`PresenceScorer`** — deterministic. "Does this artifact have its structural parts?"
  (e.g. a rubric has named criteria + performance levels; a quiz has items + an answer
  key). Code-only, cited, reproducible. **We trust this and show it.**
- **`AlignmentScorer`** — model-based, advisory. "Does this artifact serve its lesson's
  objective / cited TEKS?" Emits a 0–3 band per criterion with cited evidence.

The alignment scorer works, but it is **not yet calibrated against a gold set**. On the
Dallas golden run every artifact came back `Not aligned` / `Absent` — largely because
those units are systemically missing lesson objectives/plans, so the anchor resolver has
nothing to align against (an honest signal, but a confusing one to display as a verdict).
Showing "Not aligned" badges reads as a strong, validated claim we can't back up today.

## Decision

Per the user (2026-07-21): *"for now we should not make a big claim — remove the badge,
document the work, and we can come back to it."*

So:

1. **Unit inventory row (`UnitDetail` → `DocRow`)** — the `Aligned / Partial / Not aligned`
   badge is **removed**. Rows show only document **type** + deterministic **completeness**
   status (`Complete` / `Missing <part>`).
2. **Per-doc drill-in (`ArtifactDetail`)** — alignment is no longer a headline section.
   The informational states (no criteria / cannot-assess / offline) remain as plain notes;
   the actual model band verdicts are tucked into a **collapsed, `experimental — not yet
   validated`** disclosure so a reviewer can peek but it never reads as a verdict.

**Nothing was deleted from the data path.** `ARTIFACT-RUNG.json` still carries the full
`alignment` block per document, so re-enabling display is a pure UI change.

## What it would take to promote alignment to a real claim

1. **Hand-score a gold set** of artifacts (objective-anchored) the way we did for the
   lesson quality rung — a handful per artifact type is enough to start.
2. **Calibrate** `AlignmentScorer` against it: measure band MAE and citation rate, and
   confirm it doesn't systematically under/over-score (the lesson-rung failure mode).
3. **Fix the anchor gap** first, or scope alignment to units that actually have an
   objective/TEKS — otherwise "no anchor" dominates and swamps the signal.
4. Once MAE + citation are acceptable, re-surface the badge and un-collapse the section.

## Where the code lives

| Concern | File |
| --- | --- |
| Scorers (presence + alignment) | `artifact_scorers.py` |
| Rung orchestration + anchor resolver | `artifact_rung.py` |
| Per-type presence/alignment specs | `workflows/rubrics/artifacts/*.yaml` (+ `_fallback.yaml`) |
| Row (badge removed here) | `ui/src/components/UnitDetail.tsx` (`DocRow`) |
| Drill-in (band verdicts collapsed here) | `ui/src/components/ArtifactDetail.tsx` (`renderAlignment`) |

## Re-enable checklist (fast path)

- [ ] Restore the `alignBadge` helper + badge render in `DocRow` (see git history for this commit).
- [ ] Change the `experimental-block` disclosure in `ArtifactDetail` back to an open `<h4>` section.
- [ ] Only after the calibration steps above pass.
