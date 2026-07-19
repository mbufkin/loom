# Dataset: pathful-planning-guides-2026

| | |
|--|--|
| **Tier** | Experiment (smoke) |
| **Program** | Loom at repo root — this folder is **data only** |
| **Source** | [Pathful Planning Guides](https://www.pathful.com/material/pathful-planning-guides) (Publuu flipbooks) |
| **Corpus** | WBL + CCE (MS/HS), Special Ed Transition, Pre-ETS, activity flowchart |
| **Calendar** | Template DISD spine (dated YAG); not Pathful-native |
| **Run** | `./run-audit pathful-planning-guides-2026 --ingest --force --skip-drive-push` |

## Provenance

Text extracted from Pathful flipbooks into `sources/*.txt`. Implementation-plan flipbooks (`2068954`–`2068956`) are image-only Publuu pages and were **excluded** (OCR not run).

Flipbook IDs included: `1424833`, `1424838`, `1424840`, `1424841`, `1424890`, `1454298`, `1530547`.

## Ingest note

Model organize correctly saw **no instructional day calendars** in these planning guides. Unit calendars were scaffolded as grade-band / phase slots so Layer 0–2 can still run (see `ingest/.raw/organize-repaired.json`). Re-running with `--ingest` alone will fail until scaffolds are reapplied.
