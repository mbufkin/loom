# Graph phase into Loom (merge handoff)

**Status:** decisions locked; **first merge wired** (`graph_inventory.py`, `graph_assemble.py`, `graph_phase.py`, `run_project.py --with-graph`)  
**Map:** [.plan/graph-into-loom/map.md](../.plan/graph-into-loom/map.md)  
**Prior spike (archived off-repo):** see `~/archive/loom-experiments-*/experiments/graphing/SPIKE.md` — not runnable from this workspace.

This file is the implementer-facing merge spec. Do not reopen insert-slot, promote, contract, or prerequisite decisions here — change them only by resolving a new Wayfinder ticket.

Educational note: graph answers **belonging** (Materials → Lessons → Assessments). Layer 2 answers **structural completeness** inside a role-fulfilling doc. They are complementary; graph does not replace Layer 2.

---

## Destination / non-goals

**In scope for first merge**

- Opt-in graph phase in `run_project.py` (`--with-graph`)
- Promote assembler + inventory primitives from `experiments/graphing`
- Write artifacts under the **E2E run root** (`projects/<id>/e2e/runs/<run_id>/graph/…`); bare `projects/<id>/graph/` is legacy archive
- Narrow-steps review → code merge → `rebuild_multi`

**Out of scope (this merge)**

- Live Grok / xAI / cloud API wiring
- Full multi-module Bluebonnet corpus run
- Making route / Layer 1 / Layer 2 / calendars require graph output
- Promoting P1×D one-shot repair, viz lab, or Grok declare-spine gold as defaults
- Gold `score_haspart` as a production gate

---

## Pipeline insert slot

```text
preflight → ingest? → rollup?
  → layer0 (0-A decompose)
  → layer0 (0-B resolve-wide-spans)
  → ★ graph_phase.py          ← ONLY when --with-graph
  → route.py
  → path workflows
  → layer1 → layer2 → calendars → synthesize
```

| May consume | Must not consume | Must not mutate |
|-------------|------------------|-----------------|
| `layer0/ledger.json` | `route-map.json` | ledger, route-map |
| `manifest.yaml` → `units.*.documents` | path A–H findings | `layer1/*`, `layer2/*` |
| `sources/` | Layer 1/2, calendars | unit calendars, pacing |

Locked ticket: [Pipeline insert slot for graph phase](../.plan/graph-into-loom/tickets/03-pipeline-insert-slot.md).

---

## Promote boundary

### Promote (Loom core)

| Module (recommended name) | Source today | Responsibility |
|---------------------------|--------------|----------------|
| `graph_assemble.py` | `experiments/graphing/graph_assemble.py` | Unit slice, `SpinePolicy`, `merge_narrow_step_findings`, `rebuild_multi` |
| `graph_inventory.py` | primitives from `spike_loop.py` | `gate_a`, `build_provisional`, soft-queue/order, single-lesson `rebuild`, `write_raw_decisions`, shared ids |
| `graph_phase.py` | *new* (factor prompts from `run_bluebonnet_slice_30b.py`) | Orchestrate: provisional → narrow-steps via `audit_lib.model_chat` → merge → rebuild → write `graph/units/<id>/` |
| Tests | `test_spike_loop.py`, `test_graph_assemble.py` | Move with core; drop hard deps on experiment `results/` where practical |

**Rebuild rule:** `rebuild_multi` for module-shaped spines; single-lesson `rebuild` only for mini fixtures.

**Review mode (first merge):** narrow-steps only (role → `covers_lesson_numbers` → assessment-bearing). Not Grok declare-spine.

### Do not promote

| Stay experimental | Why |
|-------------------|-----|
| `run_pd.py`, `code_first.py` | One-shot / Day-header P1×D path |
| `run_bluebonnet_slice_30b.py` | Slice harness; logic factored into phase |
| `run_bluebonnet_slice_grok.py` | Fixture + declare-spine gold builder |
| `score_haspart.py` | Dev gold scorer — not a default gate |
| `viz/*` | Local Graph Lab |
| `invent_role` / `default_review_findings` | ledger-mini heuristics |
| `results/bluebonnet-g5-m1-grok/` | Experimental gold / slice registry |

Locked ticket: [Promote boundary from experiments/graphing](../.plan/graph-into-loom/tickets/04-promote-boundary.md).  
Inventory asset: [.plan/graph-into-loom/assets/02-graphing-promote-inventory.md](../.plan/graph-into-loom/assets/02-graphing-promote-inventory.md).

---

## Unit prerequisites + fail-closed

A unit is graphable only if **all** hold:

1. `units.<unit_id>.documents` is a non-empty basename list in `manifest.yaml`
2. Those files exist under `sources/`
3. `layer0/ledger.json` has evidence rows for at least one of those `source_file`s

| Situation | Behavior |
|-----------|----------|
| No `--with-graph` | Skip phase |
| Unit not graphable | Skip unit + log |
| `--with-graph` and zero graphable units | **Fail** graph phase (non-zero) |
| Gate A fail | **Fail** that unit / phase non-zero |
| `--only UNIT` | Scope to that unit |

No route-map required. Locked ticket: [Unit prerequisites before graph may run](../.plan/graph-into-loom/tickets/06-unit-prerequisites.md).

---

## Artifact contract, gates, CLI

### Layout (canonical — E2E only)

```text
projects/<id>/e2e/runs/<run_id>/     # LOOM_E2E_RUN (auto-set by run_project)
  sources -> ../../../sources        # shared inputs
  layer0/ … output/ …                # full pipeline plates
  graph/
    ACTIVE                           # current nested graph run id
    units -> runs/<run_id>/units
    runs/<run_id>/                   # usually same id as e2e run
      RUN.json
      PHASE-SUMMARY.json
      units/<unit_id>/
        HAS-PART.provisional.json
        HAS-PART.json
        review-findings.json
        SUMMARY.json
        .raw/<source_stem>.json
```

`run_id` defaults to a slug of the model name (`grok-4.5`, `nemotron3-nano-30b`, …).
Pass `--graph-run <id>` (also becomes `LOOM_E2E_RUN` when unset).

**Legacy:** `projects/<id>/graph/runs/*` from pre-E2E queues — read-only archive; do not start new writes there. Golden curriculum refresh uses `--allow-live-root`.

### Gates

| Gate | Strength |
|------|----------|
| Gate A (materials inventory / no orphans in unit slice) | **Hard** |
| Soft-queue Materials with no Lesson | Soft (review order) |
| Doc with no Layer 0 ledger rows | **Soft-skip** — stub as `other` / no lessons; unit still graphs |
| Gold / `pass_provisional` | **Off** in production |
| Downstream requires graph | **Off** (first merge) |

### CLI

```bash
# Full E2E (default write root = e2e/runs/<model-slug>/)
python3 run_project.py --project <id> --with-graph --graph-run nemotron3-nano-30b
python3 run_project.py --project <id> --with-graph --graph-backend cursor --graph-cursor-model grok-4.5 --graph-run grok-4.5

# Graph-only under E2E (symlinks curriculum layer0 when needed)
python3 run_project.py --project <id> --graph-only --with-graph --graph-run <model-slug>

# Escape hatch: write golden projects/<id>/ (overnight only)
python3 run_project.py --project <id> --allow-live-root --layer0-no-resume
```

Default without `--with-graph`: no graph phase (still E2E-isolated unless `--allow-live-root`).  
Direct: `LOOM_E2E_RUN=<id> python3 graph_phase.py --project <id> […]`.

Locked ticket: [Project artifact and gate contract](../.plan/graph-into-loom/tickets/05-project-artifact-gate-contract.md).

---

## Implementation status (first merge)

1. ✅ `graph_inventory.py` + `graph_assemble.py` at repo root; spike keeps ledger-mini heuristics.
2. ✅ `graph_phase.py` — narrow-steps + writes `graph/units/<unit_id>/`.
3. ✅ `run_project.py --with-graph` after Layer 0-B.
4. ✅ Spike/experiment runners archived off-repo (`experiments/` stub only).

Experiment runners (`run_bluebonnet_slice_*.py`, `run_pd.py`, viz) are **not** in-tree — do not recreate them here.

---

## Route consumption (solved)

When `--with-graph` has produced HAS-PART under the run's `graph/` tree,
`route.py` loads graph routing hints (`load_graph_routing_hints`) and **uses
them as the content router**: Material roles assign D/E and Assessment links
assign B whenever the filename is silent. Hard filename wins remain for
explicit lesson plans, quizzes, exit tickets, syllabi, and pacing names.

This closed the Bluebonnet TE/SE to Path C failure. Downstream path runners still
consume only `layer0/route-map.json` — they do not re-read the graph.

Layer 1 / Layer 2 still must not *require* graph output (`--with-graph` remains
opt-in in the CLI). Any real review should pass `--with-graph`; without it
the router is filename-only again.

## Deferred (fog — not this merge)

- Synthesize / GLOBAL-AUDIT surfacing of HAS-PART
- Soft vs hard failure policy changes beyond Gate A / zero-units
- Multi-module Bluebonnet registry expansion
- Model provider adapter beyond existing `audit_lib.model_chat` + `config.yaml`
- Making `--with-graph` the default for every run

---

## Decision index

| Ticket | Gist |
|--------|------|
| [Loom pipeline dataflow](../.plan/graph-into-loom/tickets/01-loom-pipeline-dataflow.md) | Ready after 0-B; Slot 1 before route |
| [Promote inventory research](../.plan/graph-into-loom/tickets/02-graphing-promote-inventory.md) | Promote assemble + spike primitives |
| [Pipeline insert slot](../.plan/graph-into-loom/tickets/03-pipeline-insert-slot.md) | After 0-B; graph/ only; opt-in |
| [Promote boundary](../.plan/graph-into-loom/tickets/04-promote-boundary.md) | Core vs wrappers vs fixtures |
| [Artifact / gate / CLI](../.plan/graph-into-loom/tickets/05-project-artifact-gate-contract.md) | `graph/units/<id>/`; Gate A hard; `--with-graph` |
| [Unit prerequisites](../.plan/graph-into-loom/tickets/06-unit-prerequisites.md) | manifest docs + sources + ledger; fail closed |
| [Handoff shape](../.plan/graph-into-loom/tickets/07-handoff-merge-spec-shape.md) | This file |
