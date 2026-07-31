# lab-ag-arts-mix

Ingest-organize separation test: **Ag (2) + Arts AV (8)** dumped in one `sources/` pile.

Compare artifacts under `ingest/.compare/`.

## Backends

| Label | What | Config |
|-------|------|--------|
| Grok | Cursor SDK `grok-4.5` | `config.cursor.yaml` |
| NIM hosted | `nvidia/nemotron-3-nano-30b-a3b` API | `config.nvidia.yaml` + `NVIDIA_API_KEY` |
| **Local G10** | **Nemotron-3-Nano-30B MoE GGUF** via llama.cpp `:8080` (`nemotron3-nano-30b.gguf`, ~524k ctx) | `config.yaml` |

Local ≠ hosted: same model family, different stack. Local is what `./run-audit` uses on this box.

## Results

| Backend | Separation | Manifest written | Notes |
|---------|------------|------------------|-------|
| **Grok 4.5** | Clean 2+8, 0 cross | YES | Gold working tree |
| **NIM hosted 30B** | Clean 2+8 (semantic) | NO | Schema only: `sources/` prefixes + `unit_length_days: 2.5` |
| **Local G10 30B** | **NO** | NO | Dropped 3 Arts files; **misfiled** Arts lesson plan into Ag; **hallucinated** filename `doc_ff5cd4c0712e_Arts_A_V_Tech__Lesson_Plan_.txt` (hash from Day-2 exit ticket + lesson-plan name) |

### Local failure detail

- Missing: flyer rubric, commercial rubric, exit ticket Day 2  
- Contamination: `doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt` → `agriculture-plant-science`  
- Paths were bare `doc_…` (good) and day counts were ints (good) — so this was **placement**, not schema

Working tree restored to Grok manifest after each failed run.

## Follow-up: local auto-improve (rich catalog)

`experiments/ingest_mix_local/` — local `:8080` with more text + repair loop.

**PASS on iter 3** (2+8 clean) once `unit_id` underscores were normalized to hyphens.
See `experiments/ingest_mix_local/results/SUCCESS/organize.json`.
