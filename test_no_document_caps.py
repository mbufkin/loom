#!/usr/bin/env python3
"""Guard: production code must not cap document text on its way to a model.

Loom's doctrine (docs/BETS.md, Bet 1) is that the model reads every document in
full. Large documents are split into parts (layer0.CHUNK_THRESHOLD_CHARS /
CHUNK_SIZE_CHARS) and the per-part answers merged; nothing is cut to save
context or cost. Caps creep back in quietly -- a helper adds `text[:8000]` "to
keep the prompt sane" and nothing fails, the audit just judges less of the
document than it claims to. This test makes that a red build.

It parses every production module (repo root and workflows/, never tests,
tools, experiments or the UI) and flags:

- a slice with an upper bound (`x[:N]`, `x[a:b]`) applied to anything named
  like document text or a collection of document pieces;
- `textwrap.shorten(...)`, the workflows' `_trunc(...)` helper, or any call
  passing `max_chars=` / `limit=` on such a value.

Display, log and output-only truncation is allowed, but only through ALLOWLIST
below: each entry is (file, exact source of the flagged expression) plus a
one-line reason. A new hit must either be fixed (chunk and merge) or added
there with a reason a reviewer can check.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Identifier fragments (prefixes) that mean "document text, or pieces of a
# document": `cleaned`, `excerpt_head`, `candidates`, `paragraphs` all match.
TEXT_WORDS = (
    "text", "content", "excerpt", "body", "full", "clean", "paragraph",
    "evidence", "element", "els", "candidate", "cands", "chunk", "record", "prompt",
)
# An upper bound named like a cap is flagged whatever it slices.
CAP_WORDS = ("max", "cap", "limit")
# A function that calls one of these sends a prompt; display helpers such as
# _trunc are only a problem inside such functions (or ones named *prompt*).
MODEL_CALLS = ("model_chat", "model_call", "chat_json", "call_and_parse")
DISPLAY_HELPERS = ("shorten", "_trunc", "truncate")

EXCLUDE_PARTS = {"tests", "tools", "experiments", "archive", "ui", "hosted",
                 "deploy", "node_modules", "projects", "data", "e2e", "scratch"}

# (relative path, exact flagged source) -> why it is not a cap on model input.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("audit_lib.py", "e.response.text[:300]"):
        "HTTP error body quoted in an error message",
    ("audit_lib.py", "cleaned[:500]"):
        "excerpt_head record field kept for catalog.json shape; no prompt reads it",
    ("curriculum_review.py", "tag_map[tag]['excerpt'][:55]"):
        "verbose console print",
    ("curriculum_review.py", "content[:800]"):
        "verbose console print of an unparseable model reply",
    ("curriculum_review.py", 'tag_map[tag]["excerpt"][:300]'):
        "evidence quote in the UI plate; the model saw the full excerpt",
    ("curriculum_review.py", 'v["excerpt"][:300]'):
        "role quote in the UI plate; the model saw the full excerpt",
    ("inbox-watch.py", "s[:max_len]"):
        "project slug made from a filename",
    ("layer0.py", 'hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]'):
        "short content hash used as an id",
    ("layer0.py", "full_text[:ORIENTATION_CHARS]"):
        "orientation preamble repeated on every part; each part is still sent whole",
    ("layer0.py", "paths[:limit]"):
        "--limit developer flag (number of files); run_project never passes it",
    ("layer1.py", 'normalize_ws(row["excerpt"])[:200]'):
        "near-duplicate key over ledger rows; decides duplicates, not what a model reads",
    ("layer1.py", "r['excerpt'][:200]"):
        "quote in the human review-queue markdown",
    ("lesson_bakeoff.py", "lessons[:limit]"):
        "lab CLI --limit (number of lessons); not on the audit path",
    ("lesson_quality.py", "ev.excerpt[:300]"):
        "evidence quote in the output plate; the model saw the full excerpt",
    ("lesson_quality.py", "c.evidence[0].excerpt[:200]"):
        "evidence quote in the markdown plate",
    ("lesson_scoring.py", '(self.excerpt or "")[:400]'):
        "evidence quote serialised into the scorer artifact",
    ("report_delivery.py", "t[: limit - 1]"):
        "report synthesis: quotes inside the findings pack, not documents being judged",
    ("report_delivery.py",
     "sorted( (u for u in rollup if (u.get(key) or 0) > 0), key=lambda u: u[key], "
     "reverse=True, )[:limit]"):
        "top-N units by a count for the report; numbers, not document text",
    ("report_delivery.py", "roll[: max(8, len(roll) - 4)]"):
        "report synthesis packing of per-unit counts, not document text",
    ("synthesize.py", '(excerpt or "")[:220]'):
        "quote in the cross-unit report",
    ("synthesize.py",
     'next( ( c["excerpt"] for c in r["components_present"] '
     'if (c.get("excerpt") or "").strip() ), "", )[:220]'):
        "sample quote in the report's incomplete-documents table",
    ("unit_plan_fill.py", "t[: limit - 1]"):
        "_trunc itself: display helper for plate text (flagged where a prompt uses it)",
    ("unit_rung.py", "isolated[:ISOLATED_GAP_CAP]"):
        "list of gaps shown in the unit plate; the full count is kept beside it",
    ("workflows/lesson_plan.py", '(c.get("excerpt") or "")[:80]'):
        "dedupe key in the no-model fallback; decides reuse, not what a model reads",
}


def production_files() -> list[Path]:
    out = []
    for p in sorted(BASE.rglob("*.py")):
        rel = p.relative_to(BASE)
        if any(part in EXCLUDE_PARTS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if len(rel.parts) > 1 and rel.parts[0] != "workflows":
            continue
        name = rel.name
        if name.startswith("test_") or name.startswith("spike") or name == "conftest.py":
            continue
        out.append(p)
    return out


def _words(node: ast.AST) -> set[str]:
    """Identifier fragments mentioned in an expression (names, attributes,
    string keys like r['excerpt'] or e.get('excerpt'))."""
    found: set[str] = set()
    for n in ast.walk(node):
        ident = None
        if isinstance(n, ast.Name):
            ident = n.id
        elif isinstance(n, ast.Attribute):
            ident = n.attr
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
            ident = n.value
        if ident:
            found.update(f for f in ident.lower().strip("_").split("_") if f)
    return found


def _mentions(node: ast.AST, words: tuple[str, ...]) -> bool:
    return any(f.startswith(w) for f in _words(node) for w in words)


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _sends_prompt(fn: ast.AST) -> bool:
    if "prompt" in getattr(fn, "name", "").lower():
        return True
    return any(
        isinstance(n, ast.Call) and any(m in _call_name(n) for m in MODEL_CALLS)
        for n in ast.walk(fn)
    )


def _seg(src: str, node: ast.AST) -> str:
    """The flagged expression's source, whitespace collapsed (allowlist key)."""
    return " ".join((ast.get_source_segment(src, node) or "").split())


def find_caps(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits: dict[tuple[int, str], None] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            sl = node.slice
            if sl.upper is None or sl.step is not None:
                continue
            # x[i : i + size] in a loop is splitting, not capping: the lower
            # bound moves, so every piece is still sent.
            if sl.lower is not None and not isinstance(sl.lower, ast.Constant):
                continue
            if _mentions(node.value, TEXT_WORDS) or _mentions(sl.upper, CAP_WORDS):
                hits[(node.lineno, _seg(src, node))] = None

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _sends_prompt(fn):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            capped_kw = any(k.arg in {"max_chars", "max_len", "width"} for k in node.keywords)
            if (name.startswith(DISPLAY_HELPERS) or capped_kw) and any(
                _mentions(a, TEXT_WORDS) for a in node.args
            ):
                hits[(node.lineno, _seg(src, node))] = None
    return sorted(hits)


def unallowed_caps() -> list[str]:
    problems = []
    for p in production_files():
        rel = p.relative_to(BASE).as_posix()
        for line, seg in find_caps(p):
            if (rel, seg) not in ALLOWLIST:
                problems.append(f"{rel}:{line}: {seg}")
    return problems


def test_no_document_text_is_capped_before_a_model() -> None:
    problems = unallowed_caps()
    assert not problems, (
        "Document text is cut before it reaches a model (Bet 1: never truncate). "
        "Split into parts and merge instead, or -- for display/log/output only -- "
        "add an ALLOWLIST entry with a reason:\n  " + "\n  ".join(problems)
    )


def test_every_allowlist_entry_still_exists() -> None:
    # A stale entry is a hole: it would silently permit the same expression if
    # someone reintroduced it somewhere it does reach a model.
    present = set()
    for p in production_files():
        rel = p.relative_to(BASE).as_posix()
        present.update((rel, seg) for _line, seg in find_caps(p))
    stale = [f"{f}: {s}" for (f, s) in ALLOWLIST if (f, s) not in present]
    assert not stale, "ALLOWLIST entries no longer match any code:\n  " + "\n  ".join(stale)


def test_the_guard_catches_the_shapes_it_exists_for() -> None:
    # Self-test, so a refactor of the guard cannot quietly make it toothless.
    import tempfile

    bad = (
        "import textwrap\n"
        "def build(record, els, e, text, v, cfg):\n"
        "    a = record['content_clean'][:8000]\n"
        "    b = els[:40]\n"
        "    c = (e.get('excerpt') or '')[:600]\n"
        "    d = textwrap.shorten(text, 200)\n"
        "    g = _trunc(e.get('excerpt') or '', 280)\n"
        "    h = v[:MAX_CANDS]\n"
        "    ok = [text[i : i + 10] for i in range(0, len(text), 10)]\n"
        "    return model_chat(cfg, 'analyst', [a, b, c, d, g, h, ok])\n"
        "def show(e):\n"
        "    return _trunc(e.get('excerpt') or '')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.py"
        p.write_text(bad, encoding="utf-8")
        found = [seg for _l, seg in find_caps(p)]
    assert len(found) == 6, found
    assert not any("i + 10" in s for s in found), "splitting loops are not caps"
    assert not any(s.startswith("_trunc(e.get('excerpt') or '')") for s in found), (
        "a display helper outside a prompt-building function is not a cap"
    )


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
