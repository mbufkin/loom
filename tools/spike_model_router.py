#!/usr/bin/env python3
"""
spike_model_router.py — Can a full-doc (content) Grok pass assign Path A–F?

Compares model lens vs current filename+graph cascade (route-map.json).
Writes JSON report under /tmp/loom-router-spike/ (not committed).

Usage:
  python3 tools/spike_model_router.py
  LOOM_ROUTER_SPIKE_N=20 python3 tools/spike_model_router.py

Best practice: keep spikes offline from product writes; only read ledgers/route-maps.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from route import resolve_workflow, load_graph_routing_hints, _norm_source_key  # noqa: E402

BRIDGE = os.environ.get("LOOM_ROUTER_SPIKE_URL", "http://127.0.0.1:8788/v1/chat/completions")
MODEL = os.environ.get("LOOM_ROUTER_SPIKE_MODEL", "grok-4.5")
OUT_DIR = Path(os.environ.get("LOOM_ROUTER_SPIKE_OUT", "/tmp/loom-router-spike"))
MAX_CHARS = int(os.environ.get("LOOM_ROUTER_SPIKE_CHARS", "12000"))
N = int(os.environ.get("LOOM_ROUTER_SPIKE_N", "18"))

LENSES = """Path letters / lenses (exactly one):
A lesson_plan — one instructional episode / daily lesson plan
B quiz — assessment evidence (quiz, exit ticket, answer key, rubric used to score)
C general — catch-all / coach tools / unclear
D teacher_support — teacher edition, educator guide, facilitation support
E student_practice — student edition, learn/practice/succeed, worksheet
F standards_pacing — scope/sequence, pacing, standards overview, TEKS/ELPS summaries
G syllabus — course syllabus / student-facing course contract"""


def _api_key() -> str:
    key = os.environ.get("CURSOR_API_KEY", "")
    if key:
        return key
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("CURSOR_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def chat_json(prompt: str, *, max_tokens: int = 400) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Loom's document router. Read the document content and "
                        "assign exactly one review lens. Reply with ONLY JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(BRIDGE, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    # extract JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {"raw": text, "error": "no_json"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"raw": text, "error": "bad_json"}


def ledger_text(ledger_path: Path, doc_id: str, *, max_chars: int) -> str:
    led = json.loads(ledger_path.read_text(encoding="utf-8"))
    chunks = []
    for e in led:
        if e.get("doc_id") != doc_id:
            continue
        ex = (e.get("excerpt") or "").strip()
        if ex:
            chunks.append(ex)
        if sum(len(c) for c in chunks) >= max_chars:
            break
    text = "\n\n".join(chunks)
    return text[:max_chars]


def dallas_text(sources: Path, source_file: str, *, max_chars: int) -> str:
    p = sources / source_file
    if not p.is_file():
        hits = list(sources.rglob(source_file))
        p = hits[0] if hits else None
    if not p or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")[:max_chars]


def pick_samples(route_map: dict, *, per_path: dict[str, int]) -> list[dict]:
    by = defaultdict(list)
    for r in route_map.get("routes") or []:
        by[r.get("path") or "?"].append(r)
    out: list[dict] = []
    for letter, n in per_path.items():
        rows = by.get(letter) or []
        # diversify: first, middle, last-ish
        if not rows:
            continue
        idxs = sorted({0, len(rows) // 2, len(rows) - 1})
        chosen = []
        for i in idxs:
            if rows[i] not in chosen:
                chosen.append(rows[i])
        for r in rows:
            if len(chosen) >= n:
                break
            if r not in chosen:
                chosen.append(r)
        out.extend(chosen[:n])
    return out


def classify_one(source_file: str, content: str, filename_prior: str) -> dict:
    prompt = f"""{LENSES}

Filename (PRIOR ONLY — may be wrong): {source_file}
Filename-type prior (PRIOR ONLY): {filename_prior}

Document content (excerpts / extract; may be truncated):
---
{content if content.strip() else "(no content available)"}
---

Return JSON:
{{
  "path": "A"|"B"|"C"|"D"|"E"|"F"|"G",
  "workflow_id": "lesson_plan"|"quiz"|"general"|"teacher_support"|"student_practice"|"standards_pacing"|"syllabus",
  "confidence": "high"|"medium"|"low",
  "reason": "one short sentence from content evidence"
}}
"""
    return chat_json(prompt)


def cascade_for(route_entry: dict, project_id: str, hints: dict) -> dict:
    sf = route_entry.get("source_file") or ""
    hint = hints.get(_norm_source_key(sf))
    wf, path, _, reason = resolve_workflow(
        doc_type=route_entry.get("doc_type") or "other",
        source_file=sf,
        graph_hint=hint,
    )
    return {"path": path, "workflow_id": wf, "reason": reason}


def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = _api_key()
    if not key:
        print("ERROR: CURSOR_API_KEY missing")
        return 1

    # Probe bridge
    try:
        probe = chat_json('Return {"path":"C","workflow_id":"general","confidence":"high","reason":"probe"}')
        print("bridge_ok", probe.get("path"), probe.get("error"))
    except Exception as ex:  # noqa: BLE001
        print("ERROR bridge", type(ex).__name__, ex)
        return 1

    jobs = []

    # Bluebonnet — stratified; emphasize C (ambiguous) + D/E/F
    bb_root = ROOT / "projects/bluebonnet-math-2026/e2e/runs/grok-4.5"
    bb_rm = json.loads((bb_root / "layer0/route-map.json").read_text(encoding="utf-8"))
    os.environ["LOOM_E2E_RUN"] = "grok-4.5"
    bb_hints = load_graph_routing_hints("bluebonnet-math-2026")
    bb_samples = pick_samples(
        bb_rm,
        per_path={"C": 4, "D": 3, "E": 3, "F": 2, "B": 1},
    )
    for r in bb_samples:
        jobs.append(
            {
                "corpus": "bluebonnet",
                "route": r,
                "hints": bb_hints,
                "text_fn": lambda doc_id=r["doc_id"]: ledger_text(
                    bb_root / "layer0/ledger.json", doc_id, max_chars=MAX_CHARS
                ),
            }
        )

    # Dallas — include A + suspicious D
    dal_root = ROOT / "projects/dallas-career-2026"
    dal_rm = json.loads((dal_root / "layer0/route-map.json").read_text(encoding="utf-8"))
    # temporarily clear e2e for dallas live
    os.environ.pop("LOOM_E2E_RUN", None)
    dal_hints = load_graph_routing_hints("dallas-career-2026")
    dal_samples = pick_samples(
        dal_rm,
        per_path={"A": 2, "B": 2, "D": 3, "E": 2, "C": 1},
    )
    for r in dal_samples:
        sf = r.get("source_file") or ""
        jobs.append(
            {
                "corpus": "dallas",
                "route": r,
                "hints": dal_hints,
                "text_fn": lambda sf=sf: dallas_text(
                    dal_root / "sources", sf, max_chars=MAX_CHARS
                ),
            }
        )

    # Cap total
    jobs = jobs[:N]
    print(f"spike jobs={len(jobs)} model={MODEL} max_chars={MAX_CHARS}")

    rows = []
    agree = 0
    for i, job in enumerate(jobs, 1):
        r = job["route"]
        sf = r.get("source_file") or r.get("doc_id")
        content = job["text_fn"]()
        cascade = cascade_for(r, job["corpus"], job["hints"])
        # also record what route-map currently says
        current = {
            "path": r.get("path"),
            "workflow_id": r.get("workflow_id"),
            "reason": r.get("reason"),
            "graph_role": r.get("graph_role"),
        }
        print(f"[{i}/{len(jobs)}] {job['corpus']} {sf[:60]} … chars={len(content)}")
        try:
            model = classify_one(sf, content, r.get("doc_type") or "other")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            model = {"error": f"HTTP {e.code}", "raw": body}
        except Exception as ex:  # noqa: BLE001
            model = {"error": f"{type(ex).__name__}: {ex}"}

        m_path = model.get("path")
        match = m_path == current.get("path")
        if match:
            agree += 1
        row = {
            "corpus": job["corpus"],
            "source_file": sf,
            "doc_id": r.get("doc_id"),
            "content_chars": len(content),
            "current_cascade": current,
            "recomputed_cascade": cascade,
            "model": model,
            "agree_current": match,
        }
        rows.append(row)
        print(
            f"  current={current.get('path')} model={m_path} "
            f"agree={match} conf={model.get('confidence')} "
            f"reason={str(model.get('reason') or model.get('error'))[:80]}"
        )
        time.sleep(0.8)

    summary = {
        "model": MODEL,
        "bridge": BRIDGE,
        "n": len(rows),
        "agree": agree,
        "agree_rate": round(agree / len(rows), 3) if rows else 0,
        "by_corpus": {},
        "disagreements": [],
    }
    for corpus in ("bluebonnet", "dallas"):
        sub = [x for x in rows if x["corpus"] == corpus]
        a = sum(1 for x in sub if x["agree_current"])
        summary["by_corpus"][corpus] = {
            "n": len(sub),
            "agree": a,
            "agree_rate": round(a / len(sub), 3) if sub else 0,
            "current_paths": dict(Counter(x["current_cascade"]["path"] for x in sub)),
            "model_paths": dict(
                Counter((x["model"].get("path") or "?") for x in sub)
            ),
        }
    for x in rows:
        if not x["agree_current"]:
            summary["disagreements"].append(
                {
                    "corpus": x["corpus"],
                    "source_file": x["source_file"],
                    "current": x["current_cascade"]["path"],
                    "model": x["model"].get("path"),
                    "model_reason": x["model"].get("reason"),
                    "current_reason": x["current_cascade"].get("reason"),
                    "graph_role": x["current_cascade"].get("graph_role"),
                }
            )

    report = {"summary": summary, "rows": rows}
    out = OUT_DIR / "model_router_spike.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = OUT_DIR / "model_router_spike.md"
    lines = [
        "# Model router spike (Grok :8788)",
        "",
        f"- n={summary['n']} agree={summary['agree']} ({summary['agree_rate']:.0%})",
        f"- model=`{MODEL}` max_chars={MAX_CHARS}",
        "",
        "## By corpus",
        "",
    ]
    for c, s in summary["by_corpus"].items():
        lines.append(
            f"- **{c}**: {s['agree']}/{s['n']} agree ({s['agree_rate']:.0%}) "
            f"current={s['current_paths']} model={s['model_paths']}"
        )
    lines += ["", "## Disagreements", ""]
    if not summary["disagreements"]:
        lines.append("(none)")
    for d in summary["disagreements"]:
        lines.append(
            f"- `{d['source_file']}`: current **{d['current']}** → model **{d['model']}** "
            f"— {d.get('model_reason')} _(was: {d.get('current_reason')})_"
        )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}")
    print(f"wrote {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
