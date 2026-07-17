# TESTING_STRATEGY — Pre-Flight Check Framework

**Purpose:** Define verification beyond unit tests — schema validation, integration verification, and golden regression.  
**Rule:** A change is not “done” until the applicable pre-flight tier below passes.  
**Charter:** Tests MUST verify auditing behavior; they MUST NOT require the system to generate curriculum content.

---

## 1. Testing tiers (overview)

| Tier | Name | Goal | When required |
|------|------|------|---------------|
| **T0** | Static / contract | Enums & validators match DATA_MAP | Any schema or validator change |
| **T1** | Unit | Pure functions behave | Library / helper changes |
| **T2** | Schema validation | On-disk & model-shaped payloads | Ingest, Layer 0/1, calendar edits |
| **T3** | *(retired)* | Was scrub→place integration | Archived path — use T4 |
| **T4** | Integration (headline) | Layer 0 → 1 → 2 → synthesize | Layer 0/1/2 / synthesize changes |
| **T5** | Golden regression | Metrics within expected envelope | Before claiming golden still green |
| **T6** | Operator pre-flight | Models up, config sane | Before any live corpus run |

---

## 2. T0 — Contract alignment (DATA_MAP ↔ code)

**MUST verify** that closed vocabularies in code match [DATA_MAP.md](DATA_MAP.md) §3:

| Vocabulary | Code symbol | Test action |
|------------|-------------|-------------|
| Artifact roles | `ARTIFACT_ROLES` / `DOC_TYPES` | Assert frozenset equality with documented list |
| Element types | `ELEMENT_TYPES` | Same |
| Confidence | `CONFIDENCE_LEVELS` | Same |
| Day id pattern | `DAY_ID_RE` | Accept `d1`, reject `day1` |
| Unit id pattern | `UNIT_ID_RE` | Accept `engineering`, reject spaces |

**Command:**

```bash
python3 test_schema_validate.py
```

**Pass criteria:** Exit 0; no drift between docs and frozensets (update both together if extending).

---

## 3. T1 — Unit tests (existing suite)

| Test file | Covers | Command |
|-----------|--------|---------|
| `test_doc_extract.py` | Extraction + iter sources + scrub smoke | `python3 test_doc_extract.py` |
| `test_schema_validate.py` | Validators / invalid payloads | `python3 test_schema_validate.py` |
| `test_audit.py` | classify / scrub / clean helpers | `python3 test_audit.py` |
| `test_rollup.py` | Rollup against dallas calendars | `python3 test_rollup.py` |
| `test_loom_pipeline.py` | Router → Path A/B/C → inferred calendars → tiers | `python3 test_loom_pipeline.py` |

**Minimum local gate before PR:**

```bash
python3 test_doc_extract.py
python3 test_schema_validate.py
python3 test_audit.py
python3 test_rollup.py
python3 test_loom_pipeline.py
```

**Pass criteria:** All exit 0.  
**Note:** `test_audit.py` / `test_rollup.py` may require sample project artifacts present under `projects/dallas-career-2026/`.

---

## 4. T2 — Schema validation (pre-flight on artifacts)

Treat validators as **gates**, not optional lint.

### 4.1 What to validate

| Artifact | Validator | Input columns / fields that MUST match DATA_MAP |
|----------|-----------|--------------------------------------------------|
| Ingest plan (model JSON) | `validate_ingest_plan` | `unit_id`, `source_files`, `calendar.days[].id`, `expected` roles |
| `manifest.yaml` | `validate_manifest` | `project.id`/`project_id`, `units.*`, `known_overlaps` pairs |
| `calendar.yaml` | `validate_unit_calendar` | `unit_id`, `days[].id`, `expected[]` ∈ ARTIFACT_ROLES |
| Place payload | `validate_placements` | `doc_id`, `slot`, `role`, `confidence`, `excerpt` |
| Layer 0 decompose | `validate_layer0_elements` | `element_type`, paragraph ints, confidence, flags |
| Layer 1 Phase 1 | `validate_layer1_placements` | `element_id`, nullable match fields |
| Layer 1 Phase 3 | `validate_layer1_fulfillment` | `role`, `fulfilled_by[]`, confidence, reasoning |

### 4.2 Column / field match protocol (Schema Validation)

For any new raw or model input, you MUST:

1. List every required field from DATA_MAP for that artifact.  
2. Confirm presence, type, and enum membership.  
3. Reject unknown roles/types — **do not coerce** silently to `other` in validators (classification helpers may map filenames; validators enforce closed sets on structured output).  
4. Fail fast with `raise_on_errors(errors, context)`.

### 4.3 Ad-hoc check pattern

```bash
python3 - <<'PY'
from pathlib import Path
import yaml, json
from schema_validate import validate_manifest, validate_unit_calendar, raise_on_errors
from audit_lib import project_dir

pid = "dallas-career-2026"
root = project_dir(pid)
man = yaml.safe_load((root / "manifest.yaml").read_text())
raise_on_errors(validate_manifest(man), "manifest")
for uid, entry in man["units"].items():
    cal = yaml.safe_load((root / entry["calendar"]).read_text())
    raise_on_errors(validate_unit_calendar(cal), f"calendar:{uid}")
print("T2 calendars+manifest OK")
PY
```

**Pass criteria:** No `ValueError`; all units in manifest have loadable calendars.

---

## 5. T3 — Retired (legacy doc-level)

Doc-level scrub→place integration checks are **retired** with
[`archive/legacy-unit-audit/`](archive/legacy-unit-audit/). Use **T4** for product
integration. Historical gap/evidence files under `output/<unit>/` are not
regenerated by `./run-audit`.

---

## 6. T4 — Integration verification (headline Layer 0 → 1 → 2)

**Scope:** Element lineage integrity through completeness.

| Check | Method | Pass criteria |
|-------|--------|---------------|
| FK integrity | Every `bucket-ledger.element_id` ∈ `ledger.element_id` | 100% |
| Doc integrity | Every ledger `doc_id` resolvable to a `sources/` file or catalog row | 100% |
| Status vocabulary | `match_status` ∈ DATA_MAP §3.4 | 100% |
| Findings vocabulary | `status` ∈ {FULFILLED, MISSING, DUPLICATE} | 100% |
| Fulfillment FKs | Every id in `fulfilled_by` ∈ ledger | 100% |
| Layer 2 precondition | `layer2/findings.json` exists after a full `./run-audit` | Present when Layer 0/1 ran |
| Synthesize precondition | `layer1/bucket-ledger.json` exists | synthesize does not abort |

**Commands:**

```bash
python3 layer0.py --project dallas-career-2026
python3 layer0.py --project dallas-career-2026 --resolve-wide-spans
python3 layer1.py --project dallas-career-2026
python3 layer2.py --project dallas-career-2026
python3 synthesize.py --project dallas-career-2026 --report all --delivery model
```

**Lightweight FK script (pre-flight):**

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path("projects/dallas-career-2026")
ledger = {e["element_id"] for e in json.loads((root/"layer0/ledger.json").read_text())}
bucket = json.loads((root/"layer1/bucket-ledger.json").read_text())
findings = json.loads((root/"layer1/findings.json").read_text())
missing = [b["element_id"] for b in bucket if b["element_id"] not in ledger]
bad_fb = [f for f in findings for eid in f.get("fulfilled_by", []) if eid not in ledger]
assert not missing, missing[:5]
assert not bad_fb, bad_fb[:5]
print(f"T4 OK ledger={len(ledger)} bucket={len(bucket)} findings={len(findings)}")
PY
```

---

## 7. T5 — Golden regression

**Golden project:** `projects/dallas-career-2026/`  
**Snapshot file:** `layer1/GOLDEN.json` (counts / status histograms)

| Check | Pass criteria |
|-------|---------------|
| `GOLDEN.json` present after Layer 1 | File exists |
| Status histogram stable | No unexplained explosion of MISMATCH/ORPHAN vs prior snapshot |
| Review queue | `REVIEW-QUEUE.md` pending pairs understood (not silently ignored) |
| Globals regenerate | `output/GLOBAL-AUDIT.md` and `DASHBOARD.md` refresh from Layer 1 |

**MUST:** If taxonomy or prompts change, update GOLDEN deliberately — do not “fix” by deleting the snapshot.

**Tooling:** `tools/snapshot_findings.py` may assist; it is **not** part of production orchestration.

---

## 8. T6 — Operator pre-flight (live runs)

Run before any unattended Layer 0/1/2 or ingest on a real corpus:

```bash
# Config present
test -f config.yaml

# Endpoints healthy (derive /health from models.*_url in config.yaml).
# Single-model doctrine: analyst and verifier may share one host — one curl is enough then.
curl -sf "$ANALYST_HEALTH_URL"   # e.g. http://127.0.0.1:8081/health
# Only if verifier_url is a different host:
# curl -sf "$VERIFIER_HEALTH_URL"

# Optional extractors
command -v pdftotext >/dev/null

# Project skeleton
test -d projects/<id>/sources
```

| Check | Failure mode if skipped |
|-------|-------------------------|
| Models down | Empty/invalid JSON → false ORPHAN/UNVERIFIED |
| Missing `sources/` | No-op or crash |
| Stale ledger after source add | Silent under-audit |

Full operator reference: [OPERATORS.md](OPERATORS.md).

---

## 9. Pre-flight matrix by change type

| Change type | Required tiers |
|-------------|----------------|
| Typo in docs only | None (still update Context Layer cross-links if needed) |
| `schema_validate.py` | T0, T1 |
| `doc_extract.py` / scrub helpers | T1 |
| `ingest.py` / calendars | T0, T1, T2, T6 if live |
| `layer0.py` | T0, T1, T2, T4, T5, T6 |
| `layer1.py` | T0, T1, T2, T4, T5, T6 |
| `layer2.py` | T4 (reads L0/L1 artifacts), spot-check findings |
| `synthesize.py` / `render_pdf.py` / `report_delivery.py` | T4 (read path), PDF spot-check |
| Archived `legacy-unit-audit/` | None (do not extend) |
| New project | T2 on manifest/calendars, T6 before full run |
| Context Layer docs only | Consistency review vs code (no py tests required) |

---

## 10. Definition of done

A change meets Definition of Done when:

1. Required tiers in §9 have passed.  
2. Context Layer files listed in [CONTRIBUTING.md](CONTRIBUTING.md) §9 checklist are updated.  
3. No new orphan project directories without README.  
4. No production imports from `tools/`, `experiments/`, or `archive/`.  
5. Auditor charter intact.

---

## 11. Gaps / future test debt (tracked)

| Gap | Desired test | Status |
|-----|--------------|--------|
| Automated FK check in CI | Promote §6 script to `test_layer_lineage.py` | Not yet |
| Layer 0/1 wired into `run_project.py` | Orchestrator integration test | Roadmap |
| OCR path | Extract fixtures for scans | Roadmap |
| Enum-doc drift linter | Parse DATA_MAP tables vs frozensets | Nice-to-have |

When you close a gap, you MUST remove it from this table and add the test file to PROJECT_INDEX §2.7.
