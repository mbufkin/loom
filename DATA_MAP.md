# DATA_MAP — Source of Truth for Keys & Schemas

**Purpose:** Define every primary/secondary key and the mapping from raw inputs to standardized outputs.  
**Enforcement:** Runtime shape checks live in [`schema_validate.py`](schema_validate.py). This document is the human/agent contract; code is the machine contract.  
**Rule:** If you change a key name, enum, or required field, you MUST update this file, `schema_validate.py`, and `DEPENDENCY_FLOW.md` in the same change.

---

## 1. Primary keys

| Primary key | Format | Issued by | Uniqueness scope | Notes |
|-------------|--------|-----------|------------------|-------|
| **`project_id`** | Slug: lowercase letters, digits, hyphens | Human (directory name) | Repo-wide under `projects/` | Validated by `validate_slug_id` |
| **`unit_id`** | `UNIT_ID_RE`: `^[a-z0-9.]+(?:-[a-z0-9.]+)*$` | `ingest.py` (models) / human | Per project | Directory name under `units/` MUST match |
| **`doc_id`** | 12-char hex **or** basename fallback | Filename convention / `doc_id_from_filename` | Per project | Preferred: from `doc_<hex>_<slug>.*` |
| **`element_id`** | `{doc_id}-e{n}` | `layer0.py` | Per project | Stable across re-runs if content_hash unchanged |
| **`day_id`** | `d` + integer (`d1`, `d2`, …) | Calendar authors / ingest | Per unit calendar | `DAY_ID_RE` |

### 1.1 Composite logical keys

| Composite | Composition | Used for |
|-----------|-------------|----------|
| Role expectation | `(unit_id, day_id, role)` | Layer 1 fulfillment / MISSING detection |
| Legacy placement | `(doc_id, slot, role)` | `place.py` placements |
| Overlap pair | `(unit_id_a, unit_id_b)` | `manifest.known_overlaps` → EXPECTED_OVERLAP |

---

## 2. Secondary keys & foreign references

| Field | Points to | Appears in |
|-------|-----------|------------|
| `source_file` | Filename under `sources/` | catalog, evidence, layer0 ledger |
| `matched_unit_id` / `final_unit_id` | `unit_id` in manifest | layer1 bucket-ledger |
| `matched_day_id` / `final_day_id` | `day_id` or null / supporting | layer1 bucket-ledger |
| `parent_link_unit_id` | Related unit | layer1 cross-refs |
| `fulfills_role` | `ARTIFACT_ROLES` member | layer1 bucket-ledger |
| `fulfilled_by[]` | `element_id` list | layer1 findings |
| `duplicate_of` | `element_id` | layer1 bucket-ledger |
| `taxonomy_version` | `LAYER0_TAXONOMY_VERSION` | layer0 ledger |
| `content_hash` | Hash of cleaned text | layer0 cache / idempotency |
| `regex_doc_type_prior` | `DOC_TYPES` hint | layer0 (hint only) |

---

## 3. Closed enumerations (MUST NOT invent values)

### 3.1 Artifact roles / doc types

```
lesson_plan | lesson_content | exit_ticket | quiz | answer_key | rubric |
worksheet | project_work | presentation | game_activity | lab_activity |
flex_day | other
```

Source: `schema_validate.ARTIFACT_ROLES`, `audit_lib.DOC_TYPES`.

### 3.2 Layer 0 element types

```
hook_engagement | direct_instruction | guided_practice | independent_practice |
assessment_checkpoint | reflection_closure | logistics_materials |
standards_objectives | unclear
```

Source: `schema_validate.ELEMENT_TYPES`. Version string: `v1-hypothesis`.

### 3.3 Confidence

```
high | medium | low
```

### 3.4 Layer 1 `match_status`

```
MATCH | MISMATCH | CROSS_REFERENCE | EXPECTED_OVERLAP | ORPHAN | UNVERIFIED
```

### 3.5 Layer 1 finding `status`

```
FULFILLED | MISSING | DUPLICATE
```

### 3.5a Layer 2 completeness `status`

```
COMPLETE | INCOMPLETE
```

Source: `layer2.py` (computed, not model-emitted). Version string: `v1-hypothesis`
(`LAYER2_TAXONOMY_VERSION`).

### 3.6 Placement slot (legacy)

```
d<N> | unit_supporting
```

---

## 4. Raw input → standardized output map

### 4.1 Document ingest path

| Stage | Input | Standardized output | Key fields |
|-------|-------|---------------------|------------|
| Human drop | Arbitrary `pdf/docx/pptx/xlsx/txt/…` | Files in `sources/` | Path relative to `sources/` |
| Extract | Source bytes | Plain text + meta | `source_format`, `extraction_method` |
| Catalog / scrub | Clean text | `ingest/catalog.json` or `output/<unit>/evidence/<doc_id>.json` | **`doc_id`**, `doc_type`, `content_clean`, `day_hints` |
| Ingest organize | Catalog + models | `manifest.yaml` | **`unit_id`** → `{title, calendar, documents[]}` |
| Ingest calendars | Models | `units/<unit_id>/calendar.yaml` | **`day_id`**, `expected[]` roles |
| Rollup | Calendars + optional school calendar | `pacing-plan.yaml` | Unit date spans (structural) |

### 4.2 Headline conformance path

| Stage | Input | Standardized output | Key fields |
|-------|-------|---------------------|------------|
| Layer 0 | Sources + scrub priors | `layer0/ledger.json` (list) | **`element_id`**, `doc_id`, `element_type`, citation range, `excerpt` |
| Layer 1 Phase 1 | Ledger + manifest/calendars | Placement judgments in `bucket-ledger.json` | `match_status`, `final_unit_id`, `final_day_id` |
| Layer 1 Phase 3 | Placements + expected roles | `findings.json` | `(unit_id, day_id, role)` → `status` |
| Layer 2 | Layer 0 ledger + Layer 1 findings (no model calls) | `layer2/findings.json` | `(doc_id, role)` → `status`, `components_present/missing` |
| Synthesize | Layer 1 + Layer 2 JSON | `GLOBAL-AUDIT.md`, `DASHBOARD.md`, `aggregate-stats.json` | Rollups by unit/status, plus Layer 2 completeness section |
| Render | Markdown/JSON + pacing | `*.pdf` | Presentation only |

### 4.3 Filename → `doc_id` algorithm

```
IF basename matches ^doc_([a-f0-9]+)_
    THEN doc_id = capture group 1
ELSE
    doc_id = basename with trailing ".txt" removed
```

Implementation: `audit_lib.doc_id_from_filename`.  
**MUST:** Prefer the `doc_<hex>_` convention for all new extracts so IDs stay stable across renames of the slug portion.

---

## 5. On-disk schema contracts

### 5.1 `manifest.yaml`

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `project.id` or `project_id` | Yes | string | Project identity |
| `sources_dir` | Optional | string | Default resolved at runtime |
| `units` | Yes | mapping `unit_id` → entry | Non-empty |
| `units.*.title` | Yes | string | |
| `units.*.calendar` | Yes | path string | Relative path to calendar YAML |
| `units.*.documents` or `source_files` | Yes | string list | Filenames |
| `known_overlaps` | Optional | list of `[unit_id, unit_id]` | Both IDs MUST exist in `units` |

Validator: `validate_manifest`.

### 5.2 `units/<id>/calendar.yaml`

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `unit_id` | Yes | string | MUST match directory |
| `title` | Typical | string | |
| `unit_length_days` | Optional | positive int | |
| `days` | Yes | non-empty list | |
| `days[].id` | Yes | `d<N>` | Unique within calendar |
| `days[].label` | Typical | string | |
| `days[].expected` | Yes (list) | roles from §3.1 | May be empty list only if intentional |
| `unit_supporting` | Optional | role list | Unit-level supporting artifacts |

Validator: `validate_unit_calendar`.

### 5.3 Layer 0 ledger item (`ledger.json[]`)

| Field | Required | Type |
|-------|----------|------|
| `element_id` | Yes | string |
| `doc_id` | Yes | string |
| `source_file` | Yes | string |
| `element_type` | Yes | §3.2 |
| `taxonomy_version` | Yes | string |
| `excerpt` | Yes | string (resolved citation text) |
| `excerpt_start_paragraph` | Yes | int |
| `excerpt_end_paragraph` | Yes | int |
| `inferred_position` | Yes | string (`unknown` allowed) |
| `inferred_timing` | Yes | string (`unknown` allowed) |
| `confidence` | Yes | §3.3 |
| `tier` | Yes | int |
| `content_hash` | Yes | string |
| `cited` / sanity flags | Typical | bool |

Model payload before resolve: `validate_layer0_elements`. **`element_type` is
guaranteed a single §3.2 member as of 2026-07-09** — both the main decompose
path (`build_ledger_rows`) and Layer 0-B's split path (`run_layer0b`) now run
the model's raw value through `coerce_element_type()` before writing to the
ledger (falls back to `unclear` on anything outside the enum, e.g. a
pipe-joined compound value). Ledgers built before this fix may still contain
non-conformant values; see docs/BETS.md Bet 14 for the incident writeup and
`layer2._element_types()` for the defensive `"|"`-split reader.

### 5.4 Layer 1 bucket-ledger item

| Field | Required | Type |
|-------|----------|------|
| `element_id` | Yes | FK → layer0 |
| `doc_id` | Yes | FK |
| `element_type` | Yes | §3.2 |
| `match_status` | Yes | §3.4 |
| `matched_unit_id` / `matched_day_id` | Nullable strings | Bet 4: null / “not stated” OK |
| `final_unit_id` / `final_day_id` | Typical | Resolved home |
| `fulfills_role` | Optional | §3.1 |
| `confidence` | Typical | §3.3 |

### 5.5 Layer 1 findings item

| Field | Required | Type |
|-------|----------|------|
| `unit_id` | Yes | FK |
| `day_id` | Yes | FK / slot |
| `role` | Yes | §3.1 |
| `fulfilled_by` | Yes | list of `element_id` (may be empty) |
| `status` | Yes | §3.5 |
| `reasoning` | Typical | string |

### 5.5a Layer 2 findings item (`layer2/findings.json[]`)

| Field | Required | Type |
|-------|----------|------|
| `doc_id` | Yes | FK → layer0 |
| `role` | Yes | §3.1, restricted to `ROLE_EXPECTED_COMPONENTS` keys (v1: `lesson_plan` only) |
| `taxonomy_version` | Yes | string (`LAYER2_TAXONOMY_VERSION`) |
| `components_expected` | Yes | list of §3.2 members |
| `components_present` | Yes | list of `{component, element_id, excerpt}` |
| `components_missing` | Yes | list of §3.2 members |
| `status` | Yes | §3.5a |

Computed by `layer2.compute_completeness` — no model call, no validator (pure
set arithmetic over already-validated Layer 0 `element_type` values).

### 5.6 Legacy evidence JSON

Mirrors catalog fields: `source_file`, `doc_id`, `doc_type`, `content_clean`, `day_hints`, `standards_refs`, counts, excerpts.

### 5.7 Legacy placements payload (`place.py`)

| Field | Required | Notes |
|-------|----------|-------|
| `placements[].doc_id` | Yes | |
| `placements[].slot` | Yes | `d<N>` or `unit_supporting` |
| `placements[].role` | Yes | §3.1 |
| `placements[].confidence` | Yes | §3.3 |
| `placements[].excerpt` | Yes | Citation |
| `calendar_corrections[]` | Optional | Tier A |
| `notes` | Optional | list |

Validator: `validate_placements`.

---

## 6. Policy flags that affect data

| Flag / setting | Location | Effect |
|----------------|----------|--------|
| `policy.auditor_only: true` | `config.yaml` | MUST never generate curriculum content |
| `known_overlaps` | `manifest.yaml` | Downgrades certain mismatches to EXPECTED_OVERLAP |
| `LAYER0_TAXONOMY_VERSION` | `schema_validate.py` | Retaxonomy requires Layer 0 re-run |
| `LAYER2_TAXONOMY_VERSION` | `layer2.py` | Changing `ROLE_EXPECTED_COMPONENTS` requires a Layer 2 re-run (no Layer 0/1 re-run needed) |

---

## 7. Non-keys (do not treat as identity)

| Field | Why not a PK |
|-------|----------------|
| Document title | Unstable, non-unique |
| Filename slug after hex | May change; hex is identity |
| Unit title | Display only |
| `excerpt` text | Content, not identity |
| PDF page numbers alone | Not used as Layer 0 citation unit — paragraphs are |

---

## 8. Change control checklist

Before merging a schema change:

1. [ ] Update `schema_validate.py` enums/validators  
2. [ ] Update this `DATA_MAP.md`  
3. [ ] Update `GLOSSARY.md` if a term/status is new  
4. [ ] Update `DEPENDENCY_FLOW.md` blast-radius notes  
5. [ ] Add/adjust tests in `test_schema_validate.py`  
6. [ ] Re-run Layer 0/1 on golden project if taxonomy or element shape changed  
