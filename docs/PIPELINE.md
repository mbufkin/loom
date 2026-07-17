# Pipeline — Crystallize

**Program:** one orchestrator. **Data:** any `projects/<id>/`.

`run_project.py` / `./run-audit` runs the full path below (unless you pass skip flags).
Canonical lineage (including artifact names): [DEPENDENCY_FLOW.md](../DEPENDENCY_FLOW.md).

## One command

```bash
cp config.example.yaml config.yaml   # first time only
./run-audit my-district
```

## Stages

```
sources/                    ← curriculum DATA (any supported format)
    │
    ▼  doc_extract.py       text extraction (code)
    │
    ▼  ingest.py            organize + infer unit calendars (models → YAML)
    │
    ▼  rollup.py            unit calendars → pacing-plan / year map (code)
    │
    ▼  layer0.py            0-A: element extraction, cited (models)     ← headline
    │
    ▼  layer0.py            0-B: --resolve-wide-spans (models)          ← citation precision
    │
    ▼  layer1.py            placement conformance (models)              ← headline
    │
    ▼  layer2.py            lesson structural completeness (code)       ← no new model calls
    │
    ▼  synthesize.py        FIRST-PASS / teachers / dashboard
    │                       (default --delivery model = hybrid narrative)
    │
    ▼  render_pdf.py        GLOBAL-AUDIT-REPORT.pdf (+ teacher PDFs as needed)
    │
    ▼  tools/push_drive_reports.py   optional Drive upload (default on)
```

**Orchestrator:** `run_project.py`

| Flag | Effect |
|------|--------|
| `--skip-layer01` | Omit Layer 0, 1, **and** 2 (globals / completeness not refreshed) |
| `--only UNIT` | Scope Layer 0 filename filter + Layer 1/2 `--only-unit` |
| `--skip-drive-push` | Keep reports local only (no Google Drive upload) |
| `--layer0-no-resume` | Full Layer 0 re-extract |
| `--ingest` / `--force` / `--skip-rollup` | As in [OPERATORS.md](../OPERATORS.md) |

Doc-level scrub→place lived under `archive/legacy-unit-audit/` and is **not** part of this path.

## Models vs code

| Step | Engine |
|------|--------|
| Extract, rollup, Layer 2, PDF, dashboard / review-queue plates | **Code** |
| Organize documents, infer unit structure | **Models** |
| Layer 0 / Layer 1 conformance | **Models** |
| First-pass / teacher narrative (`--delivery model`) | **Models** (hybrid; see [REPORT-DELIVERY.md](REPORT-DELIVERY.md)) |

Configure endpoints in `config.yaml`. **Single-model doctrine:** analyst and verifier may share one endpoint (second-pass framing of the same model). This repo does not ship models.

## Dataset artifacts

| File | Role |
|------|------|
| `manifest.yaml` | Unit ↔ document registry |
| `school-calendar.yaml` | District year spine (optional) |
| `units/<id>/calendar.yaml` | Day grid + expected roles |
| `pacing-plan.yaml` | Inferred year map (`rollup.py`) |
| `layer0/` / `layer1/` / `layer2/` | Extraction, conformance, completeness ledgers |
| `output/**` | Deliverable reports (see [OUTPUTS.md](OUTPUTS.md)) |

## Prerequisites

- Python 3.10+
- OpenAI-compatible local model server(s) per `config.yaml`
- Optional: `pdftotext` (poppler)
