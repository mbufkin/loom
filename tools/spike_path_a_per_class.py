#!/usr/bin/env python3
"""SPIKE — Path A A5 per class inside a multi-class View Lesson Plan.

Educational note
----------------
iCEV "View Lesson Plan" files are often multi-day packs (Seat Time: N Classes).
Whole-doc Path A scores Hunter once against the entire pack, so evidence from
*any* class can mark the pack 8/8. This spike splits Class 1..N, runs the
same A5 Hunter matrix on each class's text, and emits a scorecard + HTML
review against the original source.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lesson_plan_fill import HUNTER_CORE_IDS, load_daily_lesson_checklist  # noqa: E402
from workflows.lesson_plan import (  # noqa: E402
    a2_standards,
    a3_coherence,
    a4_assessment_path,
    a5_hunter_matrix,
    a6_model_place,
    a7_supports,
)

LAB = ROOT / "projects" / "lab-graph-cte-cattle"
SOURCE = LAB / "sources" / "023-breeds-of-livestock-cattle__view-lesson-plan.html"
OUT_DIR = LAB / "path_a" / "per_class"
OUT_JSON = OUT_DIR / "PER-CLASS-A5.json"
OUT_MD = OUT_DIR / "PER-CLASS-A5.md"
OUT_HTML = ROOT / "docs" / "PATH-A-CATTLE-PER-CLASS-REVIEW.html"

# Heuristic typing of class-local snippets so we can reuse a5_hunter_matrix.
TYPE_RULES: list[tuple[str, list[str]]] = [
    # Hunter-ish + iCEV steps
    ("hook_engagement", [r"bell\s*ringer", r"warm-?up", r"do now", r"\bengage\b", r"kwl"]),
    ("standards_objectives", [r"essential questions?", r"objectives?", r"learning (?:goals?|target)", r"teks"]),
    ("direct_instruction", [r"powerpoint", r"show the", r"segment", r"key concepts", r"\bexplain\b", r"slideshow", r"interactive lesson"]),
    ("assessment_checkpoint", [r"check for understanding", r"\bcfu\b", r"formative", r"\bevaluate\b", r"question stems?"]),
    ("guided_practice", [r"\bexplore\b", r"guided", r"with support", r"small groups?", r"we do", r"together"]),
    ("independent_practice", [r"project", r"on your own", r"independently", r"build a breed", r"\bextend\b", r"\belaborate\b", r"shark tank", r"pitch"]),
    ("reflection_closure", [r"exit ticket", r"closure", r"wrap.?up", r"turn it in", r"\bevaluate\b", r"what did you learn"]),
]

# Episode headers — keep matches INSIDE one <p>…</p> so we never latch from
# Class 1's blue bar across later "Class N" titles (multi-LP formats).
EPISODE_HEADER_RES: list[re.Pattern[str]] = [
    # iCEV / Word export blue banner: Class|Day|Lesson|Session N
    re.compile(
        r"<p[^>]*background\s*:\s*#165DA2[^>]*>"
        r"(?:(?!</p>).){0,400}?"
        r"(?:Class|Day|Lesson|Session)\s+(\d+)\s*"
        r"(?:(?!</p>).){0,200}?</p>",
        re.I | re.S,
    ),
    # Fallback: bold paragraph whose visible text is basically "Class N"
    re.compile(
        r"<p[^>]*>\s*(?:<[^>]+>\s*)*"
        r"(?:Class|Day|Lesson|Session)\s+(\d+)\s*"
        r"(?:<[^>]+>\s*)*</p>",
        re.I,
    ),
]

# Pack-level appendix that follows the last daily episode (not part of that class).
# Order matters: first hit after an episode start wins as the cut.
# iCEV often uses green banners (#3D861B) for these pack sections.
_PACK_SECTION = (
    r"Activity\s+Overview|"
    r"Project\s+Overview|"
    r"Career\s*(?:&amp;|&)?\s*Technical\s+Student\s+Organizations|"
    r"Career\s+Connections|"
    r"Human\s+Resources|"
    r"Resources|"
    r"References"
)
PACK_APPENDIX_RES: list[re.Pattern[str]] = [
    # Colored section banner (iCEV green / similar)
    re.compile(
        rf"<p[^>]*background\s*:\s*#[0-9A-Fa-f]{{3,8}}[^>]*>"
        rf"(?:(?!</p>).){{0,400}}?(?:{_PACK_SECTION})"
        rf"(?:(?!</p>).){{0,200}}?</p>",
        re.I | re.S,
    ),
    # Plain / bold paragraph titles
    re.compile(
        rf"<p[^>]*>\s*(?:<[^>]+>\s*)*(?:{_PACK_SECTION})\s*(?:<[^>]+>\s*)*</p>",
        re.I,
    ),
    re.compile(
        r"<img[^>]+(?:copyright|protected under copyright)[^>]*>",
        re.I,
    ),
]


def strip_tags(s: str) -> str:
    t = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", "", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _find_episode_headers(raw_html: str) -> list[re.Match[str]]:
    for pat in EPISODE_HEADER_RES:
        matches = list(pat.finditer(raw_html))
        if len(matches) >= 2:
            return matches
        if len(matches) == 1:
            # Single-episode LP — still usable
            return matches
    return []


def _appendix_cut(raw_html: str, start: int, hard_end: int) -> int | None:
    """Earliest pack-appendix marker in [start, hard_end), or None."""
    window = raw_html[start:hard_end]
    hits: list[int] = []
    for pat in PACK_APPENDIX_RES:
        m = pat.search(window)
        if m:
            hits.append(start + m.start())
    return min(hits) if hits else None


def split_lesson_episodes(raw_html: str) -> tuple[str, list[dict], str]:
    """Split a multi-episode lesson pack into overview / episodes / appendix.

    Designed for many LP shapes (Class/Day/Lesson/Session N banners), not only
    iCEV cattle. Each episode is clipped to *its* range — never the next
    episode, and never pack-level appendix after the last Exit Ticket.

    Returns (overview_html, episodes, appendix_html).
    """
    matches = _find_episode_headers(raw_html)
    if not matches:
        raise SystemExit(
            "Could not find episode headers (Class/Day/Lesson/Session N) in source HTML"
        )

    overview = raw_html[: matches[0].start()]
    appendix = ""
    episodes: list[dict] = []

    for i, m in enumerate(matches):
        start = m.start()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(raw_html)
        end = next_start
        # Last episode (or any): cut pack appendix out of the episode body.
        cut = _appendix_cut(raw_html, start + len(m.group(0)), next_start)
        if cut is not None:
            end = cut
            if i + 1 == len(matches):
                appendix = raw_html[cut:]
        elif i + 1 == len(matches):
            # No appendix marker — still drop trailing </div></body></html>
            tail = raw_html[start:next_start]
            close = re.search(r"</div>\s*</body>", tail, re.I)
            if close:
                end = start + close.start()
                appendix = raw_html[end:]

        num = int(m.group(1))
        chunk = raw_html[start:end]
        lab_m = re.search(r"(Class|Day|Lesson|Session)\s+\d+", m.group(0), re.I)
        kind = (lab_m.group(1) if lab_m else "Class").lower()
        label = {"class": "Class", "day": "Day", "lesson": "Lesson", "session": "Session"}.get(
            kind, "Class"
        )
        episodes.append(
            {
                "class_num": num,
                "episode_num": num,
                "label": label,
                "html": chunk,
                "text": strip_tags(chunk),
                "title": f"{label} {num}",
                "char_count_html": len(chunk),
            }
        )

    # Deduplicate by episode number (keep first)
    seen: set[int] = set()
    uniq: list[dict] = []
    for c in episodes:
        if c["class_num"] in seen:
            continue
        seen.add(c["class_num"])
        uniq.append(c)
    uniq.sort(key=lambda c: c["class_num"])
    return overview, uniq, appendix


def split_classes(raw_html: str) -> tuple[str, list[dict]]:
    """Back-compat wrapper — drops appendix (use split_lesson_episodes)."""
    overview, episodes, _appendix = split_lesson_episodes(raw_html)
    return overview, episodes


def normalize_plain_lesson_text(raw: str) -> str:
    """Normalize Dallas-style table exports for episode splitting.

    Educational note: many Dallas ISD career LPs are pasted from multi-column
    tables, so each line/paragraph is repeated 3×. Collapse that before split.
    """
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "|" in line:
            line = line.split("|")[0].rstrip()
        lines.append(line.rstrip())

    # Drop consecutive duplicate lines
    deduped: list[str] = []
    for line in lines:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)

    # Drop near-duplicate short blocks (same normalized text back-to-back)
    paras = re.split(r"\n\s*\n+", "\n".join(deduped))
    out_paras: list[str] = []
    prev_norm = ""
    for p in paras:
        norm = re.sub(r"\s+", " ", p).strip().lower()
        if not norm:
            continue
        if norm == prev_norm:
            continue
        # Also skip if this para is an exact prefix-repeat of the previous
        if prev_norm and (norm in prev_norm or prev_norm in norm) and abs(len(norm) - len(prev_norm)) < 40:
            continue
        out_paras.append(p.strip())
        prev_norm = norm
    return "\n\n".join(out_paras).strip() + "\n"


def split_text_episodes(raw_text: str) -> tuple[str, list[dict], str]:
    """Split Dallas / plain-text multi-day LPs into episodes.

    Prefer 5E cycle boundaries (Engage Activity … next Engage Activity).
    Fall back to Day/Class/Lesson/Session N line headers with real body text.
    """
    text = normalize_plain_lesson_text(raw_text)
    lines = text.splitlines()

    # --- Strategy A: 5E cycles starting at Engage Activity ---
    engage_idxs = [
        i
        for i, ln in enumerate(lines)
        if re.match(r"^Engage\s+Activity\b", ln.strip(), re.I)
        or re.match(r"^Engage\s*:\s*\(", ln.strip(), re.I)
    ]
    # Prefer labeled "Engage Activity" headers
    engage_headers = [
        i for i, ln in enumerate(lines) if re.match(r"^Engage\s+Activity\b", ln.strip(), re.I)
    ]
    if len(engage_headers) >= 2:
        starts = engage_headers
        overview = "\n".join(lines[: starts[0]]).strip()
        episodes: list[dict] = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(lines)
            chunk_lines = lines[start:end]
            chunk = "\n".join(chunk_lines).strip()
            num = i + 1
            day_m = re.search(r"Day\s+(\d+)", chunk[:200], re.I)
            if day_m:
                num = int(day_m.group(1))
            topic = ""
            for ln in chunk_lines[:12]:
                if re.match(r"^Engage\s*:", ln.strip(), re.I):
                    topic = ln.strip()[:120]
                    break
            episodes.append(
                {
                    "class_num": num,
                    "episode_num": num,
                    "label": "Day",
                    "html": f"<pre class='plain-ep'>{html.escape(chunk)}</pre>",
                    "text": chunk,
                    "title": f"Day {num}",
                    "topic_hint": topic,
                    "char_count_html": len(chunk),
                }
            )
        # Deduplicate nums if Day labels collide
        seen: set[int] = set()
        uniq: list[dict] = []
        for ep in episodes:
            n = ep["class_num"]
            while n in seen:
                n += 1
            ep["class_num"] = n
            ep["episode_num"] = n
            ep["title"] = f"Day {n}"
            seen.add(n)
            uniq.append(ep)
        return overview, uniq, ""

    # --- Strategy B: Day/Class/Lesson/Session N headers with body ---
    header_idxs: list[tuple[int, int, str]] = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(Day|Class|Lesson|Session)\s+(\d+)\s*$", ln.strip(), re.I)
        if m:
            header_idxs.append((i, int(m.group(2)), m.group(1)))
    usable: list[tuple[int, int, str]] = []
    for j, (i, num, kind) in enumerate(header_idxs):
        end = header_idxs[j + 1][0] if j + 1 < len(header_idxs) else len(lines)
        body = "\n".join(lines[i + 1 : end]).strip()
        if len(body) >= 80:  # skip empty stub "Day 1" TOC lines
            usable.append((i, num, kind))
    if usable:
        overview = "\n".join(lines[: usable[0][0]]).strip()
        episodes = []
        for j, (i, num, kind) in enumerate(usable):
            end = usable[j + 1][0] if j + 1 < len(usable) else len(lines)
            chunk = "\n".join(lines[i:end]).strip()
            label = kind[0].upper() + kind[1:].lower()
            episodes.append(
                {
                    "class_num": num,
                    "episode_num": num,
                    "label": label,
                    "html": f"<pre class='plain-ep'>{html.escape(chunk)}</pre>",
                    "text": chunk,
                    "title": f"{label} {num}",
                    "char_count_html": len(chunk),
                }
            )
        return overview, episodes, ""

    # --- Strategy C: single episode = whole doc ---
    return (
        "",
        [
            {
                "class_num": 1,
                "episode_num": 1,
                "label": "Lesson",
                "html": f"<pre class='plain-ep'>{html.escape(text)}</pre>",
                "text": text,
                "title": "Lesson 1",
                "char_count_html": len(text),
            }
        ],
        "",
    )


def looks_like_html(raw: str) -> bool:
    head = raw.lstrip()[:500].lower()
    return head.startswith("<!doctype") or head.startswith("<html") or "<p class=" in raw[:2000].lower()


def synthetic_elements(
    class_num: int, text: str, *, source_file: str = "source"
) -> list[dict]:
    """Turn class text into ledger-like elements for a5_hunter_matrix."""
    # Split into step-ish chunks on "Step N:" or blank lines / 5E headers
    parts = re.split(
        r"(?=Step\s+\d+:|Essential Questions:|Class Overview:|"
        r"Engage\s+Activity|Explain\s+Activity|Explore\s+Activity|"
        r"Elaborate\s+Activity|Extend\s+Activity|Evaluate\s+Activity|"
        r"Engage\s*:|Explain\s*:|Explore\s*:|Evaluate\s*:)",
        text,
    )
    parts = [p.strip() for p in parts if p and p.strip()]
    if len(parts) < 2:
        parts = [text]

    elements: list[dict] = []
    for i, part in enumerate(parts):
        etype = "other"
        low = part.lower()
        for t, pats in TYPE_RULES:
            if any(re.search(p, low) for p in pats):
                etype = t
                break
        elements.append(
            {
                "element_id": f"class-{class_num}-e{i+1}",
                "element_type": etype,
                "excerpt": part[:1200],
                "source_file": source_file,
            }
        )
    # Always include full-class excerpt so keyword matching can still hit
    elements.append(
        {
            "element_id": f"class-{class_num}-full",
            "element_type": "other",
            "excerpt": text[:4000],
            "source_file": source_file,
        }
    )
    return elements


def _score_path_a_bundle(
    els: list[dict], checklist: dict
) -> dict:
    """Run A2–A7 (A6 = code fallback; no model) on synthetic elements."""
    a2 = a2_standards(els)
    a3 = a3_coherence(els, a2)
    a4 = a4_assessment_path(els)
    a5 = a5_hunter_matrix(els, checklist)
    a6 = a6_model_place(els, checklist, cfg=None, use_model=False)
    a7 = a7_supports(els)
    a6_fields = a6.get("fields") or {}
    a6_missing = [k for k, v in a6_fields.items() if (v or {}).get("status") == "MISSING"]
    a6_present = [k for k, v in a6_fields.items() if (v or {}).get("status") == "PRESENT"]
    return {
        "A2": a2,
        "A3": a3,
        "A4": a4,
        "A5": a5,
        "A6": {
            "method": a6.get("method"),
            "present": len(a6_present),
            "missing": len(a6_missing),
            "missing_fields": a6_missing[:12],
            "fields": a6_fields,
        },
        "A7": a7,
    }


def score_classes(
    classes: list[dict],
    checklist: dict,
    *,
    source_file: str = "source",
    overview_text: str = "",
) -> list[dict]:
    rows = []
    # Pack/overview checks (TEKS often lives in the header, not each Day)
    if overview_text.strip():
        ov_els = synthetic_elements(0, overview_text, source_file=source_file)
        # Tag overview chunks as standards when TEKS/goals language appears
        for e in ov_els:
            ex = (e.get("excerpt") or "").lower()
            if "teks" in ex or "student expectation" in ex or "learning goal" in ex:
                e["element_type"] = "standards_objectives"
        pack = _score_path_a_bundle(ov_els, checklist)
    else:
        pack = None

    for c in classes:
        els = synthetic_elements(c["class_num"], c["text"], source_file=source_file)
        # Promote TEKS/objective-looking chunks so A2 can see them inside a Day
        for e in els:
            ex = (e.get("excerpt") or "")
            low = ex.lower()
            if re.search(r"teks|§\s*\d+|student expectation", low) or re.search(
                r"learning goals?|objective|students will", low
            ):
                e["element_type"] = "standards_objectives"
            if re.search(r"evaluate|exit ticket|formative|check for understanding", low):
                if e.get("element_type") == "other":
                    e["element_type"] = "assessment_checkpoint"

        bundle = _score_path_a_bundle(els, checklist)
        a5 = bundle["A5"]
        missing = [m["id"] for m in a5["matrix"] if m["status"] == "MISSING"]
        present_ids = [m["id"] for m in a5["matrix"] if m["status"] == "PRESENT"]
        topic = (c.get("topic_hint") or "").strip()
        if not topic:
            overview_m = re.search(
                r"Class Overview:\s*(.+?)(?:Essential Questions:|Step\s+1:|$)",
                c["text"],
                re.S | re.I,
            )
            if overview_m:
                topic = re.sub(r"\s+", " ", overview_m.group(1)).strip()[:120]
        if not topic:
            for ln in c["text"].splitlines():
                s = ln.strip()
                if s and not re.match(r"^(Day|Class|Lesson|Session)\s+\d+", s, re.I):
                    topic = s[:120]
                    break
        rows.append(
            {
                "class_num": c["class_num"],
                "title": c["title"],
                "topic": topic,
                "char_count": len(c["text"]),
                "element_count": len(els),
                "hunter_core_present": a5["hunter_core_present"],
                "hunter_core_total": a5["hunter_core_total"],
                "missing": missing,
                "present": present_ids,
                "matrix": a5["matrix"],
                "steps": bundle,
                "pack_overview": pack,
            }
        )
    return rows


def write_md(payload: dict) -> str:
    lines = [
        f"# Path A per-episode A5 spike — {payload.get('doc_title') or payload['source_file']}",
        "",
        f"**Source:** `{payload['source_file']}`",
        f"**Episodes detected:** {payload['class_count']}",
        f"**Whole-doc A5:** {payload.get('whole_doc_hunter', 'n/a')}",
        "",
        "## Scorecard",
        "",
        "| Episode | Hunter | A2 TEKS | A2 Obj | A3 | A4 Form | A7 ELPS | A5 missing |",
        "|---------|--------|---------|--------|----|---------|---------|------------|",
    ]
    for r in payload["classes"]:
        steps = r.get("steps") or {}
        a2 = steps.get("A2") or {}
        a3 = steps.get("A3") or {}
        a4 = steps.get("A4") or {}
        a7 = steps.get("A7") or {}
        miss = ", ".join(r["missing"]) if r["missing"] else "—"
        title = r.get("title") or f"Episode {r['class_num']}"
        lines.append(
            f"| {title} | "
            f"**{r['hunter_core_present']}/{r['hunter_core_total']}** | "
            f"{(a2.get('teks') or {}).get('status', '?')} | "
            f"{(a2.get('objective') or {}).get('status', '?')} | "
            f"{a3.get('status', '?')} | "
            f"{(a4.get('formative') or {}).get('status', '?')} | "
            f"{(a7.get('elps') or {}).get('status', '?')} | "
            f"{miss} |"
        )
    lines += [
        "",
        "## What this proves",
        "",
        "Whole-document Path A can look strong while individual episodes are thin.",
        "Multi-day / multi-class packs must be split before A5/A6.",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_html(
    raw_html: str,
    overview: str,
    classes: list[dict],
    scores: list[dict],
    appendix: str = "",
    *,
    source_label: str = "",
    doc_title: str = "lesson plan",
    whole_doc_label: str = "",
    serve_path: str = "PATH-A-PER-CLASS-REVIEW.html",
    is_plain: bool = False,
) -> str:
    # Sanitize source for embedding
    styles = "".join(re.findall(r"<style[\s\S]*?</style>", raw_html, flags=re.I)) if not is_plain else ""

    # Rebuild from split chunks — sibling episode divs only.
    def _scrub(chunk: str) -> str:
        chunk = re.sub(r"<script[\s\S]*?</script>", "", chunk, flags=re.I)
        chunk = re.sub(r"</body>[\s\S]*$", "", chunk, flags=re.I)
        chunk = re.sub(r"</html>[\s\S]*$", "", chunk, flags=re.I)
        return chunk

    if is_plain:
        overview_body = (
            f"<pre class='plain-ep overview'>{html.escape(overview)}</pre>"
            if overview.strip()
            else ""
        )
        parts = [overview_body] if overview_body else []
        for c in classes:
            num = c["class_num"]
            parts.append(
                f'<div class="class-block" id="class-{num}" data-class="{num}">'
                f"{c['html']}</div>"
            )
        if appendix.strip():
            parts.append(
                '<div class="pack-appendix" id="pack-appendix">'
                '<div class="appendix-banner">Pack appendix (not scored as an episode)</div>'
                f"<pre class='plain-ep'>{html.escape(appendix)}</pre></div>"
            )
    else:
        overview_body = overview
        body_m = re.search(r"<body[^>]*>([\s\S]*)", overview, flags=re.I)
        if body_m:
            overview_body = body_m.group(1)
        overview_body = _scrub(overview_body)
        parts = [overview_body]
        for c in classes:
            num = c["class_num"]
            parts.append(
                f'<div class="class-block" id="class-{num}" data-class="{num}">'
                f'{_scrub(c["html"])}</div>'
            )
        if appendix.strip():
            parts.append(
                '<div class="pack-appendix" id="pack-appendix">'
                '<div class="appendix-banner">Pack appendix (not part of any Class episode — '
                "activity accommodations, CTSO, career connections, copyright)</div>"
                f"{_scrub(appendix)}</div>"
            )
    body = "\n".join(parts)

    scores_json = json.dumps(scores, ensure_ascii=False)
    src = html.escape(source_label or "source")
    title = html.escape(doc_title)
    whole_chip = html.escape(whole_doc_label or "n/a")

    rows_html = []
    for r in scores:
        miss = ", ".join(r["missing"]) if r["missing"] else "—"
        tone = "ok" if r["hunter_core_present"] >= 7 else ("mid" if r["hunter_core_present"] >= 5 else "bad")
        label = html.escape(r.get("title") or f"Episode {r['class_num']}")
        rows_html.append(
            f"""<button type="button" class="score-row {tone}" data-class="{r['class_num']}">
  <span class="n">{label}</span>
  <span class="hunter">{r['hunter_core_present']}/{r['hunter_core_total']}</span>
  <span class="topic">{html.escape(r.get('topic') or '')}</span>
  <span class="miss">{html.escape(miss)}</span>
</button>"""
        )

    def _st(status: str) -> str:
        return (status or "UNKNOWN").lower()

    matrix_panels = []
    for r in scores:
        steps = r.get("steps") or {}
        a2 = steps.get("A2") or {}
        a3 = steps.get("A3") or {}
        a4 = steps.get("A4") or {}
        a6 = steps.get("A6") or {}
        a7 = steps.get("A7") or {}
        pack = r.get("pack_overview") or {}
        pack_a2 = (pack.get("A2") or {}) if pack else {}

        cells = "".join(
            f'<li class="{_st(m["status"])}"><b>{html.escape(m["label"])}</b> '
            f'<em>{html.escape(m["status"])}</em></li>'
            for m in r["matrix"]
        )
        ep_label = html.escape(r.get("title") or f"Episode {r['class_num']}")
        teks = (a2.get("teks") or {}).get("status", "?")
        obj = (a2.get("objective") or {}).get("status", "?")
        form = (a4.get("formative") or {}).get("status", "?")
        summ = (a4.get("summative") or {}).get("status", "?")
        elps = (a7.get("elps") or {}).get("status", "?")
        acc = (a7.get("accommodations") or {}).get("status", "?")
        pack_teks = (pack_a2.get("teks") or {}).get("status")
        pack_note = (
            f'<p class="pack-note">Pack overview A2 TEKS: <em class="{_st(pack_teks)}">'
            f"{html.escape(str(pack_teks))}</em> (often in header, not each day)</p>"
            if pack_teks
            else ""
        )
        a6_miss = ", ".join(a6.get("missing_fields") or []) or "—"
        matrix_panels.append(
            f'<div class="matrix" data-class="{r["class_num"]}" hidden>'
            f"<h3>{ep_label} · Path A checks</h3>"
            f"{pack_note}"
            f'<ul class="checks">'
            f'<li class="{_st(teks)}"><b>A2 TEKS</b><em>{html.escape(str(teks))}</em></li>'
            f'<li class="{_st(obj)}"><b>A2 Objectives</b><em>{html.escape(str(obj))}</em></li>'
            f'<li class="{_st(a3.get("status"))}"><b>A3 Coherence</b>'
            f'<em>{html.escape(str(a3.get("status") or "?"))}</em></li>'
            f'<li class="{_st(form)}"><b>A4 Formative</b><em>{html.escape(str(form))}</em></li>'
            f'<li class="{_st(summ)}"><b>A4 Summative</b><em>{html.escape(str(summ))}</em></li>'
            f'<li class="present"><b>A6 Fields placed</b>'
            f'<em>{a6.get("present", 0)} present / {a6.get("missing", 0)} missing</em></li>'
            f'<li class="{_st(elps)}"><b>A7 ELPS</b><em>{html.escape(str(elps))}</em></li>'
            f'<li class="{_st(acc)}"><b>A7 Accommodations</b><em>{html.escape(str(acc))}</em></li>'
            f"</ul>"
            f'<p class="a6-miss"><b>A6 missing fields:</b> {html.escape(a6_miss)}</p>'
            f"<h4>A5 Hunter matrix</h4><ul>{cells}</ul></div>"
        )

    whole = scores  # for avg
    avg = sum(r["hunter_core_present"] for r in whole) / max(len(whole), 1)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Path A per-class A5 — cattle LP</title>
<style>
  :root {{
    --bg:#eceae4; --ink:#1c1917; --muted:#57534e; --line:#d6d3d1;
    --accent:#0f766e; --ok:#15803d; --mid:#b45309; --bad:#b91c1c; --hi:#fde68a;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; height:100%; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--ink); }}
  .app {{ display:grid; grid-template-rows:auto 1fr; height:100vh; }}
  header {{ background:#134e4a; color:#ecfdf5; padding:10px 16px; display:flex; flex-wrap:wrap; gap:12px; justify-content:space-between; align-items:center; }}
  header h1 {{ margin:0; font-size:1rem; }}
  header .meta {{ font-size:.75rem; opacity:.9; }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; font-size:.72rem; }}
  .chip {{ border:1px solid rgba(255,255,255,.3); padding:3px 8px; border-radius:999px; }}
  .main {{ display:grid; grid-template-columns:minmax(0,1fr) 400px; min-height:0; }}
  @media (max-width:960px) {{ .main {{ grid-template-columns:1fr; grid-template-rows:50vh 50vh; }} }}
  .doc-pane {{ overflow:auto; padding:14px; }}
  .doc-shell {{ max-width:860px; margin:0 auto; background:#fff; border:1px solid var(--line); padding:8px 12px 36px; }}
  .doc-label {{ font-size:.72rem; color:var(--muted); margin:4px 8px 12px; padding-bottom:8px; border-bottom:1px solid var(--line); }}
  .class-block {{ border-left:3px solid transparent; scroll-margin-top:20px; }}
  .class-block.active {{ background:var(--hi); border-left-color:#f59e0b; outline:2px solid #fbbf24; }}
  .pack-appendix {{
    margin-top: 18px; padding-top: 8px; border-top: 2px dashed #a8a29e;
    opacity: 0.85;
  }}
  .appendix-banner {{
    font-size: 0.78rem; font-weight: 700; color: #78716c;
    background: #f5f5f4; border: 1px solid var(--line);
    padding: 8px 10px; margin: 0 0 10px; border-radius: 8px;
  }}
  .sidebar {{ border-left:1px solid var(--line); background:#fafaf9; display:flex; flex-direction:column; min-height:0; }}
  .side-head {{ padding:12px 14px; border-bottom:1px solid var(--line); }}
  .side-head h2 {{ margin:0 0 4px; font-size:.95rem; }}
  .side-head p {{ margin:0; font-size:.75rem; color:var(--muted); }}
  .score-list {{ overflow:auto; padding:10px; display:flex; flex-direction:column; gap:8px; flex:0 0 auto; max-height:48%; }}
  .score-row {{
    display:grid; grid-template-columns:64px 48px 1fr; grid-template-rows:auto auto;
    gap:2px 8px; text-align:left; width:100%;
    background:#fff; border:1px solid var(--line); border-radius:10px; padding:10px;
    cursor:pointer; font:inherit;
  }}
  .score-row .n {{ font-weight:700; font-size:.8rem; }}
  .score-row .hunter {{ font-weight:700; font-size:.8rem; }}
  .score-row .topic {{ grid-column:1 / -1; font-size:.72rem; color:var(--muted); }}
  .score-row .miss {{ grid-column:1 / -1; font-size:.7rem; color:var(--bad); }}
  .score-row.ok .hunter {{ color:var(--ok); }}
  .score-row.mid .hunter {{ color:var(--mid); }}
  .score-row.bad .hunter {{ color:var(--bad); }}
  .score-row.active {{ border-color:var(--accent); box-shadow:0 0 0 2px rgba(15,118,110,.25); }}
  .detail {{ overflow:auto; padding:10px 14px 16px; border-top:1px solid var(--line); flex:1; }}
  .matrix ul {{ list-style:none; padding:0; margin:0; }}
  .matrix li {{ display:flex; justify-content:space-between; gap:8px; padding:6px 0; border-bottom:1px solid var(--line); font-size:.78rem; }}
  .matrix li.present em, .matrix li.coherent em {{ color:var(--ok); font-style:normal; font-weight:700; }}
  .matrix li.missing em, .matrix li.partial em {{ color:var(--bad); font-style:normal; font-weight:700; }}
  .matrix h4 {{ margin:14px 0 6px; font-size:.8rem; }}
  .matrix .pack-note, .matrix .a6-miss {{ font-size:.72rem; color:var(--muted); margin:8px 0; }}
  .matrix .checks {{ margin-bottom: 8px; }}
  .hint {{ padding:8px 14px; font-size:.7rem; color:var(--muted); border-top:1px solid var(--line); }}
  pre.plain-ep {{
    white-space: pre-wrap; word-break: break-word;
    font-family: ui-sans-serif, system-ui, sans-serif;
    font-size: 0.86rem; line-height: 1.4; margin: 0; color: #1c1917;
  }}
  {styles}
  .original {{ margin-left:0 !important; }}
</style>
</head>
<body>
<div class="app">
  <header>
    <div>
      <h1>Path A spike — A5 per episode (not whole pack)</h1>
      <div class="meta">{title} · {len(scores)} episode(s) scored separately · {src}</div>
    </div>
    <div class="chips">
      <span class="chip">episodes {len(scores)}</span>
      <span class="chip">avg Hunter {avg:.1f}/8</span>
      <span class="chip">whole-doc {whole_chip}</span>
    </div>
  </header>
  <div class="main">
    <div class="doc-pane" id="docPane">
      <div class="doc-shell">
        <div class="doc-label">
          Source split into episode blocks. Click a scorecard row to highlight that episode.
          Yellow = selected.
        </div>
        <div class="original" id="originalDoc">{body}</div>
      </div>
    </div>
    <aside class="sidebar">
      <div class="side-head">
        <h2>Per-episode A5 scorecard</h2>
        <p>Same Hunter checklist as Path A — scoped to each episode only.</p>
      </div>
      <div class="score-list" id="scoreList">
        {"".join(rows_html)}
      </div>
      <div class="detail" id="detail">
        {"".join(matrix_panels)}
        <p class="hint" id="emptyHint">Select an episode to see its A5 matrix.</p>
      </div>
      <div class="hint">
        Over SSH open:
        <code>http://100.85.15.59:8778/{html.escape(serve_path)}</code>
      </div>
    </aside>
  </div>
</div>
<script>
const SCORES = {scores_json};
function scrollDocTo(el) {{
  // Doc lives in overflow:auto (#docPane). Compute offset relative to pane.
  const pane = document.getElementById("docPane");
  if (!pane || !el) return;
  let top = 0;
  let node = el;
  while (node && node !== pane) {{
    top += node.offsetTop;
    node = node.offsetParent;
    // If offsetParent jumps outside pane (e.g. to body), fall back to rects.
    if (node && !pane.contains(node) && node !== pane) {{
      const paneRect = pane.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      top = pane.scrollTop + (elRect.top - paneRect.top);
      break;
    }}
  }}
  pane.scrollTo({{ top: Math.max(0, top - 12), behavior: "smooth" }});
}}

function selectClass(n) {{
  document.querySelectorAll(".score-row").forEach(el => {{
    el.classList.toggle("active", Number(el.dataset.class) === n);
  }});
  document.querySelectorAll(".class-block").forEach(el => {{
    el.classList.toggle("active", Number(el.dataset.class) === n);
  }});
  document.querySelectorAll(".matrix").forEach(el => {{
    el.hidden = Number(el.dataset.class) !== n;
  }});
  const hint = document.getElementById("emptyHint");
  if (hint) hint.hidden = true;
  const block = document.getElementById("class-" + n);
  if (block) scrollDocTo(block);
}}
document.getElementById("scoreList").addEventListener("click", (e) => {{
  const btn = e.target.closest(".score-row");
  if (!btn) return;
  selectClass(Number(btn.dataset.class));
}});
// Default: weakest class
const weakest = [...SCORES].sort((a,b) => a.hunter_core_present - b.hunter_core_present)[0];
if (weakest) selectClass(weakest.class_num);
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--html-name", default=None)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    source = args.source.resolve()
    raw = source.read_text(encoding="utf-8", errors="replace")
    plain = not looks_like_html(raw)

    if plain:
        overview, classes, appendix = split_text_episodes(raw)
    else:
        overview, classes, appendix = split_lesson_episodes(raw)

    checklist = load_daily_lesson_checklist()
    ov_text = overview if plain else strip_tags(overview)
    scores = score_classes(
        classes,
        checklist,
        source_file=source.name,
        overview_text=ov_text,
    )

    # Compare against THIS file scored as one blob (not project-wide pooled findings).
    project_root = source.parents[1] if source.parent.name == "sources" else source.parent
    full_text = normalize_plain_lesson_text(raw) if plain else strip_tags(raw)
    one = score_classes(
        [{"class_num": 0, "title": "WHOLE", "text": full_text, "html": ""}],
        checklist,
        source_file=source.name,
        overview_text=ov_text,
    )[0]
    whole = f"{one['hunter_core_present']}/{one['hunter_core_total']} whole-file"

    out_dir = args.out_dir or (project_root / "path_a" / "per_class")
    html_name = args.html_name or (
        "PATH-A-DALLAS-PER-CLASS-REVIEW.html"
        if "dallas" in str(source).lower()
        else "PATH-A-CATTLE-PER-CLASS-REVIEW.html"
    )
    out_json = out_dir / "PER-CLASS-A5.json"
    out_md = out_dir / "PER-CLASS-A5.md"
    out_html = ROOT / "docs" / html_name
    doc_title = args.title or source.stem.replace("_", " ")[:80]

    payload = {
        "spike": "path_a_per_class_a5",
        "source_file": source.name,
        "doc_title": doc_title,
        "plain_text": plain,
        "class_count": len(classes),
        "overview_chars": len(overview if plain else strip_tags(overview)),
        "appendix_chars": len(appendix if plain else strip_tags(appendix)) if appendix else 0,
        "episode_chars": {c["class_num"]: len(c["text"]) for c in classes},
        "whole_doc_hunter": whole,
        "hunter_ids": list(HUNTER_CORE_IDS),
        "classes": scores,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_md.write_text(write_md(payload), encoding="utf-8")
    out_html.write_text(
        build_html(
            raw,
            overview,
            classes,
            scores,
            appendix=appendix,
            source_label=source.name,
            doc_title=doc_title,
            whole_doc_label=whole,
            serve_path=html_name,
            is_plain=plain,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    print(f"Wrote {out_html}")
    print(f"format={'plain' if plain else 'html'} whole-doc={whole}")
    for c in classes:
        print(f"  episode chars {c['title']}: {len(c['text'])}")
    for r in scores:
        print(
            f"  {r['title']}: {r['hunter_core_present']}/{r['hunter_core_total']} "
            f"missing={r['missing'] or '—'}"
        )


if __name__ == "__main__":
    main()
