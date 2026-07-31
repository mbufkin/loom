---
type: grilling
blocked_by: [03, 04]
claimed_by:
claimed_at:
assets: []
---

# Rebuild trigger contract

## Question

After document review on provisional graph nodes, **what events or outputs trigger a graph rebuild**, what inputs does rebuild consume (review findings, L0 ledger, calendars), and what is allowed to change vs must stay stable across the rebuild?

## Answer

**Batch rebuild after all Materials in the unit are reviewed; rebuild closes the unit pass (rollup-adjacent). Minimal inputs. Materials inventory stable.**

### Trigger

- **Not** per-finding auto-rebuild during review.
- Fire **one batch rebuild** when **every Material in the unit has been reviewed** (soft-queued items are reviewed once a Lesson exists, then count toward done).
- That batch is the **closing step of unit review** — last in the unit pass / part of rollup framing — after materials have been reviewed and structural reorg intent is recorded in findings.
- Richer trigger matrices (L0/calendar coupling, live auto-rebuild) are a **later test suite**, not this spike.

### Inputs (minimal for spike)

1. **Review findings** (structured deltas: re-parent, retype, Assessment attach, role hints, split multi-day, etc.)
2. **Current provisional graph** (organization v0)

L0 ledger and calendars are **out of the minimal spike input set** (can join a later suite).

### Stable vs may change

| Stable across rebuild | May change |
|----------------------|------------|
| **Material inventory** — one Material per source file; files not re-split on disk | Organization tree (Lessons, Assessment placement) |
| | Edges (`hasPart`, `describes`, `uses`, `spanIn`, …) |
| | Spans / element attachment |
| | Material **roles** (plan vs slides vs …) |

### Contract summary

```text
provisional graph (inventory hard-pass)
    → review each Material (soft-queue until Lesson exists)
    → all Materials reviewed + findings recorded
    → batch rebuild(findings, provisional graph)  ← unit-close / rollup-adjacent
    → organization v1 (same Materials, revised belonging)
```
