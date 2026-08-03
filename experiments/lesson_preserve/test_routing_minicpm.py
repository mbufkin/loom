#!/usr/bin/env python3
"""
Local-only LP routing cascade (nothing off-box).

Pass1 — filename/route match + hard non-LP filename skips.
Pass2 — Nano 9B on :8081 (/no_think), tight classify, full doc.
Pass3 — if unsure, escalate to Nano 30B on :8080 (/think).

Start dual servers first:
  bash experiments/lesson_preserve/scripts/start_dual_routing_servers.sh

Use --single-30b only when deliberately scoring a 30B-only fallback.
Use --units all to walk every unit in the project manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from audit_lib import classify_doc_type, doc_id_from_filename, load_manifest, project_dir
from experiments.lesson_preserve.detect import is_lesson_plan_doc
from experiments.lesson_preserve.detect import load_doc_type_priors, load_route_workflow_by_doc

DEFAULT_PASS2_BASE = "http://127.0.0.1:8081/v1"  # Nano 9B (when dual servers up)
DEFAULT_PASS3_BASE = "http://127.0.0.1:8080/v1"  # Nano 30B escalate
# Override with LOOM_PASS2_MODEL / LOOM_PASS3_MODEL env vars for local GGUF paths.
DEFAULT_PASS2_MODEL = os.environ.get(
    "LOOM_PASS2_MODEL", "nvidia_NVIDIA-Nemotron-Nano-9B-v2-Q4_K_M.gguf"
)
DEFAULT_PASS3_MODEL = os.environ.get("LOOM_PASS3_MODEL", "nemotron3-nano-30b.gguf")
# Fallback: if 9B isn't up, both passes hit 30B (single-server mode).
DEFAULT_BASE = DEFAULT_PASS3_BASE
DEFAULT_MODEL = DEFAULT_PASS3_MODEL
MAX_DOC_CHARS = 200_000
LABELS = ("lesson_plan", "quiz", "rubric", "other")

SYSTEM_CORE = """Classify this Texas CTE curriculum document.
Return ONLY one JSON object. label MUST be exactly one of:
lesson_plan, quiz, rubric, other
Example: {"label":"lesson_plan","confidence":0.9}

lesson_plan — ONLY if the document is an instructional plan a teacher would follow across class meeting(s):
  estimated day(s)/timing, TEKS or learning goals, and a teaching sequence (Engage/Explain/Do Now/closure or Day 1/2/3 activities).
  Subject-only filenames (e.g. Financial_Literacy.txt) still count IF the body is that plan.

quiz — quizzes, Quizizz, exit tickets, answer keys, check-for-understanding sheets.

rubric — project/scoring rubrics.

other — use when in doubt. Includes:
  - slide decks / presentation notes (filename has Slides, or body is slide bullets / "click the hands" / raise-hand polls)
  - role-play scripts, resume builders, attire answer keys, scenarios worksheets
  - content guides that only describe a topic (e.g. dress-code reading) without a full instructional plan frame
  - standalone labs without Estimated Day(s) + teaching sequence

Be conservative: if it might be slides or a handout, choose other (confidence <= 0.7).
Only choose lesson_plan with confidence >= 0.9 when the instructional-plan evidence is clear.
"""

ESCALATE_EXTRA = """
A smaller pass already looked at this and was unsure. Decide carefully.
Prefer other unless instructional-plan evidence is clear in the body.
"""

LABEL_RE = re.compile(r"\b(lesson_plan|quiz|rubric|other)\b", re.I)
JSON_RE = re.compile(r"\{[^{}]*\}", re.S)
_SKIP_SECOND_PASS_TYPES = frozenset(
    {"quiz", "exit_ticket", "answer_key", "rubric", "assessment"}
)
_HARD_NON_LP_NAME = re.compile(
    r"(slides?|role[_\s-]*play|resume|attire[_\s-]*answers?|answer[_\s-]*key|"
    r"exit[_\s-]*ticket|quizizz|scenarios?)",
    re.I,
)
_LP_EVIDENCE = re.compile(
    r"(estimated\s*day\(?s?\)?|teks\b|learning\s*(objective|goal)s?|"
    r"day\s*\d+\s*[-–:]\s*(engage|explain|explore|elaborate|evaluate))",
    re.I,
)


def _read_full(path: Path, limit: int = MAX_DOC_CHARS) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit] + "\n\n[TRUNCATED]"
    return text


def _has_lp_evidence(body: str) -> bool:
    return bool(_LP_EVIDENCE.search(body or ""))


def _normalize_label(lab: str) -> str | None:
    s = lab.strip().lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"_+", "_", s)
    if s in LABELS:
        return s
    if "lesson" in s and "plan" in s:
        return "lesson_plan"
    if "quiz" in s or "exit_ticket" in s:
        return "quiz"
    if "rubric" in s:
        return "rubric"
    if s in ("other", "misc", "general", "slides", "script", "lab"):
        return "other"
    return None


def _clamp_conf(raw) -> float | None:
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        return None
    if conf > 1.0:
        conf = conf / 100.0 if conf <= 100 else 1.0
    return max(0.0, min(1.0, conf))


def _parse_label(gen: str) -> tuple[str, float | None]:
    blob = gen.strip()
    blob_stripped = re.sub(r"<think>.*?</think>", " ", blob, flags=re.S | re.I)
    matches = list(JSON_RE.finditer(blob)) or list(JSON_RE.finditer(blob_stripped))
    for m in reversed(matches):
        try:
            obj = json.loads(m.group(0))
            lab = _normalize_label(str(obj.get("label") or ""))
            if lab:
                return lab, _clamp_conf(obj.get("confidence"))
        except json.JSONDecodeError:
            continue
    m = LABEL_RE.search(blob_stripped.replace("-", "_").lower())
    if m:
        return m.group(1).lower(), None
    if "lesson plan" in blob_stripped.lower():
        return "lesson_plan", None
    return "other", None


def _system(*, thinking: bool, escalate: bool = False) -> str:
    prefix = "/think\n" if thinking else "/no_think\n"
    body = SYSTEM_CORE + (ESCALATE_EXTRA if escalate else "")
    return prefix + body


def classify_local(
    *,
    base_url: str,
    model: str,
    filename: str,
    body: str,
    thinking: bool,
    escalate: bool = False,
    timeout: int = 300,
) -> tuple[str, float | None, str]:
    """OpenAI-compatible chat against local llama-server (or any local v1 endpoint)."""
    user = f"Filename: {filename}\n\nDocument:\n{body}\n\nJSON:"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system(thinking=thinking, escalate=escalate)},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2 if thinking else 0.0,
        "top_p": 0.95 if thinking else 1.0,
        "max_tokens": 1024 if thinking else 128,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise SystemExit(f"Local model unreachable at {base_url}: {e}") from e
    # Best practice: even experiment bypasses of model_chat should meter tokens
    # so research comparisons stay apples-to-apples. Failures here must not abort.
    try:
        import sys
        from pathlib import Path

        _root = Path(__file__).resolve().parents[2]
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from usage_lib import record_model_call, set_usage_project

        set_usage_project(os.environ.get("LOOM_USAGE_PROJECT") or "lesson-preserve-minicpm")
        record_model_call(
            role="analyst",
            step="lesson_preserve.minicpm_route",
            model=str(data.get("model") or model),
            messages=payload["messages"],
            resp=data,
            elapsed_ms=0.0,
            ok=True,
        )
    except Exception:
        pass
    msg = data["choices"][0]["message"]
    reasoning = (msg.get("reasoning_content") or "").strip()
    content = (msg.get("content") or "").strip()
    gen = "\n".join(p for p in (reasoning, content) if p)
    lab, conf = _parse_label(gen)
    return lab, conf, gen.strip()[:400]


# Default focus set — matches prior Nano / local-cascade baselines (28 docs).
FOCUS_UNITS = [
    "engineering",
    "financial-literacy",
    "professional-preparedness",
    "family-community",
    "health-science",
]


def collect_sample_docs(project_id: str, unit_ids: list[str] | None) -> list[dict]:
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    routes = load_route_workflow_by_doc(project_id)
    priors = load_doc_type_priors(project_id)
    units = manifest.get("units") or {}
    # Best practice: pass unit_ids=["all"] (or CLI --units all) for a full
    # corpus sweep; otherwise keep the 5-unit focus set for regression gates.
    if unit_ids and len(unit_ids) == 1 and unit_ids[0].lower() == "all":
        selected = list(units.keys())
    else:
        selected = unit_ids or list(FOCUS_UNITS)
    rows: list[dict] = []
    for uid in selected:
        u = units.get(uid)
        if not u:
            continue
        for rel in u.get("documents") or []:
            did = doc_id_from_filename(rel)
            name = Path(rel).name
            src = root / "sources" / name
            fname_type = classify_doc_type(name)
            wf = routes.get(did)
            prior = priors.get(did)
            ok, reasons = is_lesson_plan_doc(
                doc_id=did,
                source_file=name,
                title=name,
                route_workflow=wf,
                doc_type_prior=prior,
            )
            rows.append(
                {
                    "unit_id": uid,
                    "doc_id": did,
                    "filename": name,
                    "path": src,
                    "filename_type": fname_type,
                    "route_workflow": wf,
                    "spike_is_lp": ok,
                    "spike_reasons": reasons,
                    "doc_chars": src.stat().st_size if src.is_file() else 0,
                }
            )
    return rows


def _needs_second_pass(row: dict) -> tuple[bool, str]:
    if row["spike_is_lp"]:
        return False, "pass1_lp"
    if row["route_workflow"] in ("quiz", "rubric"):
        return False, "route_non_lp"
    if row["filename_type"] in _SKIP_SECOND_PASS_TYPES:
        return False, "filename_type_non_lp"
    if _HARD_NON_LP_NAME.search(row["filename"]):
        return False, "hard_non_lp_filename"
    return True, ""


def _is_unsure(
    *,
    label: str | None,
    conf: float | None,
    min_confidence: float,
    blocked_no_evidence: bool,
) -> bool:
    """Escalate when the tight pass cannot settle the call confidently."""
    if blocked_no_evidence:
        return True  # model said LP, evidence gate disagreed
    if conf is None:
        return True
    if label == "lesson_plan" and conf < min_confidence:
        return True
    # Gray-zone non-LP: model is soft — let biggest local model recheck
    if label != "lesson_plan" and 0.40 <= conf < min_confidence:
        return True
    return False


def _decide_promote(label: str | None, conf: float | None, body: str, min_confidence: float):
    conf_ok = (conf is not None) and (conf >= min_confidence)
    evidence_ok = _has_lp_evidence(body)
    if label == "lesson_plan" and conf_ok and not evidence_ok:
        return False, True  # promoted, blocked_no_evidence
    return (label == "lesson_plan" and conf_ok and evidence_ok), False


def run_hybrid(
    rows: list[dict],
    *,
    pass2_base: str,
    pass2_model: str,
    pass3_base: str,
    pass3_model: str,
    min_confidence: float,
    escalate: bool,
) -> list[dict]:
    results: list[dict] = []
    for r in rows:
        pass1_lp = bool(r["spike_is_lp"])
        needs2, skip_reason = _needs_second_pass(r)
        label = conf = raw = None
        label3 = conf3 = raw3 = None
        promoted = False
        body_chars = 0
        blocked_no_evidence = False
        did_escalate = False
        source = f"skip_{skip_reason}" if not needs2 and not pass1_lp else "pass1_match"

        if pass1_lp:
            source = "pass1_match"
            final_lp = True
        elif not needs2:
            final_lp = False
        else:
            body = _read_full(r["path"])
            body_chars = len(body)
            # Pass2 — Nano 9B (or fallback), /no_think
            label, conf, raw = classify_local(
                base_url=pass2_base,
                model=pass2_model,
                filename=r["filename"],
                body=body,
                thinking=False,
            )
            promoted, blocked_no_evidence = _decide_promote(
                label, conf, body, min_confidence
            )
            unsure = _is_unsure(
                label=label,
                conf=conf,
                min_confidence=min_confidence,
                blocked_no_evidence=blocked_no_evidence,
            )

            if escalate and unsure and not promoted:
                did_escalate = True
                # Pass3 — biggest on-machine (30B) with /think
                label3, conf3, raw3 = classify_local(
                    base_url=pass3_base,
                    model=pass3_model,
                    filename=r["filename"],
                    body=body,
                    thinking=True,
                    escalate=True,
                )
                promoted3, blocked3 = _decide_promote(
                    label3, conf3, body, min_confidence
                )
                label, conf, raw = label3, conf3, raw3
                blocked_no_evidence = blocked3
                promoted = promoted3
                source = "pass3_local_think" if promoted else (
                    "pass3_blocked_no_evidence" if blocked3 else "pass3_not_lp"
                )
            else:
                if promoted:
                    source = "pass2_local"
                elif blocked_no_evidence:
                    source = "blocked_no_lp_evidence"
                else:
                    source = "pass2_not_lp"

            final_lp = promoted

        conf_s = f"{conf:.2f}" if conf is not None else ("—" if not needs2 else "?")
        tag = {
            "pass1_match": "P1",
            "pass2_local": "P2+",
            "pass2_not_lp": "P2-",
            "blocked_no_lp_evidence": "BLK",
            "pass3_local_think": "P3+",
            "pass3_not_lp": "P3-",
            "pass3_blocked_no_evidence": "P3B",
        }.get(source, "skip")
        esc = " esc" if did_escalate else ""
        print(
            f"{tag:4} {r['unit_id'][:18]:18} "
            f"final={str(final_lp):5} lab={label or '—':<12} c={conf_s:<4} "
            f"chars={body_chars:<5}{esc} | {r['filename'][:38]}"
        )
        results.append(
            {
                **{k: v for k, v in r.items() if k != "path"},
                "pass1_lp": pass1_lp,
                "second_pass": needs2,
                "skip_reason": skip_reason or None,
                "model_label": label,
                "model_confidence": conf,
                "model_raw": raw,
                "escalated": did_escalate,
                "pass3_label": label3,
                "pass3_confidence": conf3,
                "pass3_raw": raw3,
                "body_chars_sent": body_chars,
                "blocked_no_evidence": blocked_no_evidence,
                "promoted": promoted if needs2 else False,
                "final_lp": final_lp,
                "decision_source": source,
                "pass2_base": pass2_base,
                "pass3_base": pass3_base,
                "pass2_model": pass2_model,
                "pass3_model": pass3_model,
                "min_confidence": min_confidence,
                "prompt_format": "local_9b_30b_cascade",
            }
        )
    return results


def _endpoint_up(base_url: str) -> bool:
    try:
        health = base_url.rstrip("/").removesuffix("/v1") + "/health"
        with urllib.request.urlopen(health, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Local 9B→30B LP routing cascade")
    ap.add_argument("--project", default="dallas-career-2026")
    ap.add_argument(
        "--units",
        default="",
        help="comma-separated unit ids, or 'all' for every unit in the manifest",
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pass2-base", default=DEFAULT_PASS2_BASE)
    ap.add_argument("--pass2-model", default=DEFAULT_PASS2_MODEL)
    ap.add_argument("--pass3-base", default=DEFAULT_PASS3_BASE)
    ap.add_argument("--pass3-model", default=DEFAULT_PASS3_MODEL)
    ap.add_argument(
        "--single-30b",
        action="store_true",
        help="force both passes on :8080 30B (9B not required)",
    )
    ap.add_argument("--min-confidence", type=float, default=0.90)
    ap.add_argument("--no-escalate", action="store_true")
    ap.add_argument(
        "--out",
        default="",
        help="optional output JSON path (default depends on --units)",
    )
    args = ap.parse_args()
    units = [u.strip() for u in args.units.split(",") if u.strip()] or None
    all_units = bool(units and len(units) == 1 and units[0].lower() == "all")
    rows = collect_sample_docs(args.project, units)
    if args.limit:
        rows = rows[: args.limit]

    pass2_base, pass2_model = args.pass2_base, args.pass2_model
    pass3_base, pass3_model = args.pass3_base, args.pass3_model
    if args.single_30b:
        pass2_base, pass2_model = pass3_base, pass3_model
    elif not _endpoint_up(pass2_base):
        # Fail loud: a dual-cascade score must not silently become 30B-only.
        raise SystemExit(
            f"Pass2 {pass2_base} is not up. Start dual servers:\n"
            f"  bash experiments/lesson_preserve/scripts/start_dual_routing_servers.sh\n"
            f"Or pass --single-30b only if you intentionally want 30B-only."
        )

    print(
        f"Local cascade (no cloud)\n"
        f"pass2 → {pass2_base}  ({pass2_model.split('/')[-1]})\n"
        f"pass3 → {pass3_base}  ({pass3_model.split('/')[-1]})\n"
        f"escalate_unsure={not args.no_escalate}  min_confidence={args.min_confidence}  "
        f"docs={len(rows)}\n"
    )
    results = run_hybrid(
        rows,
        pass2_base=pass2_base,
        pass2_model=pass2_model,
        pass3_base=pass3_base,
        pass3_model=pass3_model,
        min_confidence=args.min_confidence,
        escalate=not args.no_escalate,
    )

    p1 = sum(1 for x in results if x["pass1_lp"])
    called = sum(1 for x in results if x["second_pass"])
    esc = sum(1 for x in results if x.get("escalated"))
    promoted = [x for x in results if x.get("promoted")]
    final = sum(1 for x in results if x["final_lp"])
    hard = sum(1 for x in results if (x.get("skip_reason") or "").startswith("hard_"))

    print("\n=== Local cascade summary ===")
    print(f"pass1 LP:            {p1}")
    print(f"hard filename skips: {hard}")
    print(f"pass2 local calls:   {called}")
    print(f"pass3 escalations:   {esc}")
    print(f"promotions:          {len(promoted)}")
    print(f"final LP:            {final}")
    if promoted:
        print("\nPromoted:")
        for x in promoted:
            print(
                f"  + {x['unit_id']}: c={x['model_confidence']} "
                f"via={x['decision_source']}  {x['filename']}"
            )

    default_name = (
        "routing_hybrid_local_9b_30b_cascade_all_units.json"
        if all_units
        else "routing_hybrid_local_9b_30b_cascade.json"
    )
    out = Path(args.out) if args.out else (
        _ROOT / "experiments/lesson_preserve/out" / args.project / default_name
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
