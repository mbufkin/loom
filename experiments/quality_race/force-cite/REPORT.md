# Quality-race — approach `force-cite`

**Goal:** make Loom's model-based lesson QUALITY scorers (`s4_quality`,
`s2_ubd`) return **trustworthy, verbatim-cited** 0–3 bands on the local model
(Nemotron nano 30B, llama.cpp `:8080`), so quality scoring can graduate from
"deferred / needs-review" into the locked lesson rung.

**Scope / constraints honored:** additive only — everything lives under
`experiments/quality_race/force-cite/` and only *imports* the shared stack
(`lesson_scoring`, `lesson_scorers`, `rubrics`, `audit_lib`, `layer1`). No shared
file was edited. New scorers register under distinct ids
(`s4_quality_forcecite`, `s2_ubd_forcecite`).

---

## Approach summary

Keep the shared design's **one model call per lesson** (all dimensions at once),
but make citation *mandatory and self-healing*:

1. **Tighten the prompt.** Candidates are shown with short synthetic ids
   (`[E0] (type) <text>`). Small models copy `E7` reliably but mangle the real
   Layer-0 ids (`<file>-chunk13of23-e7`), so we do the id-matching ourselves and
   map `E#` back to the real element id after parsing. The preamble states plainly
   that **band > 0 is invalid without an exact verbatim quote**, and that an honest
   0 is correct.
2. **Constrain with GBNF grammar.** The llama.cpp server *does* honor a `grammar`
   field (verified live — see below). We generate a grammar that forces valid JSON
   **and restricts `evidence_element_id` to the real candidate id set** (∪ `""`).
   That structurally eliminates the "cited a non-existent id" failure entirely.
3. **Validate + self-heal.** Grammar can't prove a free-text quote is a real
   substring, so every `band > 0` is validated in code: the quote must be a
   verbatim (whitespace-normalized) substring of the cited element
   (`audit_lib.excerpt_cited_in`, the repo's own citation check). Dimensions that
   fail are **re-prompted alone** (grammar restricted to just those criteria, with
   the specific failure reason shown), up to 2 retries.
4. **Honest fallback.** Any dimension still uncitable after the retries is forced
   to **band 0 / needs-review** — never a trusted uncited band.

### GBNF grammar verification (prerequisite)

A tiny `curl` confirmed the server honors and *enforces* `grammar`: with
`root ::= "PURPLE_TOKEN_XYZ"` the model returned exactly `PURPLE_TOKEN_XYZ`
despite being asked for a color. A JSON grammar with an enumerated `elemid` rule
also worked. **Gotcha found:** each GBNF rule must be on a **single line** — a
multi-line rule body returns HTTP 400. The generator emits one line per rule, and
`_grammar_call` transparently drops the grammar and falls back to prompt-only if a
400 ever occurs, so a grammar hiccup can never hard-fail a lesson.

---

## Metric table (6 lessons: 3 enumerated Dallas + 3 hand-crafted)

| Metric | Baseline `s4_quality` | `force-cite` | Lift |
|---|---|---|---|
| **citation_rate** (band>0 that is verbatim-cited to a real candidate) | **0.00** | **1.00** | **+1.00** |
| coverage (all criteria with valid evidence) | 0.00 | 0.389 | +0.389 |
| calls / lesson | 1.00 | 1.17 | +0.17 |
| wall-time / lesson | 17.5 s | 16.5 s | ~flat |
| gold MAE (normalized band vs human) | N/A¹ | N/A¹ | — |

¹ The 3 lessons the (partial, rebuild-pending) Dallas ledger currently enumerates
(`1787e9b5bfde`, `0acbc6d0b180`, `052a682bd60f`) are **not** in
`GOLD-LESSON.json` (whose ids came from an earlier, fuller ledger), so there is no
gold overlap in this slice. The eval computes MAE automatically the moment an
overlapping lesson exists (`normalized_score` vs gold `quality`); it is simply
empty today. This was expected per the task's "data reality" note and is not a
blocker.

Both scorers are held to the **identical strict bar**, recomputed independently
from each lesson's candidates (not read from the scorer's own stored evidence), so
the comparison is apples-to-apples.

### Per-lesson detail

| Lesson | Baseline band>0 / cited | force-cite band>0 / cited | force-cite calls | forced-zero |
|---|---|---|---|---|
| Career Clusters – Slides (Dallas) | 5 / 0 | 4 / 4 | 1 | 0 |
| Engineering Lesson Plan (Dallas) | 2 / 0 | 2 / 2 | 1 | 0 |
| Family & Community Wellness (Dallas) | 2 / 0 | 0 / 0² | 1 | 0 |
| Mini STRONG (photosynthesis) | 5 / 0 | 5 / 5 | 1 | 0 |
| Mini WEAK (skeleton) | 0 / 0³ | 0 / 0³ | 1 | 0 |
| Mini ELPS-supported | 5 / 0 | 3 / 3 | 2⁴ | 0 |

² force-cite honestly assigned all-0 here rather than the baseline's 2 uncited
bands. ³ The skeleton lesson correctly earns all-zero from both (honest floor).
⁴ One heal-retry fixed the failing dimension(s); no dimension needed the band-0
fallback anywhere in the slice.

**Read of the numbers:** the baseline produces plenty of non-zero bands (2–5 per
lesson) but **not one** survives a strict verbatim check — exactly the documented
failure that got `s2/s4` deferred. force-cite converts that to **100% verbatim
citation** at ~1.17 calls/lesson and roughly the same wall time. It is also
visibly **more honest**: on the ELPS and Family/Wellness lessons it assigns *fewer*
bands than the baseline, declining to score what it can't cite.

---

## One concrete produced CITED band

From the Mini STRONG lesson (single call, no retry):

- **dimension:** `objective_clarity` (Clarity of learning objective)
- **band:** 3 (Exemplary)
- **element_id:** `s-obj`
- **quote (verbatim substring of that element):** *"Students will be able to
  explain how plants convert sunlight, water, and carbon dioxide into glucose and
  oxygen, and diagram the inputs and outputs of photosynthesis."*

The quote is a character-for-character span of element `s-obj`, so it passes
`excerpt_cited_in` and is stored as trusted `Evidence`.

---

## Honest failure modes

- **No gold overlap right now.** Because the Dallas ledger is mid-rebuild, none of
  the enumerable lessons are in the gold set, so agreement-with-human (MAE) is
  unproven on this slice. citation trust is proven; *calibration* of the band
  values against human judgment is not yet. Re-run once the ledger rebuild lands.
- **Coverage ≠ 1.0 by design.** force-cite only counts a criterion as covered when
  it has a real citation; genuinely-absent dimensions (e.g. differentiation in a
  lesson with no supports) stay at 0. That is correct auditor behavior, but it
  means "coverage" here measures *evidence density*, not lesson quality.
- **Verbatim check is whitespace-normalized, not semantic.** A model that quotes
  the right element but trims/paraphrases fails validation and gets re-asked or
  zeroed. This is deliberately strict (no invented authority), but it can zero a
  band that a human would have accepted from a near-verbatim paraphrase.
- **Small extra cost + latency variance.** Heal-retries add calls (1.17 avg here;
  worst case 1 + 2 = 3). On a single shared GPU that is modest but non-zero.
- **Grammar is a guard-rail, not the fix.** It only guarantees id-validity and
  JSON shape; the verbatim-quote correctness comes from validate+self-heal. If the
  server ever rejects the grammar (400), the code degrades to prompt-only and
  leans entirely on validation — still correct, just less constrained.

---

## Recommendation: **promote — conditionally (yes\*)**

**Yes**, `force-cite` should be promoted into the model band of the lesson rung —
it turns the exact defect that got `s2/s4` deferred (0% trustworthy citations)
into **100% verbatim-cited bands at ~1 call/lesson**, with an honest band-0 floor
and graceful degradation. It cleanly satisfies the auditor-only, evidence-bound
contract the schema demands, and it's strictly additive (drop-in
`s4_quality_forcecite` / `s2_ubd_forcecite`).

**\*One gate before it enters `LOCKED_SCORERS`:** confirm **calibration** against
gold. Citation *trust* is solved; agreement with human quality (MAE) is currently
unmeasured because the partial ledger yields no gold overlap. Re-run
`eval_force_cite.py` after the Dallas ledger rebuild (or seed gold ids for the
newly-enumerated lessons); if MAE is competitive with the deterministic scorers
(~0.07 on the old gold), lock it in. Until then, run it as an **advisory** scorer
in the bake-off — its citations are already trustworthy enough to surface to a
human reviewer.
