# Quality-scorer race — approach `grounded-rate`

**Branch:** `quality-race/grounded-rate`
**Scorer id:** `s4_quality_grounded` (+ `s2_ubd_grounded`), registered in
`experiments/quality_race/grounded-rate/grounded_scorer.py`
**Baseline compared:** shipped `s4_quality` (`lesson_scorers.py`)

## The problem, in one line

The shipped band scorers ask the local model (Nemotron-3-Nano-30B) to *both* assign
a 0-3 band *and* cite a verbatim quote + element id. The model returns bands but
invalid/missing citations, so `_band_result`'s guardrail downgrades them to
`[unevidenced band — needs review]`. Quality scoring is therefore untrusted and
deferred (`lesson_rung.LOCKED_SCORERS` excludes `s2`/`s4`).

## The approach: code owns the evidence, the model only rates

Flip the responsibility so citation is guaranteed **by construction**:

1. **Deterministic evidence selection.** For each criterion, code ranks the
   lesson's own elements by a transparent lexical score:
   `4 × rubric-keyword-phrase hits + 1 × content-token overlap with the criterion
   description/label + 2 if the element's Layer 0 type is one the criterion
   reads_from`. The top 1-2 elements are the evidence. Candidate pool is restricted
   to the criterion's `reads_from` types (falls back to all elements on a
   partially-tagged corpus).
2. **Model rates only.** The model is shown the *pre-selected* excerpt(s) and asked
   for a band 0-3 + one-line justification — nothing else. The `element_id`/`quote`
   come from code, so the guardrail can never fire.
3. **Deterministic proxy floors.** `cognitive_rigor` gets a floor of 2 when a
   DOK/Bloom verb is present; `differentiation_supports` gets a floor of 2 when an
   ELPS/scaffold/accommodation term is present; objective criteria get a floor of 1.
   The reported band is `max(model_band, floor)` — a guardrail against the model
   under-rating evidence whose relevance the lesson's own words make unambiguous.

Auditor-only throughout: every quote is copied verbatim from the lesson; nothing is
invented or rewritten. Additive-only: no shared file was edited.

## Evaluation set (honest about data reality)

The Dallas ledger is a PARTIAL rebuild — `enumerate_lessons("dallas-career-2026")`
returns **3** lessons whose doc_ids **no longer overlap** `GOLD-LESSON.json` (0
id-overlap, confirmed). Per the brief we did not block. We evaluated over:

- the **3 Dallas lessons** enumerate returns, plus
- **3 hand-crafted mini lessons**: one clearly STRONG, one WEAK/skeletal, one with an
  explicit ELPS/language-support sentence.

**Gold for MAE** (n=4): the 3 mini anchors (values we *designed*, labelled as such —
not SME truth) + 1 Dallas lesson we could confidently title-match to the shipped gold
("Engineering Lesson Plan" ↔ gold "Engineering Lesson" = 0.6). Both scorers are graded
identically on this set. Reproduce with `python3 run_eval.py` (raw:
`eval_results.json`).

## Metric table

| Metric | baseline `s4_quality` | `s4_quality_grounded` |
|---|---|---|
| **citation_rate** (non-zero bands that carry a valid citation) | **0.412** | **1.000** |
| **on-point rate** (code-selected evidence genuinely relevant) | n/a¹ | **0.611** |
| **gold MAE** (n=4, lower is better) | **0.203** | **0.147** |
| calls per lesson | 1.0 | 1.0 |
| wall-time per lesson | 13.6 s | 11.1 s |

¹ The baseline lets the *model* pick evidence, so "was our selection on-point" is not a
meaningful question for it; its analogue is the citation_rate itself.

### Where the difference comes from (per-lesson normalized score, 0-1)

| Lesson | gold | baseline (cited/nonzero) | grounded (cited/nonzero) |
|---|---|---|---|
| MINI strong | 0.85 | 0.83 (5/5) | 0.72 (6/6) |
| MINI weak/skeletal | 0.15 | 0.11 (0/2) | 0.06 (1/1) |
| MINI explicit-ELPS | 0.60 | 0.33 (2/4) | 0.50 (5/5) |
| Engineering Lesson Plan (Dallas) | 0.60 | 0.11 (0/2) | 0.33 (4/4) |
| Career Clusters – Slides (Dallas) | — | 0.11 (0/2) | 0.44 (5/5) |
| Family & Community Wellness (Dallas) | — | 0.11 (0/2) | 0.33 (4/4) |

The pattern is the whole story: on messy real Dallas lessons the baseline collapses to
`0.11` with **zero cited bands** (every band downgraded to needs-review), so it is both
untrusted *and* wrong vs gold. Grounded still extracts a differentiated, fully-cited
signal. The baseline edges grounded only on the clean, short STRONG mini, where the
model *can* cite reliably.

## One concrete cited-band example

From the explicit-ELPS mini lesson, criterion **differentiation_supports**:

- **band = 3** (`model_band=3`, `proxy_floor=2` → blended 3)
- **element_id** `mini_elps-gp`
- **quote (verbatim, code-selected):** *"Language objective / ELPS support: provide
  sentence stems ('The ____ branch is responsible for ____') and a bilingual word bank
  as an accommodation for emergent bilingual (ELL) students; scaffold with a graphic
  organizer."*
- model justification: *"The lesson explicitly provides ELPS supports such as bilingual
  word banks, sentence stems, and graphic organizers…"*

Code found the exact ELPS element by keyword overlap (score 28 — six keyword hits), the
model rated it exemplary, and the proxy floor independently confirms ≥2. Citation is
valid by construction.

## Is the code-selected evidence trustworthy? (honest discussion)

**Yes for citation_rate — that claim is airtight.** 1.000 by construction, confirmed
both offline and live. The `[unevidenced band]` failure mode is structurally eliminated.

**Only partially for the evidence itself.** The on-point rate is **0.611**, not ~1.0,
and that is the honest headline caveat: guaranteed citation is worthless if the quote is
off-topic. Two clear regimes emerged:

- **Keyword-anchored criteria are excellent.** `differentiation_supports` (rubric ships
  an ELPS keyword list) and the DOK-verb proxy for `cognitive_rigor` select
  strongly-relevant evidence — this is where lexical overlap shines and the proxy floors
  fire correctly.
- **Abstract criteria degrade to "right section, unproven topic."** `engagement`,
  `coherent_sequence_closure`, and rigor-without-a-verb have little literal vocabulary
  overlap with lesson prose, so selection falls back to the `reads_from` type bonus:
  it picks the correct *kind* of element but can't lexically prove relevance. Fragmented
  slide decks are the worst case — "Career Clusters – Slides" scored on-point only 0.167
  because its elements are title-fragments ("Career Cluster Overview / Day 1").

So the MAE win is real but partly carried by the proxy floors on two criteria, not by
uniformly great selection. Token overlap is a floor, not a ceiling.

## Promote or not

**Promote as a candidate — behind a flag, not straight into `LOCKED_SCORERS` yet.**

- The core bet is validated: citation becomes a solved problem (0.41 → 1.00) at **equal
  cost** (1 call/lesson, actually slightly faster), and gold agreement improves ~28%
  (MAE 0.203 → 0.147), decisively so on the messy real lessons that matter.
- **But** the new bottleneck is evidence-selection quality (on-point 0.61). Before this
  scorer earns a spot in the locked rung it should either (a) upgrade selection beyond
  bag-of-words for abstract criteria (small embedding similarity, or richer per-criterion
  keyword lists like differentiation already has), and (b) be re-run against a **real,
  id-aligned Dallas gold** once the ledger rebuild lands — the current n=4 gold (3 of
  which are anchors we designed) is a smoke test, not a verdict.

Recommendation: adopt `s4_quality_grounded` as the trusted-citation replacement for
`s4_quality` in the next bake-off, keep it out of `LOCKED_SCORERS` until on-point rate
clears ~0.8 on an aligned gold, and surface `on_point_rate` in the bake-off report as the
gate metric.

## Files (all additive, under `experiments/quality_race/grounded-rate/`)

- `grounded_scorer.py` — the scorer (selection + proxy floors + rater), registers
  `s4_quality_grounded` / `s2_ubd_grounded`.
- `run_eval.py` — the head-to-head harness (`--offline` for a no-model dry run).
- `eval_results.json` — raw per-lesson results from the live run.
- `REPORT.md` — this file.
