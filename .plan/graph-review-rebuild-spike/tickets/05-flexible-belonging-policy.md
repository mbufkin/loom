---
type: grilling
blocked_by: [02]
claimed_by:
claimed_at:
assets: []
---

# Flexible belonging policy

## Question

What attachment policy do we lock for the spike: how an exit ticket (or similar) may appear as **embedded span** and/or **separate file**, what node/edge shapes are allowed for each, and what is *non-negotiable* (Assessment belongs to a Lesson) versus intentionally flexible?

## Answer

**Placement over form. Non-negotiable = Lesson belonging. Quality is a later step.**

### Non-negotiable

Once an exit ticket (or similar) is known, it **must belong to a Lesson**. That is placement only — not pedagogy/quality scoring (deferred).

Until a Lesson exists, soft-queue from [Provisional completeness gate](./04-provisional-completeness-gate.md) still applies (Material in inventory; review waits).

### Intentionally flexible

**Physical form:** embedded span **or** separate assessment file — both allowed in spike policy **if** the Lesson belonging link exists. Do not force one packaging shape.

### Node / edge shapes

| Form | Shape |
|------|--------|
| **Separate file** (what `ledger-mini` exercises) | Source file → `Material`; typed `Assessment` node; **`Lesson -hasPart→ Assessment`**. Material remains inventory; Assessment is the belonging child. |
| **Embedded span** (allowed later; not required on mini) | `Assessment` with span / `element_ids` into a host `Material` (plan/slides); still **`Lesson -hasPart→ Assessment`**. Host file stays whole. |

### Edge choice

Belonging edge for the spike: **`Lesson hasPart → Assessment`** (not `references`-only). Rebuild may refine roles/spans; it must not drop Lesson belonging once known.

### Mini reading

`doc_aaaa03_Mini_Exit_Ticket.txt` → Material + Assessment under the Lesson via `hasPart`. Plan/slides stay Materials; whole docs respected.
