---
type: research
blocked_by: []
claimed_by: cursor-research
claimed_at: 2026-08-03T23:30:00Z
resolved_at: 2026-08-03T23:35:56Z
assets:
  - ../assets/01-current-path-a-output-inventory.md
---

# Current Path A output inventory

## Question

What does Path A **emit today** on golden Dallas (and one Bluebonnet sample if present): `path_a/findings.json` shape, LESSON-PLAN plate fields, approximate length, and which signals a human could already use vs noise — so later tickets reshape passes against reality, not the doc alone?

## Answer

Full inventory: [01-current-path-a-output-inventory asset](../assets/01-current-path-a-output-inventory.md).

**Gist:**

- Dallas Path A emits one project-level `path_a/findings.json` (~22–23 KB) with steps **A1–A8**, top-level `a6_fields` (14 plate ids), and `emit_paths`; plus duplicate per-doc JSON that only changes `doc_id`.
- Status language today: `PRESENT`/`MISSING`, A3 `COHERENT`/`PARTIAL`/`MISSING`, A6 `method` (`code_fallback`|`model`), A8 `emitted`; cites are ≤~500-char truncated excerpts (often table-dump noise) or `_(Source: …)_` on unit plates.
- Unit `LESSON-PLAN.md` plates are ~7–20 KB; Path A only overlays `path_a.hunter` + `a6_method` — plate body is discovery fill, not A6 text.
- **Usable now:** per-unit matrix PRESENT/MISSING, A2 TEKS/objective flags, A3 mismatch codes, A4 formative/summative with `element_id`, A7 honest MISSING on Dallas CTE.
- **Noise now:** project-scoped cite bleed across careers, false PRESENT on wrong Hunter slots, table-dump duplicates, per-doc JSON that isn’t doc-scoped, Bluebonnet empty Path A (`doc_ids: []`) beside rich TE plates.
- **Bluebonnet:** no `lesson_plan`-routed docs → Path A is an empty shell; closest substitute is discovery-filled `LESSON-PLAN.*`, not `path_a/findings.json`.
