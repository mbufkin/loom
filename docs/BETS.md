# Design Bets & Doctrine

> These are the owner's opinions and bets for this project. They are deliberate
> wagers, not settled facts. Everything downstream — architecture, roadmap, code
> review — should be judged against them. If a change contradicts a bet here,
> that is a decision to make consciously, not by accident.
>
> Written down because these convictions kept getting re-derived from scratch in
> conversation. This is the north star so we stop re-fighting the same thought.

---

## Bet 0 — The whole point is local small models doing real reading

We are betting that a **small model running locally is good enough** to read
curriculum documents and reason about them — and that its lack of per-token cost
is a structural advantage, not a limitation.

Cloud APIs are designed around one constraint: **tokens cost money**, so you
minimize them (send excerpts, batch aggressively, one clever pass). On this
machine that constraint **does not exist**. The only budget is wall-clock time
and electricity. That inverts the entire design philosophy:

| Cloud assumption | Our reality |
|------------------|-------------|
| Tokens are expensive → send excerpts | Tokens are ~free → send full content |
| Minimize calls → batch everything | Calls are free → one item, one call, repeated |
| Model does one clever pass | Model does thousands of boring careful passes |
| Latency per call matters | Unattended overnight batch is fine |

If a design choice only makes sense under "tokens are expensive," it is probably
wrong for this project.

---

## Bet 1 — The model reads the whole document, not a reduction of it

The model **must see the full document text**, not a filename, not a 200-character
excerpt, not a regex summary. Reducing a document to metadata before the model
sees it throws away the exact thing we built this system to use: the model's
ability to actually read.

**If a document is too big for context, it is chunked and reassembled — never
truncated.**
- **Map:** split into overlapping, heading-aware chunks (split on structure, so a
  heading is never severed from its body). The model reads each chunk and emits
  structured observations with citations.
- **Reduce:** a second pass merges the per-chunk observations into one
  document-level judgment, and is explicitly allowed to conclude
  "ambiguous / contradictory."

Chunk boundaries lose context; overlap + structural splitting is how we pay that
tax honestly.

**Is heading/paragraph-aware chunking actually the right method, or just the one
we happened to build?** We went and checked the literature (July 2026) rather than
assume. Headline finding: almost all published chunking research targets **RAG
retrieval** (find the one chunk relevant to a query, out of a corpus) — a
different problem from ours, which is **exhaustive per-document extraction** (get
every element, out of one document, no query involved). Findings had to be read
through that lens, not applied blindly:

- **Structure-based (paragraph/heading) chunking is the validated default, not a
  naive shortcut.** A 2026 taxonomy reproduction (arXiv 2602.16974) and an
  independent 7-strategy benchmark (Vecta, Feb 2026) both found paragraph/recursive
  splitting *beats* semantic (embedding-boundary) chunking on real documents —
  semantic chunking needs careful similarity-threshold tuning or it fragments into
  useless 40-token slivers. We are not leaving performance on the table by skipping
  semantic chunking.
- **The one method that *does* beat structure-based splitting is LLM-guided
  boundary detection** (LumberChunker, arXiv 2406.17526) — and specifically for
  "in-document" tasks (locating/using content within one long document), which is
  the closer analogue to Layer 0 than "in-corpus" retrieval is. The catch: it costs
  one extra LLM pass per document just to find topic-shift breakpoints. Logged as a
  candidate upgrade (see roadmap.md), not built — Gemma is cheap enough that this
  is plausible later, but "chunk boundaries occasionally split an element, caught
  by overlap + dedup" hasn't yet shown up as our actual bottleneck, so there's
  nothing to fix yet.
- **Overlap's classic RAG justification (recall for a query near a boundary)
  doesn't apply to us, and some 2026 work finds it gives no measurable retrieval
  benefit at all** (arXiv 2601.14123). We keep overlap anyway, for a *different*
  reason that literature doesn't test: preventing an element from being silently
  truncated or split in half at a chunk seam. That's an extraction-correctness bet,
  not a retrieval-recall one — worth remembering next time someone proposes
  dropping overlap "because the paper said it doesn't help."
- **Anthropic's "Contextual Retrieval" prefix trick does not straightforwardly
  transfer.** Anthropic has an LLM write a paragraph situating each chunk within
  the whole document before embedding it, and it meaningfully improves retrieval.
  But the 2026 taxonomy paper's direct reproduction found that same technique
  *degrades* in-document effectiveness (chunks become too similar to
  discriminate) — which is exactly our setting. We adapted the underlying
  *principle* (give the model document-level orientation), not the mechanism: each
  chunk sent to Layer 0 now gets the document's own opening ~600 characters
  prepended, verbatim, at zero extra model cost (`build_doc_orientation()` in
  `layer0.py`) — no LLM call to generate it, no hallucination risk. **Tested same
  day, result was negative**: re-running the AP CSP CED document with this
  change (plus an unrelated `max_tokens` fix landing at the same time) produced
  more elements overall, but the like-for-like uncited rate was statistically
  unchanged (79.1% vs. 79.9% before) — see roadmap.md #6 for the full numbers.
  Kept anyway (it's free and correct in principle) but it did not fix the
  memorization problem. The uncited excerpts are still clean textbook prose even
  on the *first* chunk, which never gets an orientation prefix at all (redundant
  with its own content) — direct proof the failure isn't a missing-context
  problem, it's the underlying PDF extraction being too garbled for the model to
  quote from, full stop. That's a `doc_extract.py` problem, not a chunking one.
  **Confirmed and fixed same day**: `_extract_pdf()` was calling `pdftotext
  -layout`, which preserves literal column *position* instead of reading order —
  actively wrong for multi-column PDFs. Removing that flag dropped the uncited
  rate on this same document from ~79% to 68.1% from a one-line change, versus a
  rounding-error improvement from the orientation prefix — see roadmap.md #7 for
  the full before/after. Good confirmation that chunking-strategy research had
  already correctly ruled itself out as the fix, and pointed at the right place.

**2026-07-08 update — the free-text quote citation mechanism itself was replaced.**
Everything above this point in Bet 1 was written while Layer 0 still asked the
model to *retype* a verbatim excerpt and verified it post-hoc with a fuzzy
whitespace-normalized substring search. Three separate rounds of real-corpus
testing (Dallas, AP CSP CED, region10 — roadmap.md #4-#8) kept surfacing new
*shapes* of the same underlying problem — trailing truncation, mid-quote
ellipsis-splicing, and (found last) silent internal omission with no marker at
all — each one requiring a new prompt rule that reduced but never eliminated the
behavior. That pattern is exactly what it looks like: patching symptoms of a
design choice (asking a generator to reproduce text verbatim) that cannot be
prompted into 100% reliability, because the failure lives in the act of
generating the quote, not in any rule about how to do it.

Went and checked whether this is a solved problem elsewhere before writing
another prompt rule — it is. **Anthropic's Citations API** (GA 2026) computes
`start_char_index`/`end_char_index` at the API layer instead of having the model
generate quote text: *"the model can't fabricate citations — every citation maps
to a real position in the documents you provided."* The `instructor-ai` and
`verbatim-rag` projects converge on the identical idea from the open-source side:
force the model to emit a *pointer* into source text, then have your own code
slice the actual excerpt — never the model. A pointer literally cannot be
truncated, spliced, or paraphrased; it's an integer that either resolves to real
text or doesn't.

Adapted for a local model with no dedicated citations feature: `layer0.py` now
numbers the paragraphs of whatever text a Tier 1/Tier 2 call is reading and asks
the model to cite `excerpt_paragraphs: [3]` or `[4, 5]` instead of retyping any
text at all (`number_paragraphs()`, `resolve_excerpt()`). The real excerpt is
then sliced from our own already-known paragraph list. This makes the entire
class of problems from #4-#8 — truncation, splicing, silent omission,
fabrication — structurally impossible, not just less likely. Validated live: ran
against a document immediately after the change and it surfaced a genuinely new
and more useful signal in the same motion — `excerpt_noncontiguous` — flagging
elements where the model pointed at real but far-apart paragraphs (a document
that repeated a "WHERETO" framework outline twice, once as a summary, once in
detail), which is a "is this really one element or two" question, a categorically
different and more actionable finding than "is this text fake."

**Honest trade-off, stated plainly:** excerpts are now whole-paragraph
granularity instead of a hand-picked <=50-word sentence — coarser, but verbatim
by construction rather than by post-hoc verification. For an evidence ledger
whose entire job is faithful citation, that trade was worth taking. The old
`excerpt_has_ellipsis` tracking field is now moot (there's no generated text left
to contain an ellipsis) and has been removed from the ledger schema.
- **Bottom line: our own citation/coverage checks on real curriculum documents
  outrank any RAG benchmark for deciding what's "best" here** — none of the
  papers above evaluate anything resembling "decompose this into instructional
  elements with verbatim citations." Treat this section as directional evidence
  that our current approach isn't naive, plus a shortlist of upgrades to reach for
  if a specific failure mode (not a benchmark score) demands it.

---

## Bet 2 — Regex is a hint, never the decision-maker

Deterministic heuristics (filename → type, `Day N` → timing, `Estimated Day(s)`)
are **cheap priors and cross-checks**, not ground truth. They must never
short-circuit the model's own read of the content.

Better still: the disagreement is *itself* a finding. "Filename says
`exit_ticket` but the model reading the content says `rubric`" is a real
conformance signal. **Demote the regex, don't delete it.**

Documents will NOT arrive well-organized. The system must work on messy,
mislabeled, unstructured material. Anything that depends on clean headers is
overfitting to the lucky cases.

---

## Bet 3 — Narrow the task, then repeat it a thousand times

Small models fail on **breadth**, not **repetition**. Asking one model call to
group 19 documents *and* invent calendars *and* assign roles at once is the
breadth that makes small models flail.

The correct shape is the opposite: **one document (or one chunk), one question,
one strict output schema — repeated as many times as it takes.** This is exactly
where local small models are genuinely strong, and exactly the "long, repetitive,
boring" work we are betting the machine can grind through reliably.

---

## Bet 4 — Citations required; "unknown" is a first-class answer

This is an **auditor**. A model asked "what unit does this belong to?" will
confidently invent an answer if allowed to. Two guardrails are non-negotiable:

1. **Every claim must cite** a verbatim excerpt from the source.
2. **"The document does not say / insufficient evidence" is a valid, expected,
   honorable answer.** Inventing structure that isn't in the documents violates
   the auditor charter.

We would rather have an honest "unknown" than a confident fabrication.

---

## Bet 5 — Trust comes from redundancy, not scale

We buy reliability from small models with **cross-checking**, not bigger models.
Two models (Analyst + Verifier) read the *same full text*; one infers, the other
validates. **Disagreement is flagged for a human, never silently resolved.**

Corollary — when a document's self-evidence disagrees with where the structure
says it belongs: **flag both, let a human decide.** The system does not pick a
winner.

**Why two models, specifically (carried forward from the original v1 spec,
`archive/crystallize-legacy/crystallization-pipeline-spec.md` §3):** a single
model misses three distinct categories of failure that a second, independently
reading model can catch:

1. **False confirmations** — "this unit looks complete" because one model's
   blind spot happens to align with the actual gap.
2. **Missed contradictions** — subtle cross-document issues, e.g. "the
   worksheet calls for a presentation, but the lesson plan allocates no
   presentation time."
3. **Overconfidence** — a single model's output has no built-in check against
   a confident, wrong answer. A second independent read is that check.

> **Caveat:** the v1 spec also claimed "reconciliation surfaced 7 findings that
> neither model found alone" from proof-of-concept runs. No run logs or output
> exist anywhere in this repo to substantiate that number — it is kept in the
> archived spec for the record, but should not be cited here as a measured
> result, only as the qualitative rationale above.

**2026-07-08 revision — two *different* weaker models retired in favor of one
strong model + on-demand recheck (changed on purpose, per this document's own
rule).** The original mechanism was Gemma (Analyst) and Qwen-a3b (Verifier)
reading the same text — two *different, individually weaker* models. The owner's
call: retire that arrangement. The reasoning, stated honestly so it can be
re-judged later:

- The second model's job was to catch **overconfidence, false confirmations, and
  missed contradictions** (the three failure modes above). But since this bet was
  written, three *structural* guardrails were built that already carry most of
  that load more directly: **pointer citations** (Bet 1 — the model emits a
  paragraph index, our code slices the text, so a fabricated quote is
  *impossible*, not "caught by a second reader"); **never-show-the-answer-key**
  (Bet 11 — what actually surfaces MISMATCH, and doesn't depend on redundancy at
  all); and **human-in-the-loop on MISMATCH** (Bet 12 — the real escalation for a
  contested call is a curriculum expert, not a second small model).
- What a second *weaker* model mostly added on top of those was **noise**, not
  signal: a3b (3B active params/token) disagreeing with Gemma is often just the
  shallower model being wrong, which a human then has to adjudicate anyway.

**Redundancy is kept, but bought from strength instead of from a second model.**
When correctness matters on a specific item (a low-confidence classification, or a
MISMATCH candidate before it reaches the report), the *same strong model* is run a
second time, independently, with different framing — and disagreement is flagged
per this bet's standing corollary ("flag both, let a human decide"), never
silently resolved. This is Bet 0 applied correctly: compute is free, so spend a
second pass from the good model where it's earned, rather than keeping a permanently
loaded weaker model around to save time we don't need to save.

**Model choice (see docs/roadmap.md "Single strong model"):** NVIDIA
Nemotron-3-Nano-30B-A3B at Q8 (Unsloth UD-Q8_K_XL). The G10 (GB10, 273 GB/s unified
memory) is **memory-bandwidth-bound**, so the practical ceiling isn't "what fits" but
"what reasons well per pass at a workable speed" — and speed here is set by *how many
weights are read per token*, not total parameter count. We first tried Qwen3-32B
*dense* Q8 for its per-pass depth, but reading all 32B params/token pinned it at
~6.4 tok/s — impractical for Bet 3's thousands of repeated calls (a full corpus would
run overnight). Nemotron-3 is a 30B **MoE** activating only ~3B params/token, so it
runs ~44 tok/s (7×) while still reasoning per pass well above the a3b MoE it replaces.
The lesson: on a bandwidth-bound box, prefer a well-trained sparse-MoE at the size
ceiling over a dense model whose every parameter you must re-read each token.

Validated on the model swap (Region10, 2026-07-09): coarser but cleaner decomposition
(41→22 elements on the unit-1 scope), *more* role-fulfillments correctly found
(1→3), zero new MISMATCH false-positives, and no citation-fidelity loss (0 uncited
across all 19 docs). One brittleness surfaced and was fixed — Nemotron emits
off-enum confidence tokens like "placeholder" on empty slots, so `layer1.py` now
normalizes confidence to high|medium|low instead of discarding the whole judgment
(a single stray token had been forcing CHECK_FAILED).

---

## Bet 6 — It must run unattended: idempotent, cached, resumable

Full-content reading + chunking + two-model verification multiplies calls into the
thousands for a real district. That is fine — but it means this **cannot be a
blocking foreground command.** It must be a queue/worker that:

- **caches** each item's result by content hash (never re-do settled work),
- **resumes** exactly where it died (item 211 of 300, not from zero),
- makes **stateless per-item calls** (no shared conversation → no drift over a
  long batch),
- reports **progress** and runs overnight without a human watching.

Building it as a blocking command is the single easiest way to make a
fundamentally sound system feel broken.

---

## Bet 9 — Layer 0: shared evidence extraction before structural analysis (the eDiscovery insight)

This bet comes from studying how large-scale litigation document review actually
works — **Technology-Assisted Review (TAR)** in eDiscovery. See Grossman & Cormack,
*"Technology-Assisted Review in E-Discovery Can Be More Effective and More
Efficient Than Exhaustive Manual Review,"* Richmond Journal of Law & Technology
(2011), built on TREC Legal Track data — the canonical academic grounding for this
approach.

**The insight: lawyers don't read every document before they organize it — they
extract first, then triage, in tiers.** TAR's shape:

1. **Metadata extraction first** — type, date, custodian — before deep reading.
2. **Tiered review** — first pass (classification) → second pass (relevance) →
   third pass (privilege/final check). Deep reading is reserved for what the
   earlier tiers flag as ambiguous, not spent uniformly on everything.
3. **Batching with QC** — review in batches, sample-check, adjust.
4. **The coding decisions accumulate in a shared ledger** that every later stage
   references — no reviewer, human or model, ever re-reads the whole corpus to
   make one decision.

**We violated this once already, on purpose learning from it.** The legacy
`crystallize.py` (see `archive/crystallize-legacy/`) concatenated every document
in a cluster into one string and **truncated at 60,000 characters**, then ran 4
independent layers against that same truncated blob — each layer re-reading and
re-interpreting it from scratch, with no shared memory between them and no
record of what got cut off. That is precisely the failure mode this bet exists
to prevent.

**The fix: Layer 0 — Document Ingestion & Evidence Extraction — runs once, before
any structural analysis, and produces a shared evidence base every downstream
layer references instead of re-deriving.**

For every source document, Layer 0 extracts (per Bet 1: full content, never
truncated; per Bet 2: regex is a prior/cross-check only):
- entities, claims, dates, standards references
- **decomposed instructional elements** (see Bet 10) — a document is not
  necessarily one atomic unit of evidence
- citations for every extracted claim (per Bet 4)

All of it is written to **one shared evidence ledger per project** — "the table."
Layers 1+ (organize, calendar inference, placement, conformance) read from this
ledger. They do not re-open and re-interpret raw source text independently of
each other — that is what causes drift.

**Tiered processing keeps this affordable at scale**, mirroring TAR's classification
→ relevance → privilege progression:
- **Tier 1 (fast, cheap, on everything):** classify every document/element —
  type, rough position, timing hint. **Model: Gemma (Analyst)** — the smaller,
  faster model, run on every single document/element with no exceptions.
- **Tier 2 (deeper reading, only on what Tier 1 flags ambiguous):** full
  reasoning reserved for genuinely unclear cases, not spent uniformly.
  **Model: Qwen (Verifier)** — the deeper-reading model, reserved for what
  Tier 1 could not confidently classify, never run uniformly on everything
  (that would just be Bet 0 done wastefully).
- **Tier 3 (final cross-check):** the Analyst/Verifier conformance pass
  (Bet 5), analogous to a privilege/final review — both models read the same
  material and cross-check each other.

Bet 0 says tokens are ~free — but wall-clock time on an unattended box is still
a real budget (Bet 6). Tiering is how we spend model depth where it's earned,
not everywhere uniformly.

**2026-07-08 revision — tiering retired (changed on purpose).** The Gemma-Tier1 /
Qwen-Tier2 escalation described above is no longer used. It was justified as a
wall-clock hedge ("don't spend the deep model on everything"), but that is the
same *tokens-are-expensive* instinct Bet 0 exists to reject, just wearing a
wall-clock disguise: it rationed model *depth* to save time we've decided we don't
need to save (the box runs unattended overnight — Bet 6). The owner's priority is
explicit: correct context over cheap/fast passes, because the passes are free.

New shape: **one strong model (Nemotron-3-Nano-30B-A3B, see Bet 5's revision) reads
every element once**, with no cheap-first classification tier. The TAR mapping still
holds — this is still "AI does the initial coding" — but the tiers collapse from
"fast model everywhere, deep model on the ambiguous" into "the good model
everywhere." The only place a second pass happens is Bet 5's on-demand recheck of
genuinely low-confidence or MISMATCH items, and that recheck uses the *same* strong
model, not a separate tier. "Spend depth where earned" survives; "keep a weaker
model loaded to triage" does not.

**Processing is document by document, not batched by cluster (for now).**
Layer 0 iterates one document at a time across the whole corpus — no
cluster/unit-level grouping at this stage (Bet 3's narrow-task discipline:
one document, one pass). Batching by cluster is a possible later optimization,
not a current decision — revisit only if document-by-document proves too slow
at real scale.

**Where TAR's "AI does initial coding, lawyers review edge cases" lands in our
system:** Tier 1 and Tier 2 are the AI-does-initial-coding step. The
"lawyers review edge cases" step is **not** a third model tier — it is Bet 5's
existing corollary: when Tier 3 cross-check produces a disagreement, **flag
both and let a human decide.** We don't invent a fourth AI tier to resolve
what the two models can't agree on; that's exactly the escalation-to-human
point TAR reserves for privileged/contested documents.

## Bet 10 — Universal element taxonomy, not curriculum-specific (open research question)

Once documents are decomposed into elements (Bet 9), those elements need a
vocabulary. **That vocabulary must not be tied to one curriculum design
framework.** Real curricula use different pedagogical models:

- **5E** (Engage / Explore / Explain / Elaborate / Evaluate) — seen in Dallas
  ISD engineering lesson plans.
- **WHERETO** (Where / Hook / Explore / Rethink / Evaluate / Tailor / Organize)
  — seen in Region 10's planning guides.
- Workshop model, direct instruction, project-based design, and others we
  haven't seen yet.

A fixed enum borrowed from any one of these will silently fail — or worse,
force-fit — on curricula built around a different framework. This is the same
mistake as Bet 2 (don't overfit to clean structure) applied one level deeper:
don't overfit the *element vocabulary* to the first curriculum's design model.

**Working hypothesis, not yet settled:** classify elements by **universal
instructional function** rather than framework-specific phase name — e.g.
hook/engagement, direct instruction, guided practice, independent practice or
project work, assessment/checkpoint, reflection/closure, logistics/materials,
standards/objectives. This is closer to a framework-agnostic "instructional
function" ontology than to any single named model.

**This is explicitly flagged as needing further research** before being locked
in — do not treat the working hypothesis above as final. Revisit before or
during the Layer 0 build.

---

## Bet 11 — Categorization is a distinct phase from extraction; never blend model judgment with code comparison

Bet 9 grounds Layer 0 in TAR's *extraction* phase (metadata first, then
tiered classification). eDiscovery treats what comes next — actually putting
each piece of evidence in its correct bucket — as a **separate, later phase**
with its own established practices, not a free extension of extraction. We
went and looked (2026 sources: Relativity, Everlaw, Reveal, Epiq, TCDI,
ACEDS) before designing Layer 1 (the ledger → unit/day/role placement stage),
rather than assume extraction's playbook just carries over:

1. **Issue coding uses natural-language protocols, not keyword lists.**
   Reviewers describe a category in prose; the model codes against that
   description with a citation and a confidence score. Same discipline Layer
   0 already applies to element *type* — Layer 1 applies it to *placement*.
2. **Calibration before full-scale coding.** Every current source describes
   the same sequence: draft the category description, pilot it on a small
   known sample, a human validates and refines it, only then run the full
   population. We had not done this anywhere in this pipeline before Layer 1
   — Layer 0 and `place.py` both went straight to full-corpus runs. Adopted
   as a named step: pilot on a small, already-understood unit before scaling.
3. **Concept clustering for batch consistency.** Group related items before
   coding so they get judged together, consistently — for us, batching a
   model call by source document (all of one doc's elements share one
   parent-link) rather than fully atomizing every element in isolation.
4. **Near-duplicate / threading detection**, so the same underlying claim
   seen in two documents (e.g. a course-map's one-paragraph unit summary and
   that unit's own detailed planning guide) gets recognized as one claim, not
   silently double-counted as two independent findings.
5. **Confidence-based escalation (CAL-style), not online retraining.** Modern
   platforms continuously re-route low-confidence items to reviewers; our
   static Tier 1 → Tier 2 escalation already does the equivalent, applied to
   this new decision rather than needing a new mechanism.
6. **QC via statistical sampling, done repeatedly, as a named step** — not a
   one-off "let's go check by hand" the next time something looks wrong. We
   already did this informally for Layer 0-B; the research confirms it's
   standard practice, not something we improvised.

**The core principle this adds, one level deeper than Bet 2:** a model's
*independent* read of a piece of evidence must never be shown the answer
it's about to be checked against. Bet 2 says regex/filename hints are priors,
never authoritative. Layer 1 extends that: **the manifest (which unit a
document was assigned to) is a hint to check against, never an input to the
inference that produces the thing being checked.** Show a model the manifest
before asking it to independently infer placement, and it will just parrot
the answer key back — making the one finding this system exists to produce
(MISMATCH: content contradicts its own stated structure) invisible by
construction.

**A Bet 0 correction, found live while designing Layer 1's role-fulfillment
check:** the first draft of that check proposed a static lookup table
mapping Layer 0's `element_type` taxonomy onto the calendar's artifact-kind
roles (`lesson_plan`, `exit_ticket`, ...), reasoned about as a hedge against
"the cost of a real per-case check." That reasoning is itself the cloud-token
instinct Bet 0 exists to reject — optimizing to avoid model calls that are
already free, in exchange for a static artifact that can silently go stale.
Corrected: spend a cheap, narrow, per-candidate model call instead ("does
this specific excerpt function as this expected role, yes/no/unclear, with a
citation") — cheaper to keep honest than a table, and it produces the one
thing a table never can: proof.

## Bet 12 — Signal-to-noise on MISMATCH needs a class-aware rule AND a human, not just a threshold

The first full-corpus Layer 1 run on Dallas (112 documents) raised 143 raw
MISMATCH rows. Hand-checking a sample surfaced two distinct, unrelated sources
of noise that a single corroboration-count threshold cannot tell apart from a
real finding on its own — each needed its own fix, in order:

**1. Hub/overview units need a class-aware equality rule, not flat ID equality.**
73 of the 143 were "Career Cluster"/"Career Exploration"/"Dallas ISD" hub
documents whose own elements correctly cross-reference other units (a
"Career Clusters" slide covering Agriculture is that hub doing its job, not a
filing error) or repeat non-substantive boilerplate branding ("Connect with
Dallas ISD CTE"). Fix: tag these `kind: overview` in `manifest.yaml`
(human-curated, never shown to Phase 1's model — Bet 11's core principle),
and give `check_placement()` two hub-aware rules ahead of the plain-equality
fallback: a hub-unit self-declaration is discounted to `UNVERIFIED`
unconditionally (not specific enough to be evidence), and a hub *parent*
document naming one specific other unit is `CROSS_REFERENCE`, not MISMATCH,
*unless* the disagreement is itself corroborated (`CONCENTRATION_MIN_COUNT`/
`FRACTION` — 3+ elements, 70%+ of a document's own declarations) — the
Carrasco_Brainstorm.txt case (10/10 elements independently declaring
"hospitality-tourism" while filed under the "career-cluster" hub) is exactly
the corroborated exception this must NOT suppress. This is the same
ontological "parent/child class overlap" Northcutt et al.'s Confident
Learning paper describes (their example: ImageNet "missile" mislabeled as
parent class "projectile") — some class pairs are structurally more
confusable than others and need a class-aware rule, not a flat one. A
further 12 were standards-code citations (TEKS text mentioning a skill by
name, not the document declaring its own unit) — fixed by a `PHASE1_RULES`
addition distinguishing *aboutness* (a document's own content, in its own
words) from *mention* (a standards code that happens to name a term),
grounded in the library/information-science literature on the same
distinction (Hutchins; Library of Congress subject-heading practice).

**2. Even after that fix, two equally-corroborated MISMATCH findings can mean
opposite things — and telling them apart needs domain knowledge no model or
threshold has.** Of the ~44 corroborated findings remaining, hand-checking
found the paper-tower activity (Architecture & Construction, self-declaring
"engineering") and the Lego-airplane activity (Transportation & Distribution,
self-declaring "engineering") were both **on-topic, expected overlap**
— Texas CTE's own Architecture & Construction TEKS explicitly include
engineering design methodologies — sitting right alongside genuinely wrong
cases (Carrasco_Brainstorm.txt; two swapped project rubrics whose own header
text names the *other* cluster's subject) that had identical corroboration
strength (8/8, 2/2). No code-only signal distinguishes these; only a human
curriculum reviewer, who knows which disciplines legitimately share content,
can. This is Bet 5's "flag both, human decides" made durable rather than a
one-off conversation, using the same human-curated-config pattern
`kind: overview` already proved: a `known_overlaps` list of unit-id pairs in
`manifest.yaml`, consulted by a new `EXPECTED_OVERLAP` status in
`check_placement()` (checked only after the hub rules, so a hub-unit
disagreement stays governed by the hub rules even if it also happens to name
a listed pair). `layer1/REVIEW-QUEUE.md` is generated every run — every
remaining MISMATCH grouped by unit-pair (the pair, not the document, is the
reusable decision — one human verdict covers every future document that pair
shows up on) with sample excerpts, so a reviewer never has to go spelunking
through `bucket-ledger.json` by hand to find what to look at next. Validated
live on Dallas: adding the two confirmed engineering pairs to
`known_overlaps` and re-running Phase 2 (zero model calls needed — Phase 1's
extracted facts don't need to be re-read) reclassified exactly those 10
elements to `EXPECTED_OVERLAP`, while Carrasco_Brainstorm.txt and the two
swapped rubrics remained MISMATCH, still corroborated, still in the report —
confirming the mechanism resolves ambiguity without hiding real errors.

## Bet 7 — Conformance over calendar synthesis (the headline)

We are **not** betting we can turn a pile of documents into a trustworthy
day-by-day year-at-a-glance. Real curricula declare *milestone ranges*
("~10 days"), not individual days, and lack the district calendar spine needed
for honest dated pacing.

The headline goal is **conformance**: verify that each small piece of curriculum
lands where it — and its parent structure — claims it should. Match, mismatch,
orphan, missing, duplicate. The year-at-a-glance is **demoted** to a clearly
labeled rough scaffold, not the product.

---

## Bet 8 — Structural fill only, forever

The system audits, maps, and reports on **structure**. It never authors lessons,
assessments, rubrics, or content. This boundary is not a limitation to grow out
of — it is the identity of the product. (See `STRUCTURAL-FILL.md`.)

**Report delivery** (`report_delivery.py`, default `--delivery model`) is still
inside this bet: the model writes curriculum-**audit** narrative (findings →
patterns → revision options) grounded in locked ledgers. It does not re-extract,
does not invent documents, and does not author curriculum. Presentation follows
curriculum-audit / mapping / review-cycle practice — not teacher evaluation.
See `docs/REPORT-DELIVERY.md`. Use `--delivery code` when you only need tables.

---

## Bet 13 — The report must explain itself; a director will not have an agent to ask

Found live (2026-07-08): after Layer 1 was fully built and validated on the
Dallas corpus, the owner pointed out that nothing downstream actually turned
`bucket-ledger.json`/`findings.json` into something a curriculum director could
open and understand — only an agent manually reading the JSON and narrating it
in chat could. That's a real gap, not a documentation nicety: **the product is
the report** (Bet 7's opening line), and a report that requires an AI session
to interpret isn't a report, it's raw output.

Fix, applied to `synthesize.py`'s rewrite onto Layer 1 data: `GLOBAL-AUDIT.md`
embeds a plain-language glossary defining every status this pipeline can
produce (MATCH/MISMATCH/CROSS_REFERENCE/EXPECTED_OVERLAP/ORPHAN/UNVERIFIED/
MISSING/DUPLICATE/FULFILLED) directly in the document, not in a separate doc
the reader has to go find. The one-sentence test for whether a status vocabulary
extension (this project keeps adding them — Bet 12 added two in one pass) is
actually done: **does the report that surfaces it also explain it, in the same
place, without assuming the reader already knows this project's internals?**
A new `match_status` value that only ever shows up in code and `docs/BETS.md`
is an incomplete change, not a finished one.

---

## Bet 14 — Layer 2 (structural completeness) is a checklist against an already-selected document, not a routing decision, so a static table is correct here

Found live (2026-07-09), directly after Bet 11's correction: once Layer 1 has
already independently confirmed one specific document IS the thing anchoring
role X (e.g. `lesson_plan`), a further, narrower question remains unanswered —
does *that document itself* contain the internal instructional-function parts
(Bet 10's `element_type` taxonomy) a complete document of that role should
have? E.g. a lesson plan with no `standards_objectives` element anywhere in it
is missing a part, even though it was correctly filed and correctly confirmed
as the unit's lesson plan.

This looks, at first glance, like the exact mistake Bet 11 corrected — "a
static lookup table mapping `element_type` onto role expectations" is the
same shape of table Bet 11 rejected for role-fulfillment routing. It is not
the same problem, and the distinction matters:

- Bet 11's rejected table would have mapped ONE element_type to ONE role and
  used that to decide whether a *candidate* element counts as fulfilling a
  role slot — a **routing** decision (which of many candidate elements, across
  possibly many documents, gets selected for this slot). Real corpora get
  this wrong constantly (the same `assessment_checkpoint` element might
  legitimately fulfill one slot but not a superficially similar one), which
  is exactly why that needed a per-case model judgment call instead.
- Layer 2's table instead answers "given a document already selected (by a
  real model judgment call, Layer 1 Phase 3), what internal parts does a
  complete document of this role have" — a **checklist against a subject
  already chosen**, not a selection among candidates. There is no routing
  ambiguity left to resolve; the only question is presence/absence of parts
  within one already-known document, which a static table answers correctly
  and for free (Bet 0).

**One-sentence test for which side of this line a new check falls on:**
if the table's job is to pick WHICH element/document a judgment applies to,
it needs a model call; if the table's job is to check WHAT a
*already-identified* subject contains, a static table is the right, cheap
tool. Layer 2 (`layer2.py`) is the first concrete instance of the second
case: zero new model calls, reusing only data Layer 0/1 already produced.

**A Bet 10 integrity gap found while building this (2026-07-09):** Layer 2's
first real run surfaced `element_type` values like
`"hook_engagement|direct_instruction"` in already-produced ledgers — not a
valid taxonomy member, but the model echoing the pipe-delimited enum LIST
from the JSON schema prompt back as if it were itself a value. The real bug
predates Layer 2: `layer0.py`'s `validate_layer0_elements()` schema check
*was* already flagging this, but that flag was only ever used to decide
whether to trigger a same-model recheck (Bet 5/9) — never to actually reject
or sanitize what got written to the ledger, so a still-invalid value survived
every retry and landed in `ledger.json` uncaught. Layer 0-B's separate
split-review path (`run_layer0b`) had the same gap, with no schema check
at all on its own model output. Both paths now run every element_type
through a shared `coerce_element_type()` (falls back to the taxonomy's own
`unclear`, never drops the element or its real, resolved citation — losing
real evidence over a mistaged classification is the worse failure). Affected
~26% of `dallas-career-2026`'s elements and ~7% of `region10-career-college-2026`'s
at discovery. `layer2.py` also defensively splits on `"|"` when matching
against already-produced (pre-fix) ledgers, so existing output is judged
fairly without requiring a full, costly Layer 0 re-run — but a future full
re-run would still be the cleaner long-term fix for those two corpora's
ledgers. **Lesson, general beyond this one field:** a schema validator that
only *decides whether to retry* and never *gates what ships* is not
enforcement — it's a suggestion. Every schema check in this pipeline should
be re-examined against that distinction, not just this one.

---

## How to use this document

- **Building something?** Check it against these bets first.
- **A bet turns out wrong?** Change it *here, on purpose*, with a note on why —
  don't quietly violate it in code.
- **A model working in this repo** should treat these as standing instructions
  for how this project wants to work.
