---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
  - 04-path-h-presence-plate-and-fixtures
claimed_by: cursor
claimed_at: 2026-08-05T16:30:00Z
resolved_at: 2026-08-05T16:45:00Z
assets:
  - ../../docs/PATH-F-STANDARDS-PACING.md
  - ../../workflows/checklists/standards_pacing.yaml
---

# Path F presence plate and fixtures

## Question

For Path F (standards & pacing), what are the **presence steps (F1–Fn)** for scope/sequence / pacing / standards-overview docs, and which **named strong·mixed·weak fixtures** lock the offline tests and lab?

## Answer

**Plate (shipped):** F1 inventory · F2 doc-role cues (YAG/pacing/S&S/standards overview) · F3 time spine · F4 optional soft standards cues · F5 stub emit. Checklist: `workflows/checklists/standards_pacing.yaml`.

**Router fix:** `_STANDARDS_RE` now matches `yag` / `year at a glance` (YAG was falling through to Path C).

**CI fixtures** (`tests/fixtures/path_f/`): `strong_pacing.txt` / `mixed_yag.txt` / `weak_sequence.txt` via `test_path_f_standards_pacing.py`.

**Lab** (`projects/lab-standards-path-f/`): evidence-flattened Alg1 Topic Pacing Guide (strong), YAG 150-day (mixed), pathful sequence stub renamed `…Pacing_Stub` (weak). Smoke: ingest → route → `run_paths --no-model`.
