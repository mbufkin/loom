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

## Two axes, held apart (why every unit used to read "Weak")

A unit carries **two independent verdicts** that must never be conflated:

1. **QUALITY** — "how good is the material that IS here?" — the `band` (below).
2. **COMPLETENESS / INVENTORY** — "what kind of packet is this, and how whole is it
   *for that kind*?" — the `completeness` profile (next section).

Collapsing these into one band is what made every Dallas unit read Weak: a
curriculum-wide design choice (e.g. "this Teacher Edition ships no formal exit
tickets") was being treated as a per-unit quality defect and smeared across all 18
units. Systemic role gaps and pacing thinness describe the *shape* of the packet,
not the *quality* of its lessons, so they now live only on the completeness axis.

## The band (QUALITY only, deterministic, tunable)

A pure function `unit_band()` decides Strong / Developing / Weak / Unrated from the
assembled metrics. Constants live at the top of `unit_rung.py`:

- **Weak** — `gate_pass_rate < 0.34` (fewer than ⅓ of the unit's own lessons clear
  the completeness gate). Nothing else forces Weak.
- **Strong** — `gate_pass_rate >= 0.67` AND mean gate coverage `>= 0.70` AND no
  structurally-incomplete artifact (`has_artifact_gap`, e.g. a quiz with no items).
- **Developing** — anything in between.
- **Unrated** — no lessons were found for the unit. We refuse to call an unmeasured
  unit "Weak" (that would be a fabricated judgment); its thinness shows up on the
  completeness axis + pacing flag instead.

Deliberately **not** band inputs (they are inventory, not quality):
- **Systemic role gaps** — surfaced once in the "decide once" patterns panel and in
  each unit's `systemic_absent` list. They never force Weak.
- **Pacing under-coverage** — shown descriptively; it no longer blocks Strong. (A
  thin-but-good Teacher Edition unit can be Strong on quality yet 1/3 on inventory.)

Pacing is `UNDER_COVERED` when days-with-evidence fall below 80% of planned days
(e.g. 6 evidence days in a 10-day module).

> **Follow-up (documented, not yet built):** how pacing is *presented* still needs a
> rethink — it currently reads as a defect even for packet types that never ship a
> day-by-day plan. It should render as part of the inventory profile, interpreted in
> light of the declared packet type. Tracked for a future pass.

## Completeness axis — declared packet type (`packet_types.py`)

Completeness is measured against a **declared** curriculum packet type (never
inferred): the human states `packet_type:` in the project manifest, and the unit is
scored against that type's checklist in `workflows/packet_types.yaml`
(`full_curriculum` / `teacher_edition` / `lesson_plans_only`, extensible via config).
Each checklist `component` lists the document roles (`any_of`) that satisfy it;
presence comes from the Layer 0 ledger classified by `audit_lib.classify_doc_type`.

Per unit this emits a `completeness` block: `{packet_type, label, short, present,
expected, components[], missing[]}` — **descriptive, never a grade**. A unit with no
ledger evidence reports `completeness: null` (honest "unknown", not `0/N`). An
undeclared/typo'd type degrades to the registry `default` rather than crashing.

The run-review site declares this at the "start point" (a segmented selector), which
persists to the manifest and regenerates this rung. The heatmap renders the two axes
as two chips: **Chip 1** (packet + completeness, descriptive) and **Chip 2** (the
quality band, which carries the row color).

## Output: `layer_unit/UNIT-RUNG.json` (+ `.md`)

Per unit: `band`, `completeness` (packet-type inventory profile), `lessons`
(count/gate-pass/coverage), `roles` (fulfilled/missing, `systemic_absent`, capped
`isolated_gaps`), `pacing`, `internal`, and a `cites` block pointing back at the
source artifacts. The top-level `packet_type` records the declared type + its
expected components, and `summary.band_counts` is the stable hand-off the curriculum
rung will read — exactly as the lesson rung's per-unit rollup fed this rung.

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
