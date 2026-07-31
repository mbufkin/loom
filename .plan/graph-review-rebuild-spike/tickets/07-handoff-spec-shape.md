---
type: grilling
blocked_by: [04, 05, 06]
claimed_by:
claimed_at:
assets:
  - experiments/graphing/SPIKE.md
---

# Handoff spec shape

## Question

When this map is clear, what artifact do we hand off (sections, invariants, fixture contract, non-goals) so an implementer can build the ledger-mini spike without re-opening these decisions — and where should that spec live in the repo?

## Answer

**Lean handoff at `experiments/graphing/SPIKE.md`, plus per-source flat decision JSON under `graph/.raw/`.**

### Where

[`experiments/graphing/SPIKE.md`](../../../experiments/graphing/SPIKE.md) — next to the graphing runner; not under `docs/` and not only inside `.plan/`.

### Sections (lean — decisions only, not a cookbook)

1. Loop diagram (provisional → review → batch rebuild)
2. Gate A (inventory hard; soft-queue; deferred fine print)
3. Belonging policy (`Lesson hasPart → Assessment`; either physical form; mini = separate file)
4. Rebuild contract (batch after all Materials reviewed; inputs = findings + provisional graph; Materials stable)
5. **Per-document flat JSON** — one file per source under `graph/.raw/`, exposing model choices with **provisional_choice / rebuild_choice** (before/after)
6. Fixture contract (`ledger-mini` only)
7. Non-goals
8. Links to map tickets / research assets

No sample CLI, no full findings schema dump, no dual-model requirement in this spike.

### Per-doc JSON (added in grilling)

Known pattern in-repo: Layer 0 `.raw/` + `docs/GRAPHING.md` “Raw model I/O” under `graph/.raw/`. Spike requires a **flat** per-source decision record (not buried chat) so operators can see what the model chose for each document at a glance, including before vs after rebuild.
