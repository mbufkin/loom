# Loom — Plan

**Canonical flow:** see [`docs/DATA-FLOW.md`](docs/DATA-FLOW.md) and [`docs/DATA-FLOW.png`](docs/DATA-FLOW.png).

## Locked pipeline order

```
sources → extract → Layer 0 (decompose + classify)
       → Loom router (BEFORE units) → Path A / B / C
       → place into units → unit assemble
       → model calendars + year map
       → education plates + teacher packet → Drive
```

**Doctrine:** templates are checkboxes/guidelines. Fill only evidence. Blank / MISSING = curriculum gap signal. Never invent lesson content. Call weak / developing / strong honestly when tiers land.

## What Loom adds vs Crystallize

Crystallize classifies then runs the same analysis for everything. Loom **routes** after Layer 0 so lesson plans, quizzes, and other docs get different workflows — and **nothing is placed into a unit until it has been routed**.

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
2. **Generic fallback always works.** Unknown types → Path C + feedback log.
3. **Feedback is data you read**, not a notification (`_loom_feedback.yaml`).
4. **Auditor-only.** Report gaps; never author curriculum.

## Path docs

- [`docs/PATH-A-LESSON-PLAN.md`](docs/PATH-A-LESSON-PLAN.md) — A1–A8
- [`docs/PATH-B-QUIZ.md`](docs/PATH-B-QUIZ.md) — B1–B3 stubs
- [`docs/PATH-C-GENERAL.md`](docs/PATH-C-GENERAL.md) — C1–C3 stubs

## Handoffs

JSON Schema contracts under [`workflows/handoffs/`](workflows/handoffs/).

## Templates (Northwest ISD)

See [`TEMPLATE_WORKFLOW_MAP.md`](TEMPLATE_WORKFLOW_MAP.md) and checklists under [`workflows/checklists/`](workflows/checklists/). Partner/district template packs stay local and are not redistributed. Staff-role templates = future delivery metadata (who receives what), not a second router yet.

## Out of scope (for now)

- Delivery/role router
- Full Path B/C academic depth
- Inventing content to fill blanks
- Rewriting decompose/classify models
