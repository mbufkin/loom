# lab-culinary-syllabus — Path G smoke seed

Tiny lab for **Path G (Syllabus)** presence extractors (G1–G7).

| | |
|--|--|
| **Docs** | `Culinary I Syllabus.docx`, `Culinary Prac Syllabus.docx` (+ unrelated culinary assets not routed to G) |
| **Route** | Both syllabi → Path **G** (`layer0/route-map.json`) |
| **Runner** | `python3 -c 'from workflows.syllabus import run_path_g_for_project; run_path_g_for_project("lab-culinary-syllabus")'` |
| **Artifact** | `path_g/findings.json` — expect `status: ok`, `doc_ids` length 2 |

This is the on-disk Path G seed for A–H pathway testing (Dallas has no syllabus filenames; Bluebonnet covers Path F).

Cross-check summary: [`experiments/pathway-a-g-verify/RESULTS.json`](../../experiments/pathway-a-g-verify/RESULTS.json).
