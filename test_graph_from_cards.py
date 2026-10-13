#!/usr/bin/env python3
"""Tests for graph_from_cards.build_graph (pure function; no model, no disk).

All fixtures are invented. The repo is public: never paste real district file names
or card text into a test.

Run:  python3 test_graph_from_cards.py
"""
from __future__ import annotations

import sys

import graph_from_cards as g


def card(role="other", **kw) -> dict:
    base = {"role": role, "topic": "", "skills": [], "unit_cues": [], "day_numbers": [],
            "references": [], "standards": [], "course_wide": False}
    base.update(kw)
    return base


def two_unit_fixture():
    """Two clearly different units plus shared files the organiser could not place."""
    cards = {
        # unit A: volcano
        "Volcano Lesson Plan.docx": card("lesson_plan", topic="how volcanoes erupt magma lava", day_numbers=[1, 2],
                                        unit_cues=["Volcano eruption"]),
        "Volcano Slides.pptx": card("slides", topic="volcano eruption diagrams"),
        "Volcano Exit Ticket Day 1.docx": card("assessment", topic="volcano magma"),
        "Volcano Exit Ticket Day 2.docx": card("assessment", topic="volcano lava"),
        "Volcano Quiz.pdf": card("assessment", topic="volcano quiz", references=["https://quiz.example/v1"]),
        "Volcano Quiz Answers.pdf": card("answer_key", topic="volcano answers", references=["https://quiz.example/v1"]),
        # unit B: bridges
        "Bridge Lesson Plan.docx": card("lesson_plan", topic="how bridges carry load tension compression",
                                        day_numbers=[1], unit_cues=["Bridge engineering"]),
        "Bridge Slides.pptx": card("slides", topic="bridge truss arch diagrams"),
        "Bridge Rubric.docx": card("rubric", topic="bridge model rubric"),
        # shared (listed under both units by the organiser)
        "Lava Lamp Worksheet.docx": card("student_practice", topic="lava magma density experiment", skills=["volcano density"]),
        "Mystery Worksheet.docx": card("student_practice", topic="general reflection questions"),
    }
    units = {
        "volcano": {"title": "Volcano Science", "documents": [n for n in cards if n.startswith("Volcano")] +
                    ["Lava Lamp Worksheet.docx", "Mystery Worksheet.docx"]},
        "bridges": {"title": "Bridge Engineering", "documents": [n for n in cards if n.startswith("Bridge")] +
                    ["Lava Lamp Worksheet.docx", "Mystery Worksheet.docx"]},
    }
    return cards, units


def materials(graph):
    return [n for n in graph["nodes"] if n["type"] == "Material"]


def unit_of(graph, name):
    mid = next(n["id"] for n in materials(graph) if n["source_file"] == name)
    for e in graph["edges"]:
        if e["rel"] == "hasPart" and e["to"] == mid:
            return e["from"]
    return None


def test_every_document_appears_exactly_once_even_when_shared() -> None:
    cards, units = two_unit_fixture()
    graph = g.build_graph(cards, units, "t")
    names = sorted(n["source_file"] for n in materials(graph))
    assert names == sorted(cards), "a document was dropped or duplicated"
    # The old graph copied shared files into every unit; each must have ONE parent now.
    for name in cards:
        parents = [e for e in graph["edges"] if e["rel"] == "hasPart"
                   and e["to"] == next(n["id"] for n in materials(graph) if n["source_file"] == name)]
        assert len(parents) == 1, f"{name} has {len(parents)} parents"


def test_shared_file_goes_where_the_evidence_points_or_to_the_shelf() -> None:
    cards, units = two_unit_fixture()
    graph = g.build_graph(cards, units, "t")
    assert unit_of(graph, "Lava Lamp Worksheet.docx") == "unit:volcano"
    assert unit_of(graph, "Mystery Worksheet.docx") == f"unit:{g.SHELF_ID}", "ambiguous file must be shelved, not guessed"
    assert any(f["kind"] == "unattached" and f["docs"] == ["Mystery Worksheet.docx"] for f in graph["findings"])


def test_organiser_placement_is_kept_when_unambiguous() -> None:
    cards, units = two_unit_fixture()
    graph = g.build_graph(cards, units, "t")
    assert unit_of(graph, "Bridge Rubric.docx") == "unit:bridges"
    assert graph["stats"]["placed_by_organiser"] == 9


def test_document_kinds() -> None:
    table = {
        "Unit 1 Answer Key.pdf": ("other", "answer_key"),
        "Exit Ticket Day 3.docx": ("assessment", "exit_ticket"),
        "Unit Quizizz.pdf": ("other", "quiz"),
        "Flyer Rubric.docx": ("other", "rubric"),
        "Intro Slides.pptx": ("lesson_plan", "slides"),  # extension beats a wrong card role
        "Week Lesson Plan.docx": ("other", "lesson_plan"),
        "Student Notes.docx": ("other", "handout"),
        "Misc.docx": ("other", "other"),
    }
    for name, (role, want) in table.items():
        assert g.doc_kind(name, {"role": role}) == want, name


def test_answer_key_links_by_shared_url_even_when_titles_differ() -> None:
    cards = {
        "Alpha Lesson Plan.docx": card("lesson_plan"),
        "Unit Check.pdf": card("assessment", references=["https://q.example/abc"]),
        "Totally Different Name.pdf": card("answer_key", references=["https://q.example/abc"]),
    }
    units = {"u": {"title": "Alpha", "documents": list(cards)}}
    graph = g.build_graph(cards, units, "t")
    links = [e for e in graph["edges"] if e["rel"] == "answerKeyFor"]
    assert len(links) == 1 and "same quiz URL" in links[0]["why"]


def test_days_come_only_from_evidence_never_invented() -> None:
    cards = {"Solo Lesson Plan.docx": card("lesson_plan"), "Solo Slides.pptx": card("slides")}
    units = {"u": {"title": "Solo", "documents": list(cards)}}
    graph = g.build_graph(cards, units, "t")
    assert not [n for n in graph["nodes"] if n["type"] == "Lesson"], "no day evidence -> no Lesson nodes"
    cards2, units2 = two_unit_fixture()
    graph2 = g.build_graph(cards2, units2, "t")
    lessons = {n["name"] for n in graph2["nodes"] if n["type"] == "Lesson" and n["id"].startswith("lesson:volcano")}
    assert lessons == {"Day 1", "Day 2"}


def test_duplicate_exit_ticket_is_flagged() -> None:
    cards = {
        "Alpha Lesson Plan.docx": card("lesson_plan"),
        "Alpha Day 2 Exit Ticket.docx": card("assessment"),
        "Alpha Exit Ticket Day 2.docx": card("assessment"),
        "Alpha Exit Ticket Day 3.docx": card("assessment"),
    }
    units = {"u": {"title": "Alpha", "documents": list(cards)}}
    graph = g.build_graph(cards, units, "t")
    dups = [f for f in graph["findings"] if f["kind"] == "possible_duplicate"]
    assert len(dups) == 1 and len(dups[0]["docs"]) == 2


def test_merged_unit_is_reported_and_a_normal_unit_is_not() -> None:
    cards = {
        "Cat Lesson Plan.docx": card("lesson_plan"), "Cat Slides.pptx": card("slides"), "Cat Quiz.pdf": card("assessment"),
        "Dog Lesson Plan.docx": card("lesson_plan"), "Dog Slides.pptx": card("slides"), "Dog Quiz.pdf": card("assessment"),
    }
    merged = {"u": {"title": "Pets", "documents": list(cards)}}
    f = g.build_graph(cards, merged, "t")["findings"]
    assert any(x["kind"] == "possible_split" for x in f)
    single = {k: v for k, v in cards.items() if k.startswith("Cat")}
    f2 = g.build_graph(single, {"u": {"title": "Cat", "documents": list(single)}}, "t")["findings"]
    assert not any(x["kind"] == "possible_split" for x in f2)


def test_file_named_lesson_plan_is_the_hub_over_other_plan_typed_files() -> None:
    cards = {
        "Garden Lesson Plan.docx": card("lesson_plan", topic="garden soil seeds"),
        "Free Curriculum Asset.pdf": card("lesson_plan", topic="garden soil seeds planting guide"),
        "Garden Day 2 Exit Ticket.docx": card("assessment", topic="soil seeds planting guide"),
    }
    units = {"u": {"title": "Garden", "documents": list(cards)}}
    graph = g.build_graph(cards, units, "t")
    mid = {n["source_file"]: n["id"] for n in materials(graph)}
    targets = [e["to"] for e in graph["edges"] if e["rel"] == "assesses"]
    assert targets == [mid["Garden Lesson Plan.docx"]]


def test_unit_without_assessment_is_reported() -> None:
    cards = {"Solo Lesson Plan.docx": card("lesson_plan"), "Solo Slides.pptx": card("slides")}
    graph = g.build_graph(cards, {"u": {"title": "Solo", "documents": list(cards)}}, "t")
    assert any(f["kind"] == "no_assessment" for f in graph["findings"])


def test_every_link_explains_itself_and_output_is_deterministic() -> None:
    cards, units = two_unit_fixture()
    a, b = g.build_graph(cards, units, "t"), g.build_graph(cards, units, "t")
    assert a == b, "same input must give the same graph"
    assert all(e.get("why") for e in a["edges"]), "every edge needs a why"


def test_router_compatible_shapes() -> None:
    """Assessment documents get an Assessment node linked by `uses` (what route.py reads)."""
    cards, units = two_unit_fixture()
    graph = g.build_graph(cards, units, "t")
    by_id = {n["id"]: n for n in graph["nodes"]}
    assessments = [n for n in graph["nodes"] if n["type"] == "Assessment"]
    assert assessments
    for a in assessments:
        uses = [e for e in graph["edges"] if e["rel"] == "uses" and e["from"] == a["id"]]
        assert len(uses) == 1 and by_id[uses[0]["to"]]["type"] == "Material"
    assert {n["role"] for n in materials(graph)} <= {"other", "practice_student"}


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
