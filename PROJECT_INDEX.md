# PROJECT_INDEX — Master Table of Contents

**Product:** Loom (routed curriculum auditor — fork of Crystallize)  
**Repo root:** `g10-control-center-loom/`  
**Audience:** Humans and AI agents  
**Rule:** Before creating or moving any file, you MUST locate the correct zone in this index and in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

---

## 1. Quick entry points

| Need | Go here |
|------|---------|
| What the product does | [README.md](README.md) — **one program; curricula are data** |
| Operator commands | [OPERATORS.md](OPERATORS.md) · `./run-audit <dataset-id>` |
| Dataset shelf | [projects/STATUS.md](projects/STATUS.md) |
| Where files live | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — **sole** tree / zone contract |
| Domain terms | [GLOSSARY.md](GLOSSARY.md) |
| Keys & schemas | [DATA_MAP.md](DATA_MAP.md) |
| Blast radius / lineage | [DEPENDENCY_FLOW.md](DEPENDENCY_FLOW.md) |
| How to contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| How to test | [TESTING_STRATEGY.md](TESTING_STRATEGY.md) |
| Design doctrine | [docs/BETS.md](docs/BETS.md) |
| Pipeline stages | [docs/PIPELINE.md](docs/PIPELINE.md) |

---

## 2. Module catalog (production code)

### 2.1 Orchestration

| File | Role | Downstream consumers |
|------|------|----------------------|
| [`run_project.py`](run_project.py) | **One-command program entry** | ingest → rollup → **layer0 (0-A+0-B) → layer1 → layer2 → synthesize** |
| [`run-audit`](run-audit) | Shell wrapper: `./run-audit <dataset-id>` | Operators |
| [`inbox-watch.py`](inbox-watch.py) | Watch folder → copy into `sources/` | Ingest inputs |

### 2.2 Headline mechanism (Layer 0 / Layer 1 / Layer 2)

| File | Role | Primary outputs |
|------|------|-----------------|
| [`layer0.py`](layer0.py) | Element-level extraction with verbatim citations (+ `--resolve-wide-spans`) | `projects/<id>/layer0/ledger.json`, `REPORT.md` |
| [`layer1.py`](layer1.py) | Placement conformance (MATCH / MISMATCH / …) | `projects/<id>/layer1/bucket-ledger.json`, `findings.json`, `REPORT.md`, `REVIEW-QUEUE.md` |
| [`layer2.py`](layer2.py) | Lesson structural completeness (code-only; no new model calls) | `projects/<id>/layer2/findings.json`, `REPORT.md` |

> **Wired into `run_project.py` by default.** Escape hatch: `--skip-layer01` skips Layer 0, 1, **and** 2. Manual stage runs still supported for debug.

### 2.3 Organize + structural map

| File | Role | Primary outputs |
|------|------|-----------------|
| [`doc_extract.py`](doc_extract.py) | Multi-format text extraction | In-memory / catalog text |
| [`ingest.py`](ingest.py) | Organize docs → units + calendars (models) | `manifest.yaml`, `units/*/calendar.yaml`, `ingest/catalog.json` |
| [`rollup.py`](rollup.py) | Unit calendars → year map (code) | `pacing-plan.yaml`, `output/03-year-calendar-map.*` |

### 2.4 Reporting

| File | Role | Reads |
|------|------|-------|
| [`reports.py`](reports.py) | Modular report registry (`first-pass`, `teacher`, `dashboard`, …) | Layer 1/2 ledgers, pacing |
| [`report_delivery.py`](report_delivery.py) | Hybrid curriculum-audit narrative (findings→patterns→recommendations) | Packed ledger facts via `model_chat` |
| [`synthesize.py`](synthesize.py) | CLI + renderers; `--report` / `--delivery` / `--list-reports` | Delegates writes via `reports.py` |
| [`render_pdf.py`](render_pdf.py) | Global PDF (+ optional archived unit gap PDF CLI) | First-pass / GLOBAL-AUDIT markdown, pacing |

### 2.5 Shared libraries

| File | Role |
|------|------|
| [`audit_lib.py`](audit_lib.py) | Config, logging, model chat, paths, `scrub_document`, `doc_id_from_filename` |
| [`schema_validate.py`](schema_validate.py) | Structural validators for ingest, calendars, Layer 0/1 payloads |
| [`report_lib.py`](report_lib.py) | Coverage matrix helpers (archived unit PDF path) |

### 2.6 Configuration

| File | Role |
|------|------|
| [`config.example.yaml`](config.example.yaml) | Template — copy to `config.yaml` |
| [`config.yaml`](config.yaml) | Local model URLs (**gitignored**) |
| [`requirements.txt`](requirements.txt) | Python dependencies |

### 2.7 Tests

| File | Scope |
|------|-------|
| [`test_doc_extract.py`](test_doc_extract.py) | Extraction + scrub helpers |
| [`test_schema_validate.py`](test_schema_validate.py) | Schema validators |
| [`test_audit.py`](test_audit.py) | Classification / scrub helpers |
| [`test_rollup.py`](test_rollup.py) | Rollup against `dallas-career-2026` |

### 2.8 Archived (not production)

| Path | Role |
|------|------|
| Local-only `archive/` (not shipped publicly) | Retired scrub→place / legacy batch — removed from `./run-audit` |

---

## 3. Curriculum data (`projects/`) — not separate products

Canonical shelf: [projects/STATUS.md](projects/STATUS.md). Layout: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) §3.

| Dataset ID | Tier | README | Layer 0 | Layer 1 | Notes |
|------------|------|--------|---------|---------|-------|
| [`dallas-career-2026`](projects/dallas-career-2026/) | **Golden** | Yes | Yes | Yes | Acceptance / demo dataset |
| [`region10-career-college-2026`](projects/region10-career-college-2026/) | Active | Yes | Yes | Yes | Live district corpus |
| [`ap-csp-2026`](projects/ap-csp-2026/) | Stress | Yes | Yes | Partial | Framework PDF stress |
| [`openscied-6`](projects/openscied-6/) | Experiment | Yes | — | — | + `experiments/openscied/` |
| [`_template`](projects/_template/) | Template | Yes | — | — | Copy for new corpora |
| [`_fixtures/`](projects/_fixtures/) | Fixture | Yes | — | — | `ingest-pilot`, `ingest-test` |

---

## 4. Documentation zone (`docs/`)

| Doc | Purpose |
|-----|---------|
| [docs/README.md](docs/README.md) | Doc index |
| [docs/BETS.md](docs/BETS.md) | Design doctrine (read first for architecture decisions) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Product boundary |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Stage-by-stage flow |
| [docs/DATA-FLOW.md](docs/DATA-FLOW.md) | Historical Mermaid canvases (not structure SoT) |
| [docs/FILE-FLOW.md](docs/FILE-FLOW.md) | Historical on-disk canvas (not structure SoT) |
| [docs/OUTPUTS.md](docs/OUTPUTS.md) | Deliverable catalog |
| [docs/STRUCTURAL-FILL.md](docs/STRUCTURAL-FILL.md) | Maps vs content boundary |
| [docs/SAMPLE-PROJECT.md](docs/SAMPLE-PROJECT.md) | Dallas walkthrough |
| [docs/roadmap.md](docs/roadmap.md) | Build plan / open work |
| [docs/REORG-2026-07.md](docs/REORG-2026-07.md) | Path migration notes |

---

## 5. Non-production zones

Zone paths and import rules live only in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) §1–§2
(`tools/`, `experiments/`, `data/`, `research/`, `archive/`, `logs/`).  
Do not duplicate the zone table here.

---

## 6. Phase 1 audit snapshot (2026-07-09)

### 6.1 File inventory (approx.)

| Kind | Count (approx.) | Location |
|------|-----------------|----------|
| Production `.py` | 15 | Repo root |
| Test `.py` | 4 | Repo root |
| Tool / experiment `.py` | 13 | `tools/`, `experiments/` |
| Project YAML | ~51 | `projects/**` |
| Project JSON | ~827 | ledgers, evidence, catalogs, stats |
| Project Markdown | ~138 | reports, READMEs |
| Source `.txt` extracts | ~130 | `projects/*/sources/` |
| PDF reports | ~48 | `projects/*/output/` |

### 6.2 Orphaned directories (functional logic or data, no `README.md`)

| Path | Severity | Action required |
|------|----------|-----------------|
| `data/` | Low | Has [data/README.md](data/README.md) — backup, not I/O |
| `research/` | Low | Optional private README |
| `logs/` | Low | Optional |
| `archive/` | Low | Local-only if present; not shipped publicly |
| Generated subdirs (`ingest/`, `layer0/`, `layer1/`, `layer2/`, `sources/`, `units/`, `runs/`) | Info | Covered by [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — per-subdir READMEs optional |

### 6.3 Pivot points (change these → widest blast radius)

| Pivot | Why |
|-------|-----|
| `projects/<id>/sources/` + `doc_id` | Every downstream stage keys off document identity |
| `manifest.yaml` | Unit registry; Layer 1 vocabulary; synthesize rollups |
| `units/*/calendar.yaml` | Expected roles; placement targets; gap findings |
| `layer0/ledger.json` | Sole element source for Layer 1 (and Layer 2 re-read) |
| `layer1/bucket-ledger.json` + `findings.json` | Sole conformance source for first-pass / dashboard / Layer 2 |
| `layer2/findings.json` | Structural-completeness input for synthesize / teacher packets |
| `schema_validate.py` | Contract for all model JSON and on-disk YAML |
| `config.yaml` | Model endpoints — silent failure if wrong |

---

## 7. Maintenance rule

When you add a module, project, or zone, you MUST:

1. Add a row to **§2 or §3** of this file.
2. Update [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) if the hierarchy changes.
3. Update [GLOSSARY.md](GLOSSARY.md) for any new domain term.
4. Update [DATA_MAP.md](DATA_MAP.md) / [DEPENDENCY_FLOW.md](DEPENDENCY_FLOW.md) if keys or lineage change.
5. Follow [CONTRIBUTING.md](CONTRIBUTING.md).
