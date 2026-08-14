# Path B — Assessment workflow — quiz ↔ key

**Lens name:** Assessment (Path B). Taxonomy: [PATHS.md](PATHS.md).

Entry: filename quiz/key **or** graph Assessment link (or rubric when
assessment-bearing). **Exit tickets are Path H.**

## Steps (B1 → B6)

| Step | Name | Intent |
|------|------|--------|
| **B1** | Inventory | Layer 0 / source excerpts for this doc |
| **B2** | Item stems | Numbered questions + choice options |
| **B3** | Answer key signal | “Answer key(s)” section / keyed answers |
| **B4** | Targets | Optional objective / TEKS cue |
| **B5** | Pairing | Quiz↔key match by normalized filename stem |
| **B6** | Emit | Stub — short one-pager later |

## Pairing

Two routed docs share a **pair key** (hash prefix + `quiz` / `answer_key` /
`quizizz` noise stripped). Matched quiz+key → B5 PRESENT. Orphan quiz or key
→ B5 PARTIAL. Rubrics alone → NOT_APPLICABLE.

## Guardrails

- Auditor-only: blank = not found.
- No Hunter plate (Path A). No exit-ticket checks (Path H).
- Never invent items or keys.

## Lab + tests

- Lab smoke: `projects/lab-assessment-path-b/`
- Offline: `test_path_b_assessment.py` + `tests/fixtures/path_b/`
- Checklist: `workflows/checklists/assessment.yaml`

## Outputs

- `path_b/findings.json` — `inventory` + `steps_by_doc`
