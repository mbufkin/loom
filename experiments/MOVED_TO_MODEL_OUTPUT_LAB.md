# Moved — do not use these older experiment entrypoints

Model comparison work now lives in a clearly named sandbox:

**→ [`experiments/model-output-lab/`](model-output-lab/README.md)**

| Old / confusing name | Use instead |
|----------------------|-------------|
| `multi_backend_bakeoff.py` | `model-output-lab/run_serial_compare.py` |
| `backends.yaml` (repo experiments/) | `model-output-lab/backends.yaml` |
| `config.zen.yaml` (repo root) for lab runs | `model-output-lab/configs/zen.yaml` |
| Parallel bake-off | **Removed from the lab** — serial only |

The files below may still exist as leftovers; prefer the lab.
