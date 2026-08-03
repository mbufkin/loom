---
type: grilling
blocked_by:
  - 03-pipeline-insert-slot
  - 04-promote-boundary
  - 05-project-artifact-gate-contract
  - 06-unit-prerequisites
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:53:30Z
assets:
  - ../../../docs/GRAPH-PHASE.md
---

# Handoff merge-spec shape

## Question

Where does the implementer-facing merge spec live (path + sections), and what must it include so someone can wire graph into Loom without reopening insert-slot / promote / contract / prerequisite decisions?

## Answer

HITL authorized recommended package (2026-08-02).

**Path:** [`docs/GRAPH-PHASE.md`](../../../docs/GRAPH-PHASE.md) — implementer handoff (same role SPIKE.md played for the ledger-mini spike).

**Must include sections:**

1. Destination / non-goals (opt-in first merge; no cloud API; no full Bluebonnet corpus)
2. Pipeline insert slot + dataflow diagram
3. Promote list vs experiment-only vs fixtures
4. Unit prerequisites + fail-closed policy
5. On-disk artifact contract + gates + CLI
6. Review mode (narrow-steps) + rebuild ownership
7. Suggested module layout (`graph_phase.py`, `graph_assemble.py`, `graph_inventory.py`)
8. Pointers to locked Wayfinder tickets under `.plan/graph-into-loom/`

**Pointers:** add a one-line link from `experiments/graphing/SPIKE.md` and `experiments/graphing/README.md` to `docs/GRAPH-PHASE.md` when implementing (not required to reopen decisions).
