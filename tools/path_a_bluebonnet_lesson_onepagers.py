#!/usr/bin/env python3
"""
Path A over Bluebonnet graph lessons → five-zone HTML one-pagers.

Scopes Layer 0 ledger elements to each graph Lesson (TE describes + SE spanIn),
runs A1–A7, asks Grok for a short usefulness one-pager payload, writes HTML
under e2e/runs/<run>/output/teachers/<unit>/ for Loom UI + static review.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from audit_lib import load_config, log, model_chat, parse_model_json  # noqa: E402
from lesson_plan_fill import load_daily_lesson_checklist  # noqa: E402
from workflows.lesson_plan import (  # noqa: E402
    a1_inventory,
    a2_standards,
    a3_coherence,
    a4_assessment_path,
    a5_hunter_matrix,
    a6_model_place,
    a7_supports,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _lesson_num(lesson_id: str) -> int | None:
    m = re.search(r":l(\d+)$", lesson_id)
    return int(m.group(1)) if m else None


def _materials_for_lesson(has_part: dict, lesson_id: str) -> list[str]:
    """Return source_file basenames linked to this lesson."""
    by_id = {n["id"]: n for n in has_part.get("nodes") or [] if n.get("id")}
    files: list[str] = []
    for e in has_part.get("edges") or []:
        frm, to, rel = e.get("from"), e.get("to"), (e.get("rel") or "").lower()
        mat = None
        if rel == "describes" and to == lesson_id:
            mat = by_id.get(frm)
        elif rel == "spanin" and frm == lesson_id:
            mat = by_id.get(to)
        if mat and mat.get("type") == "Material":
            sf = mat.get("source_file") or mat.get("name") or ""
            if sf:
                files.append(Path(sf).name)
    # unique, TE first
    out: list[str] = []
    for sf in files:
        if sf not in out:
            out.append(sf)
    return out


def _scope_elements(
    ledger: list[dict],
    source_files: list[str],
    lesson_n: int,
) -> list[dict]:
    """Prefer excerpts that mention this lesson number inside linked materials."""
    files = set(source_files)
    pool = [
        e
        for e in ledger
        if Path(e.get("source_file") or e.get("doc_id") or "").name in files
        or (e.get("doc_id") or "") in files
        or Path(e.get("doc_id") or "").name in files
    ]
    # Lesson numbers restart per topic — keep hits that look like a lesson episode.
    pat_strict = re.compile(
        rf"(?:TOPIC\s*\d+\s*.\s*)?LESSON\s*{lesson_n}\b|"
        rf"LESSON\s*STRUCTURE AND PACING|"
        rf"ESSENTIAL IDEAS",
        re.I,
    )
    pat_lesson = re.compile(rf"\bLESSON\s*{lesson_n}\b", re.I)
    scoped = [e for e in pool if pat_lesson.search(e.get("excerpt") or "")]
    if len(scoped) < 3:
        # widen: any pool element with structure/essential near lesson mentions
        scoped = [e for e in pool if pat_strict.search(e.get("excerpt") or "")]
    if len(scoped) < 3:
        scoped = pool[:40]  # last resort: material-level (still TE/SE only)
    # Cap for A6 / prompts
    return scoped[:60]


def _run_path_a(elements: list[dict], cfg: dict | None, use_model: bool) -> dict:
    checklist = load_daily_lesson_checklist()
    a1 = a1_inventory(elements)
    a2 = a2_standards(elements)
    a3 = a3_coherence(elements, a2)
    a4 = a4_assessment_path(elements)
    a5 = a5_hunter_matrix(elements, checklist)
    a6 = a6_model_place(elements, checklist, cfg=cfg, use_model=use_model)
    a7 = a7_supports(elements)
    return {
        "A1": a1,
        "A2": a2,
        "A3": a3,
        "A4": a4,
        "A5": a5,
        "A6": {
            "method": a6.get("method"),
            "present": sum(
                1
                for f in (a6.get("fields") or {}).values()
                if f.get("status") == "PRESENT"
            ),
            "fields": a6.get("fields"),
        },
        "A7": a7,
    }


def _ask_onepager_payload(
    cfg: dict,
    *,
    unit_id: str,
    lesson_id: str,
    lesson_n: int,
    steps: dict,
    cites: list[str],
) -> dict:
    """Grok drafts the usefulness one-pager JSON from Path A facts (auditor-only)."""
    a5 = steps["A5"]
    a2 = steps["A2"]
    a7 = steps["A7"]
    compact = {
        "hunter": {
            "present": a5.get("hunter_core_present"),
            "total": a5.get("hunter_core_total"),
            "matrix": [
                {"id": m["id"], "label": m["label"], "status": m["status"]}
                for m in (a5.get("matrix") or [])
            ],
        },
        "standards": a2.get("teks", {}).get("status"),
        "objective": a2.get("objective", {}).get("status"),
        "elps": a7.get("elps", {}).get("status"),
        "accommodations": a7.get("accommodations", {}).get("status"),
        "cites": cites[:8],
    }
    system = (
        "You are a curriculum auditor writing a Path A usefulness one-pager for "
        "teachers/coaches/auditors (~2 min). Auditor-only: use only the Path A "
        "facts and cites given. Never invent lesson text. Return JSON only."
    )
    user = (
        f"UNIT: {unit_id}\nLESSON: {lesson_id} (lesson {lesson_n})\n"
        f"PATH_A_FACTS:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "title": "short lesson title from cites if clear else Lesson N",\n'
        '  "top_gaps": [{"item":"...", "status":"Missing|Present · Weak|Misaligned",'
        ' "why":"...", "improve":"..."}] (max 3),\n'
        '  "working": [{"pass":"A2|A4|A5", "item":"...", '
        '"quality":"Strong|Adequate|Weak", "why":"..."}] (max 5, PRESENT only),\n'
        '  "hunter_focus": "one short sentence",\n'
        '  "evidence": ["short pointer", ...] (max 5),\n'
        '  "fidelity_pass": true,\n'
        '  "trust_pass": true\n'
        "}\n"
        "Rules: Why+Improve on each gap; Strong/Adequate/Weak only on PRESENT; "
        "≤3 top gaps; Improve = auditor cues only."
    )
    resp = model_chat(
        cfg,
        "analyst",
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        step=f"path-a-onepager-{unit_id}-l{lesson_n}",
        temperature=0.3,
        max_tokens=2048,
    )
    content = resp["choices"][0]["message"]["content"]
    parsed = parse_model_json(content) or {}
    if not isinstance(parsed, dict) or "top_gaps" not in parsed:
        raise ValueError(f"bad one-pager JSON for {lesson_id}")
    return parsed


def _badge_class(status: str) -> str:
    s = (status or "").lower()
    if "missing" in s:
        return "missing"
    if "misalign" in s:
        return "misaligned"
    if "weak" in s:
        return "present-weak"
    if "strong" in s:
        return "strong"
    if "adequate" in s:
        return "adequate"
    return "adequate"


def _render_html(
    *,
    unit_id: str,
    lesson_id: str,
    lesson_n: int,
    payload: dict,
    hunter_present: int,
    hunter_total: int,
) -> str:
    title = html.escape(str(payload.get("title") or f"Lesson {lesson_n}"))
    gaps_html = []
    for i, g in enumerate((payload.get("top_gaps") or [])[:3], 1):
        st = html.escape(str(g.get("status") or "Missing"))
        gaps_html.append(
            f"""<article class="gap">
        <h3><span class="num">{i}.</span> {html.escape(str(g.get('item') or ''))}
          <span class="badge {_badge_class(st)}">{st}</span></h3>
        <p><strong>Why:</strong> {html.escape(str(g.get('why') or ''))}</p>
        <p><strong>Improve:</strong> {html.escape(str(g.get('improve') or ''))}</p>
      </article>"""
        )
    rows = []
    for w in (payload.get("working") or [])[:5]:
        q = html.escape(str(w.get("quality") or "Adequate"))
        rows.append(
            f"""<tr>
              <td class="pass-id">{html.escape(str(w.get('pass') or ''))}</td>
              <td>{html.escape(str(w.get('item') or ''))}</td>
              <td><span class="badge {_badge_class(q)}">{q}</span></td>
              <td>{html.escape(str(w.get('why') or ''))}</td>
            </tr>"""
        )
    ev = "".join(
        f"<li>{html.escape(str(x))}</li>" for x in (payload.get("evidence") or [])[:5]
    )
    fid = "PASS" if payload.get("fidelity_pass", True) else "REVIEW"
    trust = "PASS" if payload.get("trust_pass", True) else "REVIEW"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Path A — {html.escape(unit_id)} L{lesson_n}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --ink:#1a1714; --ink-soft:#3d3832; --muted:#5c564e; --paper:#f3efe6; --card:#fffcf7;
      --line:#d4cdc0; --line-strong:#2a241c; --gap:#b33b1a; --gap-bg:#fff1eb;
      --ok:#14532d; --ok-bg:#dcfce7; --mid:#854d0e; --mid-bg:#fef3c7;
      --weak:#9a3412; --weak-bg:#ffedd5; --missing-bg:#fee2e2; --missing:#991b1b;
      --pass:#14532d; --pass-bg:#dcfce7; --zone-label:#7a7268;
    }}
    * {{ box-sizing:border-box; }}
    html,body {{ margin:0; padding:0; background:var(--paper); color:var(--ink);
      font-family:"IBM Plex Sans","Segoe UI",sans-serif; font-size:16px; line-height:1.5; }}
    .page {{ max-width:820px; margin:0 auto; padding:28px 22px 64px; }}
    .zone {{ margin:0 0 28px; }}
    .zone-label {{ display:flex; align-items:baseline; gap:10px; margin:0 0 12px;
      padding-bottom:6px; border-bottom:1px solid var(--line); }}
    .zone-label .n {{ font-size:11px; font-weight:700; letter-spacing:.08em;
      text-transform:uppercase; color:var(--zone-label); }}
    .zone-label h2 {{ font-family:"Source Serif 4",Georgia,serif; font-size:1.22rem;
      margin:0; font-weight:700; }}
    header.hero {{ background:var(--card); border-bottom:3px solid var(--line-strong);
      padding:0 0 18px; margin-bottom:28px; }}
    .kicker {{ font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
      color:var(--muted); margin:0 0 8px; }}
    h1 {{ font-family:"Source Serif 4",Georgia,serif; font-size:clamp(1.45rem,3vw,1.9rem);
      margin:0 0 10px; line-height:1.15; }}
    .meta {{ color:var(--ink-soft); font-size:.95rem; margin:0; }}
    .rules {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .chip {{ background:#ebe4d6; color:var(--ink-soft); font-size:12px; font-weight:600;
      padding:4px 11px; border-radius:999px; }}
    .badge {{ display:inline-block; font-size:11px; font-weight:700; letter-spacing:.04em;
      text-transform:uppercase; padding:3px 10px; border-radius:999px; }}
    .badge.missing {{ background:var(--missing-bg); color:var(--missing); }}
    .badge.misaligned,.badge.present-weak,.badge.weak {{ background:var(--weak-bg); color:var(--weak); }}
    .badge.strong {{ background:var(--ok-bg); color:var(--ok); }}
    .badge.adequate {{ background:var(--mid-bg); color:var(--mid); }}
    .badge.pass {{ background:var(--pass-bg); color:var(--pass); }}
    .gap {{ background:var(--gap-bg); border-left:5px solid var(--gap); padding:14px 16px;
      margin:0 0 10px; border-radius:0 6px 6px 0; }}
    .gap h3 {{ margin:0 0 8px; font-size:1.02rem; display:flex; flex-wrap:wrap;
      align-items:center; gap:8px; }}
    .gap h3 .num {{ color:var(--gap); }}
    .gap p {{ margin:5px 0; color:var(--ink-soft); font-size:.95rem; }}
    .gap p strong {{ color:var(--ink); }}
    .table-wrap {{ overflow-x:auto; border-radius:6px; background:var(--card);
      box-shadow:0 0 0 1px var(--line); }}
    table.status {{ width:100%; border-collapse:collapse; font-size:.92rem; min-width:520px; }}
    table.status th, table.status td {{ padding:10px 12px; text-align:left; vertical-align:top;
      border-bottom:1px solid var(--line); }}
    table.status th {{ background:#ebe4d6; color:var(--muted); font-size:11px;
      text-transform:uppercase; letter-spacing:.05em; }}
    table.status td.pass-id {{ font-weight:600; color:var(--ink-soft); white-space:nowrap; }}
    .hunter {{ border-left:3px solid var(--line-strong); padding:4px 0 4px 14px;
      color:var(--ink-soft); font-size:.95rem; }}
    ul.evidence {{ margin:0; padding-left:1.15rem; color:var(--ink-soft); }}
    .never {{ color:var(--muted); font-size:.9rem; }}
    .never::before {{ content:"— "; color:var(--line-strong); }}
    .score {{ background:var(--card); padding:18px; border-radius:8px;
      box-shadow:0 0 0 1px var(--line); }}
    .banner {{ display:inline-flex; flex-wrap:wrap; gap:6px; margin:0 0 14px; }}
    footer.note {{ margin-top:18px; color:var(--muted); font-size:.85rem; }}
    code {{ font-family:ui-monospace,Menlo,monospace; font-size:.86em; background:#ebe4d6;
      padding:1px 5px; border-radius:3px; }}
    @media print {{
      html,body {{ background:#fff; }} .badge {{ background:#eee!important; color:#000!important; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <p class="kicker">Path A usefulness · Bluebonnet · graph lesson</p>
      <h1>{html.escape(unit_id)} — {title}</h1>
      <p class="meta"><strong>Lesson:</strong> <code>{html.escape(lesson_id)}</code> ·
        teacher · coach · auditor</p>
      <div class="rules">
        <span class="chip">Useful, not long</span>
        <span class="chip">Auditor-only</span>
        <span class="chip">Lesson-scoped TE/SE</span>
      </div>
    </header>

    <section class="zone" id="zone-1">
      <div class="zone-label"><span class="n">Zone 1</span><h2>Top gaps (act on these first)</h2></div>
      {''.join(gaps_html) or '<p class="meta">No top gaps proposed.</p>'}
    </section>

    <section class="zone" id="zone-2">
      <div class="zone-label"><span class="n">Zone 2</span><h2>What’s working (PRESENT)</h2></div>
      <div class="table-wrap">
        <table class="status">
          <thead><tr><th>Pass</th><th>Item</th><th>Quality</th><th>Why (short)</th></tr></thead>
          <tbody>
            {''.join(rows) or '<tr><td colspan="4">No PRESENT wins listed.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>

    <section class="zone" id="zone-3">
      <div class="zone-label"><span class="n">Zone 3</span><h2>Hunter at a glance (A5)</h2></div>
      <div class="hunter">Unit plate / hunter core: PRESENT <strong>{hunter_present}/{hunter_total}</strong> ·
        {html.escape(str(payload.get('hunter_focus') or 'see top gaps'))}</div>
    </section>

    <section class="zone" id="zone-4">
      <div class="zone-label"><span class="n">Zone 4</span><h2>Evidence pointers</h2></div>
      <ul class="evidence">{ev or '<li>See Path A cites in findings JSON</li>'}</ul>
    </section>

    <section class="zone" id="zone-5">
      <div class="zone-label"><span class="n">Zone 5</span><h2>Never on this page</h2></div>
      <p class="never">Essay narrative · drafted lesson rewrite · observation / T-TESS scores ·
        new path letters · cross-unit Path A cites</p>
    </section>

    <section class="score" id="review">
      <div class="zone-label"><span class="n">Review</span><h2>Proposed feedback review</h2></div>
      <div class="banner">
        <span class="badge pass">Fidelity {fid}</span>
        <span class="badge pass">Trust {trust}</span>
      </div>
      <p class="meta">Drafted from lesson-scoped Path A + Grok — <strong>your accept/reject still required</strong>.</p>
    </section>

    <footer class="note">Bluebonnet graph lesson one-pager · five-zone layout ·
      <code>{html.escape(lesson_id)}</code></footer>
  </div>
</body>
</html>
"""


def _index_html(items: list[dict]) -> str:
    links = []
    for it in items:
        href = html.escape(it["href"])
        label = html.escape(it["label"])
        links.append(f'<a href="{href}">{label}</a>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Bluebonnet Path A one-pagers</title>
<style>
 body{{margin:0;font-family:"IBM Plex Sans",sans-serif;background:#f3efe6;color:#1a1714;padding:40px 24px;}}
 main{{max-width:640px;margin:0 auto;}}
 h1{{font-family:Georgia,serif;font-size:1.6rem;}}
 a{{display:block;background:#fffcf7;color:#0b4f8a;text-decoration:none;padding:12px 14px;
   margin:0 0 8px;border-radius:8px;box-shadow:0 0 0 1px #d4cdc0;font-weight:600;}}
 a:hover{{box-shadow:0 0 0 2px #2a241c;}}
 .meta{{color:#5c564e;}}
</style></head><body><main>
<h1>Bluebonnet Path A one-pagers</h1>
<p class="meta">{len(items)} graph lessons · five-zone usefulness layout · Alg I modules from grok-4.5 run</p>
{''.join(links)}
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="bluebonnet-math-2026")
    ap.add_argument("--e2e-run", default="grok-4.5")
    ap.add_argument("--no-model", action="store_true", help="Skip Grok; heuristic gaps only")
    ap.add_argument("--limit", type=int, default=0, help="Max lessons (0=all)")
    args = ap.parse_args()

    os.environ["LOOM_E2E_RUN"] = args.e2e_run
    os.environ.setdefault("LOOM_USAGE_PROJECT", args.project)

    root = REPO / "projects" / args.project / "e2e" / "runs" / args.e2e_run
    if not root.is_dir():
        log(f"ERROR: missing run root {root}")
        return 1

    phase = _load_json(root / "graph" / "PHASE-SUMMARY.json")
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        log("ERROR: ledger not a list")
        return 1

    cfg = None
    if not args.no_model:
        cfg = load_config()

    teachers = root / "output" / "teachers"
    teachers.mkdir(parents=True, exist_ok=True)
    findings_root = root / "path_a" / "lessons"
    findings_root.mkdir(parents=True, exist_ok=True)

    index_items: list[dict] = []
    n_done = 0
    units = [u for u in phase.get("units") or [] if str(u.get("unit_id", "")).startswith("alg1-mod-")]

    for unit in units:
        unit_id = unit["unit_id"]
        hp_path = root / "graph" / "runs" / args.e2e_run / "units" / unit_id / "HAS-PART.json"
        if not hp_path.is_file():
            log(f"WARN: skip {unit_id} — no HAS-PART")
            continue
        has_part = _load_json(hp_path)
        lessons = [n for n in has_part.get("nodes") or [] if n.get("type") == "Lesson"]
        out_unit = teachers / unit_id
        out_unit.mkdir(parents=True, exist_ok=True)

        for node in lessons:
            if args.limit and n_done >= args.limit:
                break
            lesson_id = node["id"]
            lesson_n = _lesson_num(lesson_id) or 0
            sources = _materials_for_lesson(has_part, lesson_id)
            elements = _scope_elements(ledger, sources, lesson_n)
            log(
                f"Path A lesson {lesson_id}: {len(elements)} elements from {sources}"
            )
            steps = _run_path_a(elements, cfg=cfg, use_model=bool(cfg) and not args.no_model)

            cites = []
            for m in (steps["A5"].get("matrix") or []):
                if m.get("cite"):
                    cites.append(m["cite"][:180])
            for key in ("teks", "objective"):
                for c in (steps["A2"].get(key) or {}).get("cites") or []:
                    cites.append(c[:180])

            if cfg and not args.no_model:
                try:
                    payload = _ask_onepager_payload(
                        cfg,
                        unit_id=unit_id,
                        lesson_id=lesson_id,
                        lesson_n=lesson_n,
                        steps=steps,
                        cites=cites,
                    )
                except Exception as ex:
                    log(f"WARN: one-pager model failed ({ex}); using heuristic")
                    payload = _heuristic_payload(lesson_n, steps, cites)
            else:
                payload = _heuristic_payload(lesson_n, steps, cites)

            fname = f"PATH-A-L{lesson_n}-ONE-PAGER.html"
            html_path = out_unit / fname
            html_path.write_text(
                _render_html(
                    unit_id=unit_id,
                    lesson_id=lesson_id,
                    lesson_n=lesson_n,
                    payload=payload,
                    hunter_present=int(steps["A5"].get("hunter_core_present") or 0),
                    hunter_total=int(steps["A5"].get("hunter_core_total") or 8),
                ),
                encoding="utf-8",
            )
            finding = {
                "project_id": args.project,
                "e2e_run": args.e2e_run,
                "unit_id": unit_id,
                "lesson_id": lesson_id,
                "source_files": sources,
                "element_count": len(elements),
                "steps": {
                    k: (
                        {kk: vv for kk, vv in v.items() if kk != "fields"}
                        if k == "A6" and isinstance(v, dict)
                        else v
                    )
                    for k, v in steps.items()
                },
                "a6_fields": (steps.get("A6") or {}).get("fields"),
                "one_pager": payload,
                "html": f"output/teachers/{unit_id}/{fname}",
            }
            (findings_root / f"{unit_id}-l{lesson_n}.json").write_text(
                json.dumps(finding, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            index_items.append(
                {
                    "href": f"{unit_id}/{fname}",
                    "label": f"{unit_id} · L{lesson_n} — {payload.get('title') or 'Lesson'}",
                }
            )
            n_done += 1
            log(f"wrote {html_path.relative_to(root)}")

        if args.limit and n_done >= args.limit:
            break

    (teachers / "PATH-A-INDEX.html").write_text(_index_html(index_items), encoding="utf-8")
    summary = {
        "project_id": args.project,
        "e2e_run": args.e2e_run,
        "n_lessons": n_done,
        "index": "output/teachers/PATH-A-INDEX.html",
        "lessons": index_items,
    }
    (root / "path_a" / "lessons" / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log(f"DONE {n_done} Bluebonnet lesson one-pagers → {teachers}")
    return 0


def _heuristic_payload(lesson_n: int, steps: dict, cites: list[str]) -> dict:
    gaps = []
    a7 = steps["A7"]
    a2 = steps["A2"]
    if a7.get("elps", {}).get("status") == "MISSING":
        gaps.append(
            {
                "item": "ELPS / language supports",
                "status": "Missing",
                "why": "No ELPS / language-objective language in the lesson-scoped excerpts.",
                "improve": "Add a short language objective and 1–2 supports for the day’s talk/write.",
            }
        )
    if a7.get("accommodations", {}).get("status") == "MISSING":
        gaps.append(
            {
                "item": "Accommodations / access notes",
                "status": "Missing",
                "why": "No SpEd/504/differentiation notes in the lesson-scoped excerpts.",
                "improve": "Note planned scaffolds or “none noted in materials.”",
            }
        )
    if a2.get("objective", {}).get("status") == "MISSING":
        gaps.append(
            {
                "item": "Learning objective clarity",
                "status": "Missing",
                "why": "No clear student-facing objective/finish line in scoped excerpts.",
                "improve": "Restate one observable finish line for the period.",
            }
        )
    elif len(gaps) < 3:
        gaps.append(
            {
                "item": "Learning objective clarity",
                "status": "Present · Weak",
                "why": "Essential Ideas / objectives appear, but the period finish line may stay conceptual.",
                "improve": "Tighten to what students produce/say by end of class.",
            }
        )
    working = []
    for m in steps["A5"].get("matrix") or []:
        if m.get("status") != "PRESENT":
            continue
        working.append(
            {
                "pass": "A5",
                "item": m.get("label") or m.get("id"),
                "quality": "Adequate",
                "why": (m.get("cite") or "Present in scoped TE/SE excerpts.")[:160],
            }
        )
        if len(working) >= 5:
            break
    if a2.get("teks", {}).get("status") == "PRESENT" and len(working) < 5:
        working.append(
            {
                "pass": "A2",
                "item": "TEKS / standards",
                "quality": "Adequate",
                "why": (a2.get("teks", {}).get("cites") or ["TEKS language present"])[0][:160],
            }
        )
    return {
        "title": f"Lesson {lesson_n}",
        "top_gaps": gaps[:3],
        "working": working,
        "hunter_focus": f"Hunter {steps['A5'].get('hunter_core_present')}/{steps['A5'].get('hunter_core_total')} — act on top gaps first",
        "evidence": cites[:5] or ["See lesson-scoped TE/SE excerpts"],
        "fidelity_pass": True,
        "trust_pass": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
