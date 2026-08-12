---
type: research
blocked_by: []
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:46:30Z
assets:
  - ../assets/02-graphing-promote-inventory.md
---

# Graphing experiment promote inventory

## Question

What modules, runners, contracts, and tests under `experiments/graphing/` exist today, and which are **candidates to promote into Loom core**, which should stay experiment-only wrappers, and which are Bluebonnet-slice fixtures that must not become core defaults?

## Answer

**Gist:** Promote `graph_assemble` + spike loop gates/provisional/rebuild/raw contracts; keep P1×D and Bluebonnet runners, Grok gold slice, and ledger-mini heuristics experiment/fixture-only.

Full inventory table, SPIKE.md locked decisions, on-disk contracts, and tentative promote boundary: [02-graphing-promote-inventory asset](../assets/02-graphing-promote-inventory.md).
