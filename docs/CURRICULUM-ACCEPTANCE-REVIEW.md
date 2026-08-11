# Curriculum Acceptance Review (CAR)

**Purpose:** A formal, repeatable way to decide whether a curriculum pack is
**good enough overall** — and whether Loom’s run **did what we intended** —
without inventing content or scoring classroom teaching.

**Audience:** Curriculum lead + auditor (same evidence; different emphasis).  
**Grain:** One project / one E2E run (`projects/<id>/e2e/runs/<run-id>/`).  
**Doctrine:** Auditor-only ([BETS.md](BETS.md) Bet 8). EdReports-style
**gateways** — fail early gates before polishing soft quality.

**Related:** [CHAMPION-REVIEW-MAP.md](CHAMPION-REVIEW-MAP.md) · [E2E.md](E2E.md) ·
[PATHS.md](PATHS.md) · Path A trust gates
(`.plan/world-class-path-reviews/tickets/06-path-a-trust-scorecard.md`) ·
feedback research
(`.plan/world-class-path-reviews/assets/09-curriculum-feedback-form-research.md`).

---

## Verdict vocabulary

| Verdict | Meaning |
|---------|---------|
| **ACCEPT** | Gateways 0–3 pass; curriculum is reviewable and feedback is trustworthy enough to act on |
| **ACCEPT WITH GAPS** | Pipeline + routing OK; curriculum has known MISSING/INCOMPLETE that humans must own |
| **REJECT — SYSTEM** | Routing / path / feedback failed intent — do not trust plates; fix Loom or re-run |
| **REJECT — PACK** | System worked; pack is too thin or misfiled to support a champion review |

Any **hard NO** in Gateway 0 or 1 → **REJECT — SYSTEM**.  
Any **hard NO** in Gateway 2 with empty critical champion roles → **REJECT — PACK**.  
Gateway 3 soft fails → **ACCEPT WITH GAPS** (document them).

---

## The four gateways

```text
0  Run integrity          → did the pipeline finish what we asked?
1  Intent / routing       → did docs land on the lenses we intended?
2  Curriculum structure   → is the pack structurally complete for champions?
3  Feedback strength      → is the feedback useful, honest, and actionable?
```

Gateways are ordered. Do not spend time on Gateway 3 prose if Gateway 0 failed.

---

### Gateway 0 — Run integrity (system)

**Intent:** The E2E tree is a real, finished review artifact ([E2E.md](E2E.md)).

| # | Check | Evidence | Hard? |
|---|--------|----------|-------|
| 0.1 | Run folder exists with `RUN.json` | `e2e/runs/<id>/RUN.json` | YES |
| 0.2 | Layer 0 ledger non-empty | `layer0/ledger.json` | YES |
| 0.3 | Route-map covers every sourced doc | `layer0/route-map.json` vs sources / ingest | YES |
| 0.4 | Path runners wrote findings for every lens that received docs | `path_a`…`path_h/findings.json` | YES |
| 0.5 | No fatal Traceback / incomplete stage in run log | run log / monitor | YES |
| 0.6 | Optional: graph present when `--with-graph` was requested | `graph/runs/<id>/` | YES if flagged |

**Pass:** all hard checks YES.  
**Fail:** incomplete or corrupt run — re-run before judging curriculum.

---

### Gateway 1 — Intent / routing (system + product)

**Intent:** Documents hit the lenses we designed (A–H), not a junk-drawer C.

| # | Check | Evidence | Hard? |
|---|--------|----------|-------|
| 1.1 | Path letter counts match expectations for this corpus | `route-map.json` path histogram | soft* |
| 1.2 | Exit tickets → **H**, not B | sample `exit_ticket` filenames | YES |
| 1.3 | Quizzes / keys → **B**; orphans flagged B5 PARTIAL | `path_b/findings.json` | YES if quizzes exist |
| 1.4 | Worksheets / Learn·Practice·Succeed → **E** | route sample | YES if those files exist |
| 1.5 | TE / educator guides → **D** (not F unless program-impl prior) | route sample | YES if TE exists |
| 1.6 | YAG / pacing / S&S → **F**; syllabus → **G** | route sample | YES if those files exist |
| 1.7 | Lesson plans → **A** | route sample | YES if LP files exist |
| 1.8 | Catch-all **C** is nursery only (feedback logged; no stolen TEKS/quiz checks) | `path_c/findings.json`, `_loom_feedback.yaml` | YES |
| 1.9 | Compare to prior run when regressing product | `tools/compare_dallas_e2e_paths.py` or equivalent | soft |

\*Soft unless you pre-declare expected counts for a golden corpus (Dallas lab
expectations: many H from exit tickets; F/G may be 0 if pack has no YAG/syllabus).

**Pass:** no hard routing violations; C not absorbing known typed docs.  
**Fail:** e.g. exit tickets still on B → **REJECT — SYSTEM**.

**Best practice:** Keep a one-page **Intent card** per curriculum (expected
roles: LP, quiz↔key, exit, TE, SE, YAG, syllabus). Gateway 1 is “intent card vs
route-map,” not vibes.

---

### Gateway 2 — Curriculum structure (champion pack)

**Intent:** The pack can support a champion-style revisit
([CHAMPION-REVIEW-MAP.md](CHAMPION-REVIEW-MAP.md)). Loom reports gaps; humans own content.

| Champion need | Loom signal | Hard if… |
|---------------|-------------|----------|
| Dated calendar spine | `school-calendar.yaml` + pacing / year map | District-dated YAG required |
| Unit day grid | `units/*/calendar.yaml` + Layer 1 | Units expected in manifest |
| Lessons present & structurally whole | Path A + Layer 2 | Course claims daily LPs |
| Assessment pair (quiz↔key) | Path B B1–B5 | Course claims quizzes |
| Formative checks | Path H H1–H4 | Course claims exit tickets |
| Teacher supports | Path D D1–D4 | TE / guides in pack |
| Student practice | Path E E1–E4 | SE / worksheets in pack |
| Year spine | Path F F1–F4 | YAG / pacing / S&S in pack |
| Syllabus contract | Path G G1–G7 (+ G8/G9 when built) | Syllabus in pack |
| Filing / MISSING / DUPLICATE | Layer 1 + `FIRST-PASS` / `REVIEW-QUEUE` | Always review |
| Nursery leftovers | Path C + `_loom_feedback.yaml` | Soft — growth queue |

**Pass rules:**

1. Every **declared** champion role that has files in the pack got a non-skipped
   path findings file with presence steps (not empty stub).
2. Critical MISSING/INCOMPLETE items are listed on first-pass / review-queue —
   not silent.
3. No requirement that every optional role exist (Dallas may have no Path F/G).

**Verdict:**

- Structure OK + gaps listed → **ACCEPT WITH GAPS** (normal).  
- Declared roles empty or unrouted → **REJECT — PACK** or **REJECT — SYSTEM**
  (use Gateway 1 to tell which).

---

### Gateway 3 — Feedback strength (human trust)

**Intent:** Feedback is strong in the research sense: **claim → why → improve**,
priority-first, auditor cues only — not essays, observation scores, or rewritten
lessons ([09 research](../.plan/world-class-path-reviews/assets/09-curriculum-feedback-form-research.md)).

Score the **human-facing feedback artifact**, not the length of the source doc.

#### 3A — Path A one-pager (when Path A quality bar is in use)

Hard gates (any NO fails the sample) — locked Path A trust scorecard:

| Gate | Plain English |
|------|----------------|
| **C1** | Top gaps first; each has **Why** + **Improve** |
| **C2** | Skimmable ~2 minutes / ~one page |
| **C3** | Improve = add/clarify cues — never drafts the lesson |
| **C4** | No essays, no observation/teaching scores, no invented content |
| **X5** | Section order: gaps → working → Hunter glance → short evidence |
| **X6** | Strong/Adequate/Weak only on **PRESENT** |
| **X7** | Evidence pointers short (no cite bleed dumps) |
| **G8** | ≤3 Top gaps |

**Proving loop:** LP in → feedback given → feedback reviewed (fidelity to real LP
**and** gates). Golden set: engineering / teaching-and-training / family-community.

#### 3B — Presence-era paths (B/H/F/D/E/C/G today)

Until world-class one-pagers exist, score **findings honesty**:

| # | Check | Hard? |
|---|--------|-------|
| 3B.1 | Findings cite excerpts or source fallback — no invented stems/keys/TEKS | YES |
| 3B.2 | MISSING/PARTIAL appear on weak fixtures; not everything PRESENT | YES |
| 3B.3 | Pairing / nursery semantics match docs (B5 quiz↔key; C = nursery) | YES |
| 3B.4 | Emit/one-pager steps marked STUB are not sold as finished feedback | YES |
| 3B.5 | Spot-check 3 strong + 3 weak docs against findings (human) | soft |

#### 3C — Course-level plates

| Artifact | What “strong feedback” means |
|----------|------------------------------|
| `FIRST-PASS.md` / PDF | Gaps + filing + completeness visible; model narrative (if any) stays auditor-only |
| `TEACHER-PACKET.md` | Unit punch list actionable in one sitting |
| `DASHBOARD.md` / `REVIEW-QUEUE.md` | Heatmap + HITL queue usable without re-opening every ledger |

---

## Formal review session (90–120 minutes)

Use this agenda for a full curriculum acceptance.

| Step | Time | Activity |
|------|------|----------|
| 1 | 10m | Open Intent card + E2E run id; confirm Gateway 0 |
| 2 | 15m | Route histogram + 10-doc spot check (Gateway 1) |
| 3 | 25m | Champion matrix vs path findings + Layer 1 queue (Gateway 2) |
| 4 | 25m | Feedback trust: Path A scorecard **or** 3B spot checks (Gateway 3) |
| 5 | 15m | Verdict + owners (system fix vs pack fix vs accept-with-gaps) |
| 6 | 10m | Write CAR record (template below) |

**Best practice:** Two roles — **Operator** (Gateway 0–1) and **Curriculum lead**
(Gateway 2–3). Disagree in writing on the CAR record; do not merge silently.

---

## CAR record template

Copy into `projects/<id>/e2e/comparisons/CAR-<run-id>.md` (or review notes):

```markdown
# CAR — <curriculum> — <run-id>
Date:
Reviewers:

## Intent card (expected roles)
- [ ] Lessons (A)
- [ ] Quiz↔key (B)
- [ ] Exit tickets (H)
- [ ] Teacher support (D)
- [ ] Student practice (E)
- [ ] Standards/pacing (F)
- [ ] Syllabus (G)
- [ ] Other / nursery (C)

## Gateway results
| GW | Result | Notes |
|----|--------|-------|
| 0 Run integrity | PASS/FAIL | |
| 1 Intent/routing | PASS/FAIL | |
| 2 Structure | PASS/FAIL/GAPS | |
| 3 Feedback strength | PASS/FAIL/DEFER | |

## Verdict
ACCEPT | ACCEPT WITH GAPS | REJECT — SYSTEM | REJECT — PACK

## Top actions (≤5)
1.
2.

## Evidence links
- route-map:
- compare (if any):
- first-pass / packets:
```

---

## How this differs from nearby processes

| Process | Job |
|---------|-----|
| **CAR (this doc)** | Overall accept/reject of pack + run intent |
| **Champion revisit** | Human rewrite / standardization summer work |
| **Path lab smoke** | One lens presence (B/H/…) under harness |
| **World-class Path A map** | Lock quality one-pager + reusable pattern |
| **E2E A/B models** | Same curriculum, different models — not pack acceptance alone |
| **`_loom_feedback.yaml`** | Nursery signal for new checklist growth — input to CAR, not the verdict |

---

## Minimal commands

```bash
# From repo root — after an E2E run exists
python3 tools/compare_dallas_e2e_paths.py \
  --old projects/<id>/e2e/runs/<old> \
  --new projects/<id>/e2e/runs/<new> \
  --out projects/<id>/e2e/comparisons/CAR-route-diff.md

# Human plates
python3 synthesize.py --project <id> --list-reports
# (use e2e_run scoping per OPERATORS / UI when reviewing a run tree)
```

---

## Research grounding (short)

| Source | What CAR borrows |
|--------|------------------|
| EdReports gateways | Fail early structural/intent gates before soft polish |
| Hattie & Timperley | Where going / how going / where next → Why + Improve |
| Wiggins / UbD | Feedback ≠ guidance ≠ evaluation; auditor cues not rewrite |
| Path A trust scorecard | Hard YES/NO gates on the feedback artifact |
| Champion map | What “complete curriculum pack” means for CTE revisit |
| Stub-path harness | Presence-era honesty checks when one-pagers are not ready |

---

## Out of scope for CAR

- Scoring live teaching (Danielson Domains 2–3 as observation)
- Adopting / rejecting publishers as EdReports does for full suites
- Inventing lessons, keys, or TEKS alignment claims
- Declaring world-class quality on B–H before Path A pattern is locked
