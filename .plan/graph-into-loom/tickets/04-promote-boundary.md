---
type: grilling
blocked_by:
  - 02-graphing-promote-inventory
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:52:00Z
assets:
  - ../assets/02-graphing-promote-inventory.md
---

# Promote boundary from experiments/graphing

## Question

Which pieces of the proven graph loop (`spike_loop` / `graph_assemble` / score / Bluebonnet runners) become **Loom modules**, which remain thin experiment runners, and what is explicitly **not** promoted on the first merge?

## Answer

HITL authorized the research-recommended package (2026-08-02): accept inventory classifications; document, don’t re-grill.

### Promote into Loom core (first merge)

| Piece | Notes |
|-------|--------|
| `graph_assemble.py` | `load_unit_slice`, `SpinePolicy`, `merge_narrow_step_findings`, `rebuild_multi` |
| Spike primitives | `gate_a`, `build_provisional`, `materials_needing_queue`, `review_order`, `rebuild` (single-lesson), `write_raw_decisions`, shared ids (`material_id`, `_doc_id`) |
| Tests | `test_spike_loop.py`, `test_graph_assemble.py` (decouple hard deps on experiment `results/` where practical) |
| Contracts | provisional/final HAS-PART, `review-findings.json`, per-source `graph/.raw/` |

**Layout recommendation for implementers:** colocate shared ids + Gate A / provisional in a root module (e.g. `graph_inventory.py`); keep assembler as `graph_assemble.py`; thin orchestrator `graph_phase.py` (like `layer2.py`) called from `run_project` when `--with-graph`.

**Rebuild rule:** use `rebuild_multi` when unit spine is module-shaped (`SpinePolicy`); `rebuild` only for single-lesson fixtures (ledger-mini-style).

**Review producer (first merge):** production opt-in uses **narrow-steps** (role → lessons → assessment) via `audit_lib.model_chat` — not Grok declare-spine. Core owns merge/rebuild; prompts live in the phase orchestrator (factored from the 30B runner), not as Bluebonnet hardcoded gold.

### Stay experiment-only (not promoted)

`run_pd.py`, `code_first.py`, `run_bluebonnet_slice_30b.py`, `run_bluebonnet_slice_grok.py`, `score_haspart.py`, `viz/*`, `spike_loop.run_spike` CLI.

### Fixture-only — must not become core defaults

`ledger-mini` heuristics (`invent_role`, `default_review_findings`), `results/bluebonnet-g5-m1-grok/` Grok gold, `grok_review_findings` declare-spine, Dallas/lab ledger path fallbacks, viz Bluebonnet compare wiring.

Full inventory: [02-graphing-promote-inventory asset](../assets/02-graphing-promote-inventory.md).
