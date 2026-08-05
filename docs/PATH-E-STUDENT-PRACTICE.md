# Path E — Student practice workflow

**Lens name:** Student practice (Path E). Taxonomy: [PATHS.md](PATHS.md).

Entry: Loom router filename prior (`learn` / `practice` / `succeed` /
`student_edition` / `worksheet`) or graph roles `learn_student` /
`practice_student`.

## Why not Path B / Path D?

- **Path B** is quiz ↔ answer key (paired assessment).
- **Path D** is adult-facing TE / educator / implementation guides.
- **Path E** is **student-facing** Learn / Practice / Succeed / worksheets —
  task presence, not keys or facilitation scripts.

## Steps (E1 → E5)

| Step | Name | Intent |
|------|------|--------|
| **E1** | Inventory | Layer 0 / source excerpts |
| **E2** | Document role | Learn / Practice / Succeed / worksheet / SE cues |
| **E3** | Student tasks | Problems / prompts / RDW / work-process cues |
| **E4** | Target cue | Optional objective / TEKS / lesson cue |
| **E5** | Emit | Stub — short one-pager later |

## Guardrails

- Auditor-only: blank = not found.
- No answer-key requirement (Path B). No TE facilitation checks (Path D).
- Do not invent student items or solutions.
- E4 is optional soft presence — thin Practice / worksheets can still pass E2/E3.
- Learn↔Practice↔Succeed family pairing and lesson-objective alignment are
  **out of presence depth** (later quality).

## Lab + tests

- Lab smoke: `projects/lab-student-practice-path-e/`
- Offline: `test_path_e_student_practice.py` + `tests/fixtures/path_e/`
- Checklist: `workflows/checklists/student_practice.yaml`

## Outputs

- `path_e/findings.json` — `inventory` + `steps_by_doc`
