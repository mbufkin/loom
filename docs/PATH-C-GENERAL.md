# Path C — General feedback workflow (nursery)

**Lens name:** General feedback (Path C). Taxonomy: [PATHS.md](PATHS.md).

Entry: Loom router assigned `general` after A/B/D/E/F/G/H did not claim the
document (weak/unknown types, presentation, flex day, game, lab, project, …).

## Why a nursery — not a junk drawer?

Path C is the **catch-all + growth queue**. Prefer growing checklists **inside**
A/B/D/E/F/H over stuffing those lenses’ TEKS/items/TE checks into C. C’s job at
presence depth is: inventory what landed here, confirm catch-all identity,
confirm feedback logging, and optionally tag a growth bucket for later plate work.

## Steps (C1 → C5)

| Step | Name | Intent |
|------|------|--------|
| **C1** | Inventory | Layer 0 / source excerpts |
| **C2** | Catch-all identity | Route row is `general` / path C / has `doc_type` |
| **C3** | Feedback log | `route.feedback` **or** doc_id in `_loom_feedback.yaml` |
| **C4** | Growth bucket | Optional coach/protocol/presentation/flex/game/… cue |
| **C5** | Emit | Stub — growth digest / one-pager later |

## Guardrails

- Always a valid fallback — never block the pipeline.
- Auditor-only: blank = not found.
- Do **not** re-append feedback from Path C (route.py owns `_loom_feedback.yaml`).
- Do **not** copy quiz/TE/syllabus/exit-ticket presence checks here.
- C4 is optional soft presence — blank `other` handouts can still pass C1–C3.

## Lab + tests

- Lab smoke: `projects/lab-general-path-c/`
- Offline: `test_path_c_general.py` + `tests/fixtures/path_c/`
- Checklist: `workflows/checklists/general.yaml` (C4 only; C2/C3 are route/YAML)

## Outputs

- `path_c/findings.json` — `inventory` + `steps_by_doc`
- Project-level `_loom_feedback.yaml` (written by router, referenced by C3)
