# Path C — General artifact review (worksheet / rubric / project / slides / unknown)

Entry: the Loom router typed the document as `general` — worksheets, rubrics,
projects, presentations, and any unknown/`other` type. Path C is no longer a stub: it
runs the SAME artifact engine as Path B (`artifact_rung.score_artifacts`) over its
routed docs. Known roles get their per-type spec; unknown types get the generic
fallback and are logged to the feedback nursery.

## How it works

Identical two-scorer engine to Path B (see `docs/PATH-B-QUIZ.md`):

- **Presence** (deterministic, GATES): per-type spec decides PRESENT / PARTIAL /
  MISSING from Layer 0 elements + keywords; `gate_pass` gates the unit band.
- **Alignment** (model, `--with-model`, advisory): objective/TEKS-anchored, evidence-
  bound, auditor-only. "Cannot assess" when the unit's lesson has no anchor.

## Graceful degradation + feedback nursery

- Unknown/`other` types resolve to `workflows/rubrics/artifacts/_fallback.yaml`,
  which makes the one universal claim we can always defend (the doc has extractable
  instructional content) and has **no** alignment block (we won't fake a judgment for
  an unknown type).
- Every fallback doc is appended to the project's `_loom_feedback.yaml` — the "grow a
  dedicated Path" signal. Adding `workflows/rubrics/artifacts/<type>.yaml` promotes
  the type out of the nursery with **zero engine code changes** (curriculum-agnostic
  by construction).

## Specs (per role)

- `rubric.yaml` — named criteria + performance levels; criteria assess the objective.
- `worksheet.yaml` — practice tasks present; aligned (Gradual Release "you do").
- `project_work.yaml` — task/deliverable described; authentically applies the objective.
- `presentation.yaml` — instructional content present; serves the objective.
- `_fallback.yaml` — generic inventory + feedback-log (nursery).

## Outputs (built)

- `path_c/findings.json` — a **superset** of the old stub: legacy `C1/C2/C3` keys
  (now backed by the real presence gate) plus per-doc `presence` / `alignment` records
  and a pointer to `layer_artifact/ARTIFACT-RUNG.json`.
- Project-level `_loom_feedback.yaml` entries for unknown types.
- Rolls into `layer_artifact/ARTIFACT-RUNG.json` → the unit rung + review UI.

## Decision record

- **Job**: alignment audit (serve the objective; does the unit have its pieces).
- **Correctness**: auditor-only — never assert answers are right.
- **Gating**: deterministic presence/expected-role gaps GATE; model alignment ADVISES.
- **Placement**: unified on the `Scorer`/rubric framework; the router paths just select
  which docs to score — the stub string-matching logic was retired.
