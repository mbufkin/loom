"""Layer 0-B must tell the model not to think out loud.

Every step in this pipeline that wants structured JSON passes
enable_thinking=False, and layer0.model_call's comment explains why: a
reasoning model left to think spends the whole token ceiling on monologue and
returns that instead of the answer, and on NVIDIA's gateway the request does
not come back wrong -- it times out at 504 with nothing to parse.

resolve_wide_span was the one Layer 0 call path that never got the flag, and
nothing caught it because the failure is invisible until you run against a
hosted reasoning model. Measured on disd-aas-icev-smoke: Layer 0 decomposed
all 27 documents in nine minutes, then Layer 0-B resolved two of its 23
flagged spans in the next eighteen, every call retrying 504s. Graph, routing,
Layer 1/2 and every report sit behind that step, so the run never finished.
"""

import json

import layer0


class _Recorder:
    """Stands in for model_chat and remembers how it was called."""

    def __init__(self, content: str = '{"decision": "keep", "reasoning": "one element"}'):
        self.content = content
        self.calls: list[dict] = []

    def __call__(self, cfg, role, messages, step, **kwargs):
        self.calls.append({"role": role, "step": step, "messages": messages, **kwargs})
        return {"choices": [{"message": {"content": self.content}}]}


def _row():
    return {
        "element_id": "doc.html-e3",
        "element_type": "assessment_item",
        "excerpt_start_paragraph": 2,
        "excerpt_end_paragraph": 9,
    }


def _paragraphs():
    return [f"paragraph {i}" for i in range(1, 12)]


def test_layer0b_tells_the_model_not_to_think_out_loud(monkeypatch):
    """The flag whose absence stalled a live run."""
    rec = _Recorder()
    monkeypatch.setattr(layer0, "model_chat", rec)

    layer0.resolve_wide_span({}, _row(), _paragraphs())

    assert len(rec.calls) == 1
    assert rec.calls[0].get("enable_thinking") is False, (
        "Layer 0-B asks for a JSON object; without this the reply is a "
        "monologue, or on a hosted gateway, a 504"
    )


def test_layer0b_keeps_a_ceiling_big_enough_for_a_split(monkeypatch):
    """A split reply carries one object per proposed element, not just a verdict.

    Checked alongside the thinking flag because the two failures look the same
    from outside -- an unparseable reply -- but have different causes, and
    fixing one while dropping the other would read as fixed until a dense
    document arrived.
    """
    rec = _Recorder()
    monkeypatch.setattr(layer0, "model_chat", rec)

    layer0.resolve_wide_span({}, _row(), _paragraphs())

    assert rec.calls[0].get("max_tokens") == 16384


def test_layer0b_asks_the_verifier_and_names_the_element_in_the_step(monkeypatch):
    """Step ids carry the element so a 504 in the log says which one failed.

    The stalled run was only diagnosable because the warning line read
    "034-urinary__assessment-answer-key.html-e3-layer0b HTTP 504 attempt 2" --
    element, phase, and attempt in one string.
    """
    rec = _Recorder()
    monkeypatch.setattr(layer0, "model_chat", rec)

    layer0.resolve_wide_span({}, _row(), _paragraphs())

    call = rec.calls[0]
    assert call["role"] == "verifier"
    assert call["step"] == "doc.html-e3-layer0b"


def test_layer0b_only_shows_the_model_the_flagged_span(monkeypatch):
    """Nothing outside the cited range may be shown, or a split can cite text
    the original element never covered."""
    rec = _Recorder()
    monkeypatch.setattr(layer0, "model_chat", rec)

    layer0.resolve_wide_span({}, _row(), _paragraphs())

    prompt = rec.calls[0]["messages"][0]["content"]
    assert "paragraph 2" in prompt and "paragraph 9" in prompt
    assert "paragraph 1\n" not in prompt
    assert "paragraph 11" not in prompt


def test_layer0b_returns_the_parsed_object(monkeypatch):
    """The caller branches on decision/elements, so parsing must happen here."""
    rec = _Recorder(json.dumps({"decision": "split", "elements": [{"a": 1}]}))
    monkeypatch.setattr(layer0, "model_chat", rec)

    out = layer0.resolve_wide_span({}, _row(), _paragraphs())

    assert out["decision"] == "split"
    assert out["elements"] == [{"a": 1}]
