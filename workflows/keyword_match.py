#!/usr/bin/env python3
"""Word-boundary keyword matching for checklist presence extractors.

Educational note: the obvious way to test a checklist keyword is
`keyword in text.lower()`, and every path started that way. On real documents
that silently over-reports, because a substring match does not respect word
edges. Observed on the Waxahachie culinary syllabi:

    "PPE"    matched  Cli(ppe)rs, ha(ppe)n, dro(ppe)d   -> "lab safety present"
    "credit" matched  extra credit                      -> "course credit stated"
    "cover"  matched  recipe cover to protect from food -> "TEKS coverage claim"

Each one turned an absent syllabus section into PRESENT, and because presence
is the input to the rung rollups, a false hit becomes a passing grade nobody
questions. A false PRESENT is worse than a false MISSING here: a gap the
auditor never reports is a gap the teacher never fixes.

Two rules make the match trustworthy:

1. Anchor on word boundaries, but only at edges that are word characters, so
   punctuation-shaped keywords ("%", "§", "A:") still match literally.
2. Let whitespace inside a phrase stretch. Text extracted from .docx and .pdf
   is full of split runs ("A bsences", "Format i ve"), so a phrase keyword
   with a rigid single space misses text a human reads as contiguous.

Exclusions cover the residue: "extra credit" contains the word "credit" at a
clean boundary, so only an explicit negative can keep it from counting as a
course credit statement.
"""

from __future__ import annotations

import re
from functools import lru_cache

_WORD = re.compile(r"\w")


@lru_cache(maxsize=2048)
def compile_keyword(keyword: str) -> re.Pattern[str] | None:
    """Compile one checklist keyword into a boundary-aware pattern.

    A trailing plural is allowed, because a checklist author writing
    "due date" means the section whether or not the document says "due dates",
    and a boundary alone would reject the plural. Only a simple "s" is
    accepted; guessing harder stems is how a matcher starts inventing hits.

    Returns None for an empty keyword so callers can skip it rather than
    compile `\\b\\b`, which matches everywhere.
    """
    kw = str(keyword).strip()
    if not kw:
        return None
    body = r"\s+".join(re.escape(part) for part in kw.split())
    # A boundary is only meaningful next to a word character. Anchoring "%"
    # with \b would demand an adjacent letter and never fire on "60%".
    if _WORD.match(kw[-1]):
        body += r"s?\b"
    prefix = r"\b" if _WORD.match(kw[0]) else ""
    return re.compile(prefix + body, re.IGNORECASE)


def matched_keywords(
    text: str,
    keywords: list | tuple,
    exclude: list | tuple = (),
) -> list[str]:
    """Return the keywords that genuinely appear in text, in checklist order.

    A keyword is dropped when every one of its matches sits inside an excluded
    phrase - "credit" inside "extra credit" is not a course credit statement,
    but "credit" elsewhere in the same document still counts.
    """
    if not text or not keywords:
        return []
    spans = _excluded_spans(text, exclude)
    hits: list[str] = []
    for keyword in keywords:
        pattern = compile_keyword(str(keyword))
        if pattern is None:
            continue
        for m in pattern.finditer(text):
            if not _inside(m.start(), m.end(), spans):
                hits.append(str(keyword))
                break
    return hits


def matches(text: str, keywords: list | tuple, exclude: list | tuple = ()) -> bool:
    """True when any keyword genuinely appears in text."""
    return bool(matched_keywords(text, keywords, exclude))


def match_context(
    text: str,
    keywords: list | tuple,
    exclude: list | tuple = (),
    width: int = 100,
) -> str:
    """The text around the first real hit, for use as the cited evidence.

    A reviewer checks a PRESENT by reading its citation, so the citation has to
    be the sentence that caused it. Quoting the head of the excerpt instead
    makes a correct hit look arbitrary and hides a wrong one - "attendance
    present" citing a paragraph about a phone app is unreviewable either way.
    """
    if not text or not keywords:
        return ""
    spans = _excluded_spans(text, exclude)
    best: tuple[int, int] | None = None
    for keyword in keywords:
        pattern = compile_keyword(str(keyword))
        if pattern is None:
            continue
        for m in pattern.finditer(text):
            if _inside(m.start(), m.end(), spans):
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), m.end())
            break
    if best is None:
        return ""
    a = max(0, best[0] - width // 2)
    b = min(len(text), best[1] + width)
    snippet = " ".join(text[a:b].split())
    return ("..." if a > 0 else "") + snippet + ("..." if b < len(text) else "")


def _excluded_spans(text: str, exclude: list | tuple) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in exclude or ():
        pattern = compile_keyword(str(phrase))
        if pattern is None:
            continue
        spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    return spans


def _inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= start and end <= e for s, e in spans)
