---
type: grilling
blocked_by:
  - 03-pipeline-insert-slot
claimed_by:
claimed_at:
resolved_at: 2026-08-02T19:52:30Z
assets: []
---

# Unit prerequisites before graph may run

## Question

What must already exist for a unit (ledger rows, unit document list / manifest shape, route-map entry, sources layout) before graph is allowed to run, and how does a project without a module-grouped unit registry fail closed?

## Answer

HITL authorized recommended package (2026-08-02).

### Required per unit (all must hold)

1. `manifest.yaml` has `units.<unit_id>.documents` as a **non-empty** list of source basenames.
2. Each listed basename exists under the project `sources/` tree (Gate A will hard-fail the unit if orphans/missing).
3. `layer0/ledger.json` exists and contains at least one row whose `source_file` matches a document in that unit (narrow-steps needs ledger evidence).

### Not required

- `route-map.json` / path A/B/C (insert is before route).
- Layer 1/2 findings, calendars, gold HAS-PART.

### Fail-closed policy

| Situation | Behavior |
|-----------|----------|
| `--with-graph` off | Graph phase skipped entirely (no error). |
| `--with-graph` on, unit missing `documents` or empty list | **Skip that unit** with a clear log; do not invent a document list. |
| `--with-graph` on, zero units graphable | **Abort graph phase** with non-zero exit from the phase script (fail closed) — do not silently succeed. |
| `--with-graph` on, Gate A fails for a unit | Fail that unit’s graph artifacts; phase exit non-zero (hard gate). |
| Project has no module-grouped units (flat / missing registry) | Same as zero graphable units — fail closed when `--with-graph` requested. |

`--only UNIT` scopes graph to that unit slug (same as Layer 1); other units untouched.
