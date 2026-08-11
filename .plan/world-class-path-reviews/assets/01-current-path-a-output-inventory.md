# Current Path A output inventory

**Ticket:** [01-current-path-a-output-inventory](../tickets/01-current-path-a-output-inventory.md)  
**Question:** What does Path A emit today on golden Dallas (and one Bluebonnet sample if present): `path_a/findings.json` shape, LESSON-PLAN plate fields, approximate length, and which signals a human could already use vs noise — so later tickets reshape passes against reality, not the doc alone?  
**Method:** Read `workflows/lesson_plan.py`, `lesson_plan_fill.py`, `docs/PATH-A-LESSON-PLAN.md`, `workflows/run_paths.py`, checklist `workflows/checklists/daily_lesson_plan.yaml`; inventory on-disk artifacts under `projects/dallas-career-2026/` and `projects/bluebonnet-math-2026/` (main tree + e2e runs).  
**Date:** 2026-08-03  
**Constraint:** Read-only on product code and project outputs; this file is the research deliverable.

---

## 1. What Path A is designed to emit

From `docs/PATH-A-LESSON-PLAN.md` and `workflows/lesson_plan.py` / `workflows/run_paths.py`:

| Step | Name | On-disk shape today |
|------|------|---------------------|
| **A1** | Inventory cited chunks | `steps.A1`: `element_count`, `by_element_type`, `doc_ids` |
| **A2** | Standards & learning intention | `steps.A2.teks` / `.objective`: each `{status, count, cites[]}` — status `PRESENT`\|`MISSING` |
| **A3** | Backward design coherence | `steps.A3`: booleans + `mismatches[]` + `status` `COHERENT`\|`PARTIAL`\|`MISSING` |
| **A4** | Assessment path | `steps.A4.formative` / `.summative`: `{status, items[{element_id, excerpt}]}` (capped at 5) |
| **A5** | Hunter structure matrix | `steps.A5`: `hunter_core_present` / `hunter_core_total` + `matrix[{id, label, status, cite}]` (8 cores) |
| **A6** | Model place evidence | Full placements in top-level `a6_fields`; summary only in `steps.A6` as `{method, present}` |
| **A7** | Access & language supports | `steps.A7.elps` / `.accommodations`: `{status, cites[]}` |
| **A8** | Emit artifacts | Writes `path_a/findings.json` + per-routed-doc `path_a/<doc_id>.json`; `steps.A8` records `emit_paths` + `status: emitted` |

**Also after Path A** (`run_paths.py` → `write_unit_lesson_plans_from_path_a`): per-unit plates at `output/teachers/<unit_id>/LESSON-PLAN.md` (+ `.json`, optional `.pdf`). Plates are primarily **unit discovery fill** from `lesson_plan_fill.py`; Path A only overlays metadata `path_a: {hunter: <A5>, a6_method}` onto `LESSON-PLAN.json` and re-renders the MD — it does **not** replace plate field text with A6 placements (comment in `lesson_plan.py` says unit plate stays discovery fill).

**Citation style (code):** excerpts via `_trunc` (`EXCERPT_CAP = 500` chars, newlines → spaces, trailing `…`). Plate MD cites as `_(Source: <title|doc_id>)_`. Findings JSON cites are bare truncated excerpt strings (A2/A5/A7) or `{element_id, excerpt}` (A4). A6 fields add `sources: [<doc_id>]` and `element_id`.

**Guardrail (doc + code):** PRESENT / MISSING / mismatch from evidence only; never invent lesson content.

---

## 2. Samples found on disk

### Dallas career (golden) — Path A present

| Location | Artifacts |
|----------|-----------|
| `projects/dallas-career-2026/path_a/` | `findings.json` (~22 KB) + **33** per-doc JSON (mix of current 19 routed lesson_plan docs + older leftover doc ids) |
| `projects/dallas-career-2026/e2e/runs/nemotron3-nano-30b/path_a/` | `findings.json` (~23 KB) + **19** per-doc JSON (matches routed set) |
| `projects/dallas-career-2026/e2e/runs/grok-4.5/path_a/` | `findings.json` (~23 KB) + **19** per-doc JSON |
| `projects/dallas-career-2026/e2e/runs/nvidia-*` | **No** `path_a/` directory |
| `projects/dallas-career-2026/output/teachers/*/LESSON-PLAN.md` | **18** unit plates (main tree) |
| `…/e2e/runs/nemotron3-nano-30b/output/teachers/*/LESSON-PLAN.*` | **18** units with md/json/pdf |
| `…/e2e/runs/grok-4.5/output/teachers/*/LESSON-PLAN.md` | **18** units (json may lack `path_a` overlay on some runs) |

Route map (Dallas): **19** docs with `workflow_id: lesson_plan` / `path: A` (e.g. `052a682bd60f` Family and Community Wellness lesson plan).

### Bluebonnet math — Path A shell only

| Location | Artifacts |
|----------|-----------|
| `projects/bluebonnet-math-2026/path_a/findings.json` | Exists (~4.4 KB) but **`doc_ids: []`**, all steps empty/MISSING |
| `projects/bluebonnet-math-2026/e2e/runs/grok-4.5/path_a/findings.json` | Identical empty shell |
| `projects/bluebonnet-math-2026/layer0/route-map.json` | **Missing** on main tree |
| `…/e2e/runs/grok-4.5/layer0/route-map.json` | **0** `lesson_plan` routes — counts: `teacher_support: 20`, `student_practice: 29`, `standards_pacing: 10`, `general: 10`, `quiz: 1` |
| Unit LESSON-PLAN plates | **Present** via discovery fill (not Path A evidence): main `output/teachers/*/LESSON-PLAN.md` (15 units); e2e grok (6 units). Closest substitute for “what a human sees as a lesson plate” when Path A itself is a no-op. |

**Explicit gap:** Bluebonnet has **no non-empty Path A findings**. Teacher editions / student materials route off Path A, so A1–A7 never see Layer 0 elements. Later tickets must not treat Bluebonnet `path_a/findings.json` as a populated golden — use Dallas for Path A JSON shape; use Bluebonnet plates only as discovery-fill contrast.

---

## 3. `path_a/findings.json` shape (Dallas reality)

### Top-level keys

```text
project_id, workflow_id ("lesson_plan"), path ("A"),
doc_ids[], steps{A1…A8}, a6_fields{}, emit_paths[]
```

Notes from real files:

- Runtime `status: "ready"|"skipped"` is set on the return dict in `run_path_a_for_project` **after** the final write in some paths — **persisted `findings.json` does not include `status`** on Dallas or Bluebonnet samples inspected.
- `emit_paths` is always `["path_a/findings.json"]` even when content is empty (Bluebonnet).
- `steps.A6` is a **summary** (`method`, `present`); full field map lives in sibling key `a6_fields`, not under `steps`.

### Approximate lengths (bytes / lines)

| Sample | Bytes | Lines | `doc_ids` | A1 elements | A5 Hunter | A6 method / present |
|--------|------:|------:|----------:|------------:|-----------|---------------------|
| Dallas main | 21 748 | 326 | 19 | 182 | 8/8 | `code_fallback` / 11 |
| Dallas e2e `nemotron3-nano-30b` | 23 074 | 326 | 19 | 137 | 8/8 | `code_fallback` / 11 |
| Dallas e2e `grok-4.5` | 22 516 | 326 | 19 | (same shape) | 8/8 | **`model`** / 9 |
| Bluebonnet main & e2e grok | 4 418 | ~212 | **0** | 0 | 0/8 | `code_fallback` / 0 |

Per-doc sidecar: ~11.5–12.8 KB each; keys `{doc_id, hunter, placed_fields}`. **Important:** every per-doc file on Dallas carries the **same project-scoped** A5 matrix and A6 placements — only `doc_id` differs. They are not per-document audits.

### Step-by-step field detail (Dallas e2e nemotron golden)

**A1** — `by_element_type` example: `standards_objectives: 17`, `hook_engagement: 24`, `guided_practice: 23`, `independent_practice: 18`, `assessment_checkpoint: 21`, `direct_instruction: 20`, `logistics_materials: 7`, `reflection_closure: 4`, `unclear: 3`. Useful as corpus inventory; not unit-scoped.

**A2** — TEKS `PRESENT` (count 15) with cites that often start with `--- TABLE --- … TEKS Student Expectation(s): §127.2…`. Objective `PRESENT` with cleaner learning-goal cites when Layer 0 typed them well (e.g. Human Services learning goals). Status enums are human-readable.

**A3** — Dallas: `status: COHERENT`, `mismatches: []`, all three booleans true. Binary project-level coherence only (no per-lesson mismatch narrative).

**A4** — formative/summative `PRESENT` with up to 5 `{element_id, excerpt}` items. Example formative cite: peer-feedback / Evaluate block tied to `052a682bd60f-e6`. Ambiguous checkpoints default to formative in code.

**A5** — Always 8 rows (`anticipatory_set` … `closure`). Dallas samples show **8/8 PRESENT** with one `cite` string each. Labels match checklist (`1. Anticipatory set (hook / Do Now / Engage)`, etc.).

**A6** — 14 field ids (see §4). Values: `{status, text, sources, element_id}`. `lesson_title` often MISSING under A6 (A6 does not use `fill_from: manifest`; plates fill title separately). `elps_language` / `accommodations` MISSING on Dallas Path A. Grok model place: 9 PRESENT (dropped some structure fields vs code_fallback’s 11).

**A7** — Dallas: ELPS and accommodations both `MISSING` / empty cites (career lesson plans lack those keywords).

**A8** — `{step, emit_paths, status: "emitted"}`.

---

## 4. LESSON-PLAN plate fields (reality)

Checklist: `workflows/checklists/daily_lesson_plan.yaml` version `v1-test-draft-daily-lesson`, framework labeled `test_draft` in MD (JSON may say `framework: test_draft`).

### Field ids (14) — sections

| Section | Field ids |
|---------|-----------|
| Lesson header | `lesson_title`, `learning_objective`, `teks`, `materials` |
| Instructional sequence (Hunter core) | `anticipatory_set`, `objective_purpose`, `input`, `modeling`, `check_for_understanding`, `guided_practice`, `independent_practice`, `closure` |
| Supports | `elps_language`, `accommodations` |

### Plate JSON keys

```text
unit_id, title, checklist_version, framework, fields{}, summary{},
path_a?   # overlay when Path A ran: {hunter: <A5 object>, a6_method}
```

Each `fields.<id>`: `{label, section_id, section_label, status, text, sources[]}`.

MD structure: title → disclaimer → unit/framework/checklist/structure-core summary → **Structure matrix** table (8 rows PRESENT/MISSING) → per-field `###` blocks with `**Status:**` and either excerpt+`_(Source: …)_` or `*(not found in uploaded materials)*`.

### Approximate lengths (LESSON-PLAN.md)

| Corpus | n units | Bytes min / median / max | Lines min / med / max | Plate present (of 14) | Hunter core on plate |
|--------|--------:|--------------------------|------------------------|------------------------|----------------------|
| Dallas main | 18 | 9.2k / 13.6k / 17.4k | 141 / 157 / 161 | 10–13 | 6–8 |
| Dallas e2e nemotron | 18 | 7.0k / 12.9k / 17.5k | 143 / 157 / 165 | 11–13 | 7–8 |
| Dallas e2e grok | 18 | 9.8k / 13.8k / 20.3k | 147 / 161 / 165 | 11–13 | 7–8 |
| Bluebonnet main (substitute) | 15 | 17.6k / 20.4k / 21.8k | 163 / 173 / 173 | 13–14 | **8/8** |
| Bluebonnet e2e grok (substitute) | 6 | 21.8k / 23.5k / 24.1k | 167 / 171 / 173 | 13–14 | **8/8** |

Companion `LESSON-PLAN.json` is typically ~15–26 KB. PDFs also emitted on e2e nemotron / Bluebonnet runs.

**Overlay inconsistency:** Dallas e2e nemotron plates carry `path_a.hunter` showing **8/8** (project-level Path A). Bluebonnet e2e plates carry `path_a.hunter` showing **0/8** while the plate’s own `summary.hunter_core_present` is **8** — Path A overlay and plate fill disagree because Path A saw zero routed docs.

---

## 5. Useful signals vs noise (concrete)

### Already usable by a human (keep / promote in later one-pager)

1. **Binary PRESENT/MISSING on Hunter cores (A5 matrix / plate matrix)** — Fast structure inventory. Example: agriculture plate matrix all eight **PRESENT** with unit-local hook cite *“How do we grow Plants? Write it down on a Sticky note…”* (`_(Source: Agriculture- Plant Science)_`).
2. **A2 TEKS / objective status + short cites** — When cites include `§127.2` / `TEKS Student Expectation(s)` or explicit Learning Goals, auditors can verify standards presence without opening every PDF.
3. **A3 `mismatches` codes** — `activities_without_objective`, `assessment_without_objective`, `objective_without_assessment` are actionable when non-empty (Dallas golden currently empty / COHERENT).
4. **A4 formative vs summative split with `element_id`** — Traceable to Layer 0 rows (e.g. Evaluate / peer feedback blocks).
5. **A7 MISSING on Dallas** — Honest gap signal for ELPS / accommodations in CTE career plans.
6. **Plate `summary` counts** — `present` / `missing` / `hunter_core_present` give a one-line health read per unit.

### Noise / misleading (do not treat as quality bar without reshaping)

1. **Project-scoped Path A cites bleed across units** — Single `findings.json` pools all 19 lesson_plan docs. A5 cites for one matrix jump careers: anticipatory_set = Family & Community Wellness; input / independent_practice = aircraft-carrier / paper-airplane engineering; closure = “requirements to become a teacher?”. A human reading Path A alone cannot trust cites as *this lesson’s* evidence.
2. **Per-doc `path_a/<doc_id>.json` duplicates project findings** — Looks doc-scoped; is not. Wastes ~12 KB × N and invites false trust.
3. **Table dump / OCR residue in cites** — Many A2/A6 strings start with `--- TABLE ---` and repeat pipe-separated cells; ~7–11 `--- TABLE ---` markers and ~26–28 `…` truncations per Dallas findings file. High character count, low reading value.
4. **False PRESENT on wrong Hunter slot** — Agriculture plate `modeling` PRESENT with TEKS §130.2 soil/plant text (standards pasted into “I do”), not a demonstration. Bluebonnet `elps_language` PRESENT with TEKS-addressed TOC / materials prose — keyword collision, not language supports.
5. **Repeated / near-duplicate excerpts** — Same Evaluate peer-feedback paragraph repeated three times inside one A4 formative excerpt; plate fields often paste 2–3 overlapping chunks for one field.
6. **A6 vs plate divergence** — A6 `lesson_title` MISSING while plate title PRESENT from manifest; A6 does not drive plate text today. Grok `method: model` drops fields code_fallback marks PRESENT → unstable “present” counts across runs.
7. **Inflated 8/8 Hunter on corpus aggregate** — Project-level A5 8/8 means “some lesson somewhere had each slot,” not “each Dallas unit lesson is complete.”
8. **Bluebonnet empty Path A + rich plates** — Empty `path_a/findings.json` still `A8: emitted`; plates look “full” from teacher-edition discovery fill. Path A quality work cannot use Bluebonnet findings as a positive golden without fixing routing (lesson grain / `lesson_plan` doc_type).

### Citation style summary

| Artifact | Style | Cap |
|----------|-------|-----|
| `findings.json` A2/A5/A7 | Truncated excerpt string | ~500 chars + `…` |
| `findings.json` A4 | `{element_id, excerpt}` | excerpt truncated |
| `findings.json` A6 / per-doc `placed_fields` | `{status, text, sources[doc_id], element_id}` | text truncated |
| `LESSON-PLAN.md` | Excerpt + `_(Source: <human title>)_` | multi-pick join; each pick truncated |

---

## 6. Implications for later tickets (reshape against reality)

- **Pass design** should assume today’s Path A is a **project-level bag of lesson_plan docs**, not lesson-node or unit-scoped review — unless a new pass re-scopes evidence.
- **One-page artifact** should prefer: unit plate matrix + 1 cite/field from **unit fill**, plus A3 mismatch codes and A7 gaps — not raw `findings.json` dumps (~22 KB of mixed cites).
- **Quality call** cannot sit on A5 PRESENT alone: false slot fills and cross-unit cites are the dominant failure mode already visible.
- **Bluebonnet** is a routing / lens-assignment fixture for Path A emptiness; Dallas e2e `nemotron3-nano-30b` (or main `path_a/`) is the populated golden for JSON shape.
- **A6 model place** is optional and currently inconsistent (`code_fallback` vs `model`); plate text path ignores A6 field bodies — treat A6 as experimental placement metadata, not teacher-facing output.

---

## Gist for the map

- Dallas Path A emits one project-level `path_a/findings.json` (~22–23 KB, ~326 lines) with steps **A1–A8**, top-level `a6_fields` (14 plate ids), and `emit_paths`; plus duplicate per-doc JSON that only changes `doc_id`.
- Status language is concrete today: `PRESENT`/`MISSING`, A3 `COHERENT`/`PARTIAL`/`MISSING`, A6 `method` (`code_fallback`|`model`), A8 `emitted`; cites are ≤~500-char truncated excerpts (often `--- TABLE ---` noise) or `_(Source: …)_` on unit plates.
- Unit `LESSON-PLAN.md` plates are ~7–20 KB / ~140–165 lines (Dallas), 14 fields + Hunter matrix; Path A only overlays `path_a.hunter` + `a6_method` — plate body is discovery fill, not A6 text.
- **Usable now:** per-unit matrix PRESENT/MISSING, A2 TEKS/objective flags, A3 mismatch codes, A4 formative/summative with `element_id`, A7 honest MISSING on Dallas CTE.
- **Noise now:** project-scoped cite bleed across careers, false PRESENT on wrong Hunter slots, table-dump duplicates, per-doc JSON that isn’t doc-scoped, Bluebonnet empty Path A (`doc_ids: []`) beside rich TE plates.
- **Bluebonnet:** no lesson_plan-routed docs → Path A is an empty emitted shell; closest substitute is `output/teachers/*/LESSON-PLAN.*` discovery fill (e2e grok or main tree), not `path_a/findings.json`.
