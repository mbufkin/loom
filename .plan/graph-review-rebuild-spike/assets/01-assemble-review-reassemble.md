# Assemble → review → reassemble: published patterns

**Ticket:** `tickets/01-assemble-review-reassemble-literature.md`  
**Question:** What published patterns describe building a provisional instructional organization graph, running document/content review, then revising the graph from review findings — and what do they imply for loom’s spike loop (provisional HAS-PART → review → rebuild)?  
**Method:** Web research of standards, peer-reviewed guides, and widely adopted edtech practice (2026-07-31). Citations below are live sources; nothing invented.

---

## Verdict

No single standard names “provisional HAS-PART → Path review → rebuild,” but several independent, widely adopted patterns converge on the same loop: **draft an organization over a stable inventory of materials, review content/alignment against that map, then revise the organization (and belonging edges) from what review found.** Loom’s spike is therefore on solid practice ground — especially if Materials stay inventory-stable while organization/edges are allowed to change.

---

## Pattern families

### 1. Packaging standards: organization ≠ resources (rebuild the tree, keep the inventory)

**IMS / 1EdTech Content Packaging** separates the **resources** section (bill of materials / file inventory) from the **organizations** section (hierarchical presentation / TOC of items that *reference* resources). Producers may supply **multiple organizations** over the same resources; organizations do not point at files directly — they point at resource entries. Resources can be rearranged into one or multiple organizations without re-packaging physical files.

- [1EdTech Content Packaging Best Practice Guide (v1.1.3)](https://www.imsglobal.org/content/packaging/cpv1p1p3/imscp_bestv1p1p3.html) — organizations describe static structure so resources “can be moved to create one or multiple organizations”; multiple orgs allowed, one default.
- [1EdTech CP v1.2 Primer](https://www.imsglobal.org/content/packaging/cpv1p2pd2/imscp_primerv1p2pd2.html) — resources = bill of materials; organization structures components into educational content; alternate organization types (e.g. topic maps) contemplated alongside a conventional org.
- [SCORM.com — Manifest structure](https://scorm.com/scorm-explained/technical-scorm/content-packaging/manifest-structure/) — multiple organizations = alternate arrangements of the same content.
- SCORM Content Aggregation Model (built on IMS CP) restates that learning resources are separated from how they are organized, enabling multiple orgs / contexts over one resource set (see [ISO/IEC TR 29163-2 overview](https://www.iso.org/standard/53535.html); practitioner summary: [SCORM 1.2 Overview](https://scorm.com/wp-content/assets/cookbook/SCORM%201_2%20Overview.htm)).

**Loom mapping:** Provisional `HAS-PART.json` ≈ first organization. Layer 0 Materials / source files ≈ resources inventory. Rebuild after review ≈ emit a revised organization (and edges: `hasPart`, `spanIn`, `describes`, `uses`) without re-splitting files on disk — aligned with GRAPHING.md’s “break apart in the graph, not on disk.”

### 2. Learning Commons curriculum ontology: the target aggregation schema

Learning Commons K–12 curriculum ontology models instructional structure as a graph: `Course` → `LessonGrouping` → `Lesson` → `Activity` / materials, linked primarily by **`hasPart`**, with assessments and materials hanging under lessons rather than as peer “paths.”

- [Learning Commons — Curriculum entity & relationship reference](https://docs.learningcommons.org/knowledge-graph/entity-and-relationship-reference/curriculum)

**Loom mapping:** Schema for both provisional and rebuilt graphs. Literature here is **target shape**, not the review loop; the loop comes from mapping / UbD / QM / ADDIE below.

### 3. Curriculum mapping: draft map → review → revise (explicit CQI)

**Heidi Hayes Jacobs** (K–12 practice, ASCD): calendar-based curriculum maps collect what is actually taught; procedure moves from data collection through reviews to **immediate revision points** and longer-term R&D, with ongoing review. ERIC abstract for *Mapping the Big Picture* (1997): procedures “begin with collecting the data and move through several reviews to determining the points that can be revised immediately and those that will require long-term research and development”; “Curriculum review should be active and ongoing.”

- [ERIC ED411323 — Jacobs, *Mapping the Big Picture*](https://eric.ed.gov/?id=ED411323)
- Research brief summarizing Jacobs’ stages (research/development → mapping → ongoing assessment/evaluation/revision): [ERIC ED538540](https://files.eric.ed.gov/fulltext/ED538540.pdf)

**Ronald Harden** (peer-reviewed medical education): curriculum mapping makes relationships among outcomes, content, assessment, learning opportunities, and **learning resources** transparent; mapping is a tool for curriculum *development*, not a one-shot inventory.

- Harden, R. M. (2001). AMEE Guide No. 21: Curriculum mapping… *Medical Teacher*, 23(2), 123–137. [DOI](https://doi.org/10.1080/01421590120036547) · [PubMed](https://pubmed.ncbi.nlm.nih.gov/11371288/)

**Institutional / vendor CQI framing:** map → analyze content & structure → research/review/revise as continuous quality improvement (e.g. [Acuity Insights — Curriculum Mapping Best Practices](https://acuityinsights.com/wp-content/uploads/2024/04/Acuity-Insights-One45-Curriculum-Mapping-Best-Practices-1.pdf); University of Calgary *Guide to Curriculum Review*, citing Harden — [PDF](https://taylorinstitute.ucalgary.ca/sites/default/files/Curriculum/UofC_guide_to_curriculum_review_UPDATED_2019-09%202.pdf)).

**Loom mapping:** Provisional HAS-PART = diary/draft map. Document review = small/large-group read-through of content against the map. Rebuild = immediate revision of belonging / gaps; unresolved items can remain as longer “research” tickets (GRAPHING.md invariant: unknown allowed).

### 4. Understanding by Design: draft design → design-standards review → revise

UbD’s published practice is **backward design** (desired results → evidence → learning plan) plus **regular review of units against design standards** (self and peer review), then edit. Designs are drafts; peer review against rubrics drives improvement. Curriculum mapping under UbD is used to find gaps/redundancies and target revisions.

- [ASCD UbD White Paper (Wiggins & McTighe)](https://files.ascd.org/staticfiles/ascd/pdf/siteASCD/publications/UbD_WhitePaper0312.pdf) — three-stage backward design; alignment across stages.
- [UbD research-base summary (McTighe)](https://jaymctighe.com/wp-content/uploads/2011/04/UbD-Research-Base.pdf) — “Regular reviews of curriculum and assessment designs, based on design standards”; peer-review protocols.
- [McTighe & Wiggins handbook intro excerpt (ASCD)](https://files.ascd.org/pdfs/publications/books/mctighe2004_intro.pdf) — design standards for continuous improvement; draft template → peer review → revise; backward mapping identifies gaps for curriculum revision.
- Peer-reviewed application tip sheet: [Twelve tips for using UbD… (2023)](https://doi.org/10.1080/0142159x.2023.2224498) — iterative alignment of outcomes, assessments, instruction.

**Loom mapping:** Provisional graph asserts structural “knownness” (lessons, materials, assessments under spine). Path/rung review is the design-standards pass (quality + missing evidence). Rebuild absorbs review discoveries (e.g. exit ticket under Day 2, missing handout `uses`, plan `describes` both lessons) — same spirit as GRAPHING.md’s UbD row and “missing evidence under a lesson spine.”

### 5. Quality Matters: review course design → amend → re-check

QM is a widely adopted peer-review process for online/blended course *design*. Reviews score standards (including instructional materials, assessments, alignment); unmet standards require **specific improvement suggestions**; courses that fail can be **amended and re-reviewed**. Explicit continuous-improvement culture, not one-pass certification.

- [QM — How course review works](https://qualitymatters.org/qm-membership/faqs/how-course-review-works)
- [QM Rubrics & Standards](https://www.qualitymatters.org/qa-resources/rubric-standards)

**Loom mapping:** Document/content review produces structured findings that must be allowed to change the course’s structural representation (rebuild), not only annotation on a frozen peer-file routing.

### 6. ADDIE: evaluation feeds the next design (iterative, not linear)

ADDIE (Analyze → Design → Develop → Implement → Evaluate) is the classic instructional-design cycle; modern accounts treat it as **iterative** — evaluation data returns to analysis/design for the next iteration. Authoritative open textbook treatment: Bates, *Teaching in a Digital Age*.

- [Bates — The ADDIE model](https://opentextbc.ca/teachinginadigitalage/chapter/6-5-the-addie-model/) — model applied iteratively; evaluation leads to re-analysis and further design/development modifications.

**Loom mapping:** First assemble = Design/Develop of structure; review = Evaluate (and content Analysis); rebuild = next Design pass. Treats rebuild as expected cycle, not defect.

---

## What the literature does *not* claim

- None of these sources prescribe Loom’s exact artifact names (`HAS-PART.json`, Path A/B/C, Layer 0).
- Learning Commons documents a **published curriculum graph schema**, not an automated assemble–review–rebuild pipeline.
- Packaging standards authorize **reorganization over stable resources**; they do not themselves define pedagogy review rubrics — UbD/QM/Jacobs supply that half of the loop.

---

## Implications for loom’s spike loop

| Implication | Source family | Spike consequence |
|-------------|---------------|-------------------|
| Provisional organization is legitimate | Jacobs draft/diary maps; UbD draft template; ADDIE iteration | Ship a first HAS-PART that may be wrong; do not wait for gold-perfect structure before review |
| Inventory stable; organization revisable | IMS CP / SCORM CAM | Rebuild revises nodes/edges/spans; do not re-ingest or physically split Materials |
| Review must be allowed to change belonging | UbD design standards; QM amend-and-recheck; Jacobs revision points | Router/Path review findings are inputs to graph rebuild, not only to prose reports |
| Don’t freeze peer typing before structure settles | Packaging (org ≠ resource); GRAPHING.md P1 bet | Prefer provisional graph → review → rebuild over flat Path A/B/C freezing roles |
| Gaps and unknowns are first-class | Harden transparency; GRAPHING.md “unknown allowed”; Jacobs “needs research” | `unresolved` / `referenced_missing` / tickets are success states of honesty |
| Structure completeness ≠ pedagogy quality | UbD stages; GRAPHING.md invariant 5 | Provisional gate = inventory/knownness; Path review = quality; rebuild merges structural discoveries |
| Immediate vs deferred fixes | Jacobs steps 5–6 | Rebuild contract should distinguish auto-applicable edge fixes vs HITL research tickets |

### Recommended reading of the spike loop

```text
Materials inventory (L0 / sources)     ← stable “resources”
        ↓
Provisional HAS-PART (organization v0) ← draft map / first org
        ↓
Document / Path review                 ← UbD/QM/Jacobs review pass
        ↓
Rebuild HAS-PART (organization v1+)    ← revise belonging, spans, gaps
        ↓
(optional) next review cycle           ← ADDIE / CQI
```

---

## Relation to `docs/GRAPHING.md`

GRAPHING.md already lists Learning Commons `hasPart`, SCORM/IMS organization≠files, and UbD alignment as research anchors, and recommends **graphing after L0 before the router** so flat peer typing does not freeze bad structure. This ticket’s literature **extends** that one-shot assemble design into an explicit **CQI loop**: provisional organization → content review → revised organization — matching Jacobs/UbD/QM/ADDIE, while packaging standards justify keeping Material inventory fixed across rebuilds. Spike decisions (completeness gate, rebuild triggers, router coupling) should treat rebuild as the intended second organization pass, not a failure of the first.
