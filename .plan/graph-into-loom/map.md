---
label: wayfinder:map
---

# Graph phase into Loom

## Destination

A locked **insertion + merge spec** that an implementer can follow: where the graph phase sits in `run_project.py`, what it may consume, what to promote from `experiments/graphing`, on-disk contracts/gates/CLI, and unit prerequisites — ready to hand off. Done when nothing material is left to decide before someone implements the merge. **This effort does not implant code.**

**Destination met:** handoff written at [`docs/GRAPH-PHASE.md`](../../docs/GRAPH-PHASE.md).

## Notes

- Domain: Loom core pipeline (`run_project.py` / layers) × proven graph loop in `experiments/graphing` (Bluebonnet G5 M1 slice + ledger-mini spike).
- Wayfinder: **plan, don't do** — produce decisions + research assets → handoff merge-spec. No `run_project` wiring in this map.
- HITL (2026-08-02): after insert-slot grilling, authorized **agent-recommended packages** for remaining tickets — document all choices, don’t micro-grill.
- Standing preferences already voiced:
  - Insert after Layer 0 evidence exists; graph answers belonging; Layer 2 answers structural completeness — complementary.
  - Prefer narrow-steps + `rebuild_multi`, not a parallel one-shot graph stack.
  - Out of this destination: live Grok/xAI API wiring and a full multi-module Bluebonnet corpus run.
- Skills: wayfinder; grilling / domain-modeling when resolving HITL tickets; research subagents for `wayfinder:research`.
- Tracker: local markdown under `.plan/graph-into-loom/`. Blocking via ticket frontmatter `blocked_by`.
- Prior art: [SPIKE.md](../../experiments/graphing/SPIKE.md), `experiments/graphing/graph_assemble.py`, prior map [Graph review rebuild spike](../graph-review-rebuild-spike/map.md).

## Decisions so far

- [Graphing experiment promote inventory](./tickets/02-graphing-promote-inventory.md) — Promote `graph_assemble` + spike loop gates/provisional/rebuild/raw contracts; keep P1×D and Bluebonnet runners, Grok gold slice, and ledger-mini heuristics experiment/fixture-only.
- [Loom pipeline dataflow for graph insert candidates](./tickets/01-loom-pipeline-dataflow.md) — Graph is ready after Layer 0-B (ledger + manifest unit documents + sources); preferred insert before `route.py`; gold and path/L1/L2 are not required inputs.
- [Pipeline insert slot for graph phase](./tickets/03-pipeline-insert-slot.md) — After Layer 0-B, before route; inputs = ledger + manifest unit docs + sources; writes only `projects/<id>/graph/`; first merge opt-in (route/L1 do not require graph).
- [Promote boundary from experiments/graphing](./tickets/04-promote-boundary.md) — Promote assemble + inventory primitives + tests; narrow-steps review in new `graph_phase.py`; runners/score/viz/fixtures stay experimental.
- [Unit prerequisites before graph may run](./tickets/06-unit-prerequisites.md) — Need manifest `documents`, on-disk sources, ledger rows; skip unggraphable units; fail closed if `--with-graph` and zero units.
- [Project artifact and gate contract](./tickets/05-project-artifact-gate-contract.md) — `graph/units/<unit_id>/` artifacts; Gate A hard; gold scoring off; CLI `--with-graph` (+ `--only` / `--force`).
- [Handoff merge-spec shape](./tickets/07-handoff-merge-spec-shape.md) — Implementer spec at `docs/GRAPH-PHASE.md`.

## Not yet specified

- How **synthesize / GLOBAL-AUDIT** should surface HAS-PART (follow-on after first merge).
- Whether route/L1 ever **consume** graph output (ruled out for first merge).
- Multi-module Bluebonnet registry expansion (separate effort).

## Out of scope

- Live Grok / xAI (or any cloud) API wiring for a “full Grok Bluebonnet” run.
- Full multi-module Bluebonnet corpus graphing (G5 M2–M6 + Algebra I) in this effort.
- Implementing the merge / editing `run_project.py` inside this map.
- Replacing Layer 2 with graph (different job); graph complements completeness checks.
