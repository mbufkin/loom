# projects/ — Curriculum data (not the program)

**Loom** (repo root) is the **one E2E program** (`./run-audit` / `run_project.py`).  
Everything under `projects/` is **data**: interchangeable curriculum corpora.

```bash
# Any curriculum id works the same way:
mkdir -p projects/my-district/sources
# copy curriculum files into sources/
./run-audit my-district --with-graph --graph-run nemotron3-nano-30b
# → projects/my-district/e2e/runs/nemotron3-nano-30b/
#    (layer0…, output/, graph/ — review UI: curriculum → E2E · model)
```

Contract: [docs/E2E.md](../docs/E2E.md). See [STATUS.md](STATUS.md) for tiers.
New corpus: copy [_template/](_template/).

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

**Review outputs (default):** `e2e/runs/<model>/` — layers, graph, `output/**`.

| Path | Created by |
|------|------------|
| `manifest.yaml` | `ingest.py` (shared input; often symlinked into e2e) |
| `units/<unit>/calendar.yaml` | `ingest.py` |
| `e2e/runs/<model>/layer0/` … `layer2/` | `run_project.py` E2E |
| `e2e/runs/<model>/graph/` | `--with-graph` |
| `e2e/runs/<model>/output/**` | synthesize + quality plates |
| `e2e/runs/<model>/USAGE-SUMMARY.json` | usage meter |

---

## Datasets on this shelf

| Folder | Tier | Role |
|--------|------|------|
| `dallas-career-2026/` | Golden | Acceptance / demo dataset |
| `region10-career-college-2026/` | Active | Live district corpus |
| `ap-csp-2026/` | Stress | Hard PDF shape |
| `openscied-6/` | Stress | Fat TE PDFs |
| `_template/` | Template | Empty skeleton for new corpora |
| `_fixtures/` | Fixture | Tiny ingest smoke data (not operator corpora) |

Program docs: [../README.md](../README.md) · Commands: [../OPERATORS.md](../OPERATORS.md)
