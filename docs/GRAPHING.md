# Graphing — hasPart assemble step (research + experiment plan)

**Status:** open design — not wired into `run_project.py` yet  
**Related:** [PIPELINE.md](PIPELINE.md), [CREATE-WORKFLOW.md](CREATE-WORKFLOW.md), [BETS.md](BETS.md) (Bets 9–11), [UNIT-RUNG.md](UNIT-RUNG.md), `workflows/packet_types.yaml`  
**Fixture under discussion:** `projects/lab-dallas-ag/` (Plant Science, 2 docs)

---

## 1. Problem this solves

Loom already answers **“was everything received?”** (ingest → Layer 0 ledger →
route → drop-check). It does **not** yet answer **“is everything known in
relation to everything else?”**

Today’s router treats documents as **peers** (Path A lesson_plan / Path B quiz /
Path C general). That is the wrong grain when:

- One file contains **two lessons** (Day 1 + Day 2 in a single deck).
- A lesson plan **describes** those days; it is not a sibling product of the deck.
- An exit ticket **belongs under** Day 2; it is not a free-floating Path B/C job.
- Referenced handouts may be **missing Materials** even when every ingested file
  was seen.

We need a dedicated step — **graphing** — that builds a Learning Commons–style
aggregation graph (`hasPart` / `spanIn` / `describes` / `uses`) so structure is
explicit before (or instead of) flat path dispatch inventing the organization.

**Drop-check stays.** Graphing adds **knownness**.

| Question | Owner today | Owner after graphing |
|----------|-------------|----------------------|
| Was every source extracted and assigned? | ingest + L0 + drop-check | unchanged |
| What instructional *subjects* exist (units, lessons)? | partial (calendar + L1 days) | **graphing** |
| How do files/spans hang under those subjects? | flat route-map | **graphing** |
| Which review workflow runs on which node? | router A/B/C | router *informed by* graph |

---

## 2. Research anchors (what we are applying)

| Source | Practice we steal |
|--------|-------------------|
| **Learning Commons K–12 curriculum ontology** | `Course` → `LessonGrouping` → `Lesson` → `Activity` / `Assessment` → `Material`, linked primarily by **`hasPart`**. Assessments and materials hang under lessons; they are not peer “paths.” See [Learning Commons curriculum reference](https://docs.learningcommons.org/knowledge-graph/entity-and-relationship-reference/curriculum). |
| **SCORM / IMS Content Packaging** | **Organization tree ≠ resource files.** Containers (items/aggregations) reference leaf resources; one resource may be referenced from multiple items. Multi-day content in one file ⇒ multiple organization nodes, one resource. |
| **UbD (Wiggins / McTighe)** | Unit grain; backward alignment: desired results → evidence → learning plan. Graph “knownness” can later score missing evidence under a lesson spine (same spirit as create-side stage bands in [CREATE-WORKFLOW.md](CREATE-WORKFLOW.md)). |
| **Faceted / multi-aspect classification** (KO tradition) | A single `doc_type` enum is not enough. Role, unit, day, and audience are **independent facets**. Graph edges carry belonging; typing alone does not. |
| **Loom Bet 9–11** | Extract atoms first (L0); categorize/place as a **separate** phase; never blend model judgment with code equality checks. Graphing is that place/assemble phase at **Lesson** grain, not a second extraction. |

### Design choice already agreed (lab-dallas-ag)

When Day 1 and Day 2 live **inside one file**, we **break them apart in the
graph**, not on disk:

- One `Material` node for the file.
- Separate `Lesson` nodes (`d1`, `d2`) with **span pointers** (paragraph ranges
  and/or Layer 0 `element_id`s) into that file.

Hand-built toy for Ag (review only; may later live under
`projects/lab-dallas-ag/graph/HAS-PART.json`):

- Unit `plant-science` `hasPart` Lessons `d1`, `d2`.
- Deck `b5e364…` is `Material` (`lesson_content` proposed; Loom today typed it
  `other` → Path C degraded).
- Plan `e9e6ac…` is spine `Material` that **`describes`** both lessons.
- `d2` `hasPart` soil-lab `Activity` and exit-ticket `Assessment`.
- Note sheet + soil handout are **`referenced_missing`** Materials (`uses`).

---

## 3. Proposed pipeline placement

**Recommendation:** graphing runs **after Layer 0 (+ unit calendars), before the
router**. Do **not** route flat A/B/C first and then try to rearrange — the
router would freeze whole-file peer types (exactly the Ag `other` failure).

```text
sources/
  → ingest.py          organize docs into units + calendars
  → layer0.py          cited elements (atoms)
  → GRAPHING (new)     Unit → Lesson → Activity/Assessment/Material + edges
  → route.py           dispatch review work for graph nodes / materials
  → path A/B/C…        typed passes (evolve toward node-aware passes)
  → layer1.py          conformance (migrate toward graph edges)
  → …
```

Rationale:

1. Graphing needs **atoms + day slots** (L0 + calendar) — already available.
2. Router should **dispatch work**, not invent structure.
3. Drop-check / “nothing forgotten” remains an ingest+L0 property; graphing
   reports **orphan resources**, **lessons without spine**, **missing evidence**.

This placement is a **bet to validate**, not locked code. Alternate placements
are listed in §5 for A/B.

---

## 4. Step contract (draft)

### Name

`graphing` (working title). Possible future module: `graphing.py` or
`layer_graph.py`. Artifact dir (proposed): `projects/<id>/graph/`.

### Inputs

| Input | Path / source | Required |
|-------|---------------|----------|
| Manifest units + document lists | `manifest.yaml` | yes |
| Unit calendars (day ids, expected roles) | `units/*/calendar.yaml` | yes |
| Layer 0 ledger (elements, spans, types) | `layer0/ledger.json` | yes |
| Source texts (for day-boundary confirmation) | `sources/` | yes |
| Ingest catalog (titles, priors) | `ingest/catalog.json` | optional hint |
| Regex day / doc-type priors on ledger rows | ledger fields | hint only (Bet doctrine) |

### Outputs

| Output | Purpose |
|--------|---------|
| `graph/HAS-PART.json` | Nodes + edges; machine SoT for knownness |
| `graph/HAS-PART.md` | Human-readable tree + open gaps |
| `graph/REPORT.md` | Counts: lessons, span coverage, missing materials, unattached elements |
| (later) tickets into `_loom_feedback.yaml` | Ambiguous day splits, untyped materials, etc. |

### Node types (v0 — Learning Commons–aligned)

| Type | Meaning in Loom |
|------|-----------------|
| `Course` | Project / program wrapper |
| `LessonGrouping` | Unit (`unit_id`) |
| `Lesson` | Day (or equivalent session); **span pointers** into Material(s) |
| `Activity` | Lab, practice block, optional engagement task |
| `Assessment` | Exit ticket, quiz, checkpoint |
| `Material` | A source file (or referenced-missing resource) |

### Edge types (v0)

| Rel | Meaning |
|-----|---------|
| `hasPart` | Aggregation (unit→lesson, lesson→activity/assessment, unit→material) |
| `spanIn` | Lesson (or activity) occupies a span inside a Material file |
| `describes` | Spine plan Material describes a Lesson |
| `uses` | Activity/lesson references a Material (may be missing) |
| `hasEducationalAlignment` | (later) TEKS / standards nodes |

### Invariants

1. **Every ingested source file** appears as exactly one `Material` (or is
   explicitly marked non-curriculum noise with a ticket).
2. **Every Layer 0 element** is attached to ≥1 Lesson or to unit-supporting
   Material — or listed in `unattached_elements` (failure to hide orphans).
3. **Files are not physically split**; multi-subject files get multiple Lesson
   (or Activity) nodes with spans.
4. **Unknown is allowed** — emit `status: unresolved` rather than force-fit
   (same doctrine as Layer 1 “not stated”).
5. Graphing does **not** score pedagogy quality; it only asserts structure and
   inventory (completeness/knownness). Quality stays on Path / rung passes.

### Failure modes to instrument

| Failure | Symptom | Signal |
|---------|---------|--------|
| Missed day split | Two days in one Lesson span | Calendar `unit_length_days` vs lesson count |
| Over-split | Spurious Lesson nodes | Empty or logistics-only spans |
| Peer-plan mistake | Plan not linked via `describes` | Spine present but lessons have no plan edge |
| Silent missing handout | No `referenced_missing` node | Narrative mentions sheet; no `uses` edge |
| Forgotten file | Material absent | Violates invariant 1 vs `sources/` |

---

## 5. Options to A/B (how the model sorts)

We will **not** pick a pass shape from intuition alone. Each option below is an
experiment candidate against the same gold: hand-built Ag graph (+ later a
second lab unit).

### Option A — Two-pass (type, then attach)

1. **Pass 1:** each source file → Material role (`lesson_plan`, `lesson_content`,
   `assessment`, …) with confidence / unknown.
2. **Pass 2:** given unit calendar + materials + L0 elements → emit Lessons,
   spans, `hasPart` / `describes` / `uses`.

**Pros:** Separates typing from belonging (Bet 11 spirit).  
**Cons:** Two model stages; Pass 1 errors poison Pass 2.

### Option B — Unit-scoped assemble

For each unit: provide calendar days + that unit’s docs + element summaries →
emit the unit subgraph in one (or few) calls.

**Pros:** Matches Layer 1’s unit grain; bounded context.  
**Cons:** Cross-unit Materials / hub docs need a follow-up pass.

### Option C — Global rearrange after full ingest

One (chunked) pass over all files after ingest+L0; model “sees the pile” and
emits the full course graph.

**Pros:** Matches the instinct “look at everything, then arrange.”  
**Cons:** Context limits; harder to resume; higher contradiction risk.

### Option D — Code-first spans + model repair

Deterministic day-header / calendar heuristics propose Lesson spans; model only
confirms, splits, or merges and adds Activity/Assessment/`uses` edges.

**Pros:** Cheap, testable, resumable; fits “regex as hint” doctrine.  
**Cons:** Weak on docs without clear Day N headers.

### Placement variants (orthogonal to A–D)

| Placement | Idea |
|-----------|------|
| **P1 (recommended)** | After L0, before router |
| **P2** | After router — graph as assemble/stitch |
| **P3** | After Layer 1 — use MATCH/day pins as primary edges |

Placement and pass shape should be crossed in experiments (at least P1×A,
P1×B, P1×D on Ag before widening).

---

## 6. Experiment plan + documentation rules

### Risks we are explicitly guarding

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| **Ag is too small** | 2 sources / 29 elements can validate *shape* (Lesson spans, `describes`, missing `uses`) but cannot prove sorting under peer pressure (exit tickets as separate files, rubrics, slides, multi-day plans). Dallas `agriculture` unit is the **same two docs** — not a second scale tier. | Tiered fixtures (§6.1). Ag = gold + smoke only. **Score** on mid-size units. |
| **Grok ≫ local 30B** | `config.cursor.yaml` uses `grok-4.5` via Cursor SDK. Local / NIM path is ~30B (e.g. `config.nvidia.example.yaml` → `nvidia/nemotron-3-nano-30b-a3b`). A graphing method that only works on Grok is not production-ready for the box we actually run. | Every RESULTS row must record `LOOM_CONFIG` + `analyst_model`. Prefer **code-first (option D)** so the local model repairs rather than globally rearranges. Before calling a pass shape “winner,” require at least one **dual-model** row (Grok + 30B) on the same fixture/gold. Grok-only wins are provisional. |

### 6.1 Tiered fixtures

| Tier | Fixture | Size (approx) | Role |
|------|---------|---------------|------|
| **T0 shape / gold** | `projects/lab-dallas-ag/` | 2 docs, 29 elements, 2-day calendar | Hand-built gold `HAS-PART`. Schema, invariants, day-split logic. **Not** a scale verdict. |
| **T0 note** | `dallas-career-2026` unit `agriculture` | Same 2 docs as lab-dallas-ag | Do **not** treat as independent scale evidence. |
| **T1 score (first real test)** | Arts AV unit — `lab-arts-av` and/or `dallas-career-2026` unit `arts-av-technology` | **8 docs** (plan, slides, notes, 3 exit tickets, 2 rubrics) | First fixture where Materials are mostly **separate files** that must hang under Lessons. Build gold graph here before trusting any option. |
| **T2 stress** | One larger Dallas unit (e.g. `career-cluster`, ~27 docs) or full `lab-dallas-career` slice | 27–111 docs | Only after a method clears T1 on **both** Grok and 30B (or D-path where 30B matches Grok within agreed delta). |

**Decision (2026-07-31):** Gold on Ag for shape; **score on Arts AV** (not on dallas agriculture alone).

### Gold artifacts

- **T0 gold:** hand-validated Ag graph (Day split at Day 2 header / e14; plan
  `describes` both lessons; exit ticket under `d2`; two referenced_missing
  handouts). Persist under `projects/lab-dallas-ag/graph/` when approved.
- **T1 gold:** hand-validated Arts AV `HAS-PART` (separate exit-ticket files →
  `Assessment` under the right Lesson; plan/slides/`describes`/`spanIn`;
  rubrics attached without becoming false parents). Build before A/B scoring.

### Metrics (minimum)

| Metric | Definition |
|--------|------------|
| Material coverage | `|Materials ∩ sources| / |sources|` → must be 1.0 |
| Element attachment | fraction of ledger element_ids on some node |
| Lesson recall/precision vs gold | lesson span boundaries (IoU on element sets or file membership) |
| Edge F1 vs gold | `hasPart` / `spanIn` / `describes` / `uses` |
| Missing-material recall | referenced handouts detected (T0) |
| Separate-assessment attach | exit tickets / quizzes as files land under correct Lesson (T1+) |
| Degraded-type recovery | multi-day deck not left as unstructured peer-only `other` |
| Model transfer gap | metric delta (Grok − 30B) on same fixture; flag if Lesson IoU or Edge F1 drop > agreed threshold (start: 0.15) |

### Documentation requirement (non-negotiable)

Every experiment run must leave:

1. **Config** — option id (A/B/C/D), placement (P1/P2/P3), **`LOOM_CONFIG`**,
   **`analyst_model` / `verifier_model`**, prompt hash or file path.
2. **Fixture tier** — T0 / T1 / T2 + project id + unit scope if any.
3. **Raw model I/O** — under `projects/<id>/graph/.raw/` or
   `experiments/graphing/results/<run_id>/`.
4. **Graph output** — `HAS-PART.json` for that run.
5. **Scorecard** — metrics vs gold in a row of
   `experiments/graphing/RESULTS.md` (append-only).
6. **Narrative note** — what failed and whether failure was typing, spanning,
   edge semantics, or **model-capacity** (worked on Grok, failed on 30B).

No “we tried it and it felt better” without a RESULTS row.  
No “option X wins” without a **T1** score.  
No production claim without a **dual-model** T1 row (or written waiver).

### Suggested first runs

1. Persist **T0 Ag gold** (human-approved).
2. Hand-build **T1 Arts AV gold** (the real test target).
3. **P1 × D** on T0 (smoke) then T1 — code day/file attach + model repair
   (best chance local 30B survives).
4. **P1 × B** on T1 — unit-scoped assemble; run **Grok and 30B**.
5. **P1 × A** on T1 only if B/D need a typing-separated baseline.
6. T2 only after T1 dual-model clearance.

---

## 7. Relationship to existing Loom pieces

| Piece | Stays / changes |
|-------|-----------------|
| Drop-check / “nothing forgotten” | Stays; graphing must not hide unattached files |
| `packet_types.yaml` completeness slots | Later: evaluate slots **on the graph** (lesson/unit inventory) |
| Path A/B/C | Keep as **review lanes**; evolve inputs from graph nodes |
| Layer 1 MATCH/UNVERIFIED | Overlaps graphing; may shrink once graph edges are SoT for belonging |
| Create workflow UbD bands | Consume graph gaps (`Assessment` missing under Lesson) instead of flat role holes only |

---

## 8. Open questions

1. Is `Lesson` always a calendar day, or can TE multi-lesson docs create Lessons
   without `dN` ids?
2. Should unit-supporting Materials (`lesson_plan`) be `hasPart` of the unit
   only, or also `hasPart` of each Lesson they describe?
3. Do we promote graphing to a numbered layer (`layer_graph`) or keep a named
   stage (`graphing.py`) beside route?
4. When L0 elements disagree with day headers, who wins — calendar, headers, or
   model with ticket?
5. How do hub/overview docs (career-cluster intros) attach without becoming
   false parents of every unit?

---

## 9. Decision log

| Date | Decision |
|------|----------|
| 2026-07-31 | Ag toy graph: 2-day split at Day 2 header is correct (matches lesson plan). |
| 2026-07-31 | Multi-day files → Lesson nodes with **span pointers**; do not physically split sources. |
| 2026-07-31 | Prefer graph **before** router; validate via experiments. |
| 2026-07-31 | Pass shape (A/B/C/D) **not chosen** — A/B test + document every run. |
| 2026-07-31 | This doc created as the SoT for the graphing research thread. |
| 2026-07-31 | Ag too small for scale verdict; dallas `agriculture` ≠ new fixture (same 2 docs). **Score on Arts AV (T1).** |
| 2026-07-31 | Grok≠30B risk: RESULTS must record model; dual-model T1 required before a winner; prefer option D for local survival. |

---

## 10. Next actions (when we leave research)

1. Persist Ag gold graph under `projects/lab-dallas-ag/graph/` (human-approved).
2. Add `experiments/graphing/` harness + `RESULTS.md` skeleton.
3. Implement **P1 × D** prototype (code span proposal + model repair) only after
   gold + metrics exist.
4. Link a short pointer from [PIPELINE.md](PIPELINE.md) once an option wins.
