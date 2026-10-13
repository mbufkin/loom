#!/usr/bin/env python3
"""Loom graph phase: provisional → narrow-steps review → code rebuild.

Opt-in from ``run_project.py --with-graph``. Inserts after Layer 0-B, before
route. Writes under the E2E workspace
``…/e2e/runs/<e2e_id>/graph/runs/<run_id>/units/<unit_id>/``
(see graph_run_lib.py + tools/e2e_run_lib.py).

Educational note (Bet 3): the model answers per document (role / lessons /
assessment). Code owns ``merge_narrow_step_findings`` + ``rebuild_multi``.
Do not one-shot a full HAS-PART JSON from the model.

Backends:
  local  — audit_lib.model_chat (config.yaml analyst)
  cursor — Cursor SDK Agent.prompt (e.g. Grok) via tools/run_graph_cursor.mjs

See docs/GRAPH-PHASE.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from audit_lib import (
    BASE_DIR,
    batch_by_chars,
    check_coverage,
    covered_chars,
    load_config,
    log,
    model_chat,
    parse_model_json,
    project_dir,
    prompt_budget_chars,
    record_coverage,
    reset_coverage,
)
from graph_assemble import (
    load_unit_slice,
    merge_narrow_step_findings,
    rebuild_multi,
)
from graph_inventory import (
    build_provisional,
    gate_a,
    lesson_ids_in,
    materials_needing_queue,
    write_raw_decisions,
)
from graph_run_lib import (
    graph_run_dir,
    graph_unit_dir,
    resolve_run_id,
    set_active_graph_run,
    write_run_meta,
)

ROLES = {
    "teacher_edition",
    "learn_student",
    "practice_student",
    "succeed_student",
    "other",
}

_RAW_DIR: Path | None = None
# Every prompt chat_json sends, so run_unit can prove each step saw all of a
# document's evidence (the "sorting" full-text check).
_SENT: list[str] = []


def extract_content(response: dict) -> str:
    return response["choices"][0]["message"]["content"]


def _safe_step_name(step: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", step)[:120]


def save_raw_model_message(step: str, response: dict) -> Path | None:
    """Persist full model message (incl. reasoning_content when present)."""
    if _RAW_DIR is None:
        return None
    msg = ((response.get("choices") or [{}])[0] or {}).get("message") or {}
    artifact = {
        "step": step,
        "model": response.get("model"),
        "usage": response.get("usage"),
        "message": {
            "role": msg.get("role"),
            "content": msg.get("content"),
            "reasoning_content": msg.get("reasoning_content"),
            "extra_keys": sorted(
                k for k in msg.keys() if k not in {"role", "content", "reasoning_content"}
            ),
        },
    }
    for k in artifact["message"]["extra_keys"]:
        artifact["message"][k] = msg.get(k)
    path = _RAW_DIR / f"raw-{_safe_step_name(step)}.json"
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return path


# Re-asks after the first answer when a reply's JSON will not parse. One stray
# unescaped quote in one document's role reply used to stop a 7-unit audit.
JSON_RETRIES = 2


def chat_json(cfg: dict, step: str, prompt: str, *, max_tokens: int = 16384) -> dict:
    # Structured HAS-PART / connect JSON: turn thinking off for Nemotron 3.5
    # Lightning (and similar). Best practice: reasoning tokens must not exhaust
    # max_tokens and leave message.content empty — parse_model_json then fails.
    #
    # A bad reply is re-asked with the full original prompt, the reply and the
    # exact parse error, so the model repairs its own answer over the same
    # evidence. Still bad after JSON_RETRIES re-asks -> raise, as before.
    _SENT.append(prompt)
    messages = [{"role": "user", "content": prompt}]
    for attempt in range(JSON_RETRIES + 1):
        name = step if attempt == 0 else f"{step}-retry{attempt}"
        resp = model_chat(
            cfg,
            "analyst",
            messages,
            name,
            temperature=0.1,
            max_tokens=max_tokens,
            enable_thinking=False,
        )
        save_raw_model_message(name, resp)
        content = extract_content(resp)
        try:
            return parse_model_json(content, context=step)
        except ValueError as exc:
            if attempt == JSON_RETRIES:
                raise ValueError(f"{exc} (still invalid after {JSON_RETRIES} re-asks)") from exc
            log(f"graph: {step}: reply was not valid JSON ({exc}); asking again")
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"That reply is not valid JSON: {exc}. Send the same answer again as "
                        "one valid JSON object only. Escape any double quotes inside "
                        "strings and put no text outside the object."
                    ),
                },
            ]
    raise AssertionError("unreachable")


def resolve_source_path(sources_root: Path, basename: str) -> Path | None:
    """Find basename under sources_root (direct or one-level nested)."""
    direct = sources_root / basename
    if direct.is_file() or direct.is_symlink():
        return direct
    if not sources_root.is_dir():
        return None
    for child in sources_root.iterdir():
        if child.is_dir():
            cand = child / basename
            if cand.is_file() or cand.is_symlink():
                return cand
        elif child.name == basename:
            return child
    # Recursive fallback for deeper trees
    for p in sources_root.rglob(basename):
        if p.is_file() or p.is_symlink():
            return p
    return None


def unit_documents_on_disk(sources_root: Path, documents: list[str]) -> tuple[list[str], list[str]]:
    """Return (present, missing) basenames for Gate A / fail-closed checks."""
    present, missing = [], []
    for name in documents:
        if resolve_source_path(sources_root, name) is not None:
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def load_ledger_evidence(ledger_path: Path, documents: list[str]) -> dict[str, list[dict]]:
    rows = json.loads(ledger_path.read_text(encoding="utf-8"))
    by: dict[str, list[dict]] = {s: [] for s in documents}
    for e in rows:
        sf = e.get("source_file")
        if sf not in by:
            continue
        by[sf].append(
            {
                "element_id": e.get("element_id"),
                "element_type": e.get("element_type"),
                "excerpt": e.get("excerpt") or "",
                "excerpt_start_paragraph": e.get("excerpt_start_paragraph"),
                "excerpt_end_paragraph": e.get("excerpt_end_paragraph"),
            }
        )
    return by


def stub_steps_no_evidence(source_file: str) -> tuple[dict, dict, dict]:
    """Role/lessons/assess stubs when Layer 0 left no rows for a doc.

    Best practice: keep the Material inventoriable (Gate A) without inventing
    lesson coverage. Soft-queue picks these up for a later re-review.
    """
    note = "soft-skip: no ledger evidence"
    role = {
        "source_file": source_file,
        "role": "other",
        "citation_element_id": None,
        "excerpt_head": "",
        "notes": note,
    }
    lessons = {
        "source_file": source_file,
        "covers_lesson_numbers": [],
        "citations": [],
        "notes": note,
    }
    assess = {
        "source_file": source_file,
        "is_assessment_bearing": False,
        "assessment_lesson_numbers": [],
        "assessment_name": None,
        "citations": [],
        "notes": note,
    }
    return role, lessons, assess


def write_stub_step_files(raw_dir: Path, source_files: list[str]) -> None:
    """Write 01/02/03 JSON stubs so assemble-from-steps still sees every source."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for sf in source_files:
        role, lessons, assess = stub_steps_no_evidence(sf)
        stem = Path(sf).stem
        (raw_dir / f"01-role-{stem}.json").write_text(
            json.dumps(role, indent=2) + "\n", encoding="utf-8"
        )
        (raw_dir / f"02-lessons-{stem}.json").write_text(
            json.dumps(lessons, indent=2) + "\n", encoding="utf-8"
        )
        (raw_dir / f"03-assess-{stem}.json").write_text(
            json.dumps(assess, indent=2) + "\n", encoding="utf-8"
        )


def pack_evidence_for_agent(elements: list[dict]) -> dict:
    """Ledger rows for Cursor agents: every element (Bet 1: never truncate).

    The pack is a file the agent reads, not a prompt, so there is no reason to
    drop the middle of a long document as this once did (head 80 + tail 20).
    """
    return {
        "n_elements_included": len(elements),
        "truncation_note": None,
        "elements": elements,
    }


def write_unit_evidence_packs(
    evidence_dir: Path, evidence: dict[str, list[dict]]
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for sf, els in evidence.items():
        pack = pack_evidence_for_agent(els)
        pack["source_file"] = sf
        out = evidence_dir / f"{Path(sf).stem}.json"
        out.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")


def filename_role_prior(source_file: str) -> str:
    """Filename is a prior only — used if the model returns garbage."""
    low = source_file.lower()
    if "teacher_edition" in low:
        return "teacher_edition"
    if "_learn_" in low:
        return "learn_student"
    if "_practice_" in low:
        return "practice_student"
    if "_succeed_" in low:
        return "succeed_student"
    return "other"


# --- Oversized evidence: read in parts, never cut (Bet 1) ------------------
# A document's Layer 0 evidence normally fits one prompt. When its JSON exceeds
# the per-call budget (layer0.CHUNK_SIZE_CHARS, the same 60K characters Layer 0
# reads a document in), the elements are split into batches, each step runs
# once per batch, and the answers are merged. No element is ever dropped.
SPECIFIC_ROLES = ("teacher_edition", "practice_student", "learn_student", "succeed_student")


def evidence_batches(elements: list[dict]) -> list[list[dict]]:
    return batch_by_chars(
        elements, lambda el: len(json.dumps(el, ensure_ascii=False)), prompt_budget_chars()
    ) or [[]]


def _evidence_label(part: int, parts: int) -> str:
    if parts == 1:
        return "FULL_LAYER0_EVIDENCE_JSON"
    return (
        f"LAYER0_EVIDENCE_JSON (part {part} of {parts}: this document's evidence is too "
        f"large for one prompt, so it is read in {parts} parts and every part is read; "
        f"answer from THIS part)"
    )


def _part_suffix(part: int, parts: int) -> str:
    return f"-part{part}of{parts}" if parts > 1 else ""


def merge_role_answers(source_file: str, answers: list[tuple[dict, int]]) -> dict:
    """Role across parts: the specific role with the most evidence behind it
    (elements in the batches that chose it) wins over 'other'; the winning
    batch's citation is kept and every vote recorded."""
    if len(answers) == 1:
        return answers[0][0]
    votes: dict[str, int] = {}
    for data, weight in answers:
        votes[data.get("role") or "other"] = votes.get(data.get("role") or "other", 0) + weight
    specific = {r: w for r, w in votes.items() if r in SPECIFIC_ROLES}
    winner = max(specific, key=specific.get) if specific else "other"
    chosen = next(d for d, _w in answers if (d.get("role") or "other") == winner)
    merged = dict(chosen)
    merged.update(source_file=source_file, role=winner, role_votes=votes, parts=len(answers))
    merged["role_fallback"] = all(d.get("role_fallback") for d, _w in answers)
    return merged


def _union_citations(answers: list[dict]) -> list:
    out, seen = [], set()
    for d in answers:
        for c in d.get("citations") or []:
            key = json.dumps(c, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                out.append(c)
    return out


def merge_lesson_answers(source_file: str, answers: list[dict]) -> dict:
    """Lessons across parts: the union of what each part covers, citations
    deduplicated."""
    if len(answers) == 1:
        return answers[0]
    nums = sorted({n for d in answers for n in d.get("covers_lesson_numbers") or []})
    return {
        "source_file": source_file,
        "covers_lesson_numbers": nums,
        "citations": _union_citations(answers),
        "notes": " | ".join(str(d.get("notes") or "").strip() for d in answers if d.get("notes")),
        "lessons_retried": any(d.get("lessons_retried") for d in answers),
        "parts": len(answers),
    }


def merge_assessment_answers(source_file: str, answers: list[tuple[dict, int]]) -> dict:
    """Assessment across parts. Whole-file belonging is a majority question (an
    exit ticket inside one part of a Learn book must not make the whole book an
    Assessment), so it is decided by the share of elements in parts that said
    yes; the lesson numbers and citations are the union from those parts."""
    if len(answers) == 1:
        return answers[0][0]
    total = sum(w for _d, w in answers) or 1
    yes = [(d, w) for d, w in answers if d.get("is_assessment_bearing")]
    bearing = sum(w for _d, w in yes) * 2 > total
    picked = [d for d, _w in yes] if bearing else []
    return {
        "source_file": source_file,
        "is_assessment_bearing": bearing,
        "assessment_lesson_numbers": sorted(
            {n for d in picked for n in d.get("assessment_lesson_numbers") or []}
        ),
        "assessment_name": next((d.get("assessment_name") for d in picked if d.get("assessment_name")), None),
        "citations": _union_citations(picked),
        "notes": " | ".join(str(d.get("notes") or "").strip() for d, _w in answers if d.get("notes")),
        "assessment_votes": {"yes_elements": sum(w for _d, w in yes), "total_elements": total},
        "parts": len(answers),
    }


def step_role(cfg: dict, source_file: str, elements: list[dict]) -> dict:
    batches = evidence_batches(elements)
    answers = [
        (_step_role_once(cfg, source_file, b, k, len(batches)), len(b))
        for k, b in enumerate(batches, 1)
    ]
    return merge_role_answers(source_file, answers)


def step_lessons(cfg: dict, source_file: str, elements: list[dict], role: str) -> dict:
    batches = evidence_batches(elements)
    answers = [
        _step_lessons_once(cfg, source_file, b, role, k, len(batches))
        for k, b in enumerate(batches, 1)
    ]
    return merge_lesson_answers(source_file, answers)


def step_assessment(cfg: dict, source_file: str, elements: list[dict], role: str) -> dict:
    batches = evidence_batches(elements)
    answers = [
        (_step_assessment_once(cfg, source_file, b, role, k, len(batches)), len(b))
        for k, b in enumerate(batches, 1)
    ]
    return merge_assessment_answers(source_file, answers)


def _step_role_once(
    cfg: dict, source_file: str, elements: list[dict], part: int = 1, parts: int = 1
) -> dict:
    prompt = f"""Classify ONE curriculum source into exactly one role.

SOURCE_FILE: {source_file}
{_evidence_label(part, parts)}:
{json.dumps({"n": len(elements), "elements": elements}, ensure_ascii=False)}

Respond ONLY JSON:
{{"source_file":"{source_file}","role":"teacher_edition|learn_student|practice_student|succeed_student|other","citation_element_id":"...","excerpt_head":"<=120 chars"}}

role must be exactly one of those five strings — not a list, not a pipe-joined enum.
"""
    data = chat_json(cfg, f"role-{Path(source_file).stem[:40]}{_part_suffix(part, parts)}", prompt)
    role = str(data.get("role") or "").strip()
    if role not in ROLES:
        prior = filename_role_prior(source_file)
        log(f"WARN role invalid {role!r} → prior {prior}")
        data["role"] = prior
        data["role_fallback"] = True
    data["source_file"] = source_file
    return data


def lesson_nums_from_text(text: str) -> set[int]:
    if not text:
        return set()
    found: set[int] = set()
    for a, b in re.findall(r"(?i)lessons?\s+(\d+)\s*(?:to|-|–|—)\s*(\d+)", text):
        lo, hi = int(a), int(b)
        if lo > hi:
            lo, hi = hi, lo
        for n in range(lo, min(hi, 40) + 1):
            if 1 <= n <= 40:
                found.add(n)
    for n in re.findall(r"(?i)lessons?\s+(\d+)\b", text):
        v = int(n)
        if 1 <= v <= 40:
            found.add(v)
    for block in re.findall(r"(?i)lessons?\s+((?:\d+\s*,\s*)+\d+)", text):
        for n in re.findall(r"\d+", block):
            v = int(n)
            if 1 <= v <= 40:
                found.add(v)
    return found


def normalize_lesson_list(raw) -> list[int]:
    nums: list[int] = []
    for x in raw or []:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 40:
            nums.append(n)
    return sorted(set(nums))


def citation_implied_lessons(data: dict) -> set[int]:
    chunks: list[str] = []
    for c in data.get("citations") or []:
        if isinstance(c, dict):
            chunks.append(str(c.get("excerpt_head") or ""))
        else:
            chunks.append(str(c))
    chunks.append(str(data.get("notes") or ""))
    implied: set[int] = set()
    for t in chunks:
        implied |= lesson_nums_from_text(t)
    return implied


def _step_lessons_once(
    cfg: dict, source_file: str, elements: list[dict], role: str, part: int = 1, parts: int = 1
) -> dict:
    stem = Path(source_file).stem[:40] + _part_suffix(part, parts)
    base_prompt = f"""List lesson numbers this ONE document covers. Read all excerpts.

SOURCE_FILE: {source_file}
ROLE_ALREADY_CHOSEN: {role}
{_evidence_label(part, parts)}:
{json.dumps({"n": len(elements), "elements": elements}, ensure_ascii=False)}

Respond ONLY JSON:
{{"source_file":"{source_file}","covers_lesson_numbers":[1,2],"citations":[{{"element_id":"...","excerpt_head":"..."}}],"notes":"..."}}

Rules:
- Numbers must appear in the evidence (e.g. "Lesson 4", "Lessons 1 to 15").
- If the doc spans a range like "Lesson 1 to 15", expand to [1,2,...,15].
- If evidence only lists some lessons, list exactly those.
- covers_lesson_numbers MUST match your citations.
- Prefer [] over guessing.
"""
    data = chat_json(cfg, f"lessons-{stem}", base_prompt, max_tokens=16384)
    data["covers_lesson_numbers"] = normalize_lesson_list(data.get("covers_lesson_numbers"))
    data["source_file"] = source_file

    implied = citation_implied_lessons(data)
    listed = set(data["covers_lesson_numbers"])
    missing = sorted(implied - listed)
    if missing:
        previous = dict(data)
        log(
            f"WARN lessons citation/list mismatch {Path(source_file).name}: "
            f"listed={sorted(listed)} implied={sorted(implied)} missing={missing} → retry"
        )
        retry_prompt = f"""Your previous answer contradicts your own citations.

SOURCE_FILE: {source_file}
ROLE_ALREADY_CHOSEN: {role}
PREVIOUS_JSON:
{json.dumps(data, ensure_ascii=False)}

Contradiction: citations/notes imply {sorted(implied)}, but covers_lesson_numbers
was {sorted(listed)}. Missing: {missing}.

{_evidence_label(part, parts)}:
{json.dumps({"n": len(elements), "elements": elements}, ensure_ascii=False)}

Respond ONLY JSON:
{{"source_file":"{source_file}","covers_lesson_numbers":[1,2],"citations":[{{"element_id":"...","excerpt_head":"..."}}],"notes":"..."}}
"""
        data = chat_json(cfg, f"lessons-retry-{stem}", retry_prompt, max_tokens=16384)
        data["covers_lesson_numbers"] = normalize_lesson_list(
            data.get("covers_lesson_numbers")
        )
        data["source_file"] = source_file
        data["lessons_retried"] = True
        data["previous_answer"] = previous
    return data


def _step_assessment_once(
    cfg: dict, source_file: str, elements: list[dict], role: str, part: int = 1, parts: int = 1
) -> dict:
    prompt = f"""Decide if this ONE file should become a Lesson-attached Assessment node
in a HAS-PART graph (whole-file belonging), or stay a plain Material.

SOURCE_FILE: {source_file}
ROLE_ALREADY_CHOSEN: {role}
{_evidence_label(part, parts)}:
{json.dumps({"n": len(elements), "elements": elements}, ensure_ascii=False)}

Context: some curricula pack Learn / Practice / Succeed / Teacher Edition as
separate files. Exit tickets *inside* Learn do NOT make the whole Learn file an
Assessment node. A separate Practice book that is primarily practice / checks
often SHOULD be Assessment-bearing.

Respond ONLY JSON:
{{"source_file":"{source_file}","is_assessment_bearing":false,"assessment_lesson_numbers":[],"assessment_name":null,"citations":[],"notes":"..."}}
"""
    data = chat_json(
        cfg, f"assess-{Path(source_file).stem[:40]}{_part_suffix(part, parts)}", prompt, max_tokens=16384
    )
    data["is_assessment_bearing"] = bool(data.get("is_assessment_bearing"))
    nums = []
    for x in data.get("assessment_lesson_numbers") or []:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 40:
            nums.append(n)
    data["assessment_lesson_numbers"] = sorted(set(nums))
    data["source_file"] = source_file
    return data


def list_graphable_units(manifest_path: Path, only_unit: str | None) -> list[str]:
    import yaml

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    units = raw.get("units") or {}
    if not isinstance(units, dict):
        return []
    ids = []
    for uid, entry in units.items():
        if only_unit and uid != only_unit:
            continue
        docs = (entry or {}).get("documents") or (entry or {}).get("source_files") or []
        if docs:
            ids.append(str(uid))
    return ids


def run_unit_cursor(
    *,
    project_id: str,
    root: Path,
    unit_id: str,
    out_dir: Path,
    evidence: dict[str, list[dict]],
    sources: list[str],
    review_sources: list[str],
    skipped_no_evidence: list[str],
    model_id: str,
    force: bool,
) -> dict:
    """Delegate narrow-steps to Cursor SDK (Grok), then assemble into out_dir."""
    if out_dir.exists() and not force and (out_dir / "HAS-PART.json").is_file():
        log(f"graph: skip {unit_id} (exists under run; pass --force to overwrite)")
        return {"unit_id": unit_id, "skipped": True, "out_dir": str(out_dir)}

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / ".raw"
    raw_dir.mkdir(exist_ok=True)
    # Stubs first so assemble sees every manifest doc even if the agent only
    # reviews evidence-bearing sources.
    if skipped_no_evidence:
        write_stub_step_files(raw_dir, skipped_no_evidence)
    evidence_dir = out_dir / "evidence"
    write_unit_evidence_packs(evidence_dir, evidence)

    script = BASE_DIR / "tools" / "run_graph_cursor.mjs"
    sdk_cwd = Path("/tmp/cursor-sdk-graph-test")
    if not (sdk_cwd / "node_modules" / "@cursor" / "sdk").is_dir():
        raise RuntimeError(
            f"Cursor SDK not installed at {sdk_cwd}; "
            "npm install @cursor/sdk there first"
        )
    # Copy latest script into sdk cwd so imports resolve.
    dest = sdk_cwd / "run_graph_cursor.mjs"
    dest.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")

    cmd = [
        "node",
        str(dest),
        "--project",
        project_id,
        "--unit",
        unit_id,
        "--out-dir",
        str(out_dir),
        "--steps-dir",
        str(raw_dir),
        "--evidence-dir",
        str(evidence_dir),
        "--model",
        model_id,
        "--repo",
        str(BASE_DIR),
    ]
    if force:
        cmd.append("--force")
    log(f"graph cursor: {unit_id} → {model_id}")
    env = os.environ.copy()
    env["LOOM_USAGE_PROJECT"] = project_id
    proc = subprocess.run(
        cmd,
        cwd=str(sdk_cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout[-4000:], end="")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "cursor graph unit failed")[-2000:]
        raise RuntimeError(f"cursor backend failed for {unit_id}: {err}")

    summary_path = out_dir / "SUMMARY.json"
    if not summary_path.is_file():
        raise RuntimeError(f"cursor backend produced no SUMMARY.json at {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["backend"] = "cursor"
    summary["model"] = model_id
    summary["n_sources"] = len(sources)
    summary["n_reviewed"] = len(review_sources)
    summary["skipped_no_evidence"] = skipped_no_evidence
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def run_unit(
    cfg: dict,
    *,
    project_id: str,
    root: Path,
    manifest_path: Path,
    unit_id: str,
    force: bool,
    run_id: str,
    backend: str,
    cursor_model: str,
) -> dict:
    global _RAW_DIR

    import yaml

    slice_ = load_unit_slice(manifest_path, unit_id=unit_id)
    sources_root = root / "sources"
    man = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    sd = man.get("sources_dir")
    if sd:
        sources_root = (root / sd).resolve() if not Path(sd).is_absolute() else Path(sd)

    present, missing = unit_documents_on_disk(sources_root, slice_.documents)
    if missing:
        raise RuntimeError(
            f"unit {unit_id}: missing sources on disk: {missing} (under {sources_root})"
        )
    sources = list(slice_.documents)

    ledger_path = root / "layer0" / "ledger.json"
    if not ledger_path.is_file():
        raise RuntimeError(f"missing ledger at {ledger_path} — run Layer 0 first")
    evidence = load_ledger_evidence(ledger_path, sources)
    # Soft-skip: empty evidence is OK (empty PDF / Layer 0 parse miss). Keep the
    # Material on the provisional graph; don't kill the unit. Model only reviews
    # docs that have ledger rows — the rest stay soft-queued until re-reviewed.
    skipped_no_evidence = [sf for sf, es in evidence.items() if not es]
    review_sources = [sf for sf in sources if evidence.get(sf)]
    if skipped_no_evidence:
        log(
            f"graph: soft-skip {len(skipped_no_evidence)} doc(s) with no ledger "
            f"evidence (still inventoriable): {skipped_no_evidence}"
        )
    if not review_sources:
        raise RuntimeError(
            f"unit {unit_id}: every document lacks ledger evidence — nothing to graph; "
            f"re-run Layer 0 or fix sources ({skipped_no_evidence})"
        )

    out_dir = graph_unit_dir(root, run_id, unit_id)
    if out_dir.exists() and not force and (out_dir / "HAS-PART.json").is_file():
        log(f"graph: skip {unit_id} (exists; pass --force to overwrite)")
        return {"unit_id": unit_id, "skipped": True, "out_dir": str(out_dir)}

    if backend == "cursor":
        return run_unit_cursor(
            project_id=project_id,
            root=root,
            unit_id=unit_id,
            out_dir=out_dir,
            evidence={sf: evidence[sf] for sf in review_sources},
            sources=sources,
            review_sources=review_sources,
            skipped_no_evidence=skipped_no_evidence,
            model_id=cursor_model,
            force=force,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / ".raw"
    raw_dir.mkdir(exist_ok=True)
    _RAW_DIR = raw_dir

    provisional = build_provisional(project_id, unit_id, sources)
    gate = gate_a(provisional, sources)
    if not gate.ok:
        raise RuntimeError(f"unit {unit_id}: {gate.message}")

    (out_dir / "HAS-PART.provisional.json").write_text(
        json.dumps(provisional, indent=2) + "\n", encoding="utf-8"
    )

    roles: dict[str, dict] = {}
    lessons: dict[str, dict] = {}
    assesses: dict[str, dict] = {}
    models = cfg.get("models") or {}
    model_label = str(models.get("analyst_model") or "narrow-steps")

    for sf in skipped_no_evidence:
        roles[sf], lessons[sf], assesses[sf] = stub_steps_no_evidence(sf)
        write_stub_step_files(raw_dir, [sf])
        log(f"graph STEP stub (no evidence) ← {Path(sf).name}")

    for sf in review_sources:
        els = evidence[sf]
        pieces = [json.dumps(el, ensure_ascii=False) for el in els]
        step_prompts: list[list[str]] = []
        log(f"graph STEP role ← {Path(sf).name}")
        mark = len(_SENT)
        roles[sf] = step_role(cfg, sf, els)
        step_prompts.append(_SENT[mark:])
        (raw_dir / f"01-role-{Path(sf).stem}.json").write_text(
            json.dumps(roles[sf], indent=2) + "\n", encoding="utf-8"
        )

        log(f"graph STEP lessons ← {Path(sf).name}")
        mark = len(_SENT)
        lessons[sf] = step_lessons(cfg, sf, els, roles[sf]["role"])
        step_prompts.append(_SENT[mark:])
        (raw_dir / f"02-lessons-{Path(sf).stem}.json").write_text(
            json.dumps(lessons[sf], indent=2) + "\n", encoding="utf-8"
        )

        log(f"graph STEP assessment ← {Path(sf).name}")
        mark = len(_SENT)
        assesses[sf] = step_assessment(cfg, sf, els, roles[sf]["role"])
        step_prompts.append(_SENT[mark:])
        # Each step on its own must have seen every element: the weakest step
        # is what the document's coverage is.
        record_coverage(
            project_id, "sorting", Path(sf).name,
            available=sum(len(x) for x in pieces),
            sent=min(covered_chars(pieces, sp) for sp in step_prompts),
            parts=len(evidence_batches(els)),
        )
        (raw_dir / f"03-assess-{Path(sf).stem}.json").write_text(
            json.dumps(assesses[sf], indent=2) + "\n", encoding="utf-8"
        )

    findings = merge_narrow_step_findings(
        project_id,
        unit_id,
        sources,
        roles,
        lessons,
        assesses,
        spine_policy=slice_.spine_policy,
        model_label=model_label,
    )
    (out_dir / "review-findings.json").write_text(
        json.dumps(findings, indent=2) + "\n", encoding="utf-8"
    )

    final = rebuild_multi(provisional, findings)
    final["model"] = model_label
    final["method"] = "graph-phase-v0+narrow-steps+rebuild_multi"
    final["graph_run_id"] = run_id
    (out_dir / "HAS-PART.json").write_text(
        json.dumps(final, indent=2) + "\n", encoding="utf-8"
    )

    queue = materials_needing_queue(provisional)
    write_raw_decisions(
        raw_dir,
        sources,
        provisional,
        final,
        review_queue=queue,
        model=str(model_label or MODEL_LABEL),
        prompt_ref="graph_phase.py",
    )

    summary = {
        "project_id": project_id,
        "unit_id": unit_id,
        "graph_run_id": run_id,
        "backend": "local",
        "model": model_label,
        "gate_a": gate.message,
        "n_sources": len(sources),
        "n_reviewed": len(review_sources),
        "skipped_no_evidence": skipped_no_evidence,
        "n_lessons": len(lesson_ids_in(final)),
        "n_assessment_files": sum(
            1 for f in findings["findings"] if f["action"] == "attach_assessment"
        ),
        "spine_policy": findings.get("spine_policy"),
        "out_dir": str(out_dir),
        "step_summary": {
            sf: {
                "role": roles[sf].get("role"),
                "lessons": lessons[sf].get("covers_lesson_numbers"),
                "assessment": assesses[sf].get("is_assessment_bearing"),
            }
            for sf in sources
        },
    }
    (out_dir / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    log(
        f"graph: unit {unit_id} done — lessons={summary['n_lessons']} "
        f"assessment_files={summary['n_assessment_files']} run={run_id}"
    )
    return summary


MODEL_LABEL = "graph-phase"


def run_graph_phase(
    project_id: str,
    *,
    only_unit: str | None = None,
    force: bool = False,
    backend: str = "local",
    graph_run: str | None = None,
    cursor_model: str = "grok-4.5",
) -> int:
    root = project_dir(project_id)
    manifest_path = root / "manifest.yaml"
    if not manifest_path.is_file():
        raise RuntimeError(f"missing manifest at {manifest_path}")

    unit_ids = list_graphable_units(manifest_path, only_unit)
    if not unit_ids:
        raise RuntimeError(
            f"--with-graph: no graphable units in {manifest_path} "
            "(need units.<id>.documents). Fail closed."
        )

    cfg = load_config()
    models = cfg.get("models") or {}
    if backend == "cursor":
        model_label = cursor_model
    else:
        model_label = str(models.get("analyst_model") or "local-model")
    run_id = resolve_run_id(
        explicit=graph_run, backend=backend, model_label=model_label
    )
    write_run_meta(
        root,
        run_id,
        backend=backend,
        model=model_label,
        extra={"project_id": project_id, "n_units_planned": len(unit_ids)},
    )
    set_active_graph_run(root, run_id)
    log(f"graph: run_id={run_id} backend={backend} model={model_label}")
    if backend == "local":
        reset_coverage(project_id, "sorting")

    results = []
    errors: list[str] = []
    for uid in unit_ids:
        try:
            results.append(
                run_unit(
                    cfg,
                    project_id=project_id,
                    root=root,
                    manifest_path=manifest_path,
                    unit_id=uid,
                    force=force,
                    run_id=run_id,
                    backend=backend,
                    cursor_model=cursor_model,
                )
            )
        except Exception as e:
            log(f"ERROR graph unit {uid}: {e}")
            errors.append(f"{uid}: {e}")

    run_dir = graph_run_dir(root, run_id)
    phase = {
        "project_id": project_id,
        "run_id": run_id,
        "backend": backend,
        "model": model_label,
        "units": results,
        "errors": errors,
    }
    (run_dir / "PHASE-SUMMARY.json").write_text(
        json.dumps(phase, indent=2) + "\n", encoding="utf-8"
    )
    set_active_graph_run(root, run_id)  # refresh PHASE-SUMMARY symlink
    if errors:
        raise RuntimeError("graph phase failed: " + "; ".join(errors))
    if backend == "local":
        check_coverage(project_id, "sorting", "sorting")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True, help="projects/<id>/ curriculum id")
    ap.add_argument("--only-unit", help="Single unit slug from manifest")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing artifacts inside this graph run",
    )
    ap.add_argument(
        "--backend",
        choices=("local", "cursor"),
        default="local",
        help="local=model_chat (config.yaml); cursor=Cursor SDK (Grok)",
    )
    ap.add_argument(
        "--graph-run",
        help="Run id under graph/runs/<id>/ (default: slug of model name)",
    )
    ap.add_argument(
        "--cursor-model",
        default="grok-4.5",
        help="Cursor model id when --backend cursor",
    )
    args = ap.parse_args()
    try:
        return run_graph_phase(
            args.project,
            only_unit=args.only_unit,
            force=args.force,
            backend=args.backend,
            graph_run=args.graph_run,
            cursor_model=args.cursor_model,
        )
    except RuntimeError as e:
        log(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
