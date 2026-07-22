# Path B — Assessment artifact review (quiz / exit ticket / answer key)

Entry: the Loom router typed the document as an assessment (`quiz`, `exit_ticket`,
`answer_key`). Path B is no longer a stub — it runs the shared, curriculum-agnostic
**artifact engine** (`artifact_rung.score_artifacts`) over just its routed docs, so
the review is real and identical in shape to Path C and the artifact rung.

## How it works

Each doc is scored by two reused scorers (`artifact_scorers.py`), both built on the
document-agnostic `Scorer`/`Evidence` schema in `lesson_scoring.py`:

| Half | Scorer | Gates? | What it does |
|------|--------|--------|--------------|
| Presence | `PresenceScorer` (deterministic) | **GATES** | Reads the per-type spec (`workflows/rubrics/artifacts/<role>.yaml`) and decides PRESENT / PARTIAL / MISSING for each structural part from the doc's own Layer 0 element types + keywords. No model call. `gate_pass` (all required parts present) is the signal the unit rung hard-gates on. |
| Alignment | `AlignmentScorer` (model, `--with-model`) | advises only | Judges whether the artifact serves the unit's **anchor** (lesson objective → cited TEKS → "cannot assess") with **evidence-bound** citations. Auditor-only. |

## Auditor-only (locked decision)

- Items **exist**, an answer key is **present**, and items **map** to the objective/TEKS.
- We **never** assert whether an answer is correct — that would invent domain truth.
- An uncited alignment band is downgraded to needs-review (never trusted).

## Anchor + no-anchor fallback

The anchor is the unit's lesson objective, falling back to a cited TEKS/standard, and
if neither exists the alignment emits **"cannot assess alignment"**, which rolls up as
a lesson-level gap (the lesson lacks an objective/standard).

## Specs (per role)

- `exit_ticket.yaml` — Black & Wiliam formative: prompt present; aligned + actionable.
- `quiz.yaml` — items present; map to objective/TEKS; DOK spread (auditor-only).
- `answer_key.yaml` — key present and covers the items (coverage, not correctness).

## Outputs (built)

- `path_b/findings.json` — a **superset** of the old stub: legacy `B1/B2/B3` keys
  (now backed by the real presence gate) plus the full per-doc `presence` /
  `alignment` records and a pointer to `layer_artifact/ARTIFACT-RUNG.json`.
- Rolls into `layer_artifact/ARTIFACT-RUNG.json` → the unit rung (gating) and the
  review UI (per-doc drill-down).
- Docs routed to Path B but not yet decomposed are emitted as honest
  `NOT_DECOMPOSED` placeholders (never silently dropped).
