# Documentation process — Crystallize

**Purpose:** How to update docs in this repo without creating documentation debt.
**Audience:** Human contributors and AI agents.
**Doctrine:** Accuracy and sync beat exhaustive coverage. Prefer updating existing
docs over creating new top-level files.

Empirical SE research (Garousi/NovAtel; Aghajani ICSE; Uddin & Robillard; Rios
doc-debt studies) consistently ranks **up-to-dateness, correctness, completeness
for real tasks, and clarity** above volume. Blanket docstring/header sweeps create
comment smells and go stale. Continuous small repayment beats one-shot “enterprise”
rewrites.

---

## 1. Before writing docs

1. Identify the **task** the reader is trying to finish (setup, run audit, smoke one
   unit, skip layers, contribute a module, interpret FIRST-PASS).
2. Find the **canonical SoT** for that topic — do not fork a second truth:

| Topic | Source of truth |
|-------|-----------------|
| Commands / flags / outputs | [OPERATORS.md](../OPERATORS.md) |
| Stage lineage / blast radius | [DEPENDENCY_FLOW.md](../DEPENDENCY_FLOW.md) |
| Tree / zones | [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md) |
| Module catalog | [PROJECT_INDEX.md](../PROJECT_INDEX.md) |
| Design why | [BETS.md](BETS.md) |
| Schemas / enums | [DATA_MAP.md](../DATA_MAP.md) + `schema_validate.py` |

3. Diff the SoT against code (`run_project.py`, stage CLIs). Fix wrong statements
   before adding new prose.

---

## 2. Priority order (always)

| Priority | Work | Examples |
|----------|------|----------|
| **P0** | Wrong or contradictory claims | Pipeline missing Layer 2; “two-model required” vs single-model config |
| **P1** | Incomplete for a key operator/contributor task | Missing flag side-effects; missing primary output names |
| **P2** | Structure / navigation | Index links, cross-refs |
| **Defer** | Restating obvious code; file-level headers everywhere; new ceremony files | Do not “document every function” |

If uncertain about behavior: write `TODO (docs):` with what was verified — **never invent**.

---

## 3. What good docs look like here

- **Scenario-first** for operators (first dataset, after adding docs, smoke unit, skip path).
- **Working examples** that match real CLIs (`./run-audit …`).
- **Public / pivot surfaces** documented; private helpers only when non-obvious.
- **Inline comments** explain *why* or edge cases, not what the next line does.
- No `DOCUMENTATION_COMPLETE.md` or similar mission-accomplished artifacts — summarize in the PR.

---

## 4. SOP — Docs-only change set

| Step | Action |
|------|--------|
| 1 | Audit linked docs for the touched feature against code |
| 2 | Patch the SoT file first (usually OPERATORS or DEPENDENCY_FLOW) |
| 3 | Propagate one-line fixes to README / PIPELINE / PRODUCT-OVERVIEW / INDEX as needed |
| 4 | Add `docs/README.md` link only if you create a **new** doc under `docs/` |
| 5 | Check relative markdown links resolve |
| 6 | Run the test suite from [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) if any code/docs-of-contracts changed; docs-only → link check is enough |

---

## 5. Anti-patterns (forbidden)

- Rewriting OPERATORS or DEPENDENCY_FLOW wholesale when a patch suffices.
- Creating parallel ARCHITECTURE / README sections that contradict the SoT.
- Blanket Phase-4 docstring passes on every class/function.
- Claiming Layer 0/1-only as the product path (Layer 2 is on the default orchestrator).
- Describing archived scrub→place as part of `./run-audit`.

---

## 6. Definition of done

A documentation change is done when:

1. No known P0 contradictions remain for the touched topic.
2. The primary reader task has a correct command path and expected artifacts.
3. Cross-links from `docs/README.md` / Context Layer still resolve.
4. Uncertainties are tagged `TODO (docs):`, not papered over.
