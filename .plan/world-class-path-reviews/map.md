---
label: wayfinder:map
---

# World-class path reviews

## Destination

A locked **Path A quality bar**: multi-pass review (presence first, then a short evidence-backed quality call on each found element) that emits **one shared short artifact** teachers, coaches, and auditors trust — useful, not long. From that bar, extract a **reusable path-quality pattern** so Paths B–F can follow. Cheap prototypes/fixtures are in-bounds to raise fidelity. Done when nothing material is left to decide before someone builds world-class Path A. **B–F checklist depth is ticketed only after A’s bar is locked.**

## Notes

- Domain: Loom review lenses A–F (`docs/PATHS.md`); lead with Path A (`workflows/lesson_plan.py`, `docs/PATH-A-LESSON-PLAN.md`).
- Standing decisions from charting (2026-08-03):
  - Routing/organization of docs into lenses is settled; gap is review quality.
  - Reader: teacher + coach + auditor share one short artifact.
  - Shape: one-page findings — top gaps + evidence cites + what’s PRESENT — no essay.
  - Passes stay (isolate what we’re looking for → is it there? → is what’s there of quality?).
  - Quality = layered: present/missing/misaligned first, then short quality call with evidence (not bare teacher grading).
  - Map mode: plan + cheap prototypes/tests allowed; not a full B–F implementation march.
  - B–F: extract pattern from A; ticket B–F only after A’s bar is locked.
  - **Prior Path A is the starting point** (keep the pass structure / good work). Main gap to close: each rating should **explain why** it was given and **what could improve** it — today’s A does a little of this; world-class A must do it clearly and briefly (still auditor-only: no inventing content).
- Wayfinder: plan-first; prototypes/fixtures OK when a ticket needs them.
- Skills: wayfinder; grilling / domain-modeling for HITL; research subagents for `wayfinder:research`.
- Tracker: local markdown under `.plan/world-class-path-reviews/`. Blocking via ticket frontmatter `blocked_by`.
- Prior art: [PATHS.md](../../docs/PATHS.md), [PATH-A-LESSON-PLAN.md](../../docs/PATH-A-LESSON-PLAN.md), prior map [Graph phase into Loom](../graph-into-loom/map.md).

## Decisions so far

- [Syllabus quality research (Path G)](./tickets/10-syllabus-quality-research.md) — Path G is its own **course syllabus** lens (not Path A/Hunter): G1–G9 for DISD/Texas CTE HS first; lens renamed **Syllabus** (`workflow_id: syllabus`). Spec in `docs/PATH-G-SYLLABUS.md`; presence extractors next.
- [Current Path A output inventory](./tickets/01-current-path-a-output-inventory.md) — Dallas emits A1–A8 + plates (~22KB findings; useful PRESENT/MISSING + mismatch signals; noise = cite bleed, false Hunter PRESENT, non-doc-scoped per-doc JSON); Bluebonnet Path A empty without `lesson_plan` routing.
- [Path A pass set for world-class review](./tickets/02-path-a-pass-set.md) — Keep A1–A8; add why+improve on A2–A7 only (A1/A8 structural); improve = auditor cues, never draft lesson text.
- [Quality-call rubric on PRESENT elements](./tickets/03-quality-call-rubric.md) — PRESENT only: Strong/Adequate/Weak = usable teaching path (not cite density); MISSING/MISALIGNED get why+improve only; why/improve up to a short paragraph, auditor cues, no drafting.
- [One-page Path A shared artifact](./tickets/04-one-page-path-a-artifact.md) — Lock prototype section order: Top gaps → What’s working → Hunter glance → short evidence pointers; never essays/drafts/observation scores.
- [Curriculum feedback form research](./tickets/09-curriculum-feedback-form-research.md) — Field pattern is claim→why→improve, priority-first; Loom draft aligned; copy UbD/Hattie/EdReports habits; adapt ≤3 gaps + Core4+X5–7; avoid observation scores/essays/rewrite-as-improve.
- [Path A human-trust scorecard](./tickets/06-path-a-trust-scorecard.md) — Hard gates: C1–C4 + X5–X7 + G8 (≤3 Top gaps); scores the feedback one-pager, not the lesson plan length.
- [Path A golden fixtures for usefulness tests](./tickets/05-path-a-golden-fixtures.md) — Dallas trio: `engineering` (strong) · `teaching-and-training` (mixed) · `family-community` (weak); human loop **LP in → feedback given → feedback reviewed** (fidelity to real LP + trust gates C1–G8); OUT = Bluebonnet / findings-only / full corpus / observation / invented drafts.

## Not yet specified

- Exact B–F deep checklists (after A pattern exists).
- Whether lesson-level (graph `Lesson` nodes) grain is required after document-level A is world-class, or a later effort.
- How synthesize / teacher packets surface the one-pager.
- Which model backs each Path A pass in production.
- How hard to push ELPS / access beyond today’s A7 once the one-pager exists.

## Out of scope

- Implementing world-class B–F runners before A’s bar is locked.
- Further top-level path letters (H…Z) — grow checklists inside A–G (Path G syllabus already added).
- Classroom-observation rubrics (live T-TESS Domains 2–3 / walkthroughs) as primary Path A logic.
- Inventing lesson content (auditor-only stays).
- Full multi-module Bluebonnet corpus runs as a requirement of this map.
