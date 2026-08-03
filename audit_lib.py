"""Shared helpers for the Crystallize curriculum auditor (Layer 0→1→2 pipeline)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

from doc_extract import extract_with_meta
from doc_extract import iter_source_files as _iter_source_files_recursive
from schema_validate import (
    raise_on_errors,
    validate_manifest,
    validate_unit_calendar,
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOG_DIR = BASE_DIR / "logs"
SLUG_ID_RE = re.compile(r"^[a-z0-9.]+(?:-[a-z0-9.]+)*$")

_logger = logging.getLogger("crystallize.audit")
_logging_ready = False


def load_config() -> dict:
    """Load YAML config. Override path with ``LOOM_CONFIG`` (A/B / NIM queues)."""
    path = Path(os.environ["LOOM_CONFIG"]) if os.environ.get("LOOM_CONFIG") else CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"empty YAML: {path}")
    return data


def load_manifest(path: Path) -> dict:
    """Load manifest.yaml with structural validation."""
    data = load_yaml(path)
    raise_on_errors(validate_manifest(data), f"manifest {path}")
    return data


def load_unit_calendar(path: Path) -> dict:
    """Load units/<id>/calendar.yaml with structural validation."""
    data = load_yaml(path)
    raise_on_errors(validate_unit_calendar(data), f"calendar {path}")
    return data


def _init_logging() -> None:
    global _logging_ready
    if _logging_ready:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("[audit] %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / "audit.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    _logger.handlers.clear()
    _logger.setLevel(logging.INFO)
    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)
    _logger.propagate = False
    _logging_ready = True


def log(msg: str) -> None:
    _init_logging()
    _logger.info(msg)


def validate_slug_id(value: str, label: str) -> str:
    """Reject shell metacharacters in ids passed to subprocess argv."""
    if not value or not SLUG_ID_RE.match(value):
        raise ValueError(
            f"invalid {label} {value!r} — use lowercase letters, digits, and hyphens only"
        )
    return value


def parse_model_json(text: str, *, context: str = "model response") -> dict:
    """Parse JSON from model output: markdown fences, raw JSON, or embedded object."""
    if not text or not str(text).strip():
        raise ValueError(f"{context}: empty model response")

    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    # strict=False: models occasionally emit a literal raw newline/tab inside a
    # quoted string (e.g. while quoting multi-line source text) instead of a
    # properly escaped \n. That is invalid per strict JSON but unambiguous to
    # parse, and json.loads's strict=False flag exists specifically for this.
    # Rejecting it outright is a self-inflicted, deterministic parse failure —
    # retrying does nothing since a low-temperature model reproduces it exactly.
    try:
        data = json.loads(raw, strict=False)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1], strict=False)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            raise ValueError(f"{context}: invalid JSON ({exc})") from exc

    raise ValueError(f"{context}: no JSON object found; starts with {raw[:120]!r}")


def is_unit_report_success(report_text: str) -> bool:
    """True when unit REPORT.md marks a successful audit (not substring 'SUCCESS')."""
    if re.search(r"\*\*Status:\*\*\s*FAILED", report_text, re.IGNORECASE):
        return False
    return bool(re.search(r"\*\*Status:\*\*\s*SUCCESS", report_text, re.IGNORECASE))


def model_chat(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 8192,
    retries: int = 2,
) -> dict:
    """POST to analyst/verifier; retry only transient errors (not 4xx client failures).

    Best practice: every Loom model call goes through here so token usage is
    captured once (see usage_lib). Prefer server `usage` / llama.cpp `timings`;
    estimate only when both are absent.
    """
    from usage_lib import monotonic_ms, record_model_call  # local import: avoid cycles

    key = "analyst" if role == "analyst" else "verifier"
    url = cfg["models"][f"{key}_url"]
    model = cfg["models"][f"{key}_model"]
    timeout = cfg["models"]["timeout_seconds"]
    # Cloud / bridge / NIM: more attempts on 429 worker limits.
    cloudish = any(
        x in str(url)
        for x in (
            "8787",
            "8788",
            "integrate.api.nvidia.com",
            "nvidia.com",
            "api.openai.com",
            "api.x.ai",
        )
    )
    if cloudish:
        retries = max(retries, 6)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Confirmed live (2026-07-07, region10): llama.cpp can hang on repetitive
    # sources without repeat_penalty. NVIDIA NIM / OpenAI / Cursor bridge reject
    # that field (HTTP 400 Unsupported parameter), so only send it to llama.cpp.
    if not cloudish:
        payload["repeat_penalty"] = 1.15
    headers = {}
    # Cursor bridge (:8788) requires Bearer CURSOR_API_KEY when the bridge has a key set.
    if "8788" in str(url):
        key = (
            (cfg.get("models") or {}).get("api_key")
            or os.environ.get("CURSOR_API_KEY")
            or ""
        )
        if key:
            headers["Authorization"] = f"Bearer {key}"
    last_err: Exception | None = None
    t0 = monotonic_ms()
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers or None, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            record_model_call(
                role=role,
                step=step,
                model=str(data.get("model") or model),
                messages=messages,
                resp=data,
                elapsed_ms=monotonic_ms() - t0,
                ok=True,
            )
            return data
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = (e.response.text[:300] if e.response is not None else "") or str(e)
            # 429/503 = rate limit / worker exhaustion — retry with backoff.
            # Other 4xx are client errors and should not be blindly retried.
            if status in (429, 503, 529):
                last_err = e
                if attempt < retries:
                    wait = min(120, 5 * (2**attempt))
                    log(
                        f"WARN: {step} HTTP {status} (rate/capacity) attempt "
                        f"{attempt + 1}; retry in {wait}s"
                    )
                    time.sleep(wait)
                continue
            if 400 <= status < 500:
                record_model_call(
                    role=role,
                    step=step,
                    model=model,
                    messages=messages,
                    resp=None,
                    elapsed_ms=monotonic_ms() - t0,
                    ok=False,
                    error=f"HTTP {status}: {body}",
                )
                raise RuntimeError(
                    f"{step}: HTTP {status} (not retrying): {body}"
                ) from e
            last_err = e
            if attempt < retries:
                wait = 2**attempt
                log(
                    f"WARN: {step} HTTP {status} attempt {attempt + 1}; retry in {wait}s"
                )
                time.sleep(wait)
        except (requests.ConnectionError, requests.Timeout, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                wait = 2**attempt
                log(
                    f"WARN: {step} attempt {attempt + 1} failed ({e}); retry in {wait}s"
                )
                time.sleep(wait)
    record_model_call(
        role=role,
        step=step,
        model=model,
        messages=messages,
        resp=None,
        elapsed_ms=monotonic_ms() - t0,
        ok=False,
        error=str(last_err),
    )
    raise RuntimeError(f"{step}: {last_err}") from last_err


_WS_RE = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs (incl. newlines) to a single space, lowercased.

    Source documents wrap mid-sentence; models quote the same words but join them
    with a single space. Without this, a correct verbatim citation gets flagged
    as UNCITED purely because of a newline the model never saw as meaningful.
    """
    return _WS_RE.sub(" ", text).strip().lower()


def excerpt_cited_in(excerpt: str, content: str, min_len: int = 10) -> bool:
    """Whitespace-normalized substring check: is `excerpt` verbatim (mod whitespace) in `content`?"""
    if not excerpt or not content:
        return False
    norm_excerpt = normalize_ws(excerpt)
    if len(norm_excerpt) < min_len:
        return True  # too short to meaningfully check
    return norm_excerpt in normalize_ws(content)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


def project_dir(project_id: str) -> Path:
    """Resolve the writable project root.

    Best practice: set LOOM_E2E_RUN=<run_id> for full-pipeline A/B so Layer 0 /
    output / graph land under projects/<id>/e2e/runs/<run_id>/ and never clobber
    the golden curriculum tree (see tools/e2e_run_lib.py).
    """
    base = BASE_DIR / "projects" / project_id
    run = (os.environ.get("LOOM_E2E_RUN") or "").strip()
    if run:
        safe = re.sub(r"[^\w.\-]+", "-", run).strip("-._")[:80]
        if not safe:
            raise ValueError("LOOM_E2E_RUN is empty after sanitization")
        return base / "e2e" / "runs" / safe
    return base


def resolve_sources_dir(manifest: dict, root_override: Path | None = None) -> Path:
    sd = manifest.get("sources_dir")
    if sd:
        # New format: sources_dir relative to project root
        # root_override is the project root path
        p = Path(sd)
        if not p.is_absolute():
            p = (root_override or Path()).resolve() / p
        return p
    # Flat format: default to <project>/sources/
    if root_override:
        return root_override / "sources"
    return Path("sources")


def resolve_unit_paths(project_id: str, unit_id: str) -> tuple[Path, dict, dict, Path]:
    """Return (project_root, manifest, unit_entry, output_dir)."""
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    if unit_id not in manifest["units"]:
        raise KeyError(f"Unknown unit '{unit_id}' in project '{project_id}'")
    unit = manifest["units"][unit_id]
    out = root / "output" / unit_id
    return root, manifest, unit, out


SUPPORTED_EXTS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".odt",
    ".txt",
    ".md",
    ".html",
    ".rtf",
    ".doc",
}


def iter_source_files(sources: Path) -> list[Path]:
    """Iterate source directory for supported curriculum files, sorted.

    Delegates to doc_extract.iter_source_files (recursive, via rglob) rather
    than maintaining a second, divergent implementation. This used to be a
    flat, top-level-only `sources.glob(f"*{ext}")` — silently correct for the
    Dallas corpus (flat directory of 110 files) but a real, silent data-loss
    bug the moment a corpus nests files in subfolders: confirmed live
    (2026-07-07) against the region10 corpus, which stores each unit's actual
    content one level down in `unit-N/planning-guides/`. The non-recursive
    version dropped all 12 of those files with no warning — Layer 0 reported
    "5 documents" processed out of 17 real source files. Bet 1 says never
    truncate a document's content; this was the same failure one level up,
    silently truncating the *document set* itself before Layer 0 ever saw it.
    """
    return sorted(_iter_source_files_recursive(sources))


def doc_id_from_filename(name: str) -> str:
    base = os.path.basename(name)
    m = re.match(r"^doc_([a-f0-9]+)_", base)
    if m:
        return m.group(1)
    return base.replace(".txt", "")


# Hand-checked live on the Dallas corpus (docs/BETS.md Bet 12): a document's own
# elements agreeing on ONE alternate unit at least this often is corroborated
# enough to trust as a real MISMATCH signal. Shared by layer1 REPORT.md and
# synthesize/teacher plates so HIGH vs low confidence never diverges.
CONCENTRATION_MIN_COUNT = 3


def is_corroborated(row: dict) -> bool:
    """High-confidence MISMATCH requires document-internal corroboration AND
    (if an independent recheck ran) that the recheck reproduced the finding.

    A MISMATCH the second same-model pass did NOT reproduce (recheck_agreed is
    False) is demoted to low-confidence regardless of corroboration — see
    layer1.recheck_mismatches() and docs/BETS.md Bet 5. recheck_agreed is None
    (recheck errored) or missing (older ledger, pre-recheck) both fall through
    to corroboration alone.
    """
    if row.get("recheck_performed") and row.get("recheck_agreed") is False:
        return False
    return (row.get("mismatch_corroboration") or {}).get(
        "same_target_count", 0
    ) >= CONCENTRATION_MIN_COUNT


DOC_TYPES = frozenset(
    {
        "lesson_plan",
        "lesson_content",
        "exit_ticket",
        "quiz",
        "answer_key",
        "rubric",
        "worksheet",
        "project_work",
        "presentation",
        "game_activity",
        "lab_activity",
        "flex_day",
        "other",
    }
)

VALID_SLOT_ROLES = frozenset(
    {
        "lesson_plan",
        "lesson_content",
        "exit_ticket",
        "quiz",
        "answer_key",
        "rubric",
        "worksheet",
        "project_work",
        "presentation",
        "game_activity",
        "lab_activity",
        "flex_day",
        "other",
    }
)


def classify_doc_type(filename: str) -> str:
    """Infer artifact type from filename — deterministic, no model."""
    n = filename.lower()
    if "answer_key" in n or "answer key" in n:
        return "answer_key"
    if "exit_ticket" in n or "exit ticket" in n:
        return "exit_ticket"
    if "quizizz" in n or "quiz" in n:
        return "quiz"
    if "lesson_plan" in n or "lesson plan" in n:
        return "lesson_plan"
    if "slides" in n or "powerpoint" in n or n.endswith(".pptx") or n.endswith(".ppt"):
        return "lesson_content"
    if re.search(r"_lesson\.(txt|docx?|pdf)$", n) or n.endswith("_lesson.txt"):
        return "lesson_content"
    if "worksheet" in n or n.endswith(".xlsx"):
        return "worksheet"
    if "rubric" in n:
        return "rubric"
    if "bingo" in n or "game" in n or "code card" in n:
        return "game_activity"
    if "presentation" in n or "pitch" in n or "slide show" in n:
        return "presentation"
    if "project" in n or "menu" in n or "flyer" in n or "commercial" in n:
        return "project_work"
    if "lab" in n or "experiment" in n:
        return "lab_activity"
    if "flex" in n or "choice" in n or "catch" in n:
        return "flex_day"
    if "student note" in n or "notes" in n:
        return "project_work"
    return "other"


def dedupe_table_line(line: str) -> str:
    """PDF/table exports often repeat the same cell 3× separated by ' | '."""
    if " | " not in line:
        return line
    parts = [p.strip() for p in line.split(" | ")]
    if not parts:
        return line
    # Keep first segment when all non-empty parts are identical
    non_empty = [p for p in parts if p]
    if non_empty and all(p == non_empty[0] for p in non_empty):
        return non_empty[0]
    # Collapse consecutive duplicates
    out = []
    for p in parts:
        if p and (not out or out[-1] != p):
            out.append(p)
    return " | ".join(out) if len(out) > 1 else (out[0] if out else line)


def clean_document_text(raw: str) -> str:
    lines = [dedupe_table_line(ln.rstrip()) for ln in raw.splitlines()]
    cleaned = []
    prev = None
    for ln in lines:
        stripped = ln.strip()
        if stripped == prev and stripped:
            continue
        cleaned.append(ln)
        prev = stripped
    return "\n".join(cleaned).strip()


def extract_day_hints(text: str) -> list[int]:
    days = {int(m.group(1)) for m in re.finditer(r"\bDay\s*(\d+)\b", text, re.I)}
    return sorted(days)


def extract_unit_length_days(text: str) -> int | None:
    m = re.search(r"Estimated\s+Day\(s\):\s*(\d+)", text, re.I)
    return int(m.group(1)) if m else None


def extract_standards_refs(text: str) -> list[str]:
    refs = set()
    for m in re.finditer(r"(TEKS[^|\n]{0,120})", text):
        refs.add(m.group(1).strip())
    for m in re.finditer(r"(NGSS\s+[A-Z0-9\.\-]+)", text):
        refs.add(m.group(1).strip())
    return sorted(refs)[:20]


def extract_title(text: str, filename: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        if line.lower().startswith("day "):
            continue
        if len(line) > 8:
            return line[:200]
    return os.path.basename(filename).replace(".txt", "").replace("_", " ")


def scrub_document(path: Path) -> dict:
    """Turn one source file into structured evidence. Extracts text from any supported format."""
    meta = extract_with_meta(path)
    if meta.get("extraction_error"):
        return {
            "source_file": meta["source_file"],
            "doc_id": doc_id_from_filename(meta["source_file"]),
            "doc_type": classify_doc_type(meta["source_file"]),
            "source_format": meta.get("source_format"),
            "extraction_method": meta.get("extraction_method"),
            "extraction_error": meta.get("extraction_error"),
            "title": meta["source_file"],
            "char_count_raw": 0,
            "char_count_clean": 0,
            "day_hints": [],
            "unit_length_days_hint": None,
            "standards_refs": [],
            "content_clean": "",
            "excerpt_head": "",
        }

    raw = meta["raw_text"]
    cleaned = clean_document_text(raw)
    fname = path.name
    return {
        "source_file": fname,
        "doc_id": doc_id_from_filename(fname),
        "doc_type": classify_doc_type(fname),
        "source_format": meta.get("source_format"),
        "extraction_method": meta.get("extraction_method"),
        "title": extract_title(cleaned, fname),
        "char_count_raw": len(raw),
        "char_count_clean": len(cleaned),
        "day_hints": extract_day_hints(cleaned),
        "unit_length_days_hint": extract_unit_length_days(cleaned),
        "standards_refs": extract_standards_refs(cleaned),
        "content_clean": cleaned,
        "excerpt_head": cleaned[:500],
    }
