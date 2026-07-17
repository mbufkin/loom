# Loom — Operator Reference

**One program, curricula as data.** Overview: [README.md](README.md) · Datasets: [projects/STATUS.md](projects/STATUS.md)

---

## Daily use (one command)

```bash
cd loom
./run-audit <dataset-id>
```

Equivalent: `python3 run_project.py --project <dataset-id>`.

This runs: preflight → ingest (if needed) → rollup → **Layer 0 → Layer 1 → Layer 2 → synthesize --report all --delivery model** (hybrid first-pass + teacher narrative; dashboard + review-queue code-only).

### First-time dataset

```bash
cp -a projects/_template projects/my-district
# copy curriculum files into projects/my-district/sources/
# DISD: school-calendar.yaml + reference/ calendar image are already in _template
# (canonical: shared/disd-school-calendar/). Other districts: replace or remove.
./run-audit my-district
```

Dated YAG / pacing requires `projects/<id>/school-calendar.yaml`. Without it,
rollup runs in sequential mode only. After editing the spine:  
`python3 rollup.py --project <id> --force`.

### After adding documents

```bash
./run-audit my-district --ingest --force
```

### Smoke one unit (Layer 0/1 scoped)

```bash
./run-audit dallas-career-2026 --only engineering --force
```

`--only UNIT` applies to Layer 0 filename `--only` and Layer 1 `--only-unit`.

### Skip Layer 0/1/2 (rollup / ingest only; globals stale)

```bash
./run-audit my-district --skip-layer01
```

`--skip-layer01` skips Layer 0, Layer 1, **and** Layer 2 (historical flag name).
Synthesize may still run but will not refresh conformance / completeness ledgers.

---

## Prerequisites

```bash
cp config.example.yaml config.yaml   # edit model URLs for your box

# Health-check the host(s) in config.yaml models.*_url (example: port 30000)
curl -sf http://127.0.0.1:30000/health
```

### Model roles

| Role | Config keys | Notes |
|------|-------------|-------|
| Analyst | `analyst_url`, `analyst_model` | Primary judgment |
| Verifier | `verifier_url`, `verifier_model` | Second-pass framing; may be the same endpoint (single-model doctrine) |

**System packages:** `pdftotext` (poppler-utils); optional `antiword` for `.doc`.

---

## Pipeline steps (manual / debug)

| Step | Command | Purpose |
|------|---------|---------|
| 1 Ingest | `python3 ingest.py --project ID --sources path/` | Models → YAML |
| 1b Rollup | `python3 rollup.py --project ID --force` | → `pacing-plan.yaml` |
| **2a Layer 0-A** | `python3 layer0.py --project ID` | Element ledger |
| **2b Layer 0-B** | `python3 layer0.py --project ID --resolve-wide-spans` | Split over-broad citations |
| **2c Layer 1** | `python3 layer1.py --project ID` | Conformance |
| **2d Layer 2** | `python3 layer2.py --project ID` | Structural completeness (code) |
| 3 Synthesize | `python3 synthesize.py --project ID --report all` | Hybrid reports (default `--delivery model`) |
| Fast plates | `python3 synthesize.py --project ID --report all --delivery code` | Tables only, no model |
| One report | `python3 synthesize.py --project ID --report first-pass` | Or `teacher --unit X`, `dashboard`, … |
| List reports | `python3 synthesize.py --list-reports` | Implemented vs planned ids |
| PDF only | `python3 render_pdf.py --project ID --global` | Re-render first-pass PDF |

Prefer `./run-audit` unless debugging a single stage.

---

## Flags (`run_project.py`)

| Flag | Effect |
|------|--------|
| `--ingest` | Re-organize documents |
| `--force` | Force re-run rollup |
| `--sources PATH` | Alternate ingest/Layer 0 sources folder |
| `--only UNIT` | Scope Layer 0/1/**2** to one unit |
| `--skip-rollup` | Skip pacing-plan |
| `--skip-layer01` | Skip Layer 0/1/**2** (globals / completeness stale or missing) |
| `--layer0-no-resume` | Full Layer 0 re-extract |
| `--skip-drive-push` | Skip Google Drive upload of `GLOBAL-AUDIT-REPORT.pdf` (default is to push) |

---

## Google Drive (report PDFs)

After every successful `./run-audit` / `run_project.py`, Loom uploads the
course report PDF via rclone (default remote `gdrive:`):

```text
Loom/<project-id>/
  GLOBAL-AUDIT-REPORT.pdf                    # course first-pass
  runs/<stamp>-GLOBAL-AUDIT-REPORT.pdf
  <Unit Title>/                              # human name, e.g. Architecture & Construction
    TEACHER-PACKET.pdf
    README.txt
    files/<Readable Document Title>.txt      # same names as in the packet
```

Folders are created if missing. Push is soft-fail (audit still succeeds if Drive
is down). Opt out: `--skip-drive-push`. Teacher PDFs are rendered from
`TEACHER-PACKET.md` during synthesize; backfill with
`python3 render_pdf.py --project ID --teachers`.

```bash
# Manual / backfill all curricula that already have a PDF
python3 tools/push_drive_reports.py --all

# One curriculum
python3 tools/push_drive_reports.py --project dallas-career-2026
```

Loom Drive settings (env names kept for compatibility):
`CRYSTALLIZE_DRIVE_REMOTE` (default `gdrive`), `CRYSTALLIZE_DRIVE_BASE`
(default `Loom`). Setup: `docs/images/setup-gdrive-rclone.sh`.

---

## Outputs

| File | Description |
|------|-------------|
| `output/FIRST-PASS.md` | Course-level work packet (report `first-pass`) |
| `output/GLOBAL-AUDIT.md` | Alias of first-pass (compat) |
| `output/GLOBAL-AUDIT-REPORT.pdf` | PDF from first-pass markdown |
| `output/DASHBOARD.md` | Skimmable heatmap (report `dashboard`) |
| `output/teachers/<unit>/TEACHER-PACKET.md` | Per-unit punch list (report `teacher`) |
| `layer0/ledger.json` | Element ledger |
| `layer1/bucket-ledger.json` / `findings.json` | Conformance source of truth |
| `layer1/REVIEW-QUEUE.md` | Overlap HITL queue (report `review-queue`) |
| `layer2/findings.json` / `REPORT.md` | Structural completeness (Layer 2) |
| `pacing-plan.yaml` | Inferred structural year map |

---

## Known limits (MVP)

| Limit | What to do |
|-------|------------|
| **Huge single documents** (e.g. AP CSP CED) | Layer 0 can chunk; **Layer 1 ORGANIZE cannot** — exceeds model context (~113k vs 65k). Dataset stays Stress / Layer 0 only until roadmap item #13. Prefer multi-doc course packs (Dallas-shaped) for end-to-end demos. |
| Hybrid report delivery | Needs a real Layer 1 ledger. Do not treat AP CSP first-pass/teacher packets as product proof. |

Details: [`projects/ap-csp-2026/README.md`](projects/ap-csp-2026/README.md), [`docs/roadmap.md`](docs/roadmap.md) §13.

---

## Tests

Offline-safe (public clone; no private corpora):

```bash
python3 test_schema_validate.py
python3 test_audit.py
python3 test_rollup.py
python3 test_doc_extract.py
python3 test_loom_pipeline.py
```

Dallas integration cases inside `test_loom_pipeline.py` skip automatically when
local sources / Layer 0 ledgers are absent.

---

## Deprecated

Older Crystallize batch and doc-level scrub→place code lived under a local
`archive/` tree. That tree is **not shipped** in the public repo and is not
part of `./run-audit`.

**Canonical path:** `./run-audit <dataset-id>` only.
