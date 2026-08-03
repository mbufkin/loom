# Graphing experiment promote inventory

**Ticket:** [02-graphing-promote-inventory](../tickets/02-graphing-promote-inventory.md)  
**Question:** What exists under `experiments/graphing/` today, and what is promote-candidate vs experiment wrapper vs Bluebonnet-slice fixture?  
**Method:** File-by-file inventory of every `.py` / `.md` under `experiments/graphing/` excluding `results/` dumps (fixture trees under `results/bluebonnet-g5-m1-grok/` are noted as fixture artifacts, not inventoried line-by-line).  
**Date:** 2026-08-02

---

## SPIKE.md decisions already locked (do not re-litigate)

From [SPIKE.md](../../../experiments/graphing/SPIKE.md) — implementers should treat these as fixed for the first merge:

| Decision | Locked value |
|----------|--------------|
| Loop | Materials inventory → provisional HAS-PART (Gate A) → per-Material review → **batch** rebuild (organization v1) |
| Gate A (hard) | Every file under `sources/` is a Material node; no orphan sources on disk |
| Soft-queue | Material with no Lesson yet → back of review line; do not invent fake Lessons |
| Belonging | Exit ticket / whole-file assessment **must** attach via `Lesson hasPart → Assessment` once known |
| Rebuild trigger | Batch after **all** Materials in the unit reviewed; inputs = review findings + provisional graph |
| Rebuild stability | Material inventory stable (one Material per source); org tree / edges / spans / roles may change |
| Per-doc log | Flat JSON per source under `graph/.raw/<stem>.json` with `provisional_choice` / `rebuild_choice` |
| Spike fixture | `projects/_fixtures/ledger-mini/` only for the original spike runner |
| Out of spike | Production `run_project.py` wiring, dual-model bakeoff, auto-rebuild per finding, L0-coupled rebuild inputs, pedagogy scoring |

**Map preference (already voiced):** Prefer the **narrow-steps + `rebuild_multi`** path (`graph_assemble.py` + Bet 3 runners), not a parallel one-shot graph stack or the legacy P1×D full-graph repair path.

---

## Inventory table

| Path | Purpose | Public entrypoints | Hard deps (Bluebonnet vs generic) | Tests | Classification | Rationale |
|------|---------|-------------------|-------------------------------------|-------|----------------|-----------|
| [SPIKE.md](../../../experiments/graphing/SPIKE.md) | Handoff spec: loop, Gate A, belonging, rebuild trigger, per-doc raw contract, non-goals | — (doc) | References `ledger-mini` fixture | — | **Reference doc** | Locked decisions; promote **behavior**, not the file |
| [README.md](../../../experiments/graphing/README.md) | Index: spike runner, P1×D lab commands, provisional pass bar | — (doc) | Mentions `lab-dallas-ag`, `lab-arts-av` | — | **Reference doc** | Experiment README; not core |
| [spike_loop.py](../../../experiments/graphing/spike_loop.py) | Provisional → review → rebuild loop (code-first, no LLM) | `run_spike`, `build_provisional`, `gate_a`, `list_sources`, `materials_needing_queue`, `review_order`, `rebuild`, `write_raw_decisions`, `default_review_findings`, `material_id`, `invent_role` | **Generic** via `--project-root`; default = `projects/_fixtures/ledger-mini`. `invent_role` / `default_review_findings` are ledger-mini filename heuristics | [test_spike_loop.py](../../../experiments/graphing/test_spike_loop.py) | **Split:** core primitives → **promote-candidate**; ledger-mini heuristics + `run_spike` CLI → **wrapper/fixture** | Gate A, provisional inventory, soft-queue, single-lesson `rebuild`, raw decision writer are production-shaped. `invent_role`/`default_review_findings` must not become core defaults |
| [graph_assemble.py](../../../experiments/graphing/graph_assemble.py) | Manifest-driven unit slice + narrow-step merge + multi-lesson `rebuild_multi` (Bet 3 code path) | `SpinePolicy`, `UnitSlice`, `load_unit_slice`, `resolve_unit_spine`, `merge_narrow_step_findings`, `rebuild_multi`, `FULL_MODULE_ROLES` | **Generic** `manifest.yaml` / `project_id`; imports `_doc_id`, `material_id` from `spike_loop` | [test_graph_assemble.py](../../../experiments/graphing/test_graph_assemble.py) | **promote-candidate** | Preferred production assembler per map notes; curriculum knobs live in `SpinePolicy`, not hardcoded PDF lists |
| [score_haspart.py](../../../experiments/graphing/score_haspart.py) | Score predicted HAS-PART vs hand-built gold (IoU, assessment attach, edge F1, `pass_provisional`) | `score(pred_path, gold_path, sources_dir?)` | **Generic** graph JSON; no project paths in API | Used by `test_graph_assemble`, runners | **wrapper** | Dev/experiment validation harness; not a production pipeline stage unless an explicit opt-in gate is added later |
| [code_first.py](../../../experiments/graphing/code_first.py) | P1×D deterministic Day-header propose (full graph in one pass) | `propose_graph`, `day_spans_from_text`, `load_ledger_for_project` | **Mixed:** `--project` generic; `load_ledger_for_project` falls back to hardcoded `projects/dallas-career-2026/...` and `lab-dallas-career/...` | None dedicated ( exercised via `run_pd.py` ) | **wrapper** | Alternate experiment path; superseded for merge by narrow-steps + `rebuild_multi`. Day-header heuristics are Dallas/lab-shaped, not module-spine |
| [run_pd.py](../../../experiments/graphing/run_pd.py) | P1×D runner: `propose_graph` → optional model full-graph repair → score vs gold | `run_one`, `repair_with_model`, `main` | **Generic** `--project` + `--gold`; uses `audit_lib` model stack | None | **wrapper** | Thin experiment orchestrator; one-shot model JSON repair is explicitly **not** the promote path |
| [run_bluebonnet_slice_30b.py](../../../experiments/graphing/run_bluebonnet_slice_30b.py) | Bluebonnet G5 M1: 3 narrow LLM steps per doc → `merge_narrow_step_findings` → `rebuild_multi` | `step_role`, `step_lessons`, `step_assessment`, `main` | **Bluebonnet-hard:** `results/bluebonnet-g5-m1-grok/manifest.yaml`, Grok gold, `projects/bluebonnet-math-2026/layer0/ledger.json`, stub sources under experiment results | Indirect via `test_graph_assemble` replay | **wrapper** | Proves Bet 3 loop end-to-end; prompts and evidence loader are slice-specific. Core logic already factored into `graph_assemble` |
| [run_bluebonnet_slice_grok.py](../../../experiments/graphing/run_bluebonnet_slice_grok.py) | Build Bluebonnet slice fixture + Grok-authored review findings + `rebuild_multi` | `grok_review_findings`, `ensure_fixture`, `ledger_signals`, `main` | **Bluebonnet-hard:** hardcoded `SOURCES`, `N_LESSONS=15`, `PROJECT_ID`, writes to `results/bluebonnet-g5-m1-grok/` | None | **fixture-only wrapper** | Creates experimental gold and demonstrates declare-spine review; `grok_review_findings` encodes packaging knowledge that must not ship as core defaults |
| [test_spike_loop.py](../../../experiments/graphing/test_spike_loop.py) | Unit tests for SPIKE loop on `ledger-mini` | `TestSpikeLoop` | Fixture: `projects/_fixtures/ledger-mini` | Self | **promote-candidate** (tests move with core) | Covers Gate A, soft-queue, rebuild belonging, raw before/after |
| [test_graph_assemble.py](../../../experiments/graphing/test_graph_assemble.py) | Spine policy, manifest load, merge replay vs Grok gold | `TestSpinePolicy`, `TestManifestUnit`, `TestMergeReplay` | Uses `results/bluebonnet-g5-m1-grok/manifest.yaml` + gold; optional replay from `P1xD_bluebonnet-g5-m1-slice_*` | Self | **promote-candidate** (tests move with core); replay artifacts = **fixture** | Regression for TE-cap bug (12→15 lessons); manifest test is generic |
| [viz/build_data.py](../../../experiments/graphing/viz/build_data.py) | Pack `results/` into `viz/data.json` for local Graph Lab HTML | `main`, `_pack_p1xd`, `_pack_approach_compare`, `_pack_spike_slice` | **Bluebonnet-hard:** `BB_SOURCES`, Grok gold path, `bluebonnet-math-2026` ledger for doc-truth panel | None | **wrapper** | Experiment visualization only |
| [viz/index.html](../../../experiments/graphing/viz/index.html) | Static Graph Lab UI | — | Consumes `data.json` | None | **wrapper** | Not pipeline code |
| [results/bluebonnet-g5-m1-grok/](../../../experiments/graphing/results/bluebonnet-g5-m1-grok/) | Bluebonnet G5 M1 slice fixture tree: manifest, stub sources, Grok gold graph, review findings, `.raw/` | `manifest.yaml`, `graph/HAS-PART.json` (experimental gold) | **fixture-only** | Referenced by tests/runners | **fixture-only** | Experimental gold + registry for narrow-steps runs; must not become production default corpus |
| [results/RESULTS.md](../../../experiments/graphing/results/RESULTS.md) | Append-only P1×D run log | — | Run dumps | — | **fixture-only** | Results dump |
| [results/P1xD_*](../../../experiments/graphing/results/) | Timestamped run artifacts (propose/final/score/SUMMARY, `.raw/` step JSON) | — | Mixed lab + Bluebonnet | Replay input for tests | **fixture-only** | Not promoted; may seed regression fixtures |

---

## On-disk contracts (shared shape)

These paths appear across spike + Bluebonnet runs and should inform the merge artifact contract (ticket 05):

| Artifact | Role | Promote? |
|----------|------|----------|
| `graph/HAS-PART.provisional.json` | Gate A–passed inventory graph (Materials under unit) | **Yes** (contract) |
| `graph/HAS-PART.json` | Post-rebuild organization graph | **Yes** (contract) |
| `graph/review-findings.json` | Batch rebuild input (`create_lessons`, `findings[]`) | **Yes** (contract) |
| `graph/.raw/<source_stem>.json` | Per-doc flat decision log (`provisional_choice`, `rebuild_choice`) | **Yes** (contract) |
| `graph/SPIKE-SUMMARY.json` | Run summary (spike runners) | **Wrapper** (debug/telemetry) |
| `manifest.yaml` `units.<id>.documents` | Unit document registry | **Yes** (already production-shaped; slice copy is fixture) |
| `manifest.yaml` `spine_policy` | Per-curriculum lesson union policy | **Yes** (promote `SpinePolicy` semantics) |

---

## Promote boundary (tentative)

### Promote into Loom core (first merge)

1. **`graph_assemble.py`** — manifest unit slice, spine policy, narrow-step merge, `rebuild_multi`.
2. **`spike_loop.py` primitives** — `gate_a`, `build_provisional`, `materials_needing_queue`, `review_order`, `rebuild` (single-lesson variant), `write_raw_decisions`, shared id helpers (`material_id`, `_doc_id`).
3. **Tests** — `test_spike_loop.py`, `test_graph_assemble.py` (minus hard dependency on experiment results dir where possible).
4. **Contracts** — provisional/rebuilt HAS-PART, review-findings schema, per-source `.raw/` decision JSON (per SPIKE.md minimum fields).

### Stay experiment-only wrappers (do not promote on first merge)

| Module | Why stay |
|--------|----------|
| `run_pd.py` + `code_first.py` | Legacy P1×D one-shot propose + full-graph model repair; different architecture from narrow-steps |
| `run_bluebonnet_slice_30b.py` | LLM prompt harness + Bluebonnet ledger wiring; production will call models via Layer 0/1 stack, not this script |
| `run_bluebonnet_slice_grok.py` | Fixture builder + declare-spine review simulation |
| `score_haspart.py` | Gold comparison for experiments; optional dev gate only |
| `viz/*` | Local results browser |
| `spike_loop.run_spike` / `main` | Convenience CLI for ledger-mini demo |

### Fixture-only — must not become core defaults

| Item | Why |
|------|-----|
| `projects/_fixtures/ledger-mini` | SPIKE.md locked fixture; 3-file unit, single Day 1 lesson |
| `results/bluebonnet-g5-m1-grok/` | 4-book G5 M1 slice, stub PDFs, **Grok cursor rebuild as experimental gold** |
| `run_bluebonnet_slice_grok.grok_review_findings` | Hardcoded 15-lesson declare-spine + Practice→Assessment wiring from packaging knowledge |
| `spike_loop.invent_role` / `default_review_findings` | Filename heuristics tuned for ledger-mini (exit_ticket, slides, lesson_plan) |
| `code_first.load_ledger_for_project` fallbacks | Hardcoded Dallas/lab ledger paths |
| `viz/build_data.py` `BB_SOURCES`, `GOLD_BY_PROJECT` bluebonnet entry | Viz/compare panel wiring |

---

## Dependency graph (today)

```text
ledger-mini fixture ──► spike_loop.run_spike
                              │
                              ├── gate_a, build_provisional, rebuild (single-lesson)
                              └── write_raw_decisions

manifest.yaml (unit.documents) ──► graph_assemble.load_unit_slice
narrow-step JSON (role/lessons/assess) ──► merge_narrow_step_findings ──► rebuild_multi
                                              ▲
run_bluebonnet_slice_30b ─────────────────────┘ (LLM steps)
run_bluebonnet_slice_grok ── grok_review_findings ──► rebuild_multi

lab projects ──► code_first.propose_graph ──► run_pd ──► score_haspart
```

---

## Gaps for downstream tickets

- **`graph_assemble` ↔ `spike_loop` import:** `_doc_id` / `material_id` live in `spike_loop` today; promote should colocate shared graph ids in one core module.
- **Single vs multi rebuild:** `rebuild()` (single Lesson) vs `rebuild_multi()` — merge spec should state when each applies (ledger-mini vs module-spine).
- **Review findings producer:** Core owns rebuild; **Path review / narrow-steps producers** stay upstream (not in this inventory as stable core yet).
- **Gold scoring:** `pass_provisional` thresholds are experiment bars, not production gates, unless ticket 05 locks them.

---

## One-line gist

**Promote `graph_assemble` + spike loop gates/provisional/rebuild/raw contracts; keep P1×D and Bluebonnet runners, Grok gold slice, and ledger-mini heuristics experiment/fixture-only.**
