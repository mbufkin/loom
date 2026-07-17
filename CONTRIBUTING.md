# CONTRIBUTING — Rules of Engagement

**Audience:** Human contributors and AI agents  
**Tone:** Imperative — these are requirements, not suggestions.  
**Charter reminder:** Loom is a **read-only auditor**. You MUST NEVER add features that author lesson plans, assessments, rubrics, or other instructional content.

---

## 1. Before you write any code

1. Read [PROJECT_INDEX.md](PROJECT_INDEX.md) and locate the correct module (catalog).  
2. Read [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) and confirm the target path is allowed.  
   **Tree / zone facts live only in PROJECT_STRUCTURE** — do not duplicate them in REPO-MAP or PROJECT_INDEX.  
3. Read [DATA_MAP.md](DATA_MAP.md) if you touch keys, enums, or YAML/JSON shapes.  
4. Read [DEPENDENCY_FLOW.md](DEPENDENCY_FLOW.md) and identify blast radius.  
5. Read [docs/BETS.md](docs/BETS.md) if the change affects model behavior, citations, or taxonomy.
6. Read [docs/DOCUMENTATION-PROCESS.md](docs/DOCUMENTATION-PROCESS.md) before any docs-only or docs-heavy change
   (accuracy / sync first; no blanket docstring sweeps).

**MUST NOT** start by creating a new top-level folder “to keep things tidy.” Extend the canonical hierarchy in PROJECT_STRUCTURE or propose an explicit structure PR first.

---

## 2. SOP — Adding a new production module

| Step | Action | Done when |
|------|--------|-----------|
| 1 | Place the `.py` file at **repo root** (or justify a package in a structure PR) | Path matches PROJECT_STRUCTURE |
| 2 | Import only from Zone A libraries (`audit_lib`, `schema_validate`, `doc_extract`, `report_lib`) | No imports from `tools/`, `experiments/`, `archive/` |
| 3 | Accept `--project <id>` (or equivalent) — **MUST NOT** hardcode a project | Works for any `projects/<id>/` |
| 4 | Validate model/on-disk payloads via `schema_validate.py` | Failures raise clear errors |
| 5 | Write outputs only under `projects/<id>/…` per ownership table | No writes to repo root data |
| 6 | Add row to PROJECT_INDEX §2 | Index updated |
| 7 | Add lineage arrow to DEPENDENCY_FLOW §1 and blast-radius note if pivot | Lineage updated |
| 8 | Add terms to GLOSSARY if new vocabulary | Glossary updated |
| 9 | Add schema rows to DATA_MAP if new fields/enums | Data map updated |
| 10 | Add/extend tests per TESTING_STRATEGY | Tests pass |
| 11 | Update OPERATORS.md if operators need a new command | Docs updated |

---

## 3. SOP — Adding a new project corpus

```bash
mkdir -p projects/<project_id>/sources
# copy curriculum files into sources/
```

You MUST then:

1. Create `projects/<project_id>/README.md` with: tier (Golden/Stress/Active/Experiment/Fixture), how to run, and any special calendars.  
2. Add a row to PROJECT_INDEX §3.  
3. Use a valid `project_id` slug (`validate_slug_id`).  
4. Prefer `doc_<hex>_<slug>.*` naming for extracts.  
5. Run ingest + Layer 0/1 as appropriate; do not commit secrets in `config.yaml`.

**MUST NOT** leave a non-fixture project without a README (orphans are a Context Layer defect).

---

## 4. SOP — Changing schemas or enums

1. Update `schema_validate.py` first.  
2. Update DATA_MAP.md and GLOSSARY.md.  
3. Update DEPENDENCY_FLOW.md blast radius.  
4. Extend `test_schema_validate.py`.  
5. If `ELEMENT_TYPES` or taxonomy version changes: bump `LAYER0_TAXONOMY_VERSION` and plan a full Layer 0 re-run on golden.  
6. **MUST NOT** silently reinterpret old ledger files under a new taxonomy.

---

## 5. SOP — Human calibration (HITL)

| Artifact | You MAY | You MUST NOT |
|----------|---------|--------------|
| `manifest.yaml` → `known_overlaps` | Add confirmed unit pairs | Invent overlaps without review |
| `layer1/REVIEW-QUEUE.md` | Resolve / document decisions | Edit `bucket-ledger.json` by hand |
| Calendars | Fix structural errors | Invent days to “make gaps go away” without evidence |

After overlap edits: re-run `layer1.py` → `synthesize.py`.

---

## 6. Instructions for AI agents (anti-orphan protocol)

You MUST follow this protocol on every change set:

### 6.1 Navigation first

1. Open PROJECT_INDEX.md — find the owning module.  
2. Open PROJECT_STRUCTURE.md — confirm the write path.  
3. If the path is not listed, **stop** and update the Context Layer before adding files.

### 6.2 No orphan files

| You create… | You MUST also… |
|-------------|----------------|
| New directory with logic or data | README **or** an explicit entry in PROJECT_STRUCTURE stating READMEs are optional for that generated dir |
| New project under `projects/` | Project README + PROJECT_INDEX row |
| New script at repo root | PROJECT_INDEX row + DEPENDENCY_FLOW edge |
| New enum/status string | GLOSSARY + DATA_MAP + schema_validate |
| New doc in `docs/` | Link from `docs/README.md` |

### 6.3 Functional logic boundary

- Context Layer docs do **not** replace product docs in `docs/`.  
- Do **not** “fix” pipeline bugs by rewriting ledgers.  
- Do **not** merge experiment code into production imports.  
- Do **not** bypass `schema_validate` to “just make the run finish.”

### 6.4 Headline path honesty

When documenting behavior, you MUST treat **Layer 0/1** as the product path
(skippable via `--skip-layer01`). Doc-level scrub→place is archived under
`archive/legacy-unit-audit/` and MUST NOT be described as part of `./run-audit`.

Curricula are **data** under `projects/`; do not invent curriculum-specific program forks.

### 6.5 Commit discipline

- Do not commit `config.yaml`, secrets, or large private corpora under `data/` unless explicitly requested.  
- Do not commit unless the user asks.  
- Prefer small PRs: one stage or one Context Layer concern per PR when possible.

---

## 7. Code style & quality gates

| Gate | Requirement |
|------|-------------|
| Auditor charter | `policy.auditor_only` remains true; no content-authoring features |
| IDs | All CLI project/unit ids through `validate_slug_id` |
| Model JSON | Parse via `parse_model_json`; validate via `schema_validate` |
| Citations | Layer 0 excerpts MUST remain citation-backed (paragraph ranges) |
| Unknowns | Prefer `unknown` / `unclear` / null over hallucinated placement |
| Tests | Run the suite in TESTING_STRATEGY before claiming done |

---

## 8. Deprecated / forbidden contributions

| Action | Status |
|--------|--------|
| Extending `archive/crystallize-legacy/` | Forbidden |
| New imports from `archive/` | Forbidden |
| Calling `tools/` from production | Forbidden |
| Writing curriculum content into `sources/` via models | Forbidden |
| Parallel project layout that ignores §3 of PROJECT_STRUCTURE | Forbidden |

---

## 9. Review checklist (paste into PR)

```text
[ ] PROJECT_INDEX updated (if modules/projects added)
[ ] PROJECT_STRUCTURE respected (paths)
[ ] GLOSSARY updated (if new terms)
[ ] DATA_MAP updated (if keys/schemas)
[ ] DEPENDENCY_FLOW updated (if lineage)
[ ] schema_validate + tests updated (if contracts)
[ ] OPERATORS / docs updated (if operator-facing)
[ ] No Zone C/D/E imports in production
[ ] No hand-edited layer0/layer1 JSON
[ ] Charter intact (no content authoring)
```
