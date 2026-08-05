# Path H — Exit ticket workflow

**Lens name:** Exit ticket (Path H). Taxonomy: [PATHS.md](PATHS.md).

Entry: Loom router typed the document as `exit_ticket` (filename / prior).

## Why not Path B?

Quizzes and answer keys are a **paired** assessment artifact (items ↔ key).
Exit tickets are a **standalone formative check** — different length, purpose,
and quality bar. No key required.

## Steps (H1 → H5)

| Step | Name | Intent |
|------|------|--------|
| **H1** | Inventory | Layer 0 / source excerpts |
| **H2** | Formative prompt | Exit framing + student-facing question |
| **H3** | Target cue | Optional objective / today’s lesson / TEKS |
| **H4** | Next-day signal | Light formative cues (rate / learn / challenge / checkbox / hand in) |
| **H5** | Emit | Stub — short one-pager later |

## Guardrails

- Auditor-only: blank = not found.
- No Hunter plate (Path A). No answer-key requirement (Path B).
- No invented student responses or reteach scripts.

## Lab + tests

- Lab smoke: `projects/lab-exit-ticket-path-h/`
- Offline: `test_path_h_exit_ticket.py` + `tests/fixtures/path_h/`
- Checklist: `workflows/checklists/exit_ticket.yaml`

## Outputs

- `path_h/findings.json` — `inventory` + `steps_by_doc`
