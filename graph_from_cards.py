#!/usr/bin/env python3
"""Curriculum graph built from organise cards. No model calls.

Why this exists
---------------
The per-document graph phase asks a model three questions about each file in
isolation, so it can never see that a quiz belongs with its answer key, and it
copied a prompt example ("lessons 1 and 2") onto every document. The organise
step already read every document in full and wrote a card for each one (type,
topic, day numbers, references, unit cues). This module turns those cards into a
graph deterministically:

  * keep the organiser's placement where it is unambiguous (document is in one unit)
  * place the leftovers only when the evidence is clear, otherwise put them on an
    explicit "unattached" shelf (a decision for a person, never a silent guess)
  * link documents with evidence code can verify (same quiz URL, matching title
    stem, "Day N" in the file name, a lesson plan naming another file)
  * report what it noticed: duplicates, units with no assessment, files left
    unplaced, a unit that looks like two lessons merged

Educational note (best practice): every link carries a ``why`` string. A graph a
reviewer can interrogate ("why are these two connected?") is a graph they can trust;
an unexplained edge is just an opinion.

Layers (kept apart on purpose): load_inputs() reads files, build_graph() is a pure
function of its arguments (easy to test), main() writes output.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SHELF_ID = "_unattached"

# Words that describe a *kind of document*, not its subject. Removing them is what
# lets "Manufacturing Lesson Plan" and "Manufacturing exploration Quizizz" share the
# useful token ("manufacturing"). Generic across corpora, not tuned to one.
TYPE_WORDS = {
    "lesson", "plan", "plans", "slides", "slide", "powerpoint", "pptx", "exit", "ticket",
    "tickets", "day", "quiz", "quizizz", "answer", "answers", "key", "keys", "rubric",
    "project", "worksheet", "student", "notes", "template", "copy", "instructions",
    "handout", "docx", "pdf", "alternate", "example", "examples",
}
STOP_WORDS = {
    "and", "the", "for", "with", "about", "how", "what", "are", "you", "your", "from",
    "into", "this", "that", "its", "our", "all", "any", "not",
}

# Placement thresholds. Conservative on purpose: when unsure the document goes to the
# shelf, which is visible and cheap to fix, instead of into the wrong unit, which is
# invisible and corrupts every finding built on it.
MIN_PLACEMENT_SCORE = 2.0
MIN_PLACEMENT_MARGIN = 1.5  # best score must beat the runner-up by this factor
MIN_LINK_SCORE = 1.0        # shared-subject strength needed to link two documents

KINDS = (
    "lesson_plan", "slides", "handout", "exit_ticket", "quiz",
    "answer_key", "rubric", "project", "reference", "other",
)
ASSESSMENT_KINDS = {"exit_ticket", "quiz"}
# Legacy role vocabulary the router already understands (route.py). Kept so a later
# switch of the router to this graph is a mapping, not a rewrite.
LEGACY_ROLE = {"handout": "practice_student"}


# --------------------------------------------------------------------------- text
def tokens(text: str) -> list[str]:
    """Subject words: lowercase alphanumerics, minus short words, digits and doc-type words."""
    out = []
    for t in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(t) < 3 or t.isdigit() or t in STOP_WORDS or t in TYPE_WORDS:
            continue
        out.append(t)
    return out


def stem_of(name: str) -> str:
    return Path(name).stem


def day_in_name(name: str) -> int | None:
    """Explicit "Day N" in a file name only. Never inferred from content."""
    m = re.search(r"(?i)\bday\s*(\d{1,2})\b", name) or re.search(r"(?i)\b(\d{1,2})(?:st|nd|rd|th)?\s*day\b", name)
    return int(m.group(1)) if m else None


def doc_kind(name: str, card: dict) -> str:
    """What kind of document this is. File-name evidence is checked before the card's role."""
    n = name.lower()
    role = (card.get("role") or "").lower()
    ext = Path(n).suffix
    if re.search(r"answer\s*keys?", n) or role == "answer_key":
        return "answer_key"
    if re.search(r"exit\s*tickets?", n):
        return "exit_ticket"
    if "rubric" in n or role == "rubric":
        return "rubric"
    if ext in {".pptx", ".ppt", ".key", ".odp"} or re.search(r"\bslides?\b|powerpoint", n) or role == "slides":
        return "slides"
    if re.search(r"quiz|quizizz|\btest\b|\bexam\b", n) or role == "assessment":
        return "quiz"
    if re.search(r"lesson\s*plan", n) or role == "lesson_plan":
        return "lesson_plan"
    if role == "project" or re.search(r"project\s*(instructions|description)|instructions", n):
        return "project"
    if role in {"student_practice", "student_handout"} or re.search(r"worksheet|handout|notes", n):
        return "handout"
    if role == "reference":
        return "reference"
    return "other"


@dataclass
class Doc:
    name: str
    card: dict
    kind: str
    unit: str | None = None
    day: int | None = None
    placement: str = ""  # why this unit (or why none)
    toks: Counter = field(default_factory=Counter)

    @property
    def stem(self) -> str:
        return stem_of(self.name)


def _doc_tokens(name: str, card: dict) -> Counter:
    """Subject tokens for similarity: file name counts double, then cues, topic, skills."""
    c: Counter = Counter()
    for t in tokens(stem_of(name)):
        c[t] += 2
    for field_name in ("unit_cues", "skills"):
        for item in card.get(field_name) or []:
            for t in tokens(str(item)):
                c[t] += 1
    for t in tokens(str(card.get("topic") or "")):
        c[t] += 1
    return c


# ------------------------------------------------------------------------- placement
def _unit_profiles(units: dict, docs: dict[str, Doc], exclusive: dict[str, str]):
    """Per-unit token profile from the unit's title and the documents only it lists."""
    prof: dict[str, Counter] = {u: Counter() for u in units}
    for u, meta in units.items():
        for t in tokens(meta.get("title") or u.replace("-", " ")):
            prof[u][t] += 3
    for name, u in exclusive.items():
        for t, w in docs[name].toks.items():
            prof[u][t] += w
    return prof


def _score(doc: Doc, profile: Counter, idf: dict[str, float]) -> float:
    """How strongly a document's subject words appear in a unit profile, rarer words counting more."""
    return sum(idf.get(t, 0.0) * min(profile.get(t, 0), 6) * min(w, 2) for t, w in doc.toks.items() if t in profile)


def place_documents(units: dict, docs: dict[str, Doc]) -> None:
    """Fill Doc.unit / Doc.placement. Organiser placement is kept when unambiguous."""
    listed: dict[str, list[str]] = defaultdict(list)
    for u, meta in units.items():
        for name in meta.get("documents") or []:
            if name in docs:
                listed[name].append(u)
    exclusive = {n: us[0] for n, us in listed.items() if len(us) == 1}
    for n, u in exclusive.items():
        docs[n].unit, docs[n].placement = u, "organiser placed it in exactly one unit"

    profiles = _unit_profiles(units, docs, exclusive)
    n_units = max(1, len(units))
    df = Counter(t for p in profiles.values() for t in p)
    idf = {t: math.log(1 + n_units / (1 + c)) for t, c in df.items()}

    for name, doc in docs.items():
        if doc.unit:
            continue
        candidates = listed.get(name) or list(units)
        scored = sorted(((_score(doc, profiles[u], idf), u) for u in candidates), reverse=True)
        best = scored[0] if scored else (0.0, None)
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best[1] and best[0] >= MIN_PLACEMENT_SCORE and best[0] >= MIN_PLACEMENT_MARGIN * max(second, 1e-9):
            doc.unit = best[1]
            doc.placement = f"shared by the organiser; subject words match this unit best (score {best[0]:.1f} vs {second:.1f})"
        else:
            doc.unit = None
            doc.placement = f"no unit clearly fits (best score {best[0]:.1f} vs {second:.1f}); needs a decision"


# --------------------------------------------------------------------------- links
def _urls(card: dict) -> set[str]:
    return {str(r).strip() for r in card.get("references") or [] if str(r).strip().lower().startswith("http")}


def _similarity(a: Doc, b: Doc) -> float:
    """Shared subject strength between two documents (file name weighs most)."""
    shared = set(a.toks) & set(b.toks)
    return float(sum(min(a.toks[t], b.toks[t]) for t in shared))


def link_unit(unit_docs: list[Doc]) -> tuple[list[dict], list[dict]]:
    """Evidence-backed links among one unit's documents, plus findings about them."""
    edges: list[dict] = []
    findings: list[dict] = []
    by_kind: dict[str, list[Doc]] = defaultdict(list)
    for d in unit_docs:
        by_kind[d.kind].append(d)
    plans = by_kind.get("lesson_plan", [])
    # A file literally named "Lesson Plan" is the unit's main hub. Other documents the
    # organiser typed as "lesson plan" (a brainstorm, a free curriculum PDF) stay in the
    # unit but must not steal links from the real plan. Only if no file is named that way
    # do all plan-typed documents compete.
    named_plans = [p for p in plans if re.search(r"(?i)lesson\s*plan", p.name)]
    hubs = named_plans or plans

    def edge(rel: str, a: Doc, b: Doc, why: str) -> None:
        edges.append({"rel": rel, "from": a.name, "to": b.name, "why": why})

    # 1. Answer key -> the quiz/exit ticket it answers: same quiz URL beats same title.
    for key in by_kind.get("answer_key", []):
        targets = [d for d in unit_docs if d.kind in ASSESSMENT_KINDS | {"handout"}]
        matched = None
        for t in targets:
            if _urls(key.card) & _urls(t.card):
                matched, why = t, "both cite the same quiz URL"
                break
        if not matched and targets:
            best = max(targets, key=lambda t: _similarity(key, t))
            if _similarity(key, best) >= MIN_LINK_SCORE:
                matched, why = best, "closest matching title"
        if matched:
            edge("answerKeyFor", key, matched, why)
        else:
            findings.append({"kind": "answer_key_unmatched", "docs": [key.name],
                             "note": "No quiz or worksheet in this unit clearly matches this answer key."})

    # 2. Every other document -> the lesson plan it belongs with (only on real shared subject).
    for d in unit_docs:
        if d.kind in {"lesson_plan", "answer_key"} or not hubs:
            continue
        best = max(hubs, key=lambda p: _similarity(d, p))
        sim = _similarity(d, best)
        if sim >= MIN_LINK_SCORE:
            rel = "assesses" if d.kind in ASSESSMENT_KINDS else "uses"
            edge(rel, d, best, f"shares subject words with the lesson plan (strength {sim:.0f})")

    # 3. A lesson plan that names another file (card.references) -> that file.
    names = {d.name: d for d in unit_docs}
    for plan in hubs:
        for ref in plan.card.get("references") or []:
            ref = str(ref)
            if ref.lower().startswith("http"):
                continue
            rt = set(tokens(ref))
            if len(rt) < 2:
                continue
            for other in unit_docs:
                if other is plan:
                    continue
                if rt <= set(tokens(stem_of(other.name))):
                    edge("references", plan, other, f"the lesson plan names it: \"{ref[:60]}\"")

    # Findings -------------------------------------------------------------------
    if unit_docs and not plans:
        findings.append({"kind": "no_lesson_plan", "docs": [], "note": "No lesson plan found in this unit."})
    if unit_docs and not (by_kind.get("exit_ticket") or by_kind.get("quiz")):
        findings.append({"kind": "no_assessment", "docs": [], "note": "No quiz or exit ticket found in this unit."})
    groups: dict[tuple, list[Doc]] = defaultdict(list)
    for d in unit_docs:
        if d.kind in ASSESSMENT_KINDS | {"lesson_plan", "slides", "rubric"}:
            groups[(d.kind, tuple(sorted(tokens(d.stem))), d.day)].append(d)
    for (_k, _t, _day), same in groups.items():
        if len(same) > 1:
            findings.append({"kind": "possible_duplicate", "docs": [d.name for d in same],
                             "note": "Same kind of document with the same title words" +
                                     (f" for day {same[0].day}" if same[0].day else "") + ". Which is current?"})

    # A unit whose linked documents fall into 2+ separate groups, each with its own plan,
    # probably holds two lessons merged by the organiser.
    parent = {d.name: d.name for d in unit_docs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e["from"])] = find(e["to"])
    comps: dict[str, list[Doc]] = defaultdict(list)
    for d in unit_docs:
        comps[find(d.name)].append(d)
    rich = [c for c in comps.values() if len(c) >= 3 and any(d.kind == "lesson_plan" for d in c)]
    if len(rich) >= 2:
        findings.append({"kind": "possible_split", "docs": [d.name for c in rich for d in c if d.kind == "lesson_plan"],
                         "note": "This unit contains separate groups of documents that do not connect to each other; "
                                 "it may be two lessons merged into one unit."})
    return edges, findings


# ------------------------------------------------------------------------------ build
def build_graph(cards: dict, units: dict, project_id: str = "") -> dict:
    """Pure function: cards + the organiser's units -> graph (nodes, edges, findings, stats)."""
    docs = {n: Doc(name=n, card=c or {}, kind=doc_kind(n, c or {})) for n, c in cards.items()}
    for name in docs:
        docs[name].day = day_in_name(name)
        docs[name].toks = _doc_tokens(name, docs[name].card)
    place_documents(units, docs)

    nodes: list[dict] = [{"id": f"course:{project_id}", "type": "Course", "name": project_id or "course"}]
    edges: list[dict] = []
    findings: list[dict] = []
    ids: dict[str, str] = {}
    stem_count = Counter(d.stem for d in docs.values())
    for d in docs.values():
        ids[d.name] = f"material:{d.stem}" if stem_count[d.stem] == 1 else f"material:{d.name}"

    unit_order = [*units, SHELF_ID]
    for uid in unit_order:
        members = [d for d in docs.values() if (d.unit or SHELF_ID) == uid]
        if uid != SHELF_ID:
            title = (units.get(uid) or {}).get("title") or uid
            nodes.append({"id": f"unit:{uid}", "type": "LessonGrouping", "name": title, "groupName": "unit"})
            edges.append({"rel": "hasPart", "from": f"course:{project_id}", "to": f"unit:{uid}", "why": "organiser unit"})
        elif members:
            nodes.append({"id": f"unit:{SHELF_ID}", "type": "Shelf", "name": "Unattached"})
        if not members:
            continue
        unit_node = f"unit:{uid}"

        # Days come only from the lesson plan's own day numbers, never invented.
        plan_days: set[int] = set()
        for d in members:
            if d.kind == "lesson_plan":
                plan_days |= {int(x) for x in d.card.get("day_numbers") or [] if str(x).isdigit() and 1 <= int(x) <= 30}
        explicit_days = {d.day for d in members if d.day}
        day_ids = {n: f"lesson:{uid}:d{n}" for n in sorted(plan_days | explicit_days)}
        if uid != SHELF_ID:
            for n, did in day_ids.items():
                nodes.append({"id": did, "type": "Lesson", "name": f"Day {n}"})
                edges.append({"rel": "hasPart", "from": unit_node, "to": did,
                              "why": "day found in the lesson plan" if n in plan_days else "day named in a file name"})

        for d in members:
            node = {"id": ids[d.name], "type": "Material", "name": d.name, "source_file": d.name,
                    "doc_type": d.kind, "role": LEGACY_ROLE.get(d.kind, "other"), "placement": d.placement}
            nodes.append(node)
            edges.append({"rel": "hasPart", "from": unit_node, "to": ids[d.name], "why": d.placement})
            if uid != SHELF_ID and d.day and d.day in day_ids:
                edges.append({"rel": "spanIn", "from": day_ids[d.day], "to": ids[d.name], "why": f"\"Day {d.day}\" in the file name"})
            if uid != SHELF_ID and d.kind == "lesson_plan":
                for n in sorted(plan_days):
                    edges.append({"rel": "spanIn", "from": day_ids[n], "to": ids[d.name], "why": "day found in the lesson plan"})
            if d.kind in ASSESSMENT_KINDS:
                aid = f"assessment:{d.stem}" if stem_count[d.stem] == 1 else f"assessment:{d.name}"
                nodes.append({"id": aid, "type": "Assessment", "name": d.stem, "assessment_kind": d.kind})
                edges.append({"rel": "uses", "from": aid, "to": ids[d.name], "why": "assessment file"})

        if uid == SHELF_ID:
            for d in members:
                findings.append({"unit": SHELF_ID, "kind": "unattached", "docs": [d.name], "note": d.placement})
            continue
        e, f = link_unit(members)
        for x in e:
            edges.append({**x, "from": ids[x["from"]], "to": ids[x["to"]]})
        findings.extend({"unit": uid, **x} for x in f)

    stats = {
        "documents": len(docs),
        "units": len([u for u in units]),
        "placed_by_organiser": sum(1 for d in docs.values() if d.placement.startswith("organiser")),
        "placed_by_evidence": sum(1 for d in docs.values() if d.placement.startswith("shared by the organiser")),
        "unattached": sum(1 for d in docs.values() if d.unit is None),
        "kinds": dict(Counter(d.kind for d in docs.values())),
        "links": dict(Counter(e["rel"] for e in edges if e["rel"] not in {"hasPart", "spanIn"})),
        "findings": dict(Counter(f["kind"] for f in findings)),
    }
    # Sanity check (data-pipeline guardrail): every document appears exactly once as a Material.
    materials = [n["source_file"] for n in nodes if n["type"] == "Material"]
    assert sorted(materials) == sorted(docs), "every document must appear exactly once"
    return {"project_id": project_id, "method": "graph-from-cards-v1", "nodes": nodes, "edges": edges,
            "findings": findings, "stats": stats}


# --------------------------------------------------------------------------- load/main
def load_inputs(project_dir: Path) -> tuple[dict, dict]:
    """cards.json + the organiser's units from manifest.yaml. Fails with an actionable message."""
    cards_path = project_dir / "ingest" / "cards.json"
    manifest_path = project_dir / "manifest.yaml"
    for p in (cards_path, manifest_path):
        if not p.is_file():
            raise SystemExit(f"missing {p}: run Organise first")
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    if not isinstance(cards, dict) or not cards:
        raise SystemExit(f"{cards_path} has no documents")
    import yaml  # installed in the app image; not needed by build_graph()

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    units = manifest.get("units") or {}
    if not units:
        raise SystemExit(f"{manifest_path} has no units")
    return cards, units


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="directory to write graph.json into")
    args = ap.parse_args()
    cards, units = load_inputs(args.project_dir)
    graph = build_graph(cards, units, args.project_dir.name)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "graph.json").write_text(json.dumps(graph, indent=1), encoding="utf-8")
    print(json.dumps(graph["stats"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
