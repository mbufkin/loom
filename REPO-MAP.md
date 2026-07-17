# REPO-MAP — Pointer (not the structure source of truth)

**Program** = repo root pipeline. **Data** = `projects/<id>/` corpora.

**Where files and zones live:** [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)  
(That file is the **only** canonical hierarchy / Zone A–E / dataset-layout contract.)

| Need | Go here |
|------|---------|
| Tree, zones, placement rules | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |
| Module catalog / TOC | [PROJECT_INDEX.md](PROJECT_INDEX.md) |
| Operator commands | [OPERATORS.md](OPERATORS.md) |
| Dataset shelf | [projects/STATUS.md](projects/STATUS.md) |

```bash
./run-audit my-district
./run-audit dallas-career-2026 --only engineering
```

Do **not** restate the directory tree in this file — edit PROJECT_STRUCTURE instead.
