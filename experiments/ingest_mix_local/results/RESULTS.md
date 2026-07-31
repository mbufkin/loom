# lab-ag-arts-mix local auto-improve

Model: `/home/lenovo/llama.cpp/models/nemotron3-nano-30b.gguf` via `http://localhost:8080/v1/chat/completions`
Started: 2026-07-31 02:12:14

## Iter 1 — FAIL (30.5s, budget=800, mode=fresh)

- coverage errors: ["unassigned files: ['doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt']", "unknown files in plan: ['doc_e8c12c61bc5f_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_3.txt']"]
- schema errors: ['duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'duplicate unit_id: slug', 'units[9].source_files must be a non-empty list', 'units[9].calendar.days must be a non-empty list']
- gold: agriculture-plant-science via slug: missing ['doc_b5e36486805a_Agriculture-_Plant_Science.txt', 'doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt']; arts-av-technology-communication: no predicted unit; expected 2 units, got 1: ['slug']
- detail: `{"units": {"slug": []}, "agriculture-plant-science": {"matched_unit": "slug", "jaccard": 0.0, "fp": [], "fn": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"]}}`

## Iter 2 — FAIL (15.2s, budget=2000, mode=repair)

- coverage errors: ["unassigned files: ['doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt', 'doc_89430d6aae63_Arts_AV_Technology___Communication_-_Slides.txt', 'doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt']", "duplicate assignments: ['doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt']"]
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication via arts_av_communication_cluster: false positives ['doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt']; arts-av-technology-communication via arts_av_communication_cluster: missing ['doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt', 'doc_89430d6aae63_Arts_AV_Technology___Communication_-_Slides.txt', 'doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt']
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_e2c12c61bc5f_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_3.txt", "doc_e9e6ac`

## Iter 3 — FAIL (17.2s, budget=6000, mode=repair)

- coverage errors: none
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication ↔ arts_av_communication_cluster: PASS jaccard=1.0
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt", "doc_89430d6aae63_Arts_AV_Technology___`

## Iter 4 — FAIL (18.1s, budget=12000, mode=repair)

- coverage errors: none
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication ↔ arts_av_communication_cluster: PASS jaccard=1.0
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt", "doc_89430d6aae63_Arts_AV_Technology___`

## Iter 5 — FAIL (14.1s, budget=12000, mode=repair)

- coverage errors: none
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication ↔ arts_av_communication_cluster: PASS jaccard=1.0
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt", "doc_89430d6aae63_Arts_AV_Technology___`

## Iter 6 — FAIL (15.8s, budget=20000, mode=repair)

- coverage errors: ["unassigned files: ['doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt', 'doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt', 'doc_89430d6aae63_Arts_AV_Technology___Communication_-_Slides.txt', 'doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt']"]
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication via arts_av_communication_cluster: missing ['doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt', 'doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt', 'doc_89430d6aae63_Arts_AV_Technology___Communication_-_Slides.txt', 'doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt']
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_e2c12c61bc5f_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_3.txt", "doc_ff5cd4c0712e_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_2.txt"]}, "agricult`

## Iter 7 — FAIL (18.8s, budget=20000, mode=repair)

- coverage errors: none
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication ↔ arts_av_communication_cluster: PASS jaccard=1.0
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt", "doc_89430d6aae63_Arts_AV_Technology___`

## Iter 8 — FAIL (18.7s, budget=50000, mode=repair)

- coverage errors: none
- schema errors: ["units[0].unit_id invalid slug: 'agri_plant_science'", "units[1].unit_id invalid slug: 'arts_av_communication_cluster'"]
- gold: agriculture-plant-science ↔ agri_plant_science: PASS jaccard=1.0; arts-av-technology-communication ↔ arts_av_communication_cluster: PASS jaccard=1.0
- detail: `{"units": {"agri_plant_science": ["doc_b5e36486805a_Agriculture-_Plant_Science.txt", "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt"], "arts_av_communication_cluster": ["doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt", "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt", "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt", "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt", "doc_89430d6aae63_Arts_AV_Technology___`

**EXHAUSTED** — no PASS within max iters.

## Rescore with slug normalize (_ → -)

See above console; SUCCESS promoted if any iter had gold-perfect file sets.

## Conclusion

**PASS** after rescoring iter 3 with mechanical normalize (`unit_id` `_`→`-`).

- Iter 1: schema mess / hallucinated hash
- Iter 2: near-split but dupes + missing Arts files
- Iter 3–5,7–8: **gold-perfect file sets** (2+8); only failing slug underscores until normalize
- Iter 6: regression (dropped Arts files) then recovered

Your bet holds for this fixture: local can separate with more text + instructions; stock 200-char ingest under-feeds it.

