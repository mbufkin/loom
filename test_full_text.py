#!/usr/bin/env python3
"""Every model stage reads every document in full (docs/BETS.md, Bet 1).

Fake models only -- no network. Covers:

- organise: one card per document from its FULL text (content past the first
  200 characters changes the grouping), a document over layer0's threshold read
  in parts, cards reused from cache on a re-organise, and a shortfall failing;
- sorting (graph): evidence over the per-call budget batched with nothing
  dropped, answers merged;
- curriculum review and Path A placement: candidates over budget judged in a
  tournament where every candidate is read;
- the path workflows' text fallback reading the whole file;
- the per-stage and per-run "Full-text check" lines.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import audit_lib  # noqa: E402
import ingest  # noqa: E402
from layer0 import CHUNK_THRESHOLD_CHARS, split_into_chunks  # noqa: E402

# Two documents whose first 200+ characters are the same boilerplate; only the
# body says which unit each belongs to. Grouping from 200-char excerpts could
# not tell them apart.
BOILERPLATE = "Career and Technical Education course packet. " * 6  # ~280 chars


def _doc(name: str, body: str) -> dict:
    text = f"{BOILERPLATE}\n\n{body}"
    return {
        "source_file": name,
        "source_format": name.rsplit(".", 1)[-1],
        "doc_type": "unknown",
        "day_hints": [],
        "unit_length_days_hint": None,
        "title": name,
        "excerpt_head": text[:500],
        "content_clean": text,
        "char_count_clean": len(text),
    }


def _reply(obj) -> dict:
    return {"choices": [{"message": {"content": json.dumps(obj)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def _days(n: int) -> list[dict]:
    return [{"id": f"d{i}", "label": f"Day {i}", "expected": ["lesson_content"]}
            for i in range(1, n + 1)]


class _FakeOrganiser:
    """Cards from what the text says; a plan grouped by the cards' unit cues."""

    def __init__(self) -> None:
        self.card_calls: list[str] = []
        self.plan_prompts: list[str] = []

    def __call__(self, cfg, role, messages, step, temperature=0.1):
        prompt = messages[0]["content"]
        if step.startswith("organise-card"):
            self.card_calls.append(step)
            text = prompt.split("DOCUMENT TEXT:", 1)[1]
            cues = sorted(set(re.findall(r"Unit \d+", text)))
            return _reply({"topic": "t", "unit_cues": cues, "role": "lesson_plan",
                           "day_numbers": [int(d) for d in re.findall(r"Day (\d+)", text)]})
        self.plan_prompts.append(prompt)
        groups: dict[str, list[str]] = {}
        for m in re.finditer(r"^- (\S+) \|.*\n  card: (\{.*\})$", prompt, re.M):
            card = json.loads(m.group(2))
            for cue in card.get("unit_cues") or ["Unit 0"]:
                groups.setdefault(cue, []).append(m.group(1))
        units = [
            {"unit_id": cue.lower().replace(" ", "-"), "title": cue, "source_files": files,
             "calendar": {"unit_length_days": 2, "days": _days(2)}}
            for cue, files in sorted(groups.items())
        ]
        return _reply({"school_calendar_hint": None, "units": units})


def _run_ingest(records: list[dict], fake: _FakeOrganiser, tmp: Path) -> tuple[Path, list[str]]:
    logged: list[str] = []
    saved = (ingest.model_call, ingest.build_catalog, ingest.load_config,
             ingest.project_dir, ingest.log, audit_lib.log)
    ingest.model_call = fake
    ingest.build_catalog = lambda sources: ([dict(r) for r in records], [])
    ingest.load_config = lambda: {}
    ingest.project_dir = lambda pid: tmp / pid
    ingest.log = audit_lib.log = logged.append
    try:
        root = ingest.ingest("demo", tmp / "sources")
    finally:
        (ingest.model_call, ingest.build_catalog, ingest.load_config,
         ingest.project_dir, ingest.log, audit_lib.log) = saved
    return root, logged


def test_organise_groups_from_the_full_text_not_the_opening() -> None:
    records = [
        _doc("packet-a.docx", "Day 1 warm-up.\n\nThis packet is Unit 7: welding safety."),
        _doc("packet-b.docx", "Day 1 warm-up.\n\nThis packet is Unit 2: hand tools."),
    ]
    assert records[0]["content_clean"][:200] == records[1]["content_clean"][:200]
    fake = _FakeOrganiser()
    root, logged = _run_ingest(records, fake, Path(tempfile.mkdtemp(prefix="loom-ft-")))

    import yaml

    manifest = yaml.safe_load((root / "manifest.yaml").read_text())
    units = {uid: u["documents"] for uid, u in manifest["units"].items()}
    assert units == {"unit-2": ["packet-b.docx"], "unit-7": ["packet-a.docx"]}, units
    # The grouping prompt carried the cards, not 200-char excerpts.
    assert '"unit_cues":["Unit 7"]' in fake.plan_prompts[0]
    assert "excerpt:" not in fake.plan_prompts[0]
    assert "organise: packet-a.docx: read" in "\n".join(logged)
    assert any(l.startswith("Full-text check: organise 2/2 documents read in full") for l in logged), logged


def test_a_large_document_is_read_in_parts_and_cards_are_cached() -> None:
    para = "Students practise the bead weld and log each pass. " * 40  # ~2K chars
    big_body = "\n\n".join([para] * 60) + "\n\nThe final project closes Unit 9."
    records = [_doc("big-manual.pdf", big_body), _doc("small.docx", "Unit 9 quiz, Day 3.")]
    assert records[0]["char_count_clean"] > CHUNK_THRESHOLD_CHARS
    expected_parts = len(split_into_chunks(records[0]["content_clean"]))
    assert expected_parts >= 2

    tmp = Path(tempfile.mkdtemp(prefix="loom-ft-"))
    fake = _FakeOrganiser()
    root, logged = _run_ingest(records, fake, tmp)
    big_calls = [c for c in fake.card_calls if "big-manual" in c]
    assert len(big_calls) == expected_parts, big_calls
    n = records[0]["char_count_clean"]
    assert f"organise: big-manual.pdf: read {n} chars in {expected_parts} part(s)" in logged
    # "Unit 9" only appears in the LAST part; the merged card still has it.
    cards = json.loads((root / "ingest" / "cards.json").read_text())
    assert cards["big-manual.pdf"]["unit_cues"] == ["Unit 9"]
    assert any(f"(1 in {expected_parts} parts)" in l for l in logged), logged

    # Re-organise with unchanged documents: no card calls at all.
    again = _FakeOrganiser()
    _root, logged2 = _run_ingest(records, again, tmp)
    assert again.card_calls == [], again.card_calls
    assert any("card reused" in l for l in logged2)
    assert any("unchanged since a full read" in l for l in logged2), logged2

    # A changed document is re-read; the unchanged one is not.
    changed = [records[0], _doc("small.docx", "Unit 9 quiz, Day 4.")]
    third = _FakeOrganiser()
    _run_ingest(changed, third, tmp)
    assert third.card_calls == ["organise-card-small"], third.card_calls


def test_organise_fails_if_a_document_was_not_sent_in_full() -> None:
    records = [_doc("cut.docx", "Unit 1.\n\n" + "More text. " * 50)]
    saved = ingest.document_parts
    ingest.document_parts = lambda text: [text[: len(text) // 2]]
    try:
        _run_ingest(records, _FakeOrganiser(), Path(tempfile.mkdtemp(prefix="loom-ft-")))
    except audit_lib.FullTextError as e:
        assert "cut.docx" in str(e)
    else:
        raise AssertionError("a half-sent document must fail organise")
    finally:
        ingest.document_parts = saved


def test_graph_batches_oversized_evidence_and_drops_nothing() -> None:
    import graph_phase

    elements = [
        {"element_id": f"e{i}", "element_type": "direct_instruction",
         "excerpt": (f"LSN{i} " if i in (2, 17) else "") + "x" * 400 + (" teacher note" if i == 15 else "")}
        for i in range(1, 21)
    ]
    prompts: list[str] = []

    def fake_model_chat(cfg, role, messages, step, **kw):
        p = messages[0]["content"]
        prompts.append(p)
        if step.startswith("role-"):
            return _reply({"role": "teacher_edition" if "teacher note" in p else "other"})
        if step.startswith("lessons-"):
            # A marker the prompt template never contains (it quotes "Lesson 4").
            nums = sorted({int(n) for n in re.findall(r"LSN(\d+)", p)})
            return _reply({"covers_lesson_numbers": nums,
                           "citations": [{"excerpt_head": f"LSN{n}"} for n in nums]})
        return _reply({"is_assessment_bearing": False})

    saved = (graph_phase.model_chat, graph_phase.prompt_budget_chars)
    graph_phase.model_chat = fake_model_chat
    graph_phase.prompt_budget_chars = lambda: 3000  # ~6 elements per batch
    try:
        batches = graph_phase.evidence_batches(elements)
        role = graph_phase.step_role({}, "pack.pdf", elements)
        lessons = graph_phase.step_lessons({}, "pack.pdf", elements, role["role"])
    finally:
        graph_phase.model_chat, graph_phase.prompt_budget_chars = saved

    assert len(batches) >= 3 and sum(len(b) for b in batches) == len(elements)
    # Every element reached a role prompt and a lessons prompt.
    for el in elements:
        js = json.dumps(el, ensure_ascii=False)
        assert any(js in p for p in prompts[: len(batches)]), el["element_id"]
        assert any(js in p for p in prompts[len(batches):]), el["element_id"]
    assert "part 1 of" in prompts[0]
    # Only one batch saw the teacher note; the specific role still wins.
    assert role["role"] == "teacher_edition" and role["parts"] == len(batches)
    # Lessons 2 and 17 sit in different batches; both survive the merge.
    assert lessons["covers_lesson_numbers"] == [2, 17], lessons


def test_graph_merges_assessment_by_majority_of_evidence() -> None:
    import graph_phase

    small_yes = ({"is_assessment_bearing": True, "assessment_lesson_numbers": [3]}, 2)
    big_no = ({"is_assessment_bearing": False}, 30)
    merged = graph_phase.merge_assessment_answers("learn.pdf", [small_yes, big_no])
    assert merged["is_assessment_bearing"] is False, "an exit ticket in one part is not the file"
    merged = graph_phase.merge_assessment_answers(
        "practice.pdf", [({"is_assessment_bearing": True, "assessment_lesson_numbers": [1]}, 20),
                         ({"is_assessment_bearing": True, "assessment_lesson_numbers": [2]}, 10)])
    assert merged["is_assessment_bearing"] is True
    assert merged["assessment_lesson_numbers"] == [1, 2]


def test_cursor_evidence_pack_keeps_every_element() -> None:
    import graph_phase

    els = [{"element_id": f"e{i}"} for i in range(250)]
    pack = graph_phase.pack_evidence_for_agent(els)
    assert pack["n_elements_included"] == 250 and pack["truncation_note"] is None


def test_curriculum_review_reads_every_candidate_in_a_tournament() -> None:
    import curriculum_review as cr

    class El:
        def __init__(self, i, etype):
            self.element_id = f"el{i}"
            self.excerpt = f"Practice item {i}. " + "y" * 900
            self.element_type = etype

    els = [El(i, "guided_practice") for i in range(1, 13)] + [El(99, "standards_objectives")]
    tag_map = cr.assemble_tagged(els)
    cands = cr.build_candidates(tag_map)
    assert len(cands["practice"]) == 12, "no per-role cap"

    def fake_model_chat(cfg, role, messages, step, **kw):
        block = messages[1]["content"]
        tags = re.findall(r"\[(E\d+)\]", block)
        practice = [t for t in tags if t != "E13"]
        return _reply({"objective": "E13" if "E13" in tags else None,
                       "practice": practice[-1] if practice else None})

    saved = (cr.model_chat, cr.prompt_budget_chars)
    cr.model_chat = fake_model_chat
    cr.prompt_budget_chars = lambda: 3000
    prompts: list[str] = []
    try:
        verified = cr.stage1_select({}, cands, tag_map, prompts=prompts)
    finally:
        cr.model_chat, cr.prompt_budget_chars = saved
    for el in els:
        assert any(el.excerpt in p for p in prompts), el.element_id
    assert len(prompts) > 2, "batches plus a final round"
    assert verified["practice"]["tag"] == "E12" and verified["objective"]["tag"] == "E13"


def test_path_a_placement_reads_every_candidate() -> None:
    from workflows import lesson_plan as lp

    elements = [{"element_id": f"a{i}", "element_type": "direct_instruction", "doc_id": "d1",
                 "excerpt": f"Step {i}. " + "z" * 700} for i in range(1, 16)]
    calls: list[str] = []

    def fake_model_chat(cfg, role, messages, step, **kw):
        user = messages[1]["content"]
        calls.append(user)
        ids = re.findall(r'"element_id": "(a\d+)"', user)
        return _reply({"assignments": {"objective": ids[0] if ids else None}})

    saved = (lp.model_chat, lp.prompt_budget_chars)
    lp.model_chat = fake_model_chat
    lp.prompt_budget_chars = lambda: 2500
    prompts: list[str] = []
    try:
        out = lp._a6_assign({}, ["objective"], [
            {"element_id": e["element_id"], "element_type": e["element_type"], "excerpt": e["excerpt"]}
            for e in elements
        ], prompts)
    finally:
        lp.model_chat, lp.prompt_budget_chars = saved
    pieces = [e["excerpt"] for e in elements]
    assert audit_lib.covered_chars(pieces, prompts) == sum(len(p) for p in pieces)
    assert out == {"objective": "a1"}, out
    assert len(calls) > 1


def test_workflow_text_fallback_reads_the_whole_file() -> None:
    import importlib

    tmp = Path(tempfile.mkdtemp(prefix="loom-ft-"))
    (tmp / "sources").mkdir()
    text = "Opening.\n" + "filler " * 3000 + "\nRubric criteria at the very end."
    (tmp / "sources" / "doc_abc_handout.txt").write_text(text, encoding="utf-8")
    for name in ("general", "quiz", "exit_ticket", "standards_pacing",
                 "student_practice", "teacher_support"):
        mod = importlib.import_module(f"workflows.{name}")
        els = mod._source_text_elements(tmp, "abc", "doc_abc_handout.txt")
        # Path C prefixes the filename; every path must carry the whole text.
        assert text in els[0]["excerpt"] and len(text) > 8000, name


def test_full_text_lines_per_stage_and_per_run() -> None:
    import run_project

    tmp = Path(tempfile.mkdtemp(prefix="loom-ft-"))
    saved = audit_lib.project_dir
    audit_lib.project_dir = lambda pid: tmp / pid
    logged: list[str] = []
    saved_log = audit_lib.log
    audit_lib.log = logged.append
    saved_data = run_project.DATA_DIR
    run_project.DATA_DIR = tmp / "live"
    try:
        live = tmp / "live" / "projects" / "p"
        audit_lib.reset_coverage("p", "organise", root=live)
        audit_lib.record_coverage("p", "organise", "a.docx", available=10, sent=10, root=live)
        audit_lib.record_coverage("p", "organise", "b.pdf", available=500, sent=500, parts=3, root=live)
        audit_lib.reset_coverage("p", "sorting")
        audit_lib.record_coverage("p", "sorting", "a.docx", available=40, sent=40)
        # The same document in a second unit, sent short: the document is short.
        audit_lib.record_coverage("p", "sorting", "b.pdf", available=90, sent=90)
        audit_lib.record_coverage("p", "sorting", "b.pdf", available=90, sent=60)

        assert audit_lib.check_coverage("p", "organise", "organise", root=live) == (
            "organise 2/2 documents read in full (1 in 3 parts)"
        )
        try:
            audit_lib.check_coverage("p", "sorting", "sorting")
        except audit_lib.FullTextError as e:
            assert "b.pdf: 30 chars not sent" in str(e)
        else:
            raise AssertionError("a shortfall must raise")
        assert "Full-text check: sorting 1/2 documents read in full" in logged

        line, short = run_project.full_text_line("p")
        assert line == (
            "Full-text check: organise 2/2 documents read in full (1 in 3 parts); "
            "sorting 1/2 documents read in full"
        ), line
        assert short == ["sorting: b.pdf: 30 chars not sent"]
    finally:
        audit_lib.project_dir = saved
        audit_lib.log = saved_log
        run_project.DATA_DIR = saved_data


def test_covered_chars_sees_text_inside_json_prompts() -> None:
    piece = 'He said "weld"\nthen stopped.'
    prompt = json.dumps({"elements": [{"excerpt": piece}]}, ensure_ascii=False)
    assert audit_lib.covered_chars([piece], [prompt]) == len(piece)
    assert audit_lib.covered_chars([piece], ["unrelated"]) == 0



class _BadThenGood(_FakeOrganiser):
    """The first N card replies for one file are broken JSON, then good."""

    def __init__(self, bad_file: str, bad_times: int) -> None:
        super().__init__()
        self.bad_file, self.bad_left = bad_file, bad_times
        self.retry_messages: list[list[dict]] = []

    def __call__(self, cfg, role, messages, step, temperature=0.1):
        if step.startswith("organise-card") and self.bad_file in step:
            if "-retry" in step:
                self.retry_messages.append(messages)
            if self.bad_left > 0:
                self.bad_left -= 1
                return {"choices": [{"message": {"content": '{"topic": "a "quoted" word", "role": "quiz"}'}}]}
        return super().__call__(cfg, role, messages, step, temperature)


def test_a_bad_card_reply_is_re_asked_with_the_full_document() -> None:
    records = [_doc("exit-ticket.docx", "Unit 3 exit ticket.\n\nDay 4 check."),
               _doc("plan.docx", "Unit 3 lesson plan, Day 4.")]
    fake = _BadThenGood("exit-ticket", bad_times=1)
    root, logged = _run_ingest(records, fake, Path(tempfile.mkdtemp(prefix="loom-ft-")))
    assert (root / "manifest.yaml").is_file()
    assert any("not valid JSON" in l and "asking again" in l for l in logged), logged
    # The re-ask carries the whole original prompt, the bad reply and the error.
    msgs = fake.retry_messages[0]
    assert "Unit 3 exit ticket." in msgs[0]["content"] and "Day 4 check." in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant" and "not valid JSON" in msgs[2]["content"]
    assert any(l.startswith("Full-text check: organise 2/2") for l in logged), logged


def test_a_card_that_never_parses_still_fails_loudly() -> None:
    records = [_doc("exit-ticket.docx", "Unit 3 exit ticket."), _doc("plan.docx", "Unit 3 plan.")]
    fake = _BadThenGood("exit-ticket", bad_times=99)
    try:
        _run_ingest(records, fake, Path(tempfile.mkdtemp(prefix="loom-ft-")))
    except (ValueError, SystemExit) as e:
        assert "re-ask" in str(e) or isinstance(e, SystemExit), e
    else:
        raise AssertionError("organise should fail when a card never parses")
    assert len(fake.retry_messages) == ingest.CARD_JSON_RETRIES

TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
