# Path A golden fixtures — proving set

**Ticket:** [05-path-a-golden-fixtures](../tickets/05-path-a-golden-fixtures.md)  
**Scores with:** [06-path-a-trust-scorecard](../tickets/06-path-a-trust-scorecard.md) (C1–C4 + X5–X7 + G8)  
**Date:** 2026-08-04

---

## Proving set (locked)

**Corpus:** Dallas career only (`projects/dallas-career-2026/`).  
**Size:** three fixed units spanning strong / mixed / weak plate signals.  
**Bluebonnet:** out of set (empty Path A / no `lesson_plan` routes).

| Role | Unit id | Plate path | Plate summary (today) | Why in set |
|------|---------|------------|------------------------|------------|
| **Strong** | `engineering` | `output/teachers/engineering/LESSON-PLAN.md` (+ `.json`) | 13/14 PRESENT · Hunter 8/8 · missing `elps_language` | Full instructional sequence; thin support gap only |
| **Mixed** | `teaching-and-training` | `output/teachers/teaching-and-training/LESSON-PLAN.md` (+ `.json`) | 12/14 PRESENT · Hunter 8/8 · missing `elps_language`, `accommodations` | Complete Hunter; both A7-style supports missing |
| **Weak** | `family-community` | `output/teachers/family-community/LESSON-PLAN.md` (+ `.json`) | 10/14 PRESENT · Hunter 6/8 · missing `independent_practice`, `closure`, `elps_language`, `accommodations` | Sequence holes + supports; also ties to heavy A6 cite source (`052a682bd60f` Family/Community lesson plan) |

Each fixture under test = **real LP materials for that unit** + **unit plate** + **Path A one-pager**.  
Two judgments on the same page: **(a) fidelity to the actual curriculum LP** and **(b) trust gates** — not lesson-plan length.

---

## Expanded usefulness loop (locked 2026-08-04)

**Human / cheap now** — for each trio unit:

1. **Lesson plan in** — open real LP sources under `projects/dallas-career-2026/sources/` (plus unit folder context) **and** the unit plate `output/teachers/<unit>/LESSON-PLAN.*`.
2. **Feedback given** — draft/show a Path A one-pager for that unit (shape from [04-one-page-path-a-prototype](./04-one-page-path-a-prototype.md)).
3. **Feedback reviewed** — human scores:
   - **(a) Fidelity** — Top gaps / Why / evidence pointers match what is actually in the LP materials (no cross-unit cite bleed; no false PRESENT).
   - **(b) Trust gates** — C1–C4 + X5–X7 + G8; any NO fails.

Prefer all three roles (strong / mixed / weak) before calling the Path A shape trusted.

---

## IN criteria

A usefulness fixture is **IN** when all of these hold:

1. **Dallas unit** from the locked trio above (stable `unit_id` + on-disk plate + real LP sources).
2. **Inputs for the loop** — real LP materials (`sources/…`) **and** unit plate `output/teachers/<unit>/LESSON-PLAN.*`.
3. **Artifact under test is the shared one-pager** (shape from [04-one-page-path-a-prototype](./04-one-page-path-a-prototype.md)).
4. **Scored two ways** — fidelity to the LP **and** every locked hard gate (C1–C4 + X5–X7 + G8); any NO fails the sample.

---

## OUT criteria

Explicitly **OUT** of this proving set:

| Out | Why |
|-----|-----|
| Bluebonnet (any module) | Path A shell only (`doc_ids: []`); map excludes full Bluebonnet corpus |
| Project-level `path_a/findings.json` alone | Project-scoped / not unit-scoped; not the shared one-pager humans trust |
| Full 18-unit Dallas corpus | Too large for a cheap usefulness loop; stratification already covered by 3 |
| Other Dallas units not in the trio | Keep the set fixed; do not silently expand |
| Classroom observation / T-TESS walkthrough rubrics | Out of map scope as Path A logic |
| Invented lesson drafts as “Improve” oracles | Violates auditor-only; C3 |

**Not required for IN (deferred):** hand-labeled expected Top-gaps / quality oracle per unit. Nice for a later regression harness; not a gate for membership in this proving set.

---

## How to run (same as expanded loop)

See **Expanded usefulness loop** above. Scorecard worksheet: [06-trust-scorecard-example](./06-trust-scorecard-example.md).

---

## Gist

Dallas trio — `engineering` · `teaching-and-training` · `family-community` — is the Path A usefulness proving set. Loop = **LP in → feedback given → feedback reviewed** (fidelity + trust gates). OUT = Bluebonnet, findings-json-only, full corpus, observation rubrics, invented drafts.
