# Path G — Syllabus workflow

**Lens name:** Syllabus (Path G). Taxonomy: [PATHS.md](PATHS.md).  
**Research:** [.plan/.../10-syllabus-quality-research.md](../.plan/world-class-path-reviews/assets/10-syllabus-quality-research.md).

Entry: Loom router typed the document as `syllabus` (filename / `doc_type`
contains `syllabus`; legacy typo `sylibuis` still routes here).

Auditor-only: **present / missing / misaligned from evidence**. Never invent
syllabus content. No Hunter plate (that is Path A only).

## Why Path G is its own lens

| Lens | Grain | Question |
|------|-------|----------|
| **A** Lesson | One instructional episode | Is this daily plan structurally complete? |
| **F** Standards & pacing | Year/unit spine | Do S&S / YAG / pacing cohere? |
| **G** Syllabus | Whole course, student/family facing | Can a student see the course bargain and TEKS path? |

## Academically / practically proven ways to *review* a written syllabus

| Framework | What it checks | Why it matters for Loom |
|-----------|----------------|-------------------------|
| **Learner-centered syllabus** (O’Brien et al.; Duke / Notre Dame checklists) | Outcomes, assessment plan, schedule, policies, supports, success cues | Best general inventory of syllabus *sections* |
| **UbD** at course grain | Outcomes → graded evidence → sequence must align | Catches gradebooks that don’t match stated goals |
| **T-TESS 1.1** (document use) | Measurable outcomes aligned to TEKS | Texas planning language without teacher eval |
| **TEA CTE class expectations** | Syllabus + timeline so course TEKS are covered; grading; attendance; safety; acknowledgments | Primary DISD CTE bar |
| **Curriculum audit triangulation** (Fenwick English) | Written syllabus vs assessed plan vs pacing artifacts | Match/mismatch with Path F — don’t invent YAG |

**We are not using** classroom-observation rubrics or Hunter daily structure as
Path G logic. Path G stays a **written course-syllabus audit**.

---

## Path G steps (G1 → G9)

| Step | Name | Academic / practice anchor | What Loom does | Output |
|------|------|----------------------------|----------------|--------|
| **G1** | Inventory cited chunks | Curriculum audit | Collect Layer 0 excerpts for this doc | Chunk inventory |
| **G2** | Course identity & logistics | TEA expectations; district norms | Course name/number, credit/grade band, teacher contact, meeting pattern, prereqs | PRESENT/MISSING + cites |
| **G3** | Purpose & learning outcomes | Learner-centered objectives · UbD Stage 1 · T-TESS 1.1 | Why-course / description + measurable outcomes or TEKS-facing goals | Outcomes checklist |
| **G4** | Assessment & grading transparency | TEA grading procedures · Duke assessment plan | Categories + weights, scale, late/makeup, feedback norms | Grading map |
| **G5** | Course map / TEKS timeline | TEA syllabus+timeline · UbD course map | Units/topics, major dates, TEKS/content sequencing claim | Timeline checklist |
| **G6** | Policies & communication | Learner-centered policies · TEA attendance/rules | Attendance, integrity, how to contact / get updates | Policies checklist |
| **G7** | Access, safety, CTE/WBL | ELPS/UDL (light) · TEA safety + WBL | Accommodations/supports, safety, internship/WBL, parent/student acknowledgment when CTE signals present | CTE access checklist |
| **G8** | Cross-artifact alignment | English triangulation · Path F handoff | Syllabus ↔ YAG/pacing/S&S; outcomes ↔ grade categories | MISALIGNED flags |
| **G9** | Emit Path G artifacts | Shared short-artifact habit | Write findings; later short one-pager (gaps → working → evidence) | `path_g/*` |

### Guardrails (every step)

- Blank / MISSING = not found in materials  
- No authored policies, TEKS lists, calendars, or acknowledgment forms  
- Model may **route and label** evidence; may not **create** content  
- Soft tone/belonging is not a hard gate (optional note only)

### Implementation status

| Area | Status |
|------|--------|
| Router + `workflow_id: syllabus` | Wired |
| Checklist YAML | `workflows/checklists/syllabus.yaml` |
| G1 inventory | Per-doc Layer 0 excerpt inventory |
| G2–G7 presence | Keyword + type scan → PRESENT / MISSING / NOT_SIGNALED (optional CTE) |
| G8 cross-artifact | Stub |
| G9 one-pager | Stub |

---

## How this sits in the big pipeline

```
… → Layer 0 classify → Loom router → Path G (G1–G9) → synthesize / champion packet …
```

Lesson plans never enter G1–G9 (Path A). YAG/pacing docs use Path F; G8 may
*compare* to them when both exist.

## Related

- Taxonomy: [PATHS.md](PATHS.md)  
- Champion syllabus row: [CHAMPION-REVIEW-MAP.md](CHAMPION-REVIEW-MAP.md)  
- Lesson contrast: [PATH-A-LESSON-PLAN.md](PATH-A-LESSON-PLAN.md)
