# Architecture — Loom

> **Program vs data:** Loom (repo root) is one auditor program.
> Folders under `projects/<id>/` are interchangeable curriculum datasets.
> `./run-audit <id>` runs Layer 0 → **route (Path A/B/C)** → Layer 1 → Layer 2 → **calendars** → hybrid synthesize (headline path).
> See [PIPELINE.md](PIPELINE.md), [DEPENDENCY_FLOW.md](../DEPENDENCY_FLOW.md), and [projects/STATUS.md](../projects/STATUS.md).

## Single responsibility

**Loom** = read-only **curriculum document auditor** (one program, any corpus).

It is **not** a code review tool, LMS, or curriculum authoring system.

## Boundary diagram

```
┌─────────────────────────────────────────────────────────┐
│  INPUT: curriculum documents (any amount, any format)   │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  STRUCTURAL INFERENCE (maps only)                       │
│  unit calendars · pacing plan · year-at-a-glance        │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  CONTENT AUDIT (evidence only)                          │
│  Layer 0 elements → Loom router (Path A/B/C) →          │
│  → Layer 1 placement → Layer 2 completeness (code)      │
│  → model calendars (authoritative inferred map)         │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  OUTPUT: FIRST-PASS + teacher packets + PDF              │
│  never lesson plans or assessments                      │
└─────────────────────────────────────────────────────────┘
```

## Two-engine design

| Layer | Responsibility |
|-------|----------------|
| **Code** | Extraction, deterministic rollup, Layer 2 completeness, PDF layout, aggregate stats, dashboard / review-queue plates |
| **Models** | Judgment calls on messy filenames, Layer 0/1 semantics, Loom routing (Path A/B/C decision), model calendars, hybrid first-pass / teacher narrative |

Models never receive a charter to **author** curriculum — only to **classify**, **organize**, and **place** existing files.

## Shared infrastructure

Runs against local OpenAI-compatible inference endpoints configured as `analyst_*` and
`verifier_*`. **Single-model doctrine** ([BETS.md](BETS.md) Bet 5 / 9): both roles may
point at the same endpoint; “verifier” is on-demand second-pass framing of the same
model, not a required second weaker server. Model choice and hardware are deployment
concerns.

## Related tools

Code review and curriculum audit are **separate products**. Do not merge their pipelines.
