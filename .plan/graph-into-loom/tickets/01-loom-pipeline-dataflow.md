---
type: research
blocked_by: []
claimed_by:
claimed_at:
assets: [".plan/graph-into-loom/assets/01-loom-pipeline-dataflow.md"]
resolved_at: 2026-08-02T19:46:01Z
---

# Loom pipeline dataflow for graph insert candidates

## Question

What does each step in `run_project.py` today **read** and **write** (paths + key artifacts), and which insert slots between route → path workflows → layer1 → layer2 → calendars → synthesize are mechanically viable for a graph phase that needs ledger evidence and unit document lists?

## Answer

Each `run_project.py` step’s reads/writes are tabulated in the research asset (ingest → rollup → layer0-A/B → route → path workflows → layer1 → layer2 → calendars → synthesize → Drive push). Full detail: [.plan/graph-into-loom/assets/01-loom-pipeline-dataflow.md](../assets/01-loom-pipeline-dataflow.md).

**Graph minimum inputs:** post–Layer 0-B `layer0/ledger.json`, `manifest.yaml` with `units.<id>.documents[]`, matching files in `sources/`, and `config.yaml` for narrow model steps. Gold, `route-map.json`, path A/B/C findings, and Layer 1/2 outputs are **not** required by `experiments/graphing` narrow-steps + `rebuild_multi`.

**Insert slots (mechanical viability for ledger + unit doc list):**

| Slot | Viable? | Summary |
|------|---------|---------|
| After Layer 0-B, **before route** | ⭐ Yes — **preferred** | All graph inputs exist; no placement/route decisions yet; aligns with “graph after L0 evidence, before router.” |
| After route, before path workflows | Yes | Adds optional `doc_type` priors; still before L1. |
| After path workflows, before layer1 | Weak | Path findings are audit stubs, not HAS-PART; L1 follows immediately. |
| After layer1 / layer2 / calendars | Reporting-only | L1 placement and calendars already committed; too late to feed conformance. |
| Before Layer 0 | No | No ledger. |

**Gist:** Graph belongs after Layer 0-B and ideally before `route.py`; downstream slots are either redundant inputs or too late to affect Layer 1/2.
