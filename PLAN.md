# Loom — Plan

**Canonical flow:** see [`docs/DATA-FLOW.md`](docs/DATA-FLOW.md) and [`docs/DATA-FLOW.png`](docs/DATA-FLOW.png).

## Locked pipeline order

```
sources → extract → Layer 0 (decompose + classify)
       → graph HAS-PART (--with-graph)
       → Loom router (BEFORE units) → Path A–H
         (A lesson / B assessment / C general / D teacher support /
          E student practice / F standards & pacing / G syllabus / H exit ticket)
       → place into units → unit assemble
       → model calendars + year map
       → education plates + teacher packet → Drive
```

**Doctrine:** templates are checkboxes/guidelines. Fill only evidence. Blank / MISSING = curriculum gap signal. Never invent lesson content. Call weak / developing / strong honestly when tiers land.

## What Loom adds vs Crystallize

Crystallize classifies then runs the same analysis for everything. Loom **routes** after Layer 0 + graph so lesson plans, quizzes, TE/SE, pacing, syllabus, and leftovers get different workflows — and **nothing is placed into a unit until it has been routed**. Graphing solves silent names (Bluebonnet TE/SE no longer dump to Path C). `route.py` still writes `layer0/route-map.json`; path runners do not re-read the graph.

## Phases (ship order)

| Phase | Deliverable |
|-------|-------------|
| **0** | Doctrine + handoff schemas + Path B/C stub docs |
| **1** | `route.py` → `layer0/route-map.json` + `_loom_feedback.yaml` |
| **2** | Path A (A1–A8) + model Hunter placement + `LESSON-PLAN` on Drive |
| **3** | Soft gate: no unit placement without a route; Path B/C stubs |
| **4** | Model calendars after assemble; early rollup demoted |
| **5** | Weak / Developing / Strong tiers in reports |

## Design principles

1. **One file at a time.** No massive refactors.
2. **Generic fallback always works.** After filename + graph, leftovers → Path C + feedback log.
3. **Feedback is data you read**, not a notification (`_loom_feedback.yaml`).
4. **Auditor-only.** Report gaps; never author curriculum.

## Path docs

Eight lenses (A–H) — see [`docs/PATHS.md`](docs/PATHS.md). Per-path deep docs:

- [`docs/PATH-A-LESSON-PLAN.md`](docs/PATH-A-LESSON-PLAN.md) — A1–A8
- [`docs/PATH-B-QUIZ.md`](docs/PATH-B-QUIZ.md) — assessment (Path B)
- [`docs/PATH-C-GENERAL.md`](docs/PATH-C-GENERAL.md) — general feedback (Path C)

## Handoffs

JSON Schema contracts under [`workflows/handoffs/`](workflows/handoffs/).

## Templates (Northwest ISD)

See [`TEMPLATE_WORKFLOW_MAP.md`](TEMPLATE_WORKFLOW_MAP.md) and checklists under [`workflows/checklists/`](workflows/checklists/). Partner/district template packs stay local and are not redistributed. Staff-role templates = future delivery metadata (who receives what), not a second router yet.

## Out of scope (for now)

- Delivery/role router
- Full academic depth across Paths B–H (presence lenses run; deeper rubric work remains)
- Inventing content to fill blanks
- Rewriting decompose/classify models
