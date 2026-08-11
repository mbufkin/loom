# Path D — Teacher support workflow

**Lens name:** Teacher support (Path D). Taxonomy: [PATHS.md](PATHS.md).

Entry: Loom router filename prior (`teacher_edition`, `_te`, `educator_guide`,
`implementation_guide`) or graph role `teacher_edition`.

## Why not Path E / Path F?

- **Path E** is student-facing Learn / Practice / Succeed / worksheets.
- **Path F** is the year/unit spine (YAG, pacing, S&S, standards overviews).
  Bare `Program_and_Implementation` filenames stay on **F** (router).
- **Path D** is adult-facing **TE / educator / TE-named implementation guides**
  — facilitation supports for teaching modules and lessons.

## Steps (D1 → D5)

| Step | Name | Intent |
|------|------|--------|
| **D1** | Inventory | Layer 0 / source excerpts |
| **D2** | TE / guide role | Teacher-edition / educator / implementation framing |
| **D3** | Facilitation cues | Misconception / materials / facilitate / targeted instruction |
| **D4** | Spine | Optional module / lesson / topic / day cues |
| **D5** | Emit | Stub — short one-pager later |

## Guardrails

- Auditor-only: blank = not found.
- No Hunter plate (Path A). No student-practice checks (Path E).
- Do not invent facilitation scripts or misconception lists.
- D4 is optional soft presence — course guides can still pass D2/D3.
- Graph↔Lesson alignment is **out of presence depth** (later quality).

## Lab + tests

- Lab smoke: `projects/lab-teacher-support-path-d/`
- Offline: `test_path_d_teacher_support.py` + `tests/fixtures/path_d/`
- Checklist: `workflows/checklists/teacher_support.yaml`

## Outputs

- `path_d/findings.json` — `inventory` + `steps_by_doc`
