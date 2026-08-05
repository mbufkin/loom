---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
  - 05-path-f-presence-plate-and-fixtures
claimed_by: cursor
claimed_at: 2026-08-05T17:00:00Z
resolved_at: 2026-08-05T17:20:00Z
assets:
  - ../../docs/PATH-D-TEACHER-SUPPORT.md
  - ../../workflows/checklists/teacher_support.yaml
---

# Path D presence plate and fixtures

## Question

For Path D (teacher support / TE), what are the **presence steps (D1–Dn)** appropriate at G-style depth, and which **named strong·mixed·weak fixtures** lock the offline tests and lab?

## Answer

**Plate (shipped):** D1 inventory · D2 TE/guide role cues · D3 facilitation/supports cues · D4 optional soft module/lesson/topic spine · D5 stub emit. No graph↔Lesson alignment. Checklist: `workflows/checklists/teacher_support.yaml`.

**Router boundary (unchanged):** `Program_and_Implementation` → Path F; TE-named / `implementation_guide` / `_te` → Path D.

**CI fixtures** (`tests/fixtures/path_d/`): `strong_te.txt` / `mixed_impl.txt` / `weak_te.txt` via `test_path_d_teacher_support.py`.

**Lab** (`projects/lab-teacher-support-path-d/`): evidence-flattened G5 M1 TE (strong), Alg1 Course+Impl Guide (mixed), TE stub (weak). Smoke: ingest → route → `run_paths --no-model`.
