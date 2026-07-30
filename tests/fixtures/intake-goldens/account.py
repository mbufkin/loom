"""Per-stage accountability helpers for intake goldens.

Contract (wayfinder #7): every curriculum candidate labeled through
extract → ingest → L0(doc) → route → L1. Harness (wayfinder #10): real
extract/scrub; mocked organize/L0/L1 via synthetic ledgers; real
`validate_coverage` for ingest assignment.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import yaml

from audit_lib import scrub_document
from doc_extract import iter_source_files
from ingest import validate_coverage

GOLDENS_ROOT = Path(__file__).resolve().parent

STAGE_ORDER = ("extract", "ingest", "l0", "route", "l1")


def _load_generate():
    path = GOLDENS_ROOT / "generate.py"
    spec = importlib.util.spec_from_file_location("intake_goldens_generate", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def discover_packs() -> list[Path]:
    return [p.parent for p in sorted((GOLDENS_ROOT / "packs").glob("*/pack.yaml"))]


def load_pack(pack_dir: Path) -> dict:
    return yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))


def pdftotext_available() -> bool:
    return shutil.which("pdftotext") is not None


def materialize_sources(pack_dir: Path, dest: Path) -> list[str]:
    """Build sources/ tree; return skip reasons from generators."""
    cfg = load_pack(pack_dir)
    formats = list(cfg.get("required_formats") or [])
    return _load_generate().materialize_pack(pack_dir, dest, formats=formats)


def classify_extract(sources: Path) -> dict[str, dict]:
    """Return rel_path → {status, char_count_clean, extraction_error?}."""
    out: dict[str, dict] = {}
    for path in iter_source_files(sources):
        rel = path.relative_to(sources).as_posix()
        ev = scrub_document(path)
        err = ev.get("extraction_error")
        chars = int(ev.get("char_count_clean") or 0)
        if err:
            status = "extract_failed"
        elif chars <= 0:
            status = "extract_empty"
        else:
            status = "extract_ok"
        out[rel] = {
            "status": status,
            "char_count_clean": chars,
            "extraction_error": err,
        }
    return out


def _filter_pdf(paths_or_files: dict | set, *, enabled: bool):
    """Drop .pdf keys when pdftotext is unavailable (host-tool skip policy)."""
    if enabled:
        return paths_or_files
    if isinstance(paths_or_files, set):
        return {p for p in paths_or_files if not str(p).endswith(".pdf")}
    return {k: v for k, v in paths_or_files.items() if not str(k).endswith(".pdf")}


def _load_expected(pack_dir: Path, name: str) -> dict:
    return json.loads((pack_dir / "expected" / name).read_text(encoding="utf-8"))


def assert_extract_accountability(
    pack_dir: Path, sources: Path, extract: dict[str, dict] | None = None
) -> dict[str, dict]:
    """Fail closed if any expected candidate is missing or has the wrong status."""
    expected_cands = _load_expected(pack_dir, "candidates.json")
    expected_extract = _load_expected(pack_dir, "extract.json")
    actual = extract if extract is not None else classify_extract(sources)
    pdf_ok = pdftotext_available()

    for rel, row in actual.items():
        assert row["status"] in {
            "extract_ok",
            "extract_failed",
            "extract_empty",
        }, f"{rel}: unlabeled status {row['status']!r}"

    expected_paths = {c["path"] for c in expected_cands["candidates"]}
    expected_paths = _filter_pdf(expected_paths, enabled=pdf_ok)
    expected_files = _filter_pdf(dict(expected_extract["files"]), enabled=pdf_ok)
    # If PDF tool missing, also drop PDF rows from actual comparison set.
    compare_actual = _filter_pdf(dict(actual), enabled=pdf_ok)

    missing = sorted(expected_paths - set(compare_actual))
    extra = sorted(set(compare_actual) - expected_paths)
    assert not missing, f"candidates missing from extract inventory: {missing}"
    assert not extra, f"unexpected candidates (update expected/): {extra}"

    for rel, want in expected_files.items():
        got = compare_actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: expected extract status {want['status']!r}, got {got!r} "
            f"(err={compare_actual[rel].get('extraction_error')!r})"
        )
    return actual


def build_mock_ingest_plan(pack_dir: Path, extract: dict[str, dict]) -> dict:
    """Assign every extract_ok candidate once (mocked organize output)."""
    cfg = load_pack(pack_dir)
    ref = cfg.get("mock_plan_ref") or "mock_plan.yaml"
    raw = yaml.safe_load((pack_dir / ref).read_text(encoding="utf-8")) or {}
    units = raw.get("units") or [{"unit_id": "UNIT-GOLDEN", "title": cfg["id"]}]
    unit = dict(units[0])
    ok_files = sorted(p for p, row in extract.items() if row["status"] == "extract_ok")
    unit["source_files"] = ok_files
    # Minimal calendar so plan shape stays valid if later stages read it.
    unit.setdefault(
        "calendar",
        {
            "unit_length_days": max(1, min(5, len(ok_files) or 1)),
            "days": [
                {"day": i + 1, "focus": f"golden-day-{i + 1}", "documents": []}
                for i in range(max(1, min(5, len(ok_files) or 1)))
            ],
        },
    )
    return {"units": [unit]}


def synthesize_ingest_coverage(extract: dict[str, dict], plan: dict) -> dict[str, dict]:
    """Label each candidate for S2: assigned | labeled_not_in_manifest."""
    assigned = set()
    for u in plan.get("units") or []:
        assigned.update(u.get("source_files") or [])
    out: dict[str, dict] = {}
    for rel, row in extract.items():
        if row["status"] == "extract_ok":
            out[rel] = {
                "status": "assigned" if rel in assigned else "unassigned",
                "unit_id": (plan.get("units") or [{}])[0].get("unit_id"),
            }
        else:
            out[rel] = {
                "status": "labeled_not_in_manifest",
                "extract_status": row["status"],
            }
    return out


def assert_ingest_accountability(
    pack_dir: Path, extract: dict[str, dict]
) -> dict[str, dict]:
    """Real validate_coverage on extract_ok + mock plan; assert expected sidecar."""
    plan = build_mock_ingest_plan(pack_dir, extract)
    # Mirror ingest usable records (source_file + char_count_clean > 0).
    records = [
        {"source_file": rel, "char_count_clean": row["char_count_clean"]}
        for rel, row in extract.items()
        if row["status"] == "extract_ok"
    ]
    errors = validate_coverage(records, plan)
    assert not errors, f"validate_coverage failed: {errors}"

    actual = synthesize_ingest_coverage(extract, plan)
    expected = _load_expected(pack_dir, "ingest-coverage.json")
    pdf_ok = pdftotext_available()
    expected_files = _filter_pdf(dict(expected["files"]), enabled=pdf_ok)
    compare_actual = _filter_pdf(dict(actual), enabled=pdf_ok)

    assert set(compare_actual) == set(expected_files), (
        f"ingest coverage path mismatch: "
        f"missing={sorted(set(expected_files) - set(compare_actual))} "
        f"extra={sorted(set(compare_actual) - set(expected_files))}"
    )
    for rel, want in expected_files.items():
        got = compare_actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: ingest status expected {want['status']!r}, got {got!r}"
        )
    return actual


def synthesize_l0_docs(extract: dict[str, dict]) -> dict[str, dict]:
    """Mocked Layer 0 doc terminals (no model): ok→decomposed, else extract_skipped."""
    out: dict[str, dict] = {}
    for rel, row in extract.items():
        if row["status"] == "extract_ok":
            out[rel] = {"status": "decomposed", "element_count": 1}
        else:
            out[rel] = {"status": "extract_skipped", "element_count": 0}
    return out


def assert_l0_accountability(pack_dir: Path, extract: dict[str, dict]) -> dict[str, dict]:
    actual = synthesize_l0_docs(extract)
    expected = _load_expected(pack_dir, "l0-docs.json")
    pdf_ok = pdftotext_available()
    expected_files = _filter_pdf(dict(expected["files"]), enabled=pdf_ok)
    compare_actual = _filter_pdf(dict(actual), enabled=pdf_ok)
    assert set(compare_actual) == set(expected_files), (
        f"l0 docs path mismatch: "
        f"missing={sorted(set(expected_files) - set(compare_actual))} "
        f"extra={sorted(set(compare_actual) - set(expected_files))}"
    )
    for rel, want in expected_files.items():
        got = compare_actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: l0 status expected {want['status']!r}, got {got!r}"
        )
        if got == "decomposed":
            assert compare_actual[rel]["element_count"] > 0, f"{rel}: decomposed with 0 elements"
    return actual


def synthesize_route(l0: dict[str, dict]) -> dict[str, dict]:
    """Mock route reconcile: decomposed→routed; skipped→not_in_ledger (labeled)."""
    out: dict[str, dict] = {}
    for rel, row in l0.items():
        if row["status"] == "decomposed":
            out[rel] = {"status": "routed", "doc_id": f"doc_{Path(rel).stem}"}
        else:
            out[rel] = {"status": "not_in_ledger", "reason": row["status"]}
    return out


def assert_route_accountability(pack_dir: Path, l0: dict[str, dict]) -> dict[str, dict]:
    actual = synthesize_route(l0)
    expected = _load_expected(pack_dir, "route.json")
    pdf_ok = pdftotext_available()
    expected_files = _filter_pdf(dict(expected["files"]), enabled=pdf_ok)
    compare_actual = _filter_pdf(dict(actual), enabled=pdf_ok)
    assert set(compare_actual) == set(expected_files), (
        f"route path mismatch: "
        f"missing={sorted(set(expected_files) - set(compare_actual))} "
        f"extra={sorted(set(compare_actual) - set(expected_files))}"
    )
    for rel, want in expected_files.items():
        got = compare_actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: route status expected {want['status']!r}, got {got!r}"
        )
    return actual


def synthesize_l1_placement(route: dict[str, dict]) -> dict[str, dict]:
    """Mock L1: every routed input is placed; nothing unlabeled in quarantine."""
    out: dict[str, dict] = {}
    for rel, row in route.items():
        if row["status"] == "routed":
            out[rel] = {"status": "placed", "quarantine": False}
        else:
            out[rel] = {"status": "not_in_scope", "quarantine": False}
    return out


def assert_l1_accountability(pack_dir: Path, route: dict[str, dict]) -> dict[str, dict]:
    actual = synthesize_l1_placement(route)
    expected = _load_expected(pack_dir, "l1-placement.json")
    pdf_ok = pdftotext_available()
    expected_files = _filter_pdf(dict(expected["files"]), enabled=pdf_ok)
    compare_actual = _filter_pdf(dict(actual), enabled=pdf_ok)
    assert set(compare_actual) == set(expected_files), (
        f"l1 path mismatch: "
        f"missing={sorted(set(expected_files) - set(compare_actual))} "
        f"extra={sorted(set(compare_actual) - set(expected_files))}"
    )
    for rel, want in expected_files.items():
        got = compare_actual[rel]["status"]
        assert got == want["status"], (
            f"{rel}: l1 status expected {want['status']!r}, got {got!r}"
        )
        assert compare_actual[rel].get("quarantine") is False, (
            f"{rel}: unexpected quarantine (unlabeled drop)"
        )
    return actual


def run_pack_accountability(pack_dir: Path, sources: Path) -> None:
    """Run all stages listed in pack.yaml (fail closed at first broken stage)."""
    cfg = load_pack(pack_dir)
    stages = set(cfg.get("stages") or [])
    extract = classify_extract(sources)
    if "extract" in stages:
        assert_extract_accountability(pack_dir, sources, extract=extract)
    if "ingest" in stages:
        assert_ingest_accountability(pack_dir, extract)
    l0 = synthesize_l0_docs(extract)
    if "l0" in stages:
        assert_l0_accountability(pack_dir, extract)
    route = synthesize_route(l0)
    if "route" in stages:
        assert_route_accountability(pack_dir, l0)
    if "l1" in stages:
        assert_l1_accountability(pack_dir, route)
