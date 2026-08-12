---
type: grilling
blocked_by:
  - 03-pipeline-insert-slot
  - 04-promote-boundary
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:53:00Z
assets: []
---

# Project artifact and gate contract

## Question

For a project under `projects/<id>/`, what on-disk paths hold provisional/final HAS-PART, review findings, and scores; which gates are hard vs soft; and which `run_project` CLI flags (`--with-graph`, skip, force, `--only`) control the phase?

## Answer

HITL authorized recommended package (2026-08-02). Aligns with insert-slot decision: writes only under `projects/<id>/graph/`.

### On-disk layout (`projects/<id>/graph/`)

| Path | Role |
|------|------|
| `HAS-PART.provisional.json` | Gate A–passed materials inventory under unit |
| `HAS-PART.json` | Post-rebuild organization graph (final for the run) |
| `review-findings.json` | Batch rebuild input (`create_lessons`, `findings[]`, spine) |
| `.raw/<source_stem>.json` | Per-doc flat log: provisional_choice / rebuild_choice (+ narrow-step raw if kept) |
| `SUMMARY.json` | Optional phase telemetry (not a synthesize input on first merge) |

Per-unit nesting (recommended when multi-unit): `graph/units/<unit_id>/…` with the same filenames. Single-unit projects may write flat under `graph/` **or** always use `units/<id>/` for consistency — **prefer always `graph/units/<unit_id>/`**.

**Scores:** do **not** write gold scores into the production tree by default. `score_haspart` stays experiment-only; no `score_final.json` gate in `run_project` on first merge.

### Gates

| Gate | Hard / soft | Effect |
|------|-------------|--------|
| Gate A (every unit document → Material; no orphan sources in the unit slice) | **Hard** | Unit graph fails; phase non-zero |
| Soft-queue (Material with no Lesson yet) | **Soft** | Review order only; do not invent Lessons |
| Gold / `pass_provisional` | **Off** (first merge) | Dev-only via experiment runners |
| Downstream require graph | **Off** | route / L1 / L2 / calendars ignore graph |

### CLI (`run_project.py`)

| Flag | Behavior |
|------|----------|
| `--with-graph` | Opt-in: run graph phase after Layer 0-B, before route |
| (default) | Graph skipped |
| `--only UNIT` | When graph on, only that unit |
| `--force` | Existing meaning (rollup); **also** re-run graph overwrite for scoped units when `--with-graph` |
| No `--skip-graph` needed | Default is already skip |

Phase script recommendation: `graph_phase.py --project <id> [--only-unit …] [--force]`.
