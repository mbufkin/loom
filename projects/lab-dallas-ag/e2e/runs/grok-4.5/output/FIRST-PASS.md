# Curriculum Review Work Packet (first-pass)

*Report id: `first-pass` — course-level structure check.*

**Dataset:** `lab-dallas-ag`  
**Documents in the shared folder:** 2  
**Units in scope:** 1

This is a **read-only structure check** of what is already in the curriculum folder, compared to the district instructional calendar and each unit's day grid. It does **not** write lessons, syllabi, or assessments — those stay with you. Use it to prep a work session: what to bless as a YAG/pacing draft, what materials the calendar expects but the folder lacks, which lesson plans are missing core parts, and which files may be misfiled.

## 1. Work-session agenda (start here)

1. **Year-at-a-Glance / pacing** — no district school calendar was found, so dates are sequential only. Add `school-calendar.yaml` (DISD spine is in `shared/disd-school-calendar/`) and re-run rollup for a dated YAG.
2. **Scope & sequence gaps** — 8 expected material slot(s) have nothing in the folder yet (calendar/S&S expectation vs. what was uploaded). Decide what to author, what to drop from the day grid, or what still lives elsewhere.


## Work-session synthesis (model delivery)

This first-pass pack is a single-unit story: **Curriculum** is the only unit in scope and is also the sole entry on the missing-materials list, so session time should stay on clearing that backlog once—author what is truly absent, pull equivalents from another drive, or drop/adjust day-grid expectations that no longer match what you intend to keep—rather than spreading effort across units that are not in this pack. Pair that with a quick duplicate cleanup: relocate the misfiled copy or record the expected overlap in `manifest.yaml` so the same artifact stops counting twice. Layer 2 lesson-plan completeness and mismatch queues are empty here, so do not open those tracks until materials are present and filed correctly. Use the inferred two-day sequence only as a placement sketch; it does not stand in for the missing lesson materials.

*Tables and counts throughout this report are code-locked from Layer 1/2 ledgers — treat them as the inventory of record; this note only adds prioritization across them.*

## 2. Year-at-a-Glance & pacing guide (draft)

Pacing exists but is **sequential** (no dated district spine). Copy the DISD calendar from `shared/disd-school-calendar/` into this project and re-run rollup.

## 3. Scope & sequence gaps (calendar expectation vs. folder)

These counts compare **what each unit's day grid says should exist** (lesson plan, exit ticket, rubric, …) with **what was found in the uploaded files**. A high number usually means the calendar is ambitious relative to this folder — not that teachers failed. Decide per gap: author it, pull it from another drive, or remove it from the official S&S/day grid.

**Found & verified:** 0  ·  **Not in this folder:** 8  ·  **Possible duplicates:** 1

| Unit | Materials found | Not in folder | Possible duplicates |
|------|-----------------|---------------|---------------------|
| Curriculum | 0 | 8 | 1 |

## 4. Lesson plan template completeness

For documents already confirmed as lesson plans, this checks whether core **parts** are present in the file itself: standards/objectives, materials, direct instruction, and an assessment checkpoint. It does **not** score whether the lesson is engaging or pedagogically strong.

No lesson plans were confirmed for completeness yet (Layer 2 empty or no `lesson_plan` fulfillments).

## 5. Filing & cross-course alignment

Documents whose **own wording** names a different unit than the folder they live in. Strongest cases first — often a reused template or a file saved in the wrong cluster folder.

No filing conflicts detected.

## 6. What this packet does **not** do

- Write or rewrite lesson plans, assessments, rubrics, or syllabi
- Insert videos or partner curriculum modules for you
- Judge TEKS / CCMR / industry alignment as pass/fail (it can only show when standards language is present in a file)
- Replace collaborative work sessions, PD, or compensation tracking

Your team still owns content quality and the official YAG, syllabus, and S&S.

## Appendix — status glossary

| Status | What it means |
|---|---|
| **MATCH** | This content's own words agree with where it's filed. No action needed. |
| **MISMATCH** | This content's own words name a DIFFERENT unit than where it's filed. The real signal this whole system exists to produce — but check the corroboration count and excerpt before acting; see 'Needs your attention' below. |
| **CROSS_REFERENCE** | An overview/hub document (e.g. a district-wide career-cluster survey) mentions another unit by name — that's the hub doing its job, not a misfile. |
| **EXPECTED_OVERLAP** | A human reviewer already confirmed this unit-pair legitimately, expectedly overlaps (e.g. an Architecture & Construction lesson teaching engineering design methodologies). Not a filing error — see manifest.yaml known_overlaps. |
| **ORPHAN** | This document isn't linked from any unit in the manifest at all. |
| **UNVERIFIED** | This content doesn't restate its own unit/day in its own words, so placement is trusted from the manifest only, not independently confirmed. This is normal and expected for most body content — not a red flag on its own. |
| **MISSING** | An expected artifact for a specific day (e.g. a lesson plan, worksheet, rubric) was not found anywhere in the corpus. |
| **DUPLICATE** | Two or more near-identical claims independently satisfy the same day/role — likely the same content counted twice, not two distinct pieces of evidence. |
| **FULFILLED** | An expected day-level artifact was found and verified to actually function as that role, not just labeled as one. |

## Appendix — how this was produced

Every document was read in full and broken into cited instructional elements; placement was checked against the manifest and day grid without showing the model the filing answer key; expected materials were verified by function; lesson plans were checked for core parts with no extra model calls. Details: `docs/CHAMPION-REVIEW-MAP.md`, `docs/BETS.md`.
