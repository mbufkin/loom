# Structural Fill vs Content Fill

The most important product boundary in Crystallize.

## The real-world problem

Providers and districts almost never hand you a complete stack:

```
Ideal (rare):     Calendar → Year-at-a-glance → Units → Lesson plans → Materials
What you get:     Some lesson plans, some slides, maybe an exit ticket — often no pacing guide
```

Crystallize works **backward from what exists**.

## Two kinds of “fill in”

### Structural fill — **yes**

Reconstruct **planning maps** that *should* have existed, derived from evidence:

- Unit `calendar.yaml` (Day 1, Day 2, expected artifact roles)
- `pacing-plan.yaml` (which unit sits on which instructional dates)
- Year-at-a-glance grid (cluster × grading period)
- Gap reports (missing slots, unplaced files)

These are **documentation of structure**, not teachable content. They are always tagged:

```yaml
source: inferred_from_documents
```

### Content fill — **never**

The auditor **must not**:

- Write missing lesson plans
- Generate assessments, rubrics, or slides
- Invent units or courses as instructional material
- “Fix” gaps by authoring curriculum

Missing content is **reported**, not created.

## Backward flow

```
Lesson plans & materials (partial input)
        ↓ infer
Unit calendar
        ↓ infer
Pacing plan / year-at-a-glance
        ↓ compare
Gap report: missing Day 2 exit ticket, no official pacing doc, etc.
```

## Unit Plan discovery fill (Loom)

After materials are broken apart and placed into units, Loom also emits a
**Unit Plan plate** (`output/teachers/<unit>/UNIT-PLAN.md`) shaped like the
Northwest ISD / CTAT Unit Plan Template. Fields are pasted from cited Layer 0/1
evidence. **Blank = not found** — this is still structural/discovery fill, not
content authorship. The auditor unit report (`TEACHER-PACKET.md`) stays separate.

See `workflows/checklists/lesson_plan.yaml` and `unit_plan_fill.py`.

## Lesson Plan structure fill (Madeline Hunter)

Loom emits a **Hunter lesson-plan plate**
(`output/teachers/<unit>/LESSON-PLAN.md`) for each unit. Path A (A1–A8) runs
after the Loom router on `lesson_plan` docs; A6 places existing excerpts into
Hunter fields (model when available; code fallback otherwise). Blank = not found.

See `workflows/checklists/daily_lesson_plan.yaml`, `workflows/lesson_plan.py`,
and `lesson_plan_fill.py`.

## Loom order (locked)

Classify → **router** → Path A–H (A lesson / B assessment / C general /
D teacher support / E student practice / F standards & pacing / G syllabus /
H exit ticket) → place into units → assemble →
**inferred calendars** (`calendars_inferred/`) → plates → Drive.
Early `rollup.py` is provisional only.

## How to read inferred maps

> **Inferred projected map** — reconstructed from available documents. Not official district curriculum. Does not replace missing lesson materials.

Use inferred pacing for **audit and planning conversations**, not as adopted district policy unless a human director signs off.

## Best practice for operators

1. Drop whatever documents you have — partial is fine
2. Add `school-calendar.yaml` when you have an official district calendar (improves dated rollup)
3. Treat red cells on the PDF as **procurement / provider gaps**, not prompts for the model to write lessons
4. Re-run with `--ingest` when new files arrive; structural maps refresh automatically
