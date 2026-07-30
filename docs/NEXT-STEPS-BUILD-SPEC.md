# Next Steps — Build Spec (G10)

**Status:** draft build sheet (not the presentation page)  
**Surface:** Loom create-after-audit loop on the ThinkStation / G10  
**Audience:** engineering + partner walkthrough prep  
**Related:** [PRODUCT-OVERVIEW.md](PRODUCT-OVERVIEW.md), [STRUCTURAL-FILL.md](STRUCTURAL-FILL.md), [ROAD-TO-PRODUCTION.md](ROAD-TO-PRODUCTION.md), [CREATE-WORKFLOW.md](CREATE-WORKFLOW.md) (research-backed operator doctrine), UI `NextSteps.tsx` / Create Studio

---

## 1. One-line goal

After Loom **identifies** missing curriculum elements, give operators a **local, human-supervised process** to decide and close each gap — then **re-audit** to prove it — without turning the auditor into a silent content inventor.

Bridge line (product voice):

> We don’t invent what’s missing. We make “what’s missing” decidable — then creation has a known path.

---

## 2. Doctrine boundary (non-negotiable)

| Layer | Allowed | Forbidden |
|-------|---------|-----------|
| **Auditor (today, stays)** | Report gaps with citations; structural fill only | Author lessons, quizzes, rubrics, “fixed” curriculum |
| **Next Steps chapter (new)** | Human decides Author / Pull / Remove; optional supervised draft; re-run auditor | Auto-publish invented content; cloud egress; bypass QA gate |

**Architectural split (required):**

- Keep `auditor_only` pipeline unchanged.
- New code lives in a separate module/surface (e.g. `create/` or `next_steps/`) that **consumes** audit outputs and **writes** only under an explicit create workspace (e.g. `projects/<id>/create/`).
- Re-verify always means: drop/replace sources → `./run-audit` (or scoped stage) → compare findings.

Do **not** amend Bet 8 / STRUCTURAL-FILL by quietly generating content inside Layer 0–2.

---

## 3. What exists today (inputs you can use)

| Artifact | Path / API | Use for Next Steps |
|----------|------------|--------------------|
| Aggregate stats | `output/aggregate-stats.json` · `GET /api/projects/{id}/stats` | Systemic missing roles, unit rollup |
| Unit rung | `layer_unit/UNIT-RUNG.json` | Completeness missing components, isolated gaps |
| Artifact rung | `layer_artifact/ARTIFACT-RUNG.json` | `missing_required`, deterministic gaps |
| Layer 1 findings | `layer1/findings.json` (and related) | MISSING / FULFILLED rows with citations |
| First-pass packet | `output/FIRST-PASS.md` | Already names Author / Pull / Remove |
| Local UI + API | Vite `:5173` · `ui/server.py` `:8770` | Review console; extend for gap queue |
| Draft model | Cursor SDK (`composer-2.5`) via Pi `~/.pi/agent/auth.json` or `CURSOR_API_KEY` for now; local llama later | Draft assist only (gated), never silent fill |

**Presentation only (done):** `ui/src/components/NextSteps.tsx` — diagram deck, not the product.

---

## 4. Target product flow

Operator doctrine (unit matrix → UbD stage order → triage → create) is frozen in
[CREATE-WORKFLOW.md](CREATE-WORKFLOW.md). Do not invent new browse axes without
updating that doc first.

```text
Curriculum pack
    → Audit · Routing (TODAY)
         ├─ complete → Quality OK · Report → Delivered packet
         └─ gaps found
              → Unit completeness matrix (primary)
              → Gap Triage (Author | Pull | Remove)
              → Fill Stage 1 → 2 → 3 inside unit (human-supervised)     [NEXT]
              → QA Gate · Re-audit (presence · alignment · citations)
                   ├─ FAIL → feedback + retry create
                   └─ PASS → Publish-Ready QA → Delivered packet
```

Continuous learning (later phase): golden findings → offline tuning → diagnoser → config update → benchmark → deploy create prompts/gates only (not silent curriculum).

---

## 5. Phased deliverables

### Phase 0 — Gap work queue (ship first)

**Outcome:** Live queue of missing elements from a selected project; operator records a decision per gap; no model authoring yet.

| Work item | Spec |
|-----------|------|
| Gap normalizer | Read UNIT-RUNG + ARTIFACT-RUNG + aggregate-stats (+ Layer 1 findings if needed); emit one `GapItem` schema |
| Persist decisions | `projects/<id>/create/decisions.yaml` (or JSONL) — gap_id, decision, note, actor, timestamp |
| API | `GET /api/projects/{id}/gaps`, `POST /api/projects/{id}/gaps/{gap_id}/decision` |
| UI | Replace/augment Next Steps presentation with **work mode**: list gaps, filter systemic vs isolated, set Author/Pull/Remove |
| Acceptance | Open Dallas (or sample) project → see same gaps the unit heatmap implies → save decisions → reload persists |

**GapItem (minimum fields):**

```yaml
gap_id: string          # stable hash of unit_id + role/component + day_id|doc_id
project_id: string
unit_id: string
unit_title: string
kind: role | component | artifact_required
label: string           # e.g. exit_ticket, independent_practice
locus: string           # day_id or doc_id
pattern: systemic | isolated
evidence_refs: [string] # paths or element ids when available
decision: null | author | pull | remove
decision_note: string
updated_at: iso8601
```

### Phase 1 — Create workspace + brief

**Outcome:** For `decision: author`, generate a **brief/checklist** (not a finished lesson) into the create workspace.

| Work item | Spec |
|-----------|------|
| Brief builder | Deterministic template from packet type + role + unit context + cited neighboring evidence |
| Write path | `projects/<id>/create/briefs/<gap_id>.md` (+ optional `.json` sidecar) |
| UI | “Open brief” from gap row; show checklist of required parts |
| Acceptance | Brief never claims to be district curriculum; labeled `create_workspace` / human must complete |

### Phase 2 — Supervised draft (optional local model)

**Outcome:** Optional draft assist for Author gaps; human must accept before anything enters `sources/`.

| Work item | Spec |
|-----------|------|
| Create agent | Local chat/completions call; prompt = brief + allowed context excerpts only |
| Gates | Max tokens; refuse if evidence context empty; watermark draft as `DRAFT_UNVERIFIED` |
| Human accept | Explicit “Promote to sources” copies into `projects/<id>/sources/` (or staging folder) |
| K loops | Edit → re-draft capped (e.g. K≤3) with prior fail notes |
| Acceptance | No auto-write into audited sources; all model I/O logged under `create/logs/` |

### Phase 3 — QA Gate · Re-audit

**Outcome:** Closing a gap means the auditor agrees.

| Work item | Spec |
|-----------|------|
| Re-audit trigger | `POST /api/projects/{id}/re-audit` (flags: scoped unit or full `./run-audit`) |
| Compare | Diff prior vs new findings for that `gap_id` locus |
| Pass criteria | Gap no longer MISSING / missing_required cleared; citations present for new material |
| Fail path | Attach fail note to gap; return to Create (Phase 1–2) |
| Acceptance | Happy path: Author → promote → re-audit → gap status `closed` |

### Phase 4 — Continuous learning (defer)

Golden hand-checked findings, diagnoser, auto-tuning of **create prompts / triage rules** only. Out of scope for first G10 demo unless Phase 0–3 are solid.

---

## 6. G10 box requirements

### Hardware (already the target workstation)

| Need | Spec |
|------|------|
| GPU | NVIDIA workstation GPU with enough VRAM for current local model (e.g. Nemotron-class ~30B class already in use) |
| RAM / disk | Enough for project trees + create workspace + model cache |
| Network | Optional; product path is **0 curriculum egress** |

### Software / runtime

| Need | Spec |
|------|------|
| Python 3 | Existing Loom pipeline |
| Node (dev UI) | Vite for `ui/`; production can serve `ui/dist` from `ui/server.py` |
| Local inference | OpenAI-compatible endpoint (`llama-server` / vLLM) as today |
| Config | `config.yaml` model URLs; create module reads same endpoint, separate timeout/rate limits |

### Ops

| Need | Spec |
|------|------|
| Local-only bind | Create API on `127.0.0.1` (same trust model as review API) |
| Logging | Flat JSON/JSONL per create step (traceable; matches deck claim) |
| Secrets | No cloud keys required for core path |

---

## 7. Repo / module layout (proposed)

```text
create/                     # NEW — never imported by layer0/1/2 audit path
  __init__.py
  gaps.py                   # normalize GapItems from audit artifacts
  decisions.py              # read/write decisions.yaml
  brief.py                  # Phase 1 templates
  draft.py                  # Phase 2 model call (optional)
  compare.py                # Phase 3 pre/post finding diff
ui/server.py                # NEW endpoints under /api/projects/{id}/gaps…
ui/src/pages or components  # Work queue UI (deck stays or becomes secondary tab)
projects/<id>/create/       # NEW per-project workspace (gitignored if copyrighted)
  decisions.yaml
  briefs/
  drafts/
  logs/
docs/NEXT-STEPS-BUILD-SPEC.md  # this file
```

---

## 8. UI build notes (match Review, not Uber dark)

| Surface | Spec |
|---------|------|
| Visual | Neo-brutalist tokens already in `styles.css` (cream, thick border, hard shadow) |
| Entry | Topnav **Next Steps** → work queue by default; keep diagram as “How it works” subview if useful |
| Density | Title + one line per gap; systemic vs isolated chips; decision control |
| Non-goals | Rainbow node-kind legend as primary UI; horizontal overflow diagram as the product |

---

## 9. Effort sketch (rough)

| Phase | Scope | Rough order |
|-------|--------|-------------|
| 0 Gap queue + decisions | API + normalizer + UI list | 1–2 focused engineering days |
| 1 Briefs | Templates + file write + open-in-UI | +1 day |
| 2 Draft assist | Prompting + promote gate + logs | +2–3 days (prompt quality iterate) |
| 3 Re-audit compare | Hook run-audit + gap close status | +1–2 days |
| 4 Learning loops | Defer | After design-partner feedback |

*Assumes one engineer familiar with Loom artifacts on G10; not calendar commitment.*

---

## 10. Demo script (NVIDIA / interview)

1. **Review** — heatmap shows missing roles/components (today).  
2. **Next Steps (Phase 0)** — same gaps as a queue; pick Author / Pull / Remove.  
3. **Brief (Phase 1)** — open checklist for one Author gap.  
4. *(If ready)* **Draft (Phase 2)** — generate draft → human edits → promote.  
5. **Re-audit (Phase 3)** — gap closes or FAIL returns to create.  
6. Stay on doctrine: auditor still never invents; create is supervised and verified.

---

## 11. Explicit non-goals (v1 create chapter)

- Cloud-hosted curriculum generation  
- Silent overwrite of district sources  
- Replacing Path A/B/C auditor workflows with an authoring model  
- Full continuous-learning auto-deploy of agents  
- Packaging/Docker stranger-install (that’s [ROAD-TO-PRODUCTION.md](ROAD-TO-PRODUCTION.md); parallel track)

---

## 12. Definition of done (Phase 0–3)

A G10 operator can:

1. Run an audit on a real project.  
2. Open Next Steps and see a **faithful gap queue**.  
3. Record **Author / Pull / Remove** per gap (persisted).  
4. For Author: get a **brief**, optionally a **draft**, promote only with confirmation.  
5. **Re-audit** and see the gap **closed** or returned with fail notes.  
6. Prove **no cloud egress** and **no unaudited invented content** in the happy path.

---

## 13. Open decisions (resolve before Phase 2)

1. **Draft scope:** lesson-plan stubs only, or also quizzes / exit tickets?  
2. **Promote target:** straight to `sources/` vs `create/staging/` until re-audit passes?  
3. **Packet types:** which roles get first-class brief templates first?  
4. **Doctrine doc update:** add a short “Create chapter” addendum to PRODUCT-OVERVIEW without weakening auditor-only identity.
