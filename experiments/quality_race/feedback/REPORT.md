# Feedback-first quality scorer

## Why this exists
The race (force-cite / extractive-2stage / grounded-rate) all solved the *citation*
layer — making the model attach a verbatim quote to each band. But looking at the
raw model output reframed the problem: **the model already produces useful
per-dimension diagnosis.** The real defects were (1) some notes came back empty
(the prompt asked for "one short sentence" and never required a rationale for a
band-0), and (2) every note was stamped `[unevidenced band — needs review]`
because the model skipped the quote.

Decision: treat the **diagnostic note as the product** and citation as secondary.

## What changed vs baseline `s4_quality`
- Prompt requires a **specific 1-2 sentence note for every dimension**, and for a
  band 0/1 it must **name exactly what is missing** (no generic filler).
- A missing verbatim quote no longer poisons the note with a needs-review stamp;
  a quote is captured when offered, otherwise omitted.
- Deterministic fallback guarantees no dimension is ever left noteless.
- Keeps Loom's read-only **auditor** stance: diagnose what the lesson shows or
  lacks; never rewrite or prescribe new lesson content.

## Results (7 Dallas lessons, same 1 model call/lesson, ~11s)
| metric | baseline `s4_quality` | `s4_quality_feedback` |
|---|---|---|
| note_coverage (dims with a substantive note) | 0.714 | **1.000** |
| specificity (note words found in the lesson) | 0.148 | **0.177** |
| avg_note_len | 56 | **138** |

### Before / after (Hospitality Tourism — baseline returned NO notes)
- Objective — *"No explicit, student-facing learning objective is stated; the plan
  only lists vague goals like 'explore career cluster' without a clear, measurable
  target."*
- Checks for understanding — *"No formative checks, exit tickets, or questioning
  strategies are evident to gauge student understanding."*
- Differentiation — *"No indication of scaffolds, language objectives, or
  accommodations for ELPS/SpEd/Gifted learners."*

## Behavior note
The feedback scorer is a **stricter auditor** — it assigns more honest 0s/1s where
the baseline inflated to 1s/2s. That widens numeric MAE against the (lenient,
provisional) 7-lesson gold, which is precisely why band-vs-gold MAE is the wrong
target here. The note is what a teacher acts on.

## Open follow-ups
- Layer 0 emits 5E/compound element types (`explore_activity|guided_practice`)
  that get coerced to `unclear`, thinning candidate selection. Fixing that would
  raise specificity further for all scorers.
- Consider a light second-pass "accuracy" check (LLM-as-judge or human spot-check)
  on a sample, since specificity only proxies groundedness, not correctness.
