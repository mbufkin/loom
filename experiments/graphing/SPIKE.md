# Graph → review → rebuild spike (handoff)

**Status:** implemented — `python3 experiments/graphing/spike_loop.py` (+ `test_spike_loop.py`)  

**Fixture:** `projects/_fixtures/ledger-mini/` only  
**Map:** [.plan/graph-review-rebuild-spike/map.md](../../.plan/graph-review-rebuild-spike/map.md)

This file locks decisions so an implementer can build the spike without re-opening them. It is not a cookbook (no sample CLI/JSON dumps beyond the per-doc log contract).

---

## Loop

```text
Materials inventory (sources → Material nodes)
        ↓
Provisional HAS-PART (organization v0)     ← gate A
        ↓
Review each Material (soft-queue if no Lesson)
        ↓
All Materials reviewed → batch rebuild     ← unit-close / rollup-adjacent
        ↓
HAS-PART organization v1                   ← same Materials, revised belonging
```

---

## Provisional completeness gate (Gate A)

**Hard fail (blocks “ready for review”):**

1. Every file under `ledger-mini/sources/` is a Material node.
2. No orphan sources on disk.

**Soft-queue (does not fail the gate):** Material with no Lesson yet → back of the review line until a Lesson exists. Do not invent fake Lessons or force unit-bin homes.

**Deferred to rebuild:** spans, Assessment attach correctness, roles, `describes`/`uses`/`spanIn`, gold IoU/edge F1.

Detail: [Provisional completeness gate](../../.plan/graph-review-rebuild-spike/tickets/04-provisional-completeness-gate.md)

---

## Flexible belonging

**Non-negotiable (placement):** once known, an exit ticket (or similar) **belongs to a Lesson** via **`Lesson hasPart → Assessment`**. Quality scoring is a later step.

**Flexible:** embedded span **or** separate assessment file — both OK if Lesson belonging exists.

**`ledger-mini` shape:** separate file `doc_aaaa03_…Exit_Ticket.txt` → Material + Assessment under Lesson via `hasPart`. Whole docs stay whole.

Detail: [Flexible belonging policy](../../.plan/graph-review-rebuild-spike/tickets/05-flexible-belonging-policy.md)

---

## Rebuild trigger

- **Batch** after **all Materials in the unit** have been reviewed (soft-queued items count once reviewed).
- Rebuild is the **closing step** of unit review (rollup-adjacent) — not per-finding mid-pass.
- **Inputs (minimal):** review findings + current provisional graph.  
  L0 ledger / calendars → later richer suite, not this spike.
- **Stable:** Material inventory (one Material per source file; no re-split on disk).  
- **May change:** org tree, edges, spans, roles.

Detail: [Rebuild trigger contract](../../.plan/graph-review-rebuild-spike/tickets/06-rebuild-trigger-contract.md)

---

## Per-document flat JSON (model choices)

**Required for the spike.** One flat JSON **per source file** under:

`projects/_fixtures/ledger-mini/graph/.raw/<source_stem>.json`

(or the equivalent path under `experiments/graphing/results/<run_id>/` for experiment runs — see `docs/GRAPHING.md` raw I/O rule).

Purpose: open one file and see **what the model chose** for that document, quickly — same spirit as Layer 0 `.raw/` pass files, but **flat decision record**, not full decompose dump.

**Minimum fields (core + before/after):**

| Field | Meaning |
|-------|---------|
| `source_file` | On-disk name |
| `stage` | `provisional` \| `rebuild` (record may hold both choice blocks) |
| `provisional_choice` | Flat object: `role`, `node_type`, `lesson_id` (or `null` if queued), `edges_proposed[]` |
| `rebuild_choice` | Same shape after batch rebuild (or `null` if not yet rebuilt) |
| `model` / `prompt_ref` / `ts` | Optional but recommended (GRAPHING.md config/raw discipline) |

Implementers may add fields; they must not bury the choices inside nested chat transcripts.

---

## Fixture contract

| Item | Value |
|------|--------|
| Project | `ledger-mini` |
| Sources | plan, slides, exit ticket (3 files) |
| Gold scoring | **Not** required to pass provisional gate |
| Dual-model / 30B | **Out of this spike** unless a later effort adds it |
| CS loops pack | **Out of this spike** |

---

## Non-goals

- Production wiring into `run_project.py`
- Dallas T2 / Arts-AV-sized corpora
- “Winning” graphing algorithm bakeoff
- Auto-rebuild on every finding
- L0/calendar-coupled rebuild inputs
- Pedagogy quality scoring as part of assemble

---

## Research anchors (do not re-litigate)

- [Assemble → review → reassemble literature](../../.plan/graph-review-rebuild-spike/tickets/01-assemble-review-reassemble-literature.md)
- [Embedded vs separate assessment attachment](../../.plan/graph-review-rebuild-spike/tickets/02-embedded-vs-separate-assessment.md)
- [When instructional graphs get revised after review](../../.plan/graph-review-rebuild-spike/tickets/03-graph-revision-after-review.md)

Assets: `.plan/graph-review-rebuild-spike/assets/`
