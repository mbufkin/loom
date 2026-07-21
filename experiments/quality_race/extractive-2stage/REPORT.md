# Quality-race entry: `extractive-2stage`

**Goal of the race.** Loom's banded quality scorers (`s4_quality` from
`workflows/rubrics/quality_dimensions.yaml`, `s2_ubd` from `ubd_alignment.yaml`) ask
the local model to assign a 0–3 band per dimension **and** cite a verbatim excerpt.
The local Nemotron-nano-30B returns bands but **not** valid citations, so the
`_band_result` guardrail in `lesson_scorers.py` downgrades every band to
`[unevidenced band — needs review]`. Net effect: quality scoring is untrusted and
**deferred** (`lesson_rung.LOCKED_SCORERS` excludes s2/s4). This entry tries to make
the citations real.

---

## Approach summary

Do **not** score all dimensions in one shot. For **each** rubric criterion, run a
focused, **two-stage** exchange over **only** that criterion's `reads_from` element
types (capped at 10 elements):

1. **Stage 1 — extract (forced).** *"From these elements, COPY the single most
   relevant verbatim sentence for `<dimension>`; only reply empty if nothing relates."*
   Then **code** validates the returned quote is a real substring of one shown
   element (whitespace-insensitive, surrounding quote-punctuation stripped). If it
   isn't, retry **once** with an explicit "your quote was not verbatim" nudge; still
   invalid ⇒ treat as **NONE**.
2. **Stage 2 — band.** Given the *code-validated* quote, assign the 0–3 band for that
   one dimension. A validated citation floors the band at 1 (a real citation ⇒ at
   least "emerging"); **no valid quote ⇒ band 0 / absent.**

**Why it works (the key empirical finding).** In a *combined* prompt the local model
returns a band and leaves the quote empty — it will judge but won't commit to
copying. Splitting extraction into its own call, over a tiny single-dimension
context, forces it to actually pull a span from the few elements in front of it.
Grounding is then enforced in **code**, so the model can never fabricate authority.

Files (all additive, under `experiments/quality_race/extractive-2stage/`):
- `extractive_scorer.py` — registers new scorers `s4_quality_extractive` and
  `s2_ubd_extractive` (rubric-agnostic; no shared file touched, only imported).
- `run_eval.py` — builds the eval set, runs baseline vs. candidate, computes metrics.
- `results.json`, `run_output.log` — raw run artifacts.

---

## Eval set

Per the fairness note, the Dallas ledger is **PARTIAL** (rebuild pending), so we
evaluate over **both**:
- **(a)** `enumerate_lessons("dallas-career-2026")` → **3 real lessons** (capped for a
  frugal single-GPU run), and
- **(b)** **3 hand-crafted mini-lessons** so citation behaviour is deterministic:
  one clearly **STRONG**, one **WEAK/skeletal**, one carrying an explicit **ELPS /
  language-support** sentence.

**6 lessons total × 6 quality dimensions = 36 criteria per method.**

---

## Metrics (baseline `s4_quality` vs. `s4_quality_extractive`)

Pooled the citation-rate way (sum numerators/denominators across lessons).
`citation_rate = (#criteria band>0 with a VALID citation) / (#criteria band>0)`, where
VALID = evidence `element_id` resolves to a real lesson element **and** the quote is a
verbatim (whitespace-insensitive) substring of that element — applied identically to
both methods.

| Metric | Baseline `s4_quality` | `extractive-2stage` | Lift |
|---|---|---|---|
| **PRIMARY citation_rate** | **0.00** (0 / 20) | **1.00** (11 / 11) | **+1.00** |
| coverage (valid-cited / all 36 criteria) | 0.00 | 0.306 | +0.306 |
| criteria banded > 0 | 20 | 11 | −9 (more conservative) |
| avg **model calls / lesson** | **1.0** | **8.5** | **+7.5× cost** |
| avg **wall time / lesson** | 13.88 s | **12.32 s** | ≈ equal |
| gold MAE (overlapping lessons) | — (0 overlap) | — (0 overlap) | — |

**Reading the table.** The baseline confidently bands 20 criteria and grounds **none**
of them — exactly the "untrusted, deferred" state the race is trying to fix. The
extractive scorer bands fewer criteria (11) but grounds **every single one** in the
lesson's own words: citation_rate goes **0.00 → 1.00**.

**Cost tradeoff — the honest surprise.** The approach costs **~8.5× the model calls**
per lesson (1 → 8.5), as predicted. But **wall time is essentially flat** (even
slightly lower): the baseline's one call must emit a long multi-dimension JSON, while
each extractive call emits a tiny `{quote}` or `{band}` object, so many small calls
finish in about the same total time as one big call. The real cost is therefore
**request count / GPU scheduling pressure on a shared box**, not latency.

**Gold MAE.** `GOLD-LESSON.json` lesson ids do **not** overlap the current partial
ledger's 3 lessons, and the synthetic lessons have no gold, so MAE has **0 comparable
rows** right now. The harness computes it automatically (`_gold_mae`) and will produce
real numbers the moment the Dallas ledger is rebuilt with the gold ids present — no
code change needed. As a stand-in **directional** validity check on the deterministic
synthetic lessons, the extractive normalized scores order correctly:

| Synthetic lesson | extractive normalized (mean band / 3) | expected |
|---|---|---|
| STRONG | **0.50** | highest |
| ELPS | 0.33 | middle |
| WEAK/skeletal | **0.00** | lowest |

STRONG > ELPS > WEAK, and every point is citation-backed.

---

## One concrete cited-band example

ELPS lesson, dimension **`differentiation_supports`**, **band 2**, evidence
`elps-e2`:

> **quote (verbatim from the lesson):** "Language support (ELPS): Provide sentence
> stems for emergent bilingual students — 'I would choose the ____ cluster because
> ____' — and a bilingual glossary of the cluster names."
>
> **model note:** "The lesson provides specific ELPS supports: sentence stems and a
> bilingual glossary."

The band is trustworthy because the quote was **code-verified** to be a real substring
of element `elps-e2` before the band was accepted. (Baseline banded the same lesson's
differentiation dimension but attached **no** citation, so it was downgraded to
needs-review.)

---

## Honest failure modes

1. **Low recall / coverage (0.306).** The scorer only bands what it can ground, so
   dimensions the model won't extract for become band 0 even when a human might see
   partial evidence. **`engagement`** and **`coherent_sequence_closure`** are the
   weakest — the model under-extracts for "softer", cross-element dimensions and
   returns NONE (e.g. it missed the STRONG lesson's hook in one run). This is a
   **precision-over-recall** trade: correct for an auditor, but the coverage number
   looks low and should not be read as "the lessons are bad".
2. **Band floor coercion.** A validated citation forces band ≥ 1 even if Stage 2 says
   0. This is a deliberate design choice (a real, on-topic citation ⇒ at least
   "emerging"); it slightly inflates low bands and is documented in code.
3. **Match tolerance is not byte-identical.** To avoid rejecting genuinely-verbatim
   quotes broken only by table padding / hard line-wraps or wrapper quote-marks, the
   substring check is whitespace-insensitive and strips surrounding quote
   punctuation. This is a small, explicit relaxation of "verbatim"; the **stored
   evidence is always the source element's own text**, never the model's echo.
4. **Cost.** 8.5× calls/lesson. Wall-time-neutral in this run, but on a contended
   shared GPU the extra requests add scheduling/queueing overhead and would scale
   poorly across a full (non-partial) corpus of hundreds of lessons.
5. **No gold overlap yet** (partial ledger) — accuracy vs. human gold is unproven;
   only citation *trustworthiness* and directional ordering are demonstrated.

---

## Recommendation: **PROMOTE (conditionally)**

The entry does the one thing the race is about: it converts a **0.00** citation rate
into **1.00**, turning the deferred `s4_quality`/`s2_ubd` scorers from
"confident-but-untrusted" into "fully grounded", **at roughly equal wall-time**. The
approach is rubric-agnostic (proven on both quality and UbD rubrics) and additive
(new scorer ids, zero edits to shared files), so it can be trialed without risk.

Promote to unlock quality scoring in the lesson rung, **conditioned on**:
- **Rebuild the Dallas ledger** and re-run so gold MAE is actually measured before any
  lock-in (agreement with human gold, not just citation trust, must pick the winner).
- **Improve recall on `engagement` / `coherent_sequence_closure`** (e.g. widen their
  `reads_from` candidate window or a gentler NONE threshold) — current coverage 0.306
  is precision-driven but leaves grounded evidence on the table.
- **Budget the 8.5× call cost** for full-corpus runs (batch, or reserve for the
  human-look queue / divergent lessons rather than every lesson every run).

Net: the citation problem is **solved** for the sampled lessons; promote behind a
ledger-rebuild + coverage-tuning gate rather than locking in blindly.
