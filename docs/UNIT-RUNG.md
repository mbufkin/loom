# Unit rung — deterministic roll-up

The unit rung is the middle of the curriculum waterfall (lesson -> unit ->
curriculum). Its job: give each unit one honest, evidence-cited verdict by
composing signals the pipeline already computed, with no new model calls and
nothing invented. It mirrors the locked lesson rung (`docs/LESSON-RUNG.md`) one
level up, and emits the artifact the future curriculum rung will consume.

Implemented in `unit_rung.py`; runs in the pipeline right after the lesson rung
(`run_project.py`), offline.

## What it judges (and where each signal comes from)

Everything below is deterministic and already on disk before the unit rung runs:

| Signal | Source artifact | Field |
|--------|-----------------|-------|
| Lesson completeness roll-up | `layer_lesson/LESSON-RUNG.json` | `units[uid]`: `gate_pass_rate`, `mean_coverage` |
| Role fulfillment + gap patterns | `synthesize.aggregate_layer1()` over `layer1/findings.json` | `unit_rollup` (fulfilled/missing), `missing_rollup` (systemic vs isolated) |
| Pacing fit | `pacing-plan.yaml` vs `calendars_inferred/INFERRED-CALENDARS.json` | planned `unit_length_days` vs days with `HAS_EVIDENCE` |
| Internal completeness | `layer2/findings.json` (doc -> unit via `manifest.yaml`) | how many lessons lack core parts |

Gap patterns reuse the noise-reduction rollup: a role missing across the whole
curriculum (`systemic_absent`) is an expectation mismatch, while a role missing in
just this unit (`isolated`) is a real localized gap. The unit rung inherits that
distinction so a systemic absence is not re-counted as a per-unit defect.

## The band (deterministic, tunable)

A pure function `unit_band()` decides Strong / Developing / Weak / Unrated from the
assembled metrics. Constants live at the top of `unit_rung.py`:

- **Weak** — `gate_pass_rate < 0.34` OR the unit has a `systemic_absent` role gap.
- **Strong** — `gate_pass_rate >= 0.67` AND mean gate coverage `>= 0.70` AND pacing
  is not `UNDER_COVERED` AND no systemic gap.
- **Developing** — anything in between.
- **Unrated** — no lessons were found for the unit. We refuse to call an unmeasured
  unit "Weak" (that would be a fabricated judgment); its thinness still shows up in
  the pacing flag instead.

Pacing is `UNDER_COVERED` when days-with-evidence fall below 80% of planned days
(e.g. 6 evidence days in a 10-day module).

## Output: `layer_unit/UNIT-RUNG.json` (+ `.md`)

Per unit: `band`, `lessons` (count/gate-pass/coverage), `roles` (fulfilled/missing,
`systemic_absent`, capped `isolated_gaps`), `pacing`, `internal`, and a `cites`
block pointing back at the source artifacts. The top-level `summary.band_counts` is
the stable hand-off the curriculum rung will read — exactly as the lesson rung's
per-unit rollup fed this rung.

## What it does NOT judge yet (deliberate)

These are absent from the pipeline today, so scoring them would repeat the model
quality-scorer mistake: asserting a judgment we cannot back with evidence.

- **Standards / TEKS coverage matrix.** We only have regex-scraped standards strings
  and a per-lesson "objective present?" flag — no structured standard list and no
  coverage map. A real standards rung needs structured extraction first.
- **Introduced / Practiced / Assessed progression.** Nothing tracks a skill across
  lessons; there is no spiral/prerequisite model to aggregate.
- **Rigor / DOK.** Not captured at the lesson level, so there is nothing to roll up.

Each is a separate workstream with its own infrastructure. When those land, the
unit rung is the natural place to aggregate them.
