# PROJECT_STRUCTURE — Architectural Blueprint

**Status:** Canonical  
**Scope:** Entire `loom` repository  
**Rule:** New files MUST land in the directory defined below. Do not invent parallel trees.

---

## 1. Mandatory top-level hierarchy

```
loom/
├── PROJECT_INDEX.md          ← Context Layer: master TOC
├── PROJECT_STRUCTURE.md      ← Context Layer: this file
├── GLOSSARY.md               ← Context Layer: domain dictionary
├── DATA_MAP.md               ← Context Layer: keys & schemas
├── DEPENDENCY_FLOW.md        ← Context Layer: data lineage
├── CONTRIBUTING.md           ← Context Layer: rules of engagement
├── TESTING_STRATEGY.md       ← Context Layer: pre-flight checks
├── README.md                 ← Product overview
├── OPERATORS.md              ← Operator command reference
├── REPO-MAP.md               ← Thin pointer → this file (do not restate the tree there)
├── config.example.yaml       ← Config template (committed)
├── config.yaml               ← Local secrets/URLs (gitignored)
├── requirements.txt
│
├── *.py                      ← Production pipeline + tests (repo root ONLY)
├── run-audit                 ← Shell entry
│
├── docs/                     ← Product documentation ONLY
├── projects/                 ← DATA ONLY (curriculum corpora; not the program)
│   ├── STATUS.md             ← dataset tier table
│   ├── _template/            ← blank corpus skeleton
│   ├── _fixtures/            ← ingest smoke fixtures
│   └── <dataset-id>/         ← interchangeable curriculum input + generated artifacts |
├── tools/                    ← Debug scripts (not production; not called by run_project)
├── experiments/              ← R&D (openscied/, apcsp/ — not production)
├── data/                     ← Backup / OSINT only (career-curriculum/osint/; not pipeline I/O)
├── research/                 ← Private notes
├── logs/                     ← Runtime logs
└── archive/                  ← Deprecated (crystallize-legacy/, legacy-unit-audit/, …)
```

### 1.1 Placement rules (imperative)

| Artifact type | MUST live in | MUST NOT live in |
|---------------|--------------|------------------|
| Production pipeline stage | Repo root `*.py` | `tools/`, `experiments/`, `projects/` |
| Shared library | Repo root (`audit_lib.py`, `schema_validate.py`, …) | Nested package unless explicitly introduced |
| Product docs | `docs/` | Scattered READMEs that contradict `docs/` |
| Context Layer docs | Repo root (this set of 7 files) | `docs/` (docs = product narrative; Context Layer = navigation/governance) |
| Curriculum sources | `projects/<id>/sources/` | Repo root, `data/`, `inbox` without promotion |
| Generated ledgers | `projects/<id>/layer0/`, `layer1/`, `layer2/` | `output/` (output = deliverables only) |
| Deliverable reports/PDFs | `projects/<id>/output/` | `layer0/`, `layer1/`, `layer2/` |
| Operator run logs | `projects/<id>/runs/` or `logs/` | Committed as “source” |
| Debug one-offs | `tools/` | Repo root |
| Experimental pipelines | `experiments/<name>/` | `projects/` production path |
| Deprecated code | `archive/` | Active import graph |

---

## 2. Code zones (A–E)

| Zone | Path | Purpose | May import production? | May be imported by production? |
|------|------|---------|------------------------|--------------------------------|
| A — Product | Root `*.py`, `docs/`, `projects/` | Pipeline + product docs + curriculum datasets | Yes | Yes |
| B — Data & research | `data/`, `research/` | OSINT backup / private notes — not pipeline I/O | Read-only OK | **No** |
| C — Experiments | `experiments/` | Alternate R&D pipelines (`openscied/`, `apcsp/`) | May import libs | **No** |
| D — Tools | `tools/` | Debug / inspect only | May import libs | **No** |
| E — Archive | `archive/` | Deprecated code & frozen artifacts | No | **No** |

**MUST:** Production code (`run_project.py`, `layer0.py`, `layer1.py`, …) MUST NOT import from Zones C, D, or E.

**Archive contents (do not extend):** `crystallize-legacy/`, `legacy-unit-audit/` (old scrub→place), `career-curriculum-output/` (frozen pre-`projects/` batch outputs), `ornith/`, `reviews/`.

---

## 3. Canonical dataset layout (`projects/<dataset_id>/`)

**Mental model:** `projects/` is a shelf of curriculum **datasets**. The program never lives here.

Every operator dataset MUST follow this shape:

```
projects/<dataset_id>/
├── README.md                 ← REQUIRED for non-fixture datasets (tier + how to run)
├── sources/                  ← INPUT: curriculum files (human-provided)
│   └── doc_<hex>_<slug>.txt  ← preferred extracted naming (or raw pdf/docx/…)
├── reference/                ← OPTIONAL: official calendar images / links
│   └── README.md
├── school-calendar.yaml      ← District year spine (optional but preferred)
├── manifest.yaml             ← Unit ↔ document registry (generated / curated)
├── pacing-plan.yaml          ← PROVISIONAL early year map (rollup.py; authoritative = calendars_inferred/)
├── units/
│   └── <unit_id>/
│       └── calendar.yaml     ← Day grid + expected artifact roles
├── ingest/                   ← Generated catalog / raw cache
│   ├── catalog.json
│   └── .raw/
├── layer0/                   ← Headline: element ledger
│   ├── ledger.json
│   ├── REPORT.md
│   ├── LAYER0B-REPORT.md     ← if Layer 0B run
│   ├── route-map.json        ← Loom router: unit → Path A/B/C map
│   ├── workflow-handoff.json ← router → path workflows handoff
│   └── .raw/
├── path_a/                   ← Path A workflow (lesson plans) — Loom
│   └── findings.json
├── path_b/                   ← Path B workflow (quiz / assessment) — Loom
│   └── findings.json
├── path_c/                   ← Path C workflow (general) — Loom
│   └── findings.json
├── calendars_inferred/       ← Authoritative model-calendar map (calendars.py)
│   ├── INFERRED-CALENDARS.json
│   └── INFERRED-CALENDARS.md
├── _loom_feedback.yaml       ← Loom path-run feedback (workflows/run_paths.py)
├── layer1/                   ← Headline: conformance
│   ├── bucket-ledger.json
│   ├── findings.json
│   ├── REPORT.md
│   ├── REVIEW-QUEUE.md
│   ├── GOLDEN.json           ← optional snapshot metrics (layer1 + layer2 keys)
│   └── .raw/
├── layer2/                   ← Headline: lesson structural completeness
│   ├── findings.json
│   └── REPORT.md
├── output/                   ← Deliverables ONLY (reports.py via synthesize)
│   ├── FIRST-PASS.md         ← course work packet (report first-pass)
│   ├── GLOBAL-AUDIT.md       ← alias of FIRST-PASS (compat)
│   ├── GLOBAL-AUDIT-REPORT.pdf
│   ├── DASHBOARD.md
│   ├── teachers/<unit_id>/TEACHER-PACKET.md
│   ├── SUMMARY.md
│   ├── aggregate-stats.json
│   ├── 03-year-calendar-map.md
│   ├── 03-year-calendar-map.json
│   ├── batch_state.json
│   └── <unit_id>/            ← optional leftover from archived scrub→place
│       ├── AUDIT-REPORT.pdf  ← not regenerated by ./run-audit
│       ├── 01-calendar-map.json
│       ├── 02-gap-report.md / .json
│       ├── evidence/*.json
│       └── …
└── runs/                     ← Operator logs (run-*.log)
```

Dataset shelf / tiers: [projects/STATUS.md](projects/STATUS.md). Same shape for every id — no curriculum-specific code paths; only `--project <id>`.

### 3.1 Directory ownership

| Directory | Owner process | Hand-edit? |
|-----------|---------------|------------|
| `sources/` | Human / `inbox-watch.py` | Yes (add files) |
| `reference/` | Human | Yes |
| `school-calendar.yaml` | Human or ingest | Yes (careful) |
| `manifest.yaml` | `ingest.py` (+ human `known_overlaps`) | Curate overlaps only |
| `units/*/calendar.yaml` | `ingest.py` | Correct structure only; prefer `--ingest --force` |
| `pacing-plan.yaml` | `rollup.py` | No (regenerate; provisional — superseded by `calendars_inferred/`) |
| `ingest/` | `ingest.py` | No |
| `layer0/` | `layer0.py` (ledgers) + `route.py` (`route-map.json`) | No |
| `path_a/` `path_b/` `path_c/` | `workflows/run_paths.py` (+ `workflows/lesson_plan.py`, `workflows/quiz.py`, `workflows/general.py`) | No |
| `calendars_inferred/` | `calendars.py` | No |
| `_loom_feedback.yaml` | `workflows/run_paths.py` | No |
| `layer1/` | `layer1.py` | Review queue is human-facing; do not hand-edit JSON ledgers |
| `layer2/` | `layer2.py` | No |
| `output/` | `synthesize.py` / `reports.py` / `render_pdf.py`; `teachers/` from report `teacher` | No |
| `runs/` | Operators / wrappers | No |

### 3.2 Naming constraints

| Entity | Pattern | Enforced by |
|--------|---------|-------------|
| `project_id` | `^[a-z0-9]+(?:-[a-z0-9]+)*$` | `validate_slug_id` |
| `unit_id` | `^[a-z0-9.]+(?:-[a-z0-9.]+)*$` | `UNIT_ID_RE` in `schema_validate.py` |
| Day id | `^d\d+$` (e.g. `d1`, `d12`) | `DAY_ID_RE` |
| Source extract | `doc_<12-hex>_<slug>.txt` | Convention + `doc_id_from_filename` |
| `doc_id` | 12-char hex from filename, else basename | `audit_lib.doc_id_from_filename` |
| `element_id` | `{doc_id}-e{n}` (e.g. `041457651819-e1`) | `layer0.py` |

---

## 4. Headline pipeline (wired into `run_project.py`)

| Path | Default in `./run-audit` | Grain | Writes |
|------|--------------------------|-------|--------|
| **Layer 0 / Layer 1** | Yes (unless `--skip-layer01`) | Instructional element | `layer0/`, `layer1/` |
| **Loom router** | Yes (unless `--skip-layer01`) | Unit → Path A/B/C | `layer0/route-map.json`, `workflow-handoff.json` |
| **Path A / B / C** | Yes (unless `--skip-layer01`) | Document (lesson plan / quiz / general) | `path_a/`, `path_b/`, `path_c/` |
| **Model calendars** | Yes (unless `--skip-layer01`) | Unit → inferred day/year map | `calendars_inferred/` |
| **Layer 2** | Yes (unless `--skip-layer01`) | Document × role (no new model calls) | `layer2/` |
| **Reports** | Yes (`synthesize --report all`) | Project / unit plates | `output/FIRST-PASS.md`, `teachers/`, `DASHBOARD.md`; refreshes `layer1/REVIEW-QUEUE.md` |

Doc-level scrub→place (`scrub.py` / `place.py` / `run-all-units.py`) is retired
and is **not** part of production (local-only `archive/` if present on disk).

**MUST NOT** treat archived `place.py` gap reports as the source of truth for
`FIRST-PASS.md` / `GLOBAL-AUDIT.md` / `DASHBOARD.md` — those are Layer 1–sourced via `reports.py`.

---

## 5. Forbidden patterns

1. **MUST NOT** create a new top-level directory without updating this file and `PROJECT_INDEX.md`.
2. **MUST NOT** put generated ledgers under `output/` or deliverables under `layer0/` / `layer1/`.
3. **MUST NOT** author lesson plans, assessments, or rubrics into `sources/` or anywhere else via the auditor (charter: read-only).
4. **MUST NOT** hardcode a single `project_id` into production stages — use `--project <id>`.
5. **MUST NOT** leave a new functional directory without a README if it is a **project root** or a **new zone**.

---

## 6. Relationship to other docs (single source of truth)

**This file** is the only place that may define the top-level tree, zones A–E, `projects/<id>/` shape, and placement MUST/MUST NOT tables. Do not duplicate those facts in REPO-MAP or PROJECT_INDEX.

| Doc | Relationship |
|-----|--------------|
| [REPO-MAP.md](REPO-MAP.md) | Thin pointer only — links here |
| [PROJECT_INDEX.md](PROJECT_INDEX.md) | TOC + module catalog (file *roles*); paths defer to this file |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Stage semantics — must stay consistent with §4 |
| [docs/FILE-FLOW.md](docs/FILE-FLOW.md) / [docs/DATA-FLOW.md](docs/DATA-FLOW.md) | Historical Mermaid canvases — **not** structure SoT |
