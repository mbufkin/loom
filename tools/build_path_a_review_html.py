#!/usr/bin/env python3
"""Build Docs-style Path A review: original source HTML + anchored feedback sidebar.

Click a comment → scroll/highlight the matching span in the original document.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "projects" / "lab-graph-cte-cattle"
FINDINGS = LAB / "path_a" / "findings.json"
SOURCE = LAB / "sources" / "023-breeds-of-livestock-cattle__view-lesson-plan.html"
OUT = ROOT / "docs" / "PATH-A-CATTLE-LP-REVIEW.html"

# Feedback → first match of these needles in the original Word HTML (Docs-style anchors).
# Prefer distinctive phrases that exist in the source, not the plate rewrite.
ANCHOR_NEEDLES: dict[str, list[str]] = {
    "lesson_title": ["Breeds of Livestock:", "Cattle"],
    "objective": ["Objectives:"],
    "teks": ["Goal:"],  # no TEKS string in source — nearest standards-ish block
    "materials": ["Seat Time:", "Media:"],
    "anticipatory_set": ["Step 1: Bell Ringer:"],
    "objective_purpose": ["Essential Questions:"],
    "input": ["Step 3:", "Dairy Breeds"],
    "modeling": ["Key Concepts"],
    "check_for_understanding": ["Check for Understanding"],
    "guided_practice": ["Dairy Decisions Activity", "Activity"],
    "independent_practice": ["Build a Breed", "Project"],
    "closure": ["Exit Ticket"],
    "elps": ["ELPS"],
    "accommodations": ["Accommodations", "accommodations"],
}


def clean(text: str, limit: int = 220) -> str:
    t = html.unescape(text or "")
    t = t.replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def sanitize_source(raw: str) -> str:
    """Keep original Word HTML look; strip scripts / external deps."""
    s = re.sub(r"<script[\s\S]*?</script>", "", raw, flags=re.I)
    # Drop remote jquery that 404s offline
    s = re.sub(r"<link[^>]*>", "", s, flags=re.I)
    # Extract body if present; else whole file
    m = re.search(r"<body[^>]*>([\s\S]*)</body>", s, flags=re.I)
    body = m.group(1) if m else s
    # Pull style block(s) from head for fidelity
    styles = "".join(re.findall(r"<style[\s\S]*?</style>", s, flags=re.I))
    return styles, body


def inject_anchors(body: str) -> tuple[str, dict[str, bool]]:
    """Wrap first match of each needle in <mark data-anchor=…> for highlight/scroll."""
    placed: dict[str, bool] = {}
    out = body
    for anchor, needles in ANCHOR_NEEDLES.items():
        placed[anchor] = False
        for needle in needles:
            # Case-insensitive search in HTML; wrap a short surrounding text node-ish chunk
            # Match the needle even when split by tags by searching plain then falling back.
            pattern = re.compile(re.escape(needle), re.I)
            m = pattern.search(out)
            if not m:
                continue
            start, end = m.start(), m.end()
            # Expand to nearest enclosing <p ...>…</p> if small enough
            p_start = out.rfind("<p", 0, start)
            p_end = out.find("</p>", end)
            if p_start != -1 and p_end != -1 and (p_end - p_start) < 2500:
                chunk = out[p_start : p_end + 4]
                # Use div (not mark) so we can wrap a full <p> without invalid HTML.
                wrapped = (
                    f'<div class="fb-anchor" data-anchor="{anchor}" id="anchor-{anchor}">'
                    f"{chunk}</div>"
                )
                out = out[:p_start] + wrapped + out[p_end + 4 :]
            else:
                chunk = out[start:end]
                wrapped = (
                    f'<span class="fb-anchor" data-anchor="{anchor}" id="anchor-{anchor}">'
                    f"{chunk}</span>"
                )
                out = out[:start] + wrapped + out[end:]
            placed[anchor] = True
            break
    return out, placed


def build_comments(findings: dict, placed: dict[str, bool]) -> list[dict]:
    steps = findings.get("steps") or {}
    a2 = steps.get("A2") or {}
    a3 = steps.get("A3") or {}
    a4 = steps.get("A4") or {}
    a5 = steps.get("A5") or {}
    a6_meta = steps.get("A6") or {}
    a7 = steps.get("A7") or {}
    fields = findings.get("a6_fields") or {}
    comments: list[dict] = []

    def add(
        cid: str,
        step: str,
        title: str,
        status: str,
        body: str,
        anchor: str,
        *,
        quote: str = "",
        note: str = "",
    ) -> None:
        if not placed.get(anchor) and status == "MISSING":
            note = (note + " · ").lstrip(" ·") + "No matching span in original (doc-level / missing)."
        elif not placed.get(anchor):
            note = (note + " · ").lstrip(" ·") + "Highlight approximate — span not found exactly."
        comments.append(
            {
                "id": cid,
                "step": step,
                "title": title,
                "status": status,
                "body": body,
                "anchor": anchor,
                "quote": quote,
                "note": note.strip(" ·"),
                "anchored": bool(placed.get(anchor)),
            }
        )

    teks = a2.get("teks") or {}
    add(
        "a2-teks",
        "A2",
        "TEKS / standards",
        teks.get("status") or "UNKNOWN",
        "No discrete TEKS codes cited in Layer 0 evidence. Original LP has Goal/Objectives but no TEKS codes.",
        "teks",
    )
    obj = a2.get("objective") or {}
    add(
        "a2-obj",
        "A2",
        "Objectives",
        obj.get("status") or "UNKNOWN",
        f"Goals/objectives found (count={obj.get('count', 0)}).",
        "objective",
        quote=clean((obj.get("cites") or [""])[0]) if obj.get("cites") else "",
    )
    add(
        "a3",
        "A3",
        "Coherence",
        a3.get("status") or "UNKNOWN",
        (
            f"has_objective={a3.get('has_objective')} · "
            f"has_activities={a3.get('has_activities')} · "
            f"has_assessment={a3.get('has_assessment')}"
        ),
        "objective_purpose",
    )
    form = a4.get("formative") or {}
    summ = a4.get("summative") or {}
    add(
        "a4-form",
        "A4",
        "Formative assessment",
        form.get("status") or "UNKNOWN",
        f"{len(form.get('items') or [])} formative checkpoint item(s).",
        "check_for_understanding",
    )
    add(
        "a4-summ",
        "A4",
        "Summative assessment",
        summ.get("status") or "UNKNOWN",
        "No summative items placed in this Path A pass.",
        "check_for_understanding",
    )
    for row in a5.get("matrix") or []:
        add(
            f"a5-{row.get('id')}",
            "A5",
            row.get("label") or row.get("id") or "Hunter",
            row.get("status") or "UNKNOWN",
            "Hunter core structure scored from evidence.",
            row.get("id") or "anticipatory_set",
            quote=clean(row.get("cite") or ""),
        )
    method = a6_meta.get("method") or "model"
    field_anchor = {
        "lesson_title": "lesson_title",
        "learning_objective": "objective",
        "teks": "teks",
        "materials": "materials",
        "anticipatory_set": "anticipatory_set",
        "objective_purpose": "objective_purpose",
        "input": "input",
        "modeling": "modeling",
        "check_for_understanding": "check_for_understanding",
        "guided_practice": "guided_practice",
        "independent_practice": "independent_practice",
        "closure": "closure",
        "elps_language": "elps",
        "accommodations": "accommodations",
    }
    for key, field in fields.items():
        anchor = field_anchor.get(key, key)
        st = field.get("status") or "UNKNOWN"
        note = "A6 model empty → code fallback" if method == "code_fallback" else ""
        body = (
            "Field not placed from evidence."
            if st == "MISSING"
            else "Field placed from View Lesson Plan / pack evidence."
        )
        add(
            f"a6-{key}",
            "A6",
            f"Field: {key}",
            st,
            body,
            anchor,
            quote=clean(field.get("text") or ""),
            note=note,
        )
    elps = a7.get("elps") or {}
    acc = a7.get("accommodations") or {}
    add(
        "a7-elps",
        "A7",
        "ELPS / language support",
        elps.get("status") or "UNKNOWN",
        "Language-support signal from pack evidence.",
        "elps",
    )
    add(
        "a7-acc",
        "A7",
        "Accommodations",
        acc.get("status") or "UNKNOWN",
        "Accommodations signal from pack evidence.",
        "accommodations",
    )
    return comments


def build_html(findings: dict, styles: str, body: str, comments: list[dict]) -> str:
    comments_json = json.dumps(comments, ensure_ascii=False)
    a5 = (findings.get("steps") or {}).get("A5") or {}
    hunter = f"{a5.get('hunter_core_present', '?')}/{a5.get('hunter_core_total', '?')}"
    a2 = (findings.get("steps") or {}).get("A2") or {}
    teks_st = (a2.get("teks") or {}).get("status", "?")
    a6 = (findings.get("steps") or {}).get("A6") or {}

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Path A review — original cattle View Lesson Plan</title>
<style>
  :root {{
    --bg: #eceae4;
    --ink: #1c1917;
    --muted: #57534e;
    --line: #d6d3d1;
    --accent: #0f766e;
    --missing: #b91c1c;
    --sidebar: #fafaf9;
    --hi: #fde68a;
    --hi-strong: #fbbf24;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; height: 100%;
    font-family: ui-sans-serif, system-ui, sans-serif;
    color: var(--ink); background: var(--bg);
  }}
  .app {{ display: grid; grid-template-rows: auto 1fr; height: 100vh; }}
  header.bar {{
    display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center;
    justify-content: space-between;
    padding: 10px 16px; background: #134e4a; color: #ecfdf5;
  }}
  header.bar h1 {{ margin: 0; font-size: 1rem; }}
  header.bar .meta {{ font-size: 0.75rem; opacity: 0.9; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.72rem; }}
  .chip {{
    background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25);
    padding: 3px 8px; border-radius: 999px;
  }}
  .chip.bad {{ background: #7f1d1d; }}
  .main {{
    display: grid; grid-template-columns: minmax(0, 1fr) 380px; min-height: 0;
  }}
  @media (max-width: 960px) {{
    .main {{ grid-template-columns: 1fr; grid-template-rows: 55vh 45vh; }}
  }}
  .doc-pane {{ overflow: auto; padding: 16px; }}
  .doc-shell {{
    max-width: 860px; margin: 0 auto;
    background: white; border: 1px solid var(--line);
    padding: 8px 12px 40px;
  }}
  .doc-shell .doc-label {{
    font-size: 0.72rem; color: var(--muted); margin: 4px 8px 12px;
    border-bottom: 1px solid var(--line); padding-bottom: 8px;
  }}
  /* Original Word HTML lives here */
  .original {{
    background: white; color: black;
    padding: 8px 12px;
  }}
  .fb-anchor {{
    background: transparent;
    border-left: 3px solid transparent;
    scroll-margin-top: 24px;
    display: block;
  }}
  span.fb-anchor {{ display: inline; padding: 0 2px; }}
  .fb-anchor.active {{
    background: var(--hi);
    border-left-color: var(--hi-strong);
    outline: 2px solid var(--hi-strong);
  }}
  .fb-anchor.missing-active {{
    background: #fecaca;
    border-left-color: var(--missing);
    outline: 2px solid #f87171;
  }}
  .sidebar {{
    border-left: 1px solid var(--line); background: var(--sidebar);
    display: flex; flex-direction: column; min-height: 0;
  }}
  .side-head {{ padding: 12px 14px; border-bottom: 1px solid var(--line); }}
  .side-head h2 {{ margin: 0 0 4px; font-size: 0.95rem; }}
  .side-head p {{ margin: 0; font-size: 0.75rem; color: var(--muted); }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
  .filters button {{
    font: inherit; font-size: 0.72rem; cursor: pointer;
    border: 1px solid var(--line); background: white;
    padding: 4px 8px; border-radius: 6px;
  }}
  .filters button.on {{ background: #134e4a; color: white; border-color: #134e4a; }}
  .comment-list {{
    overflow: auto; padding: 10px; flex: 1;
    display: flex; flex-direction: column; gap: 8px;
  }}
  .comment {{
    background: white; border: 1px solid var(--line);
    border-radius: 10px; padding: 10px 12px; cursor: pointer;
    text-align: left; width: 100%;
  }}
  .comment.active {{
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(15,118,110,0.25);
  }}
  .comment .row {{
    display: flex; justify-content: space-between; gap: 8px; margin-bottom: 4px;
  }}
  .comment .step {{
    font-size: 0.7rem; font-weight: 700; color: var(--accent); letter-spacing: 0.04em;
  }}
  .badge {{
    font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 999px;
  }}
  .badge.PRESENT, .badge.COHERENT {{ background: #dcfce7; color: #14532d; }}
  .badge.MISSING {{ background: #fee2e2; color: #7f1d1d; }}
  .comment .title {{ margin: 0 0 4px; font-size: 0.82rem; font-weight: 650; }}
  .comment .body {{ margin: 0; font-size: 0.75rem; color: var(--muted); line-height: 1.35; }}
  .comment .quote {{
    margin: 8px 0 0; padding: 6px 8px; border-left: 3px solid #a8a29e;
    font-size: 0.7rem; color: #44403c; background: #f5f5f4;
  }}
  .comment .note {{
    margin: 6px 0 0; font-size: 0.68rem; color: #b45309; font-style: italic;
  }}
  .hint {{
    padding: 8px 14px 14px; font-size: 0.7rem; color: var(--muted);
    border-top: 1px solid var(--line);
  }}
  {styles}
  /* Override source body margin that assumed full page */
  .original body, .original {{ margin-left: 0 !important; }}
</style>
</head>
<body>
<div class="app">
  <header class="bar">
    <div>
      <h1>Path A review — original document + comments</h1>
      <div class="meta">023 View Lesson Plan (source HTML) · click feedback to highlight</div>
    </div>
    <div class="chips">
      <span class="chip">Hunter {html.escape(hunter)}</span>
      <span class="chip {"bad" if teks_st == "MISSING" else ""}">A2 TEKS {html.escape(str(teks_st))}</span>
      <span class="chip">A6 {html.escape(str(a6.get("method") or "model"))}</span>
    </div>
  </header>
  <div class="main">
    <div class="doc-pane" id="docPane">
      <div class="doc-shell">
        <div class="doc-label">
          Original source: <code>sources/023-breeds-of-livestock-cattle__view-lesson-plan.html</code>
          — not the plate rewrite. Yellow = selected feedback anchor.
        </div>
        <div class="original" id="originalDoc">
{body}
        </div>
      </div>
    </div>
    <aside class="sidebar">
      <div class="side-head">
        <h2>Path A feedback</h2>
        <p>Select a comment to highlight the matching place in the original LP.</p>
        <div class="filters" id="filters">
          <button type="button" data-filter="all" class="on">All</button>
          <button type="button" data-filter="MISSING">Missing</button>
          <button type="button" data-filter="PRESENT">Present</button>
          <button type="button" data-filter="A2">A2</button>
          <button type="button" data-filter="A5">A5</button>
          <button type="button" data-filter="A6">A6</button>
        </div>
      </div>
      <div class="comment-list" id="commentList"></div>
      <div class="hint">
        Over SSH: use Tailscale URL
        <code>http://100.85.15.59:8777/PATH-A-CATTLE-LP-REVIEW.html</code>
        (not 127.0.0.1 from your laptop). Or open the Cursor Canvas review.
      </div>
    </aside>
  </div>
</div>
<script>
const COMMENTS = {comments_json};

function render() {{
  const list = document.getElementById("commentList");
  list.innerHTML = "";
  const filter = document.querySelector(".filters button.on")?.dataset.filter || "all";
  for (const c of COMMENTS) {{
    if (filter === "MISSING" && c.status !== "MISSING") continue;
    if (filter === "PRESENT" && !(c.status === "PRESENT" || c.status === "COHERENT")) continue;
    if (["A2","A3","A4","A5","A6","A7"].includes(filter) && c.step !== filter) continue;
    const el = document.createElement("button");
    el.type = "button";
    el.className = "comment";
    el.dataset.id = c.id;
    el.innerHTML = `
      <div class="row">
        <span class="step">${{c.step}}</span>
        <span class="badge ${{c.status}}">${{c.status}}</span>
      </div>
      <p class="title"></p>
      <p class="body"></p>
      ${{c.quote ? '<p class="quote"></p>' : ""}}
      ${{c.note ? '<p class="note"></p>' : ""}}
    `;
    el.querySelector(".title").textContent = c.title + (c.anchored ? "" : " (unanchored)");
    el.querySelector(".body").textContent = c.body;
    if (c.quote) el.querySelector(".quote").textContent = c.quote;
    if (c.note) el.querySelector(".note").textContent = c.note;
    el.addEventListener("click", () => selectComment(c.id));
    list.appendChild(el);
  }}
}}

function selectComment(id) {{
  const c = COMMENTS.find(x => x.id === id);
  if (!c) return;
  document.querySelectorAll(".comment").forEach(el => {{
    el.classList.toggle("active", el.dataset.id === id);
  }});
  document.querySelectorAll(".fb-anchor").forEach(el => {{
    el.classList.remove("active", "missing-active");
  }});
  const mark = document.getElementById("anchor-" + c.anchor);
  if (mark) {{
    mark.classList.add(c.status === "MISSING" ? "missing-active" : "active");
    mark.scrollIntoView({{ behavior: "smooth", block: "center" }});
  }}
  const card = document.querySelector(`.comment[data-id="${{id}}"]`);
  if (card) card.scrollIntoView({{ behavior: "smooth", block: "nearest" }});
}}

document.getElementById("filters").addEventListener("click", (e) => {{
  const btn = e.target.closest("button[data-filter]");
  if (!btn) return;
  document.querySelectorAll(".filters button").forEach(b => b.classList.toggle("on", b === btn));
  render();
}});

render();
const first = COMMENTS.find(c => c.status === "MISSING") || COMMENTS[0];
if (first) selectComment(first.id);
</script>
</body>
</html>
"""


def main() -> None:
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))
    raw = SOURCE.read_text(encoding="utf-8", errors="replace")
    styles, body = sanitize_source(raw)
    body, placed = inject_anchors(body)
    comments = build_comments(findings, placed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_html(findings, styles, body, comments), encoding="utf-8")
    ok = sum(1 for v in placed.values() if v)
    print(f"Wrote {OUT}")
    print(f"  comments={len(comments)} anchors_placed={ok}/{len(placed)}")
    for k, v in placed.items():
        print(f"  [{'OK' if v else '--'}] {k}")


if __name__ == "__main__":
    main()
