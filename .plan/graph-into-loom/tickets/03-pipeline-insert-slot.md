---
type: grilling
blocked_by:
  - 01-loom-pipeline-dataflow
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:50:00Z
assets:
  - ../assets/01-loom-pipeline-dataflow.md
---

# Pipeline insert slot for graph phase

## Question

Relative to route, path workflows, Layer 1, Layer 2, calendars, and synthesize: **exactly where** does the graph phase run, what may it consume as inputs, and what must it **not** consume or mutate so Layer 1/2 and calendars stay coherent?

## Answer

**Insert:** after Layer 0-B (`resolve-wide-spans`), **before** `route.py`.

**May consume:** only `layer0/ledger.json`, `manifest.yaml` → `units.*.documents`, and `sources/`. Not route-map, path A/B/C findings, Layer 1/2, or calendars.

**Must not mutate:** write only under `projects/<id>/graph/`. Do not change ledger, route-map, `layer1/*`, `layer2/*`, calendars, or unit calendar YAML.

**First-merge coupling:** graph is **opt-in**; route / Layer 1 / Layer 2 must not require graph output yet (parallel artifact until a later synthesize/consume ticket).

Research slot analysis: [01-loom-pipeline-dataflow asset](../assets/01-loom-pipeline-dataflow.md) (Slot 1).
