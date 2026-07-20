# Lesson rung — method bake-off & locked decision

The lesson rung is the bottom of the curriculum waterfall (lesson → unit →
curriculum). Its job: judge whether an individual lesson is complete, coherent,
and well written — with every judgment tied to verbatim evidence, never inventing
content (Bet 5 / Bet 8, `docs/STRUCTURAL-FILL.md`).

Rather than assume one review method, we ran a **bake-off**: several *reused*
rubrics as pluggable scorers over already-decomposed lessons, compared against a
small hand-seeded gold set. This document records what we ran and what we locked.

## The methods compared (`lesson_scorers.py`, rubrics in `workflows/rubrics/`)

| Id | Method | Rubric (reused from) | Scoring | Cost |
|----|--------|----------------------|---------|------|
| S1 | Completeness gate | 8 instructional-function parts = Hunter cycle + CTAT/NW ISD (`completeness_core8.yaml`) | presence | free (deterministic) |
| S2 | UbD alignment | Wiggins & McTighe backward design (`ubd_alignment.yaml`) | band 0–3 | 1 model call/lesson |
| S3 | Curriculum's own | the project's own template (Dallas → CTAT/NW ISD; `curriculum_own/<project>.yaml`) | presence | free (deterministic) |
| S4 | LLM-as-judge quality | EQuIP + Danielson D1/D3 + 5E (`quality_dimensions.yaml`) | band 0–3 | 1 model call/lesson |

Every scorer emits the same evidence-cited shape (`lesson_scoring.py`) and every
non-absent verdict/band **must cite a verbatim excerpt** from the lesson's own
Layer 0 elements — an uncited band is downgraded to *needs-review*, never trusted.

## How they were compared

`lesson_bakeoff.py` scores every lesson with each method, normalizes each to a
0–1 signal (presence → coverage; band → mean band ÷ max), and reports:
- per-lesson scores by method,
- a **divergence** (max−min across methods) human-look queue,
- **model cost**, and
- **agreement with a hand-seeded gold set** (`layer_lesson/GOLD-LESSON.json`) as
  mean absolute error — the number that picks the winner.

Gold was bootstrap-seeded (agent read the actual lesson content, grounded each
score) and is explicitly marked `provisional` / `needs_confirmation` — an SME
should confirm/correct before treating the ranking as final.

## Result (Dallas, 7-lesson provisional gold)

| Method | Mean abs error | Within tolerance | Notes |
|--------|----------------|------------------|-------|
| **S1 completeness** | **~0.07** | 5/7 | closest to gold, free, always available |
| **S3 curriculum's own** | **~0.07** | 6/7 | ties S1, adds the district's own bar |
| S2 UbD (model) | — | — | local model returned **uncited** bands → auto-downgraded |
| S4 quality (model) | — | — | same: evidence citation unreliable on this model |

Re-run any time with `python3 lesson_bakeoff.py --project <p> --with-model`.

## Decision (locked)

The locked lesson rung is the **two deterministic, evidence-cited scorers**:
**S1 completeness** (the subject-agnostic gate) **+ S3 curriculum's-own** (the
per-project bar, when the project ships a rubric). Rationale:

- They matched the provisional gold as closely as anything, at **zero model cost**.
- They are fully **evidence-cited and reproducible** — no model variance.
- The model methods (S2/S4) did **not** clear the bar on the current local model:
  it assigned bands without citing evidence, exactly the failure the auditor guard
  exists to catch. They stay implemented and re-runnable, but out of the locked
  rung until a model that cites reliably is available.

This is codified in `lesson_rung.py` (`LOCKED_SCORERS`, `GATE_SCORER`).

## What the rung emits (feeds the unit rung)

`lesson_rung.py` runs the locked scorers over every lesson — including per-lesson
children fanned out of multi-lesson Teacher Editions by `te_prepass.py` — and
writes `layer_lesson/LESSON-RUNG.json` (+ `.md`): per-lesson gate/coverage plus a
**per-unit rollup** (lesson count, gate-pass rate, mean coverage per method). That
rollup is the stable handoff the future **unit rung** consumes to compose
Introduced/Practiced/Assessed coverage and unit coherence. Runs in the pipeline
after Layer 2 (`run_project.py`), offline, with no model calls.
