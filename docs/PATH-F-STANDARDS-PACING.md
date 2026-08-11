# Path F — Standards & pacing workflow

**Lens name:** Standards & pacing (Path F). Taxonomy: [PATHS.md](PATHS.md).

Entry: Loom router filename prior (`pacing`, `yag`, `scope and sequence`,
`teks summary`, `elps summary`, `standards overview`, …).

## Why not Path G / Path A?

- **Path G** is the student-facing course contract (syllabus).
- **Path A** is one instructional episode (Hunter / daily lesson).
- **Path F** is the teacher/champion **year or unit spine** — YAG, pacing,
  scope/sequence, standards overviews. G8 may later cross-check syllabus ↔ F.

## Steps (F1 → F5)

| Step | Name | Intent |
|------|------|--------|
| **F1** | Inventory | Layer 0 / source excerpts |
| **F2** | Document role | YAG / pacing / S&S / standards-overview cues |
| **F3** | Time spine | Day / week / unit / module order cues |
| **F4** | Standards cues | Optional TEKS / ELPS / § / standard codes |
| **F5** | Emit | Stub — short one-pager later |

## Guardrails

- Auditor-only: blank = not found.
- No Hunter plate (Path A). No syllabus contract checks (Path G).
- Do not invent TEKS coverage or calendar dates.
- F4 is optional soft presence — pacing-only docs can still pass F2/F3.

## Lab + tests

- Lab smoke: `projects/lab-standards-path-f/`
- Offline: `test_path_f_standards_pacing.py` + `tests/fixtures/path_f/`
- Checklist: `workflows/checklists/standards_pacing.yaml`

## Outputs

- `path_f/findings.json` — `inventory` + `steps_by_doc`
