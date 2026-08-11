---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
claimed_by: cursor
claimed_at: 2026-08-05T15:06:00Z
resolved_at: 2026-08-05T15:10:00Z
assets:
  - ../../docs/PATH-B-QUIZ.md
  - ../../workflows/checklists/assessment.yaml
---

# Path B presence plate and fixtures

## Question

For Path B (quiz ↔ answer key), what are the **presence steps (B1–Bn)**, required vs optional fields, how **separate quiz and key files** are treated as a pair, and which **named strong·mixed·weak fixtures** lock the offline tests and lab project?

## Answer

**Plate (shipped):** B1 inventory · B2 item stems · B3 answer-key signal · B4 optional targets · B5 filename-stem pairing · B6 stub one-pager. Checklist: `workflows/checklists/assessment.yaml`.

**Pairing:** Two docs; join on normalized stem (`pair_key()`), not one merged findings row. PRESENT when quiz+key share a stem; PARTIAL if orphan.

**CI fixtures** (`tests/fixtures/path_b/`): `strong_quiz.txt` / `strong_key.txt` / `orphan_quiz.txt` / `weak_blank.txt` via `test_path_b_assessment.py`.

**Lab** (`projects/lab-assessment-path-b/`): Dallas Engineering + Architecture pairs (strong), Manufacturing quiz alone (mixed), blank placeholder (weak). Smoke: ingest → route → `run_paths --no-model` (source-text fallback if ledger empty).
