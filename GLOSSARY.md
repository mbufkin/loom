# GLOSSARY — Domain & Technical Dictionary

**Purpose:** Semantic alignment for humans and AI agents.  
**Rule:** When introducing a new acronym or domain term in code or docs, you MUST add a row here in the same change.

---

## 1. Product & charter

| Term | Definition |
|------|------------|
| **Crystallize** | This product: a read-only curriculum document auditor. Documents in → audit reports out. |
| **Auditor charter** | The system MAY extract, classify, organize, place, and report. It MUST NEVER write lessons, assessments, rubrics, or fill empty instructional slots. |
| **Structural fill** | Inferring maps (calendars, pacing, year-at-a-glance) without inventing instructional content. See `docs/STRUCTURAL-FILL.md`. |
| **Content fill** | Authoring missing lessons/assessments — **forbidden**. |
| **Context Layer** | This documentation set (`PROJECT_INDEX`, `PROJECT_STRUCTURE`, `GLOSSARY`, `DATA_MAP`, `DEPENDENCY_FLOW`, `CONTRIBUTING`, `TESTING_STRATEGY`) — metadata/navigation/governance only; no functional logic change. |

---

## 2. Pipeline stages & engines

| Term | Definition |
|------|------------|
| **Ingest** | `ingest.py` — models organize source files into units and provisional calendars; writes `manifest.yaml` and `units/*/calendar.yaml`. |
| **Rollup** | `rollup.py` — code rolls unit calendars into `pacing-plan.yaml` (inferred year map). |
| **Scrub** | `audit_lib.scrub_document` — deterministic cleaning + text extract (used by Layer 0 / ingest). The old `scrub.py` CLI is archived. |
| **Place (archived)** | Former `place.py` — whole-document calendar slots; see `archive/legacy-unit-audit/`. Not part of `./run-audit`. |
| **Layer 0** | `layer0.py` — element-level decomposition with verbatim paragraph-range citations. |
| **Layer 1** | `layer1.py` — placement conformance of elements against manifest/calendar vocabulary. |
| **Layer 2** | `layer2.py` — lesson structural completeness: for each document Layer 1 already confirmed fulfills a role, checks whether its own elements include the internal parts a complete document of that role should have. Zero new model calls (Bet 14). |
| **Synthesize** | `synthesize.py` — builds global markdown/stats; prefers Layer 1 outputs, also renders Layer 2's completeness section. |
| **Render** | `render_pdf.py` — PDF packaging of unit and global reports. |
| **Analyst** | Model role in `config.yaml` (`analyst_url` / `analyst_model`) — primary judgment pass. |
| **Verifier** | Model role for independent second pass (may be same endpoint/model per BETS doctrine). |
| **Code vs Models** | Deterministic stages (extract, rollup, PDF, many stats) vs judgment stages (ingest organize, place, Layer 0/1). |

---

## 3. Identifiers (see also DATA_MAP)

| Term | Definition |
|------|------------|
| **project_id** | Slug for a curriculum corpus under `projects/<project_id>/`. |
| **unit_id** | Slug for a module/unit (e.g. `engineering`, `unit-1-fundamentals-leadership`). |
| **doc_id** | Stable document key — 12-hex from `doc_<hex>_…` filenames, else basename without `.txt`. |
| **element_id** | Stable element key — `{doc_id}-e{n}` produced by Layer 0. |
| **day_id** | Calendar day key — `d1`, `d2`, … (`DAY_ID_RE`). |
| **slot** | Placement target — a `day_id` or `unit_supporting`. |
| **content_hash** | Hash of cleaned content used for Layer 0 cache/idempotency. |

---

## 4. Artifact roles & document types

Closed vocabulary in `schema_validate.ARTIFACT_ROLES` / `audit_lib.DOC_TYPES`:

| Role / type | Meaning |
|-------------|---------|
| `lesson_plan` | Instructional plan document |
| `lesson_content` | Slides / instructional content body |
| `exit_ticket` | End-of-lesson formative check |
| `quiz` | Quiz / Quizizz-style assessment |
| `answer_key` | Key for quiz/worksheet |
| `rubric` | Scoring rubric |
| `worksheet` | Student worksheet |
| `project_work` | Multi-day project materials |
| `presentation` | Student/teacher presentation artifact |
| `game_activity` | Game / bingo / engagement activity |
| `lab_activity` | Lab / hands-on activity |
| `flex_day` | Flexible / buffer day marker |
| `other` | Unclassified residual |

---

## 5. Layer 0 taxonomy (element types)

Versioned as `LAYER0_TAXONOMY_VERSION` (`v1-hypothesis` — working hypothesis, not settled law):

| `element_type` | Meaning |
|----------------|---------|
| `hook_engagement` | Opening hook / engagement |
| `direct_instruction` | Teacher-led explanation |
| `guided_practice` | Supported practice |
| `independent_practice` | Solo practice |
| `assessment_checkpoint` | Check for understanding / quiz item block |
| `reflection_closure` | Exit reflection / close |
| `logistics_materials` | Materials, timing, admin logistics |
| `standards_objectives` | Standards / objectives language |
| `unclear` | First-class insufficient-evidence answer (Bet 4) |

---

## 6. Layer 1 match statuses

| Status | Meaning |
|--------|---------|
| **MATCH** | Element lands in the unit/day it claims or evidence supports. |
| **MISMATCH** | Element’s claimed home conflicts with evidence / vocabulary. |
| **CROSS_REFERENCE** | Element legitimately points across units (cited). |
| **EXPECTED_OVERLAP** | Overlap allowed by human-curated `known_overlaps` in manifest. |
| **ORPHAN** | Element cannot be placed in any known unit/day. |
| **UNVERIFIED** | Insufficient evidence to confirm placement. |

---

## 7. Layer 1 role-fulfillment statuses

| Status | Meaning |
|--------|---------|
| **FULFILLED** | Expected calendar role has supporting element(s). |
| **MISSING** | Expected role has no fulfilling elements. |
| **DUPLICATE** | Multiple elements fulfill the same role (flagged). |

---

## 7a. Layer 2 completeness statuses

Versioned as `LAYER2_TAXONOMY_VERSION` (`v1-hypothesis`); see `layer2.ROLE_EXPECTED_COMPONENTS`.

| Status | Meaning |
|--------|---------|
| **COMPLETE** | Document has every `element_type` its role (`ROLE_EXPECTED_COMPONENTS`) expects, somewhere among its own elements. |
| **INCOMPLETE** | Document is missing at least one expected internal component. Never authored/fixed — reported only. |

---

## 8. Confidence & tiers

| Term | Values / meaning |
|------|------------------|
| **confidence** | `high` \| `medium` \| `low` — model or pipeline certainty. |
| **Tier 1 / Tier 2** | Layer 0 decompose passes; Tier 2 = escalated harder pass. |
| **Tier A / Tier B (legacy place)** | Tier A = calendar wrong (corrections); Tier B = content genuinely missing. |

---

## 9. Project tiers

| Tier | Meaning |
|------|---------|
| **Active** | Real district / curriculum work in progress (e.g. `dallas-career-2026`). |
| **Stress** | Hard input shape (e.g. fat framework PDF). |
| **Experiment** | Paired with `experiments/` code paths. |
| **Fixture** | Tiny ingest smoke projects. |

---

## 10. Acronyms & external terms

| Acronym / term | Expansion |
|----------------|-----------|
| **SQE** | Software Quality Engineer |
| **LLM** | Large Language Model |
| **DISD** | Dallas Independent School District |
| **ISD** | Independent School District |
| **CTE** | Career and Technical Education |
| **CTSO** | Career and Technical Student Organization |
| **AP CSP** | AP Computer Science Principles |
| **OpenSciEd** | Open science education curriculum (middle school) |
| **TE** | Teacher Edition (fat instructional PDF) |
| **GGUF** | GPT-Generated Unified Format — local model weight file format |
| **PDF** | Portable Document Format |
| **YAML** | YAML Ain't Markup Language — config/calendar serialization |
| **JSON** | JavaScript Object Notation — ledgers/evidence |
| **OCR** | Optical Character Recognition (roadmap: scanned PDFs) |
| **PoC** | Proof of Concept |
| **SOP** | Standard Operating Procedure |
| **TOC** | Table of Contents |
| **HITL** | Human-in-the-loop (e.g. `REVIEW-QUEUE.md`, `known_overlaps`) |
| **G10** | Local ThinkStation / control-center host environment for this repo |

---

## 11. BETS doctrine shorthand

| Bet (see `docs/BETS.md`) | One-line meaning |
|--------------------------|------------------|
| Full-document reading | Prefer whole-doc context over brittle chunk-only pipelines where possible |
| Regex-as-hint-only | Filename/regex priors inform; they do not decide alone |
| Citations + unknown | Every claim needs a cite; `unknown` / `unclear` are valid answers |
| Two-pass / verifier | Independent second judgment framing (may be same strong model) |
| Unattended resumable queue | Cached, idempotent, checkpointed Layer 0/1 runs |
| Conformance over synthesis | Prefer verifying placement over inventing calendars as “truth” |

---

## 12. Output artifact names (common)

| Artifact | Meaning |
|----------|---------|
| `GLOBAL-AUDIT.md` / `.pdf` | Project-level conformance / coverage report |
| `DASHBOARD.md` | Director heatmap / rollup |
| `SUMMARY.md` | Pass/review/gap table |
| `REVIEW-QUEUE.md` | Pending human overlap calibration |
| `GOLDEN.json` | Snapshot of Layer 1 metrics for regression comparison |
| `ledger.json` | Layer 0 element list |
| `bucket-ledger.json` | Layer 1 per-element placement judgments |
| `findings.json` (layer1/) | Layer 1 per-role fulfillment findings |
| `findings.json` (layer2/) | Layer 2 per-(doc_id, role) structural completeness rows |
| `LAYER0B-REPORT.md` | Layer 0-B citation-precision review summary (kept/split/errors/type coercions) |
| `REPORT.md` (layer2/) | Layer 2 run summary (COMPLETE/INCOMPLETE counts, INCOMPLETE detail) |
| `catalog.json` | Ingest extraction catalog |
| `pacing-plan.yaml` | Inferred structural year map (not official curriculum) |
