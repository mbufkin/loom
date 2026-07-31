## Destination

A cleared decision map that hands off a buildable spike spec for: **provisional HAS-PART graph → document review → rebuild graph from what review learned**, proven conceptually against `projects/_fixtures/ledger-mini` only. Done when nothing material is left to decide before someone implements the spike.

**Destination met:** handoff written at [`experiments/graphing/SPIKE.md`](../../experiments/graphing/SPIKE.md).

## Notes

- Domain: loom graphing / Learning Commons–style curriculum assemble; fixture `ledger-mini`.
- Wayfinder: **plan, don't do** — no spike implementation in this effort; produce decisions + research assets → handoff spec.
- Standing preferences already voiced: respect whole documents *and* map parts; exit tickets may be embedded or separate; belonging (Assessment ↔ Lesson) matters more than perfect edge form; provisional “get everything in” first; rebuild after review.
- Skills: wayfinder; grilling / domain-modeling when resolving HITL tickets; research subagents for `wayfinder:research`.
- Tracker: local markdown under `.plan/graph-review-rebuild-spike/` (no repo issue-tracker wiring).
- Prior art in-repo: `docs/GRAPHING.md`, `experiments/graphing/`, Arts AV / Ag gold graphs — consult but do not treat as locked for this spike until tickets say so.

## Decisions so far

- [Assemble → review → reassemble literature](./tickets/01-assemble-review-reassemble-literature.md) — Published practice supports provisional org over stable materials, then review→revise; rebuild is expected CQI, not failure.
- [Embedded vs separate assessment attachment](./tickets/02-embedded-vs-separate-assessment.md) — Belonging ≠ packaging; embedded span or separate file both OK if Lesson↔Assessment link exists.
- [When instructional graphs get revised after review](./tickets/03-graph-revision-after-review.md) — Lock inventory early; treat org tree as hypothesis; Path A/B/C findings that re-parent/retype/split are rebuild triggers.
- [Provisional completeness gate](./tickets/04-provisional-completeness-gate.md) — Hard: Material inventory + no orphan sources; soft-queue Materials with no Lesson; defer spans/roles/attach/gold scores to rebuild.
- [Flexible belonging policy](./tickets/05-flexible-belonging-policy.md) — Non-negotiable: Assessment belongs to Lesson via hasPart; embedded or separate file both OK; mini uses separate-file shape; quality later.
- [Rebuild trigger contract](./tickets/06-rebuild-trigger-contract.md) — Batch rebuild after all unit Materials reviewed (unit-close/rollup); inputs = findings + provisional graph; Materials stable, org/edges/spans/roles change.
- [Handoff spec shape](./tickets/07-handoff-spec-shape.md) — Lean `experiments/graphing/SPIKE.md` + per-source flat `graph/.raw/` JSON with provisional/rebuild choices.

## Not yet specified

- **CS loops richer pack.** Later effort after implementers run the ledger-mini spike.
- **Viz of before/after rebuild.** Optional UI; not required to start implementation.
- **Richer rebuild suite.** L0/calendar-coupled triggers — after minimal spike lands.

## Out of scope

- Production wiring into `run_project.py` / full Dallas T2 scale.
- Authoring a full Arts-AV-sized CS companion corpus inside this map.
- Shipping a “winning” graphing algorithm — only the decide-enough-to-spike path.
- Dual-model / 30B transfer rows as a requirement of this spike handoff.
