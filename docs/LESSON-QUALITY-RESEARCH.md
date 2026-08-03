# Lesson-quality scoring — what the research says (and how it maps to our bugs)

**Date:** 2026-07-21
**Why:** our lesson-quality grader (`s4_quality_feedback`) scores *too harshly* — even a
strong curriculum (Bluebonnet) averages < 1.0 / 3, and on inspection it produces plain
**false negatives** (e.g. Algebra I Module 2, Lesson 2 scored *objective clarity = 0*
when the objectives are printed verbatim in the lesson). Before tuning anything we went
to the LLM-as-judge / automated-essay-scoring literature to understand the failure modes.

This note records the findings, maps each to a concrete defect in our code, and defines
the redesign we are testing. **Gold-set score calibration is explicitly out of scope for
now** (it's a real technique — see finding 4 — but we're deferring it).

---

## The five findings

### 1. Batching all criteria into one prompt is the known-worse design
Analytic rubrics scored **one-criterion-per-call** beat holistic / batched single-prompt
scoring. Batching causes **criterion conflation and halo effects** (a strong dimension
inflates others) and makes the judge **mentally average** across dimensions, yielding
less reliable per-criterion scores — and it destroys the ability to measure per-criterion
reliability.
- *Autorubric: Unifying Rubric-based LLM Evaluation* — arXiv:2603.00077: "per-criterion
  evaluation prevents criterion conflation and halo effects (Lee et al., 2025; Wei et al.,
  2025)… independent criterion scores enable reliability measurement."
- Practitioner rule of thumb (Nemorize, *LLM-as-Judge* course): **"One criterion, one
  prompt call. Multi-criteria single prompts invite the judge to average across
  dimensions mentally."**

**Our defect:** `feedback_scorer.py` sends **1 model call per lesson** with all 6 criteria
in one JSON blob (`cost={"model_calls": 1}`, "One entry per criterion above").

### 2. Make the judge cite/reason *before* it scores
G-Eval's Auto-CoT "form-filling" and RubricEval show that forcing the judge to produce
evaluation reasoning **before** the numeric verdict "logically constrains its own final
output… prevents the model from hallucinating a [score] that contradicts the facts it
just established." The benefit is from **decomposition + forced structure**, not "more
words."
- G-Eval (Liu et al., 2023) via Confident-AI guide; RubricEval; Medium survey
  (Masood, 2025): "criterion-by-criterion reasoning with structured output, not a
  one-line 'is this good' prompt."

**Our defect:** our prompt demotes citation to **"SECONDARY… OPTIONAL"** and lets the
model emit a band with no grounding and in any order. That's why L2 returned band 0 on
an objective that was right there in the candidate text.

### 3. Harshness is a real, documented, directional bias — and partly *our rubric's fault*
- **Deficit / negative rubric framing lowers scores by ~1.2 on a 0–6 scale**; positive
  framing +0.2; **neutral framing is the most accurate** and most stable (GMU *Journal
  of Student-Scientists' Research*, 2025 — AP US History essays, Gemini 2.5 Flash / GPT-4o,
  wording changes screened to SBERT ≥ 0.95 so only *tone* changed).
- LLMs show **stable negative (harsh) bias**, especially on some trait types
  (arXiv:2604.00259, *LLM Essay Scoring under Holistic and Analytic Rubrics*).
- **Central-tendency / range compression**: GPT-4 "was unwilling to assign a top score
  for any category" (Many-Facet Rasch study, TESOL Union, 2025) — explains why nothing
  reaches band 3.
- **Concise keyword prompts beat long rubric-style prompts** in multi-trait analytic
  scoring (arXiv:2604.00259).

**Our defect:** our prompt is aggressively deficit-framed — *"state EXACTLY what is
missing," "an honest 0 is correct; do not inflate."* The literature says that tone
mechanically drives the harshness we're seeing.

### 4. The fix for the *absolute* scale is small-sample bias correction (DEFERRED)
"Instead of relying on raw zero-shot scores, systematic score offsets can be estimated
and corrected using small human-labeled bias-estimation sets, without large-scale
fine-tuning" (arXiv:2604.00259). Bias is detectable with *very small* validation sets for
many traits.

**Status:** noted, **deferred by decision** — we want to first fix the *design* (findings
1–3, 5) so the raw signal is honest, then layer calibration later.

### 5. "Lost in the middle" explains the false-negative objective
Models use information at the **start/end** of a long context reliably but **miss it in
the middle** (U-shaped curve); reader performance *saturates and even degrades* past ~20
retrieved chunks. Remedy: **retrieve fewer, rerank so the relevant evidence is first.**
- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, TACL 2024
  (arXiv:2307.03172).

**Our defect:** `_band_candidates()` dumps up to **40 elements** (`els[:40]`), each
truncated to **600 chars** (`[:600]`). For L2 that was **32 fragments**, and the first
`standards_objectives` element was a **5,811-char ELPS boilerplate block** (mis-typed) —
truncated to 600 chars it's pure ELPS legalese, so the model "saw" boilerplate where the
objective should be and never reached the real objective bullets deeper in the list.

---

## Failure-mode map (Algebra I · Module 2 · Lesson 2)

| Observed | Root cause (finding) |
| --- | --- |
| `objective_clarity = 0` though objectives are printed | lost-in-the-middle (5) + no evidence-first grounding (2) |
| Every dimension < 1.0/3, no band 3s | deficit rubric framing (3) + central-tendency compression (3) |
| Notes generic; dimensions blur together | single-pass batching → halo/averaging (1) |
| ELPS boilerplate treated as "the objective" | candidate noise + no reranking (5); also Layer 0 mis-typing |

---

## What we're building (design fixes only; calibration deferred)

A second scorer, `s4_quality_decomposed`, that changes four things vs. the baseline:

1. **Decompose** — one focused model call per criterion (6 calls/lesson, not 1).
2. **Rerank + shrink candidates** — feed each criterion only *its* `reads_from` elements,
   reranked best-first by keyword/label relevance, top-K, at generous length (no 600-char
   guillotine, few enough elements to avoid lost-in-the-middle).
3. **Evidence-first output** — the model must copy a verbatim quote and give reasoning
   *before* it emits the band (G-Eval form-filling order).
4. **Neutral framing** — remove the deficit-oriented "do not inflate / state exactly what
   is missing" language; describe the band scale neutrally.

### How we validate (no gold set)
A/B on **one lesson we can eyeball** (`alg1-mod-2 L2`): baseline single-pass vs. decomposed.
Success signal = the **known false negative flips** (objective clarity 0 → a defensible
2–3 with a cited quote), without the other dimensions collapsing. If the design wins on a
lesson whose ground truth we can read with our own eyes, *then* we scale it and, later,
add small-sample bias correction (finding 4).

---

---

## First A/B result (Algebra I · Module 2 · Lesson 2, local nemotron3-nano-30b)

Harness: `experiments/quality_race/decomposed/ab_one_lesson.py`. Same lesson, same model,
baseline single-pass vs. decomposed. **Design change alone, no calibration.**

| Dimension | Baseline | Decomposed |
| --- | --- | --- |
| Clarity of learning objective | ○○○ Absent (0) | ●○○ Weak (1) |
| Engagement / relevance | ●○○ Weak (1) | ●●○ Developing (2) |
| Checks for understanding | ○○○ Absent (0) | ●●○ Developing (2) |
| Differentiation & language | ○○○ Absent (0) | ●○○ Weak (1) |
| Cognitive rigor | ●○○ Weak (1) | ●●○ Developing (2) |
| Coherent sequence & closure | ○○○ Absent (0) | ●●○ Developing (2) |
| **Mean band (/3)** | **0.33** | **1.67** |
| model calls / lesson | 1 | 6 |

**Wins (validates findings 1 & 5):** decomposition + reranking roughly *5×'d* the mean and
fixed clear false negatives — "Checks for understanding" went 0 → Developing with grounded
reasoning ("uses Question 3 as a formative assessment tool and ties it to instructional
decisions"), and "Closure" 0 → Developing. The model is now *reading* the text instead of
missing it in the middle.

**Two defects this A/B exposed (next iteration):**
1. **Citation still doesn't bind (0/6 cited).** The model returns confident, specific
   reasoning but leaves `evidence_element_id`/`quote` empty — it won't echo our long
   element ids. Fix: present candidates with SHORT tags `[E1]..[En]` mapped to real ids and
   require the tag (standard LLM-judge trick), rather than asking it to reproduce a
   40-char id.
2. **Objective stayed Weak for the wrong reason.** Layer 0 *split* the objective element;
   the top-ranked candidate was the teacher-prep preamble, not the "Determine/Interpret…"
   objective bullets — because this criterion's rerank keywords are meta words
   ("clarity", "purposeful") absent from the objective text. Fix: rerank objectives by
   structural cues ("objective", "students will", "SWBAT", verb-first bullets) and/or don't
   over-split objective blocks in Layer 0.

Net: the research-backed redesign is the right direction (harshness was a *design* artifact,
not the rubric being right). Citation-binding + objective-reranking are the next two fixes,
then scale beyond one lesson.

### Second A/B result — after the two fixes

Fixes applied to `decomposed_scorer.py`:
- **Short `[E1..En]` tags** mapped back to real element ids (the model would not echo our
  40-char ids; a tiny tag it reproduces reliably).
- **Structural anchors** (`_ANCHORS`) give recall beyond `reads_from` type, and
  **sibling-split reunification** pulls `-splitN` fragments back together — so the
  OBJECTIVES header (split1, `standards_objectives`) and its bullets (split2, mis-typed
  `direct_instruction`) are judged as one block.

| Dimension | Baseline | Decomposed v1 | Decomposed v2 (fixed) |
| --- | --- | --- | --- |
| Clarity of learning objective | Absent (0) | Weak (1) | **Developing (2)** ✅ cited |
| Engagement / relevance | Weak (1) | Developing (2) | Developing (2) ✅ cited |
| Checks for understanding | Absent (0) | Developing (2) | Developing (2) ✅ cited |
| Differentiation & language | Weak (1) | Weak (1) | Weak (1) ✅ cited |
| Cognitive rigor | Weak (1) | Developing (2) | Strong (3) ✅ cited |
| Coherent sequence & closure | Developing (2) | Developing (2) | Developing (2) ✅ cited |
| **Mean band (/3)** | **0.83** | 1.67 | **2.0** |
| **Citation rate** | (secondary) | **0/6** | **6/6** |

**Outcome:** the known false negative flipped (objective 0 → Developing) **with a cited
verbatim quote** — "• Identify key characteristics of linear functions. • Determine the
effects on the graph of a linear function when f(x) is replaced by f(x)+d…". Every
dimension is now evidence-bound. Harshness is materially reduced and, crucially, the
scores are now *defensible* — each has a quote you can check.

**Known residual (separate problem, not this scorer):** `alg1-mod-2 L2` is a *merged*
lesson — the TE pre-pass fused correlation-coefficient content with a later
transformations lesson, so the objective the model cited is the transformations one.
That's a Layer-0 / TE-segmentation issue to fix independently; it does not undermine the
scorer redesign.

### Next
1. Scale the decomposed scorer beyond one lesson (a handful across alg1-mod-2, then a unit).
2. Fix TE-prepass lesson-boundary bleed (separate track).
3. Later: small-sample bias correction for the absolute scale (finding 4, still deferred).

## Sources
- Autorubric — arXiv:2603.00077
- LLM Essay Scoring under Holistic & Analytic Rubrics — arXiv:2604.00259
- Lost in the Middle — arXiv:2307.03172 (TACL 2024)
- Rubric-language tone study — GMU JSSR, 2025
- Many-Facet Rasch GPT-4 rater study — TESOL Union, 2025
- Reflect-and-Revise rubric refinement — arXiv:2510.09030
- G-Eval — Confident-AI guide; RubricEval; Masood survey (Medium, 2025)
- Nemorize *LLM-as-Judge: Reproducible Evaluation* — criteria decomposition lesson
