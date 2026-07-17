# projects/ — Curriculum data (not the program)

**Loom** (repo root) is the **program**.  
Everything under `projects/` is **data**: interchangeable curriculum corpora you feed the program.

```bash
# Any dataset id works the same way:
mkdir -p projects/my-district/sources
# copy curriculum files into sources/
./run-audit my-district
# → projects/my-district/output/GLOBAL-AUDIT-REPORT.pdf
```

See [STATUS.md](STATUS.md) for tiers. New corpus: copy [_template/](_template/).

---

## Input: documents only

```
projects/<dataset-id>/sources/          ← your curriculum files
projects/<dataset-id>/reference/        ← optional district calendar image
projects/<dataset-id>/school-calendar.yaml
```

Supported formats: pdf, docx, pptx, xlsx, odt, txt, md, html, rtf, doc. Nested subfolders OK.

---

## Generated (do not hand-edit unless correcting models)

| File | Created by |
|------|------------|
| `manifest.yaml` | `ingest.py` |
| `units/<unit>/calendar.yaml` | `ingest.py` |
| `pacing-plan.yaml` | `rollup.py` |
| `layer0/` | `layer0.py` (via `run_project.py`) |
| `layer1/` | `layer1.py` (via `run_project.py`) |
| `output/**` | synthesize + PDF |

---

## Datasets on this shelf

| Folder | Tier | Role |
|--------|------|------|
| `dallas-career-2026/` | Golden | Acceptance / demo dataset |
| `region10-career-college-2026/` | Active | Live district corpus |
| `ap-csp-2026/` | Stress | Hard PDF shape |
| `openscied-6/` | Experiment | Fat TE PDFs (+ `experiments/openscied/`) |
| `_template/` | Template | Empty skeleton for new corpora |
| `_fixtures/` | Fixture | Tiny ingest smoke data (not operator corpora) |

Program docs: [../README.md](../README.md) · Commands: [../OPERATORS.md](../OPERATORS.md)
