# CTE graph sort spike — cattle + external anatomy

**Isolated from production.** Does not modify `graph_phase.py` or Bluebonnet TE/SE roles.

## Hypothesis

Full Layer 0 evidence → two model steps (type, then connect) can sort CTE
lesson packs into Course → Unit → Lesson → typed Material/Assessment, so
`view-lesson-plan` becomes `artifact_kind=lesson_plan` (Path A), not teacher edition —
**and two units in one course do not mangle** (no cross-unit edges / foreign attachments).

Evidence packing matches **production local** `graph_phase` intent: **uncapped**
Layer 0 excerpts, fresh context per document/step. When ledger rows repeat
the same wide-span text N×, the spike collapses to unique uncapped excerpts
(full doc once) so the Grok bridge does not hang — information-equivalent to
production, without 39× paste. Path letter is Python-only (`kind → Path`).
Pass 1 prompt is CTE-only (no Bluebonnet TE/SE labels) with disambiguation
for Action Plan / Key Concepts / projects.

## Units

1. `breeds-of-livestock-cattle` (023)
2. `external-anatomy-of-livestock-terms-terminology` (027)

Each unit gets its own Pass 1 / spine / Pass 2 with an **isolated** inventory and spine.

## Contract

| Check | Pass |
|-------|------|
| Both unit nodes present | yes |
| Each unit: real `Lesson` nodes | ≥1 |
| Each unit: `view-lesson-plan.html` kind | `lesson_plan` → Path **A** |
| Lesson ids namespaced | `lesson:{unit_id}:lN` |
| No cross-unit edges | yes |
| No foreign lesson attachments | yes |
| No Bluebonnet `teacher_edition` roles | kinds only |
| Gold Path matrix (`EXPECTED-PATHS.json`) | all docs match kind→Path |

## Run

```bash
cd /home/lenovo/g10-control-center-loom
# Grok (baseline)
LOOM_CONFIG=config.grok.yaml python3 tools/spike_graph_cte.py
# Local Nemotron (parity check)
LOOM_CONFIG=config.yaml python3 tools/spike_graph_cte.py
# Rescore latest without model calls:
python3 tools/spike_graph_cte.py --score-only
```

Outputs under `graph/spike-<timestamp>/` — course `HAS-PART.json`, per-unit `units/<id>/`, `SPIKE-RESULT.md`, `anti-mangle.json`, `PATH-SCORE.md`.

## Latest run

**Grok + improved Pass 1 prompt** — `graph/spike-20260811T195904Z/`

- Anti-mangle: **PASS**
- Path gold: **22/22 PASS**
- Action Plans → E; View Lesson Plans → A
- Parity with local prompt-v2 run `spike-20260811T193809Z`
