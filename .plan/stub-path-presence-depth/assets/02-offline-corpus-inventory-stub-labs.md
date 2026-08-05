# Offline corpus inventory for stub-path labs (B · H · F · D · E)

**Ticket:** [02-offline-corpus-inventory-stub-labs](../tickets/02-offline-corpus-inventory-stub-labs.md)  
**Question:** What offline, already-local quiz, answer-key, exit-ticket, pacing/YAG, teacher-edition, and student-practice samples exist under Loom projects / Desktop / fixtures that can seed strong·mixed·weak lab fixtures for Paths B, H, F, D, and E — without requiring new partner downloads?  
**Method:** Filename + path search under `projects/*/sources`, `projects/*/ _corpus`, `projects/_fixtures`, `projects/lab-*`, `data/`, Desktop (`culinary`, `career-curriculum`); verify file type/size so stub placeholders are not mistaken for real PDFs.  
**Date:** 2026-08-05  
**Constraint:** Inventory only — no downloads, no invented files. Paths relative to repo root `g10-control-center-loom/` unless absolute.

---

## Method notes / corpus caveats

| Location | Reality on disk |
|----------|-----------------|
| `projects/dallas-career-2026/sources/` | Real extracted `.txt` (usable lab seeds). Mirrored in `lab-dallas-career/sources/`, `data/career-curriculum/osint/`, `_snapshots/…`. |
| `projects/oklahoma-ag-orientation-2026/sources/` | Real `.docx` quizzes, worksheets, unit tests/keys. |
| `projects/bluebonnet-math-2026/_corpus/` | **Canonical real Bluebonnet PDFs** (Alg1 + G5). Prefer this over other Bluebonnet trees. |
| `projects/bluebonnet-full-grok/sources/` | **Name stubs only** (~48–128 byte ASCII placeholders: “corpus not mounted”). Do **not** seed labs from these PDFs. |
| `projects/bluebonnet-g5-m1-graph-test/sources/` | Same stub pattern (~150 byte text files with `.pdf` extension). |
| `projects/bluebonnet-full-grok/evidence/**/*.json` | Extracted element excerpts from a prior mount — usable as **text fixtures** when PDF stubs are empty. |
| `projects/openscied-6/sources/*-te.pdf` | Large real teacher editions (multi‑MB). |
| `/home/lenovo/Desktop/culinary/` | Syllabi + uniform/toolkit (Path **G** territory); **no** quiz / exit / YAG / TE / Learn-Practice for B–E. |
| `projects/lab-culinary-syllabus/sources/` | Same culinary set as Desktop (Path G lab). |

**Suitability legend (rough, for lab seeding):**  
- **strong** — complete enough for presence extractors to find multiple expected signals  
- **mixed** — partial structure / thin body / incomplete pairing  
- **weak** — filename-routable but nearly empty or single-prompt stubs  

---

## Counts summary (unique seed candidates)

| Path | Unique primary seeds (deduped) | Strong | Mixed | Weak | Gap? |
|------|-------------------------------|--------|-------|------|------|
| **B** Assessment | **4** Dallas quiz↔key pairs + **1** worksheet↔key; **22** OK quizzes + **3** unit test/keys | 4 Dallas pairs; OK unit test+key | OK quizzes (no per-quiz keys in sources) | — | No Bluebonnet quiz/key; OK lesson quizzes lack sibling answer keys in `sources/` |
| **H** Exit ticket | **21** Dallas + **1** synthetic mini | ~4–6 richer Dallas | ~10 mid | ~5–7 one-prompt / mini | No OK / Bluebonnet / Desktop exit tickets |
| **F** Standards & pacing | **8** Alg1 program PDFs in `_corpus` (+ evidence JSON twins) | Pacing + S&S 150/165 | YAG / TEKS / ELPS / Standards Overview (1–3 pp, small) | pathful sequence flowchart; project `pacing-plan.yaml` | No Dallas YAG/pacing docs |
| **D** Teacher support | **14** Bluebonnet TE/impl in `_corpus` + **7** OpenSciEd TE (1 stub) | OpenSciEd large TEs; BB TE modules ~150–165 KB | BB Course+Impl guides | `openscied 6.4-te.pdf` (243 B); BB name stubs elsewhere | No Dallas `Teacher_Edition` filenames |
| **E** Student practice | **18** G5 Learn/Practice/Succeed + Alg1 Skills/SE modules + **5** Dallas worksheets + **2** OK worksheets | Learn/Succeed modules; Alg1 Skills Practice | Dallas worksheets; some Succeed | Many G5 `*_Practice_*` PDFs tiny (≤2 KB) | No Desktop practice set |

---

## Path B — Assessment (`quiz` / `answer_key`)

### Recommended strong·mixed·weak seeds

| Tier | Files | Notes |
|------|-------|-------|
| **strong** | `projects/dallas-career-2026/sources/doc_fc48920a5ca9_Engineering_Lesson_Quiz___Quizizz.txt` + `…/doc_86fff193b91a_Engineering_Lesson_Quiz___Quizizz_Answer_key.txt` | Full Quizizz stem set (~2.5 KB) + matching key (~3 KB). |
| **strong** | `…/doc_d3fae80ecd3f_Architecture_and_Construction_Quizizz.txt` + `…/doc_ed1c99b4f5fa_Architecture_and_Construction_Answer_Key_Quizizz.txt` | Paired. |
| **strong** | `…/doc_3fd5e5bc561c_Manufacturing_exploration___Quizizz.txt` + `…/doc_a13c35aa5c4e_Manufacturing_exploration_Answer_keys___Quizizz.txt` | Paired. |
| **strong** | `…/doc_0b16e1424928_Dallas_ISD_High_School_Options___Quizizz.txt` + `…/doc_6caee441faaf_Dallas_ISD_High_School_Options___Quizizz_Answer_Key.txt` | Largest pair (~7.7 / ~10 KB). |
| **mixed** | `projects/oklahoma-ag-orientation-2026/sources/unit-1/OAS Unit 1 Lesson 1 Quiz.docx` (and other unit lesson quizzes) **without** a sibling answer-key file | **22** lesson quizzes under `sources/unit-{1..5}/`; real `.docx`. Pairing for B needs a key — see unit tests below. |
| **mixed / strong (test↔key)** | `…/unit-1/OAS Unit 1 Test.docx` + `OAS Unit 1 Test Key.docx`; `…/unit-3/OAS Unit 3 Test+Answers.docx`; `…/unit-4/OAS-Unit-4-Test+Answers.docx` | Assessment-bearing with keys; filename is `Test` not `Quiz` — still Path B–relevant if router treats assessment. |
| **mixed** | `projects/dallas-career-2026/sources/doc_0ace9ac9d412_Transportation__Distribution_and_Logistics_Answer_Key.txt` + `…/doc_a8248438c079_Transportation__Distribution_and_Logistics_Student_Worksheet.txt` | Key pairs to **worksheet** (Path E), not a Quizizz quiz. |
| **weak** | *(none required — Dallas already supplies thin keys if needed by truncating)* | — |

### Also present (duplicates / archives)

- Same Dallas quiz/key set: `projects/lab-dallas-career/sources/`, `data/career-curriculum/osint/`, `projects/_snapshots/dallas-career-2026-*/sources/`.
- Oklahoma zips (already local, not extracted as separate key files):  
  `projects/oklahoma-ag-orientation-2026/_download/oas-unit-*/OAS-Unit-*-Quiz*.zip`, `…Assessments.zip`, `…Quizzes-Test-and-Answers.zip`.

### Gaps

- No Bluebonnet quiz / answer_key PDFs in `_corpus` or sources.  
- Oklahoma lesson quizzes lack per-lesson `*Answer*` / `*Key*` siblings in `sources/` (unit-level keys only; more may sit inside `_download` zips — still offline, but not ready as flat lab files).

---

## Path H — Exit ticket

### Recommended strong·mixed·weak seeds

| Tier | Files | Notes |
|------|-------|-------|
| **strong** | `projects/dallas-career-2026/sources/doc_ba8b5c7a6deb_Engineering_Lesson_-__Exit_Ticket.txt` | Multi-prompt reflective exit (~869 B). |
| **strong** | `…/doc_e173d04cd3e3_Architecture___Construction_-__Exit_Ticket.txt` | ~1.2 KB. |
| **strong** | `…/doc_1bd2952ce87b_Information_Technology_-__Exit_Ticket.txt`, `…/doc_1518e9d9d4e5_Health_Science_-__Exit_Ticket.txt`, `…/doc_8ce965ac1600_Business__Marketing___Finance_-__Exit_Ticket.txt` | Paragraph / multi-part prompts. |
| **mixed** | `…/doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt` (+ Day 2/3 siblings); Hospitality Day 1–3 set; Career Cluster Day 1–3 | Short but real formative checks; also copied into `lab-arts-av/`, `lab-ag-arts-mix/`. |
| **weak** | `…/doc_4736326638c1_Professional_Preparedness_-__Exit_Ticket_Day_2.txt` | Single question (~292 B): “What would you wear to an interview?” |
| **weak** | `projects/_fixtures/ledger-mini/sources/doc_aaaa03_Mini_Exit_Ticket.txt` | Synthetic mini (2 questions, ~157 B) — good harness smoke, not partner content. |

### Full Dallas exit-ticket inventory (21)

All under `projects/dallas-career-2026/sources/`:

- `doc_041457651819_Professional_Preparedness_-__Exit_Ticket_Day_1.txt`
- `doc_09bf178d4e7e_Professional_Preparedness_-__Exit_Ticket_Day_3.txt`
- `doc_0a9fe894e4f0_Career_Cluster-__Exit_Ticket_Day_1.txt`
- `doc_1518e9d9d4e5_Health_Science_-__Exit_Ticket.txt`
- `doc_1b43180b2ba4_Dallas_ISD_High_School_Options_-__Exit_Ticket.txt`
- `doc_1bd2952ce87b_Information_Technology_-__Exit_Ticket.txt`
- `doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt`
- `doc_3f5d5ba70a87_Hospitality___Tourism_Day_2_Exit_Ticket.txt`
- `doc_4736326638c1_Professional_Preparedness_-__Exit_Ticket_Day_2.txt`
- `doc_51e75ae5f576_Exit_Ticket_Day_3_HOSPITALITY_AND_TOURISM_.txt`
- `doc_59ddeafc2ad3_Career_Cluster_-__Exit_Ticket_Day_3.txt`
- `doc_81adda4c10f7_Manufacturing_Lesson_Exit_ticket.txt`
- `doc_85c8ad2c6c50_Day_1_Exit_Ticket__HOSPITALITY_AND_TOURISM_.txt`
- `doc_8ce965ac1600_Business__Marketing___Finance_-__Exit_Ticket.txt`
- `doc_9b49036929a2_Hospitality___Tourism_Day_2_-__Exit_Ticket.txt`
- `doc_ba8b5c7a6deb_Engineering_Lesson_-__Exit_Ticket.txt`
- `doc_e173d04cd3e3_Architecture___Construction_-__Exit_Ticket.txt`
- `doc_e2c12c61bc5f_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_3.txt`
- `doc_eff81c789b58_Financial_Literacy_-__Exit_Ticket.txt`
- `doc_f52d1bc1c462_Career_Cluster_-__Exit_Ticket_Day_2.txt`
- `doc_ff5cd4c0712e_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_2.txt`

### Gaps

- No exit tickets in Oklahoma, Bluebonnet, Desktop culinary, or OpenSciEd sources.  
- Path H lab can be fully seeded from Dallas alone for strong·mixed·weak.

---

## Path F — Standards & pacing

### Real PDFs (prefer `_corpus`)

All under `projects/bluebonnet-math-2026/_corpus/algebra-1/`:

| Tier | File | Size (approx) |
|------|------|----------------|
| **strong** | `Algebra_I_Math_150-day_Topic_Pacing_Guides.pdf` | ~15 KB, 2 pp |
| **strong** | `Algebra_I_Math_Scope_and_Sequence_150-day.pdf` | ~18 KB, 3 pp |
| **strong** | `Algebra_I_Math_Scope_and_Sequence_165-day.pdf` | ~48 KB |
| **mixed** | `Algebra_I_Math_YAG_150-day.pdf` / `Algebra_I_Math_YAG_165-day.pdf` | ~3.5 / ~4.3 KB, 1 pp |
| **mixed** | `Algebra_I_Math_TEKS_Summary.pdf`, `Algebra_I_Math_ELPS_Summary.pdf`, `Algebra_1_Math_Standards_Overview.pdf` | 1–2 KB class |

### Text evidence twins (when stub PDFs elsewhere are empty)

Under `projects/bluebonnet-full-grok/evidence/`:

- `alg1-support-a/Algebra_I_Math_150-day_Topic_Pacing_Guides.json` (~27 KB excerpts)
- `alg1-support-b/Algebra_I_Math_Scope_and_Sequence_150-day.json`, `…_165-day.json`
- `alg1-support-d/Algebra_I_Math_YAG_150-day.json`, `…_YAG_165-day.json`
- `alg1-support-c/Algebra_I_Math_TEKS_Summary.json`
- `alg1-support-a/Algebra_1_Math_Standards_Overview.json`

### Thin / meta (weak for curriculum Path F)

| File | Note |
|------|------|
| `projects/pathful-planning-guides-2026/sources/doc_pathful_1530547_Planning_Guide_Activity_Sequence_Flowchart.txt` | ~1.4 KB sequence flowchart — borderline F |
| `projects/*/pacing-plan.yaml` (e.g. oklahoma, ap-csp) | Loom project calendar meta, **not** partner YAG |

### Gaps

- No Dallas CTE pacing / YAG / scope-sequence docs in sources.  
- `bluebonnet-full-grok/sources/*YAG*.pdf` etc. are **empty stubs** — use `_corpus` or `evidence/*.json` only.

---

## Path D — Teacher support

### Bluebonnet teacher editions / implementation (real `_corpus`)

**Module TEs (strong seeds — pick 1–2 modules for labs):**

- `projects/bluebonnet-math-2026/_corpus/grade-5/K-5_Math_Grade_5_Module_1_Place_Value_and_Decimals_Teacher_Edition.pdf` (~150 KB)
- Modules 2–6 + ADSY TE under same `grade-5/` (~164–165 KB each)
- `projects/bluebonnet-math-2026/_corpus/algebra-1/Algebra_I_Math_Teacher_Edition_Volume_1_Module_{1,2,3}.pdf` (+ Vol 2 Mod 4–5)

**Implementation / course guides (mixed–strong):**

- `…/algebra-1/Algebra_I_Math_Teacher_Edition_Course_and_Implementation_Guide.pdf` (~98 KB)
- `…/algebra-1/Secondary_Mathematics_Program_Implementation_Guide.pdf` (~165 KB)
- `…/grade-5/K-5_Math_Program_and_Implementation_Guide.pdf` (~81 KB)
- `…/algebra-1/Algebra_I_Math_Teacher_Edition_Glossary.pdf` (~9 KB — thin)

### OpenSciEd teacher editions (strong offline, large)

Under `projects/openscied-6/sources/`:

| File | Size | Tier |
|------|------|------|
| `7.2-te.pdf` | ~92 MB | **strong** |
| `7.1-te.pdf`, `7.4-te.pdf` | ~55 MB | **strong** |
| `7.3-te.pdf` | ~37 MB | **strong** |
| `6.3-te.pdf` | ~13 MB | **strong** |
| `6.2-te.pdf`, `8.2-te.pdf` | ~8 / ~6 MB | **strong** |
| `6.4-te.pdf` | **243 B** | **weak** stub |

### Avoid as content seeds

- `projects/bluebonnet-full-grok/sources/*Teacher_Edition*.pdf` — stubs  
- `projects/bluebonnet-g5-m1-graph-test/sources/*Teacher_Edition*.pdf` — stub  

### Gaps

- Dallas career sources have lesson plans / slides, not `Teacher_Edition` / implementation-guide filenames for Path D filename routing.  
- Desktop culinary has no TE.

---

## Path E — Student practice

### Bluebonnet Learn / Practice / Succeed (real `_corpus/grade-5/`)

| Tier | Examples |
|------|----------|
| **strong** | `K-5_Math_Grade_5_Module_1_Learn_Place_Value_and_Decimals_Student_Edition.pdf` (~39 KB); Module 4/6 Learn (~50–57 KB); several Succeed (~16–64 KB) |
| **mixed** | Module Succeed siblings mid-size; `projects/bluebonnet-math-2026/_corpus/algebra-1/Algebra_I_Math_Skills_Practice_Student_Edition.pdf` (~48 KB); Alg1 `Student_Edition_Volume_*` modules (~31–73 KB) |
| **weak** | `…_Module_1_Practice_Place_Value_and_Decimals_Student_Edition.pdf` (**886 B**); other `*_Practice_*` files ~1.6–4.8 KB |

Full G5 set (Modules 1–6 × Learn/Practice/Succeed) lives under `_corpus/grade-5/` — **18** student practice-role PDFs.

### Dallas worksheets (mixed)

Under `projects/dallas-career-2026/sources/`:

- `doc_a8248438c079_Transportation__Distribution_and_Logistics_Student_Worksheet.txt` (+ Answer_Key above → B/E boundary)
- `doc_2fc999f5e539_Students_Worksheet.txt`
- `doc_addfb0873806_Community_Problem_Brainstorming_Worksheet.txt`
- `doc_e31064aba3ae_Writing_Your_Sales_Pitch_Worksheet.txt`
- `doc_f9710e5e4e97_Career_Exploration_Worksheet-_LAW.txt`

### Oklahoma worksheets (mixed)

- `projects/oklahoma-ag-orientation-2026/sources/unit-1/OAS Unit 1 Key Terms Worksheet.docx`
- `…/unit-2/OAS Unit 2 Key Terms Worksheet.docx`

### Gaps

- Desktop / culinary: no Learn/Practice/Succeed or worksheets for Path E.  
- Prefer `_corpus` over stub trees for Bluebonnet E labs.

---

## Suggested trio picks (no new downloads)

| Path | Strong | Mixed | Weak |
|------|--------|-------|------|
| **B** | Engineering Quizizz + Answer_key (Dallas) | OAS Unit 1 Lesson 1 Quiz.docx (no key) **or** Transportation worksheet+Answer_Key | Truncate / use unpaired quiz alone if harness needs empty key side |
| **H** | Engineering Exit Ticket (Dallas) | Arts AV Exit Ticket Day 1 | Professional Prep Day 2 **or** ledger-mini Mini Exit Ticket |
| **F** | Alg1 150-day Topic Pacing Guide (`_corpus`) | Alg1 YAG 150-day (`_corpus`) | pathful Activity Sequence Flowchart **or** YAG via stub PDF (negative control) |
| **D** | G5 Module 1 Teacher Edition (`_corpus`) **or** OpenSciEd `6.2-te.pdf` | Alg1 TE Course+Implementation Guide | OpenSciEd `6.4-te.pdf` (243 B) **or** g5-m1-graph-test TE stub |
| **E** | G5 Module 1 Learn SE (`_corpus`) | Dallas Transportation Student Worksheet **or** G5 Module 1 Succeed | G5 Module 1 Practice SE (886 B) |

---

## Desktop & fixtures (cross-path)

| Path | Desktop `/home/lenovo/Desktop/culinary/` | `_fixtures` |
|------|----------------------------------------|-------------|
| B/H/F/D/E | **No** matching samples (syllabi + uniform/toolkit only → Path G) | Path H: `ledger-mini` mini exit ticket; other fixtures are ingest/calendar only |

---

## Bottom line

Offline seeding for **B and H is Dallas-complete** (plus Oklahoma for extra B quizzes/tests). **F, D, E are Bluebonnet-`_corpus`-complete** for Alg1 pacing/YAG and G5 TE + Learn/Practice/Succeed, with OpenSciEd as heavy D backups. Treat `bluebonnet-full-grok/sources` and `bluebonnet-g5-m1-graph-test/sources` as **filename stubs**, not content. Desktop culinary does not add B–E seeds without new files.
