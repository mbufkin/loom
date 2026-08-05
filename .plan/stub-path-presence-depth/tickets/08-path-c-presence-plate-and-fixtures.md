---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
  - 07-path-e-presence-plate-and-fixtures
claimed_by: cursor
claimed_at: 2026-08-05T18:10:00Z
resolved_at: 2026-08-05T18:20:00Z
assets:
  - ../../docs/PATH-C-GENERAL.md
  - ../../workflows/checklists/general.yaml
---

# Path C presence plate and fixtures

## Question

For Path C (general feedback), what **presence plate (if any)** and fixture set make the catch-all lens testable at G-style depth — versus only growing via `_loom_feedback.yaml` — without turning C into a junk drawer of every other lens’s checks?

## Answer

**Plate (shipped):** Nursery C1 inventory · C2 catch-all identity (route `general`/C/`doc_type`) · C3 feedback via `route.feedback` **or** `_loom_feedback.yaml` doc_id · C4 optional growth-bucket keywords · C5 stub emit. No TEKS/items/TE junk-drawer checks. Checklist covers C4 only (`workflows/checklists/general.yaml`).

**CI fixtures** (`tests/fixtures/path_c/`): `strong_coach.txt` / `mixed_presentation.txt` / `weak_other.txt` via `test_path_c_general.py`.

**Lab** (`projects/lab-general-path-c/`): evidence-flattened Coach Lesson Protocol (strong), Dallas CTSO Presentation (mixed), weak other stub. Smoke: ingest → route → `run_paths --no-model`.
