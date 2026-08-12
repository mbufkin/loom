# Changelog

## 0.2.0 — 2026-08-12

Loom V0.2: wire the **graph → route → Paths A–H** data path for production use
(opt-in graph; not graph-always-on).

### Graph and routing

- Opt-in belonging graph phase (`--with-graph`) sits after Layer 0-B and before
  `route.py`; HAS-PART hints feed the A–H router when present.
- E2E runs isolate graph artifacts under `e2e/runs/<id>/graph/`.
- Local llama.cpp structured JSON calls can set
  `chat_template_kwargs.enable_thinking`. Production `graph_phase.chat_json`
  and the CTE graph spike pass `enable_thinking=False` so Nemotron 3.5
  Lightning reasoning cannot empty `content` on HAS-PART / connect steps.

### Paths A–H

- Presence (or deeper) lenses for lesson, assessment, general nursery, teacher
  support, student practice, standards & pacing, syllabus, and exit ticket.
- Review UI surfaces path lenses and the rung stack for completed runs.
- Pipeline fails loudly on missing declared stage outputs; findings contract
  frozen for path scorers.

### CTE filename and Path B signals

- `classify_doc_type` recognizes `answer-key`, `final-assessment`,
  check-for-understanding, and `__assessment__` style names.
- Path B checklist keywords cover letter choices (`A.` …) and hyphenated
  answer-key cues common in web/Word CTE exports.

### Docs

- Path taxonomy and rollout notes under `docs/PATHS.md`,
  `docs/PATHWAY-ROLLOUT-REVIEW.md`, and per-path guides.
- `docs/GRAPH-PHASE.md` records that route consumes HAS-PART when present.

### Not in this release

- Spike Path B/C/D review HTML UIs (local experiments only).
- Making `--with-graph` the default.
- Deeper actionable-feedback rework for Paths C–H (tracked separately).

## 0.1.0

Initial public Loom release.
