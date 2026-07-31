---
type: grilling
blocked_by: [01]
claimed_by:
claimed_at:
assets: []
---

# Provisional completeness gate

## Question

For `ledger-mini`, what does “provisional graph is good enough to start review” mean as an explicit gate — which invariants are must-pass (e.g. every source is a Material; every calendar day has a Lesson; no orphans) and which qualities are explicitly deferred to post-review rebuild?

## Answer

**Gate A + soft-queue + defer structural fine print.**

### Must-pass (hard fail — blocks “ready for review”)

1. **Material inventory coverage:** every file under `projects/_fixtures/ledger-mini/sources/` is represented as a Material node (for mini: plan, slides, exit ticket).
2. **No orphan sources:** no on-disk source lacking a Material node.

That is the entire hard bar. Course/unit spine, Lesson nodes, Assessment typing, and correct edges are **not** hard fails.

### Soft-queue (allowed; does not fail the gate)

If a Material has **no Lesson yet**, it goes to the **back of the review line** until some Lesson exists to hang under. Temporary “no pedagogical home” is honest; do **not** invent fake Lessons or force a unit-bin home just to clear the gate (false parents are worse than waiting).

### Explicitly deferred to post-review rebuild (not required to pass)

Structural fine print, including:

- Correct Lesson presence/spans (paragraph / element ranges)
- Assessment attach (exit ticket under the right Lesson; embedded vs separate form)
- Material roles (`lesson_plan` / slides / etc.)
- Edges: `describes`, `uses`, `spanIn`, refined `hasPart`
- Gold scoring (lesson IoU, edge F1, provisional-pass metrics from `experiments/graphing`)

Pedagogy / Path quality scoring is outside this gate’s job (inventory knownness ≠ lesson quality); it was not added as a hard fail.

### Spike reading on `ledger-mini`

A graph with three Materials and zero Lessons **passes** the provisional gate; review of those Materials waits (soft-queue) until Lessons are noded. Rebuild after review is where belonging and fine structure get fixed.
