---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
  - 06-path-d-presence-plate-and-fixtures
claimed_by: cursor
claimed_at: 2026-08-05T17:55:00Z
resolved_at: 2026-08-05T18:05:00Z
assets:
  - ../../docs/PATH-E-STUDENT-PRACTICE.md
  - ../../workflows/checklists/student_practice.yaml
---

# Path E presence plate and fixtures

## Question

For Path E (student practice), what are the **presence steps (E1–En)** for learn/practice/succeed/worksheet materials, and which **named strong·mixed·weak fixtures** lock the offline tests and lab?

## Answer

**Plate (shipped):** E1 inventory · E2 role cues (Learn/Practice/Succeed/worksheet/SE) · E3 student-task cues · E4 optional soft targets · E5 stub emit. No answer-key pairing; no LPS family pairing. Checklist: `workflows/checklists/student_practice.yaml`.

**CI fixtures** (`tests/fixtures/path_e/`): `strong_learn.txt` / `mixed_succeed.txt` / `weak_practice.txt` via `test_path_e_student_practice.py`.

**Lab** (`projects/lab-student-practice-path-e/`): evidence-flattened G5 M1 Learn (strong), Succeed (mixed), Practice (weak). Smoke: ingest → route → `run_paths --no-model`.
