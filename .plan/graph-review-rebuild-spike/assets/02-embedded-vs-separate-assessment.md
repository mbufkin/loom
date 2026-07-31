# Embedded vs separate assessment — standards & practice

**Ticket:** `tickets/02-embedded-vs-separate-assessment.md`  
**Question:** How do Learning Commons, IMS/SCORM/Common Cartridge, QTI, IEEE LOM, and related academic work treat assessments embedded inside a lesson document versus separate assessment files, and what flexible attachment rules keep belonging (Assessment ↔ Lesson) without forcing one physical form?

---

## Verdict

Standards and curriculum graphs treat **assessment as a logical role/entity** and treat **organization/belonging as a separate layer** from **file packaging**. They do **not** require assessments to be either always co-located inside a lesson document or always a standalone file. Belonging is expressed by hierarchy links (organization items, `hasPart` / `isPartOf` / `references`, lesson-scoped association). Physical form is an authoring/granularity choice.

**Loom rule-of-thumb (provisional graphs):** an `Assessment` may be realized as (a) an **embedded span** inside a lesson `Material`, or (b) a **separate assessment file** (`Material` + `Assessment` node). Both are valid **if and only if** a Lesson↔Assessment belonging link exists. Prefer that link over enforcing one physical form.

---

## 1. Learning Commons Knowledge Graph

**Sources**

- [Curriculum entity & relationship reference](https://docs.learningcommons.org/knowledge-graph/entity-and-relationship-reference/curriculum)
- [Assessments in a course (API)](https://docs.learningcommons.org/api-reference/curriculum/assessments-in-a-course)

**Findings**

- Curriculum entities include `Activity`, `Assessment`, and `Material`. An `Assessment` is defined as evaluation via structured tasks/questions — “a specific type of activity designed to evaluate student understanding.”
- Hierarchy is relational, not file-shaped:
  - `Lesson` → `hasPart` → `Activity`
  - `Activity` → `hasPart` → `Material`
  - `Assessment` → `references` → `Lesson` (documented relationship path)
  - Materials may carry `educationalUse` distinguishing instruction vs assessment.
- The REST API associates assessments with **course**, **lesson grouping**, or **lesson** (`courseId` + optional `lessonId` / `lessonGroupingId`). Belonging is scoped in the graph/API, not by co-location in a single document.
- Official LC docs do **not** prescribe whether assessment content lives as HTML inside a lesson packet vs a distinct artifact. The model is entity + relationship; physical packaging is out of band.

**Implication for loom:** Keep `Assessment` as a first-class node under (or referencing) a `Lesson`. File vs span is a realization detail (`spanIn` / separate `Material`), not the belonging rule.

---

## 2. IMS Content Packaging & Common Cartridge

**Sources**

- [IMS Content Packaging v1.1.4 Information Model](https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_infov1p1p4.html)
- [IMS Content Packaging Best Practice Guide](https://www.imsglobal.org/content/packaging/cpv1p1p3/imscp_bestv1p1p3.html)
- [1EdTech Common Cartridge® 1.4 Implementation Guide](https://www.imsglobal.org/spec/cc/v1p4/impl)
- [Common Cartridge v1.3 Implementation](https://www.imsglobal.org/cc/ccv1p3/imscc_Implementation-v1p3.html)
- [Common Cartridge v1.0 Profile](https://www.imsglobal.org/cc/ccv1p0/imscc_profilev1p0.html) (explicit usage-vs-containment note)

**Findings**

- Content Packaging splits the package into:
  - **Organizations** — logical hierarchical TOC (`item` trees; nesting = presentation/organization).
  - **Resources** — inventory of files/assets (web pages, assessment objects, etc.) with **no assumed order or hierarchy**.
- An organization `item` links to a resource via `identifierref`. Structure and files are deliberately decoupled: one resource may be referenced from multiple items.
- Common Cartridge models QTI assessments as **Learning Application Objects (LAOs)** — typed resources (assessment / question bank) living in their own directory with a descriptor file and optional associated content. They appear in the organization as folder-nested **links** to those resources.
- CC sample organizations nest pretest/assessment items under study-guide/lesson folders while the QTI XML remains a separate resource file under `resources`.
- CC v1.0 notes that two LAO items may reference the same resource: folder references equate to **usage**, not physical containment.
- Cartridges also carry ordinary **webcontent** (HTML, PDF, etc.). Nothing in CC forbids assessment-like prompts inside webcontent; the interoperable *assessment object* path is the separate QTI LAO. Both forms can coexist in one package; belonging comes from organization placement.

**Implication for loom:** Mirror the CP/CC split — Lesson graph position ≠ file path. Separate exit-ticket file under a Lesson item ≡ embedded span under a Lesson node; both are “organization children,” not forced disk layouts.

---

## 3. IMS QTI (Question & Test Interoperability)

**Sources**

- [QTI v2.0 Integration Guide](https://www.imsglobal.org/question/qti_v2p0/imsqti_intgv2p0.html)
- [QTI v2.1 Implementation Guide](https://www.imsglobal.org/question/qtiv2p1/imsqti_implv2p1.html)
- [QTI v3.0 ASI XML Binding](https://www.imsglobal.org/sites/default/files/spec/qti/v3/bind/index.html)

**Findings**

- QTI defines a data model for items, tests/assessments, and (historically) object banks, exchanged as XML, typically inside an IMS Content Package (`imsmanifest.xml` + resource files).
- Packaging rules put each `assessmentItem` / `assessmentTest` (or legacy `questestinterop`) in its own `resource` entry; shared media/templates use `dependency`. Tests reference items by identifier — logical assembly, not “must live inside the lesson HTML.”
- Common Cartridge profiles a simplified QTI subset as the **assessment LAO**; questions appear only inside assessment or question-bank resources, not as free-floating loose text in the CC profile for QTI.

**Implication for loom:** When assessment is a first-class interchange object, standards prefer a **distinct resource**. When K–12 packets use informal exit tickets inside a lesson plan PDF/deck, that is outside QTI packaging — still modelable as an Assessment node with a span pointer. QTI does not outlaw embedded classroom practice; it standardizes the *separate-file* interchange form.

---

## 4. SCORM (ADL Content Aggregation Model)

**Sources**

- [SCORM Explained (Rustici) — packaging / CAM overview](https://scorm.com/scorm-explained/)
- [SCORM 1.2 developer overview](https://scorm.com/scorm-explained/technical-scorm/scorm-12-overview-for-developers/)
- ADL SCORM Content Aggregation Model (CAM) materials summarizing Assets / SCOs / Content Organization (e.g. [SCORM 1.2 CAM excerpt](http://www.vsscorm.net/docs/SCORM_1.2_CAM.pdf); ISO/IEC TR 29163-2 references the same model)

**Findings**

- **Asset** includes “assessment objects” among other media/data pieces.
- **SCO** is the launchable/trackable grain (one or more assets). Authors choose SCO size; a SCO may contain interactions/assessment *inside* it, or assessment may be a separate SCO in the organization.
- **Content Organization** (manifest items) sequences activities; physical files are listed under resources. Again: aggregation tree ≠ forced single-file lesson.

**Implication for loom:** Embedded formative checks inside a lesson SCO and separate quiz SCOs are both SCORM-normal; belonging is organizational placement / sequencing, not co-file mandate.

---

## 5. IEEE LOM (Learning Object Metadata)

**Sources**

- IEEE Std 1484.12.1 (LOM) — [IEEE SA page](https://standards.ieee.org/ieee/1484.12.1/3294/); final draft text widely mirrored (e.g. [educa.ch LOM draft PDF](https://www.educa.ch/sites/default/files/2020-11/lom_1484_12_1_v1_final_draft_0.pdf))
- [IMS Meta-data Best Practice Guide for IEEE 1484.12.1-2002](https://www.imsglobal.org/metadata/mdv1p3/imsmd_bestv1p3.html)
- SCORM CAM LOM binding tables (Relation.Kind vocabulary; same Dublin Core–derived set)

**Findings**

- **5.2 Learning Resource Type** vocabulary includes `exercise`, `questionnaire`, `exam`, `problem statement`, `self assessment`, `lecture`, etc. Educational *kind* is metadata, independent of whether the object is a fragment or a full package.
- **1.8 Aggregation Level** describes functional granularity (fragment → lesson → course → program), not “must be its own file.”
- **7 Relation / 7.1 Kind** includes `haspart`, `ispartof`, `references`, `isreferencedby`, `requires`, etc. Belonging and cross-links are first-class metadata, again without prescribing physical embedding.

**Implication for loom:** Tag role (`Assessment`) and relation (`hasPart` / `references` / loom `spanIn`) separately from storage. LOM supports both a self-assessment fragment inside a lesson aggregation and a standalone exam object.

---

## 6. Related academic framing (granularity)

**Sources**

- David A. Wiley, “Connecting learning objects to instructional design theory: A definition, a metaphor, and a taxonomy,” in *The Instructional Use of Learning Objects* (AECT) — [PDF](https://mari.usc.edu/wesrac/wired/bldg-7_file/wiley.pdf); also in [AECT collection](https://members.aect.org/publications/InstructionalUseofLearningObjects.pdf)
- David Wiley et al., “Overcoming the Limitations of Learning Objects” — [BYU ScholarsArchive](https://scholarsarchive.byu.edu/cgi/viewcontent.cgi?article=2013&context=facpub)

**Findings**

- Wiley frames the hard problems as **granularity** and **combination** (scope and sequence), not as a single mandatory file layout. Smaller objects increase reuse; larger aggregates reduce cataloging cost — designers choose grain.
- Later work notes that requiring every object to be specially formatted for LMS APIs can block reuse of existing materials “as is”; frameworks that keep assessment/roll-up out of every media object can reuse wild resources without rewriting them into a single physical form.

**Implication for loom:** Accept publisher messiness — exit ticket inside Day-2 slides *or* `exit-ticket-day2.pdf` — and stabilize **combination** (Lesson link) rather than renormalizing files.

---

## 7. Synthesis — flexible attachment rules

| Layer | What it fixes | Embedded in lesson doc? | Separate assessment file? |
|-------|---------------|-------------------------|---------------------------|
| LC curriculum graph | Entity + lesson/unit association | OK if Assessment linked to Lesson | OK if Assessment linked to Lesson |
| IMS CP / CC organization | TOC / folder belonging | Webcontent under lesson folder | QTI LAO item under lesson folder |
| QTI package | Interchangeable assessment object | Not the QTI-native form | Preferred form (item/test resources) |
| SCORM CAM | Trackable aggregation | Interactions inside a SCO | Separate quiz SCO |
| IEEE LOM | Type + Relation + AggregationLevel | Fragment / part-of | Standalone resource type |

**Non-negotiable belonging rule**

1. Every `Assessment` node must have an explicit Lesson (or, for unit-level tests, LessonGrouping) belonging edge — loom: `Lesson hasPart Assessment` and/or LC-style `Assessment references Lesson`.
2. Orphan assessments (typed but unlinked) fail provisional completeness, regardless of file form.

**Flexible realization rules**

1. **Embedded:** `Assessment` + `spanIn` (or equivalent span pointers) into a lesson `Material`; optional `describes` from a plan file. Do not require extracting a new file on disk for provisional graphs.
2. **Separate file:** `Assessment` + `Material` for that file + belonging edge to the correct Lesson (same pattern as Arts AV exit tickets in loom graphing notes).
3. **Both representations of the same evidence** (rare): one Assessment identity; multiple Materials/spans allowed if clearly the same instrument — avoid duplicate Assessment nodes for the same exit ticket.
4. **Do not** infer belonging from filename alone without a Lesson link; **do not** reject a graph solely because the exit ticket is not a separate Path-B file.

---

## 8. Concrete loom provisional-graph rule-of-thumb

> **Embedded span OR separate file — both OK if a Lesson↔Assessment link exists.**  
> Physical co-location is optional; belonging is mandatory. Prefer creating the Assessment node and Lesson edge during provisional assemble; refine span vs file during/after document review rather than blocking assemble on one packaging style.

This aligns with loom’s existing GRAPHING.md stance (organization tree ≠ resource files; exit ticket belongs under its Lesson) and with Learning Commons / IMS practice above.

---

## Citations checklist (retrieved for this note)

1. Learning Commons — Curriculum reference: https://docs.learningcommons.org/knowledge-graph/entity-and-relationship-reference/curriculum  
2. Learning Commons — Assessments API: https://docs.learningcommons.org/api-reference/curriculum/assessments-in-a-course  
3. IMS Content Packaging Info Model 1.1.4: https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_infov1p1p4.html  
4. IMS Content Packaging Best Practice: https://www.imsglobal.org/content/packaging/cpv1p1p3/imscp_bestv1p1p3.html  
5. 1EdTech Common Cartridge 1.4 Implementation Guide: https://www.imsglobal.org/spec/cc/v1p4/impl  
6. Common Cartridge 1.3 Implementation: https://www.imsglobal.org/cc/ccv1p3/imscc_Implementation-v1p3.html  
7. Common Cartridge 1.0 Profile (usage vs containment): https://www.imsglobal.org/cc/ccv1p0/imscc_profilev1p0.html  
8. QTI 2.0 Integration Guide: https://www.imsglobal.org/question/qti_v2p0/imsqti_intgv2p0.html  
9. QTI 2.1 Implementation Guide: https://www.imsglobal.org/question/qtiv2p1/imsqti_implv2p1.html  
10. QTI 3.0 Binding: https://www.imsglobal.org/sites/default/files/spec/qti/v3/bind/index.html  
11. IEEE 1484.12.1 LOM (IEEE SA): https://standards.ieee.org/ieee/1484.12.1/3294/  
12. IMS LOM Best Practice Guide: https://www.imsglobal.org/metadata/mdv1p3/imsmd_bestv1p3.html  
13. SCORM packaging overview (Rustici): https://scorm.com/scorm-explained/  
14. Wiley (learning objects / granularity): https://mari.usc.edu/wesrac/wired/bldg-7_file/wiley.pdf  
15. Wiley et al. (limitations / reuse as-is): https://scholarsarchive.byu.edu/cgi/viewcontent.cgi?article=2013&context=facpub  
