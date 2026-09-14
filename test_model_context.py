#!/usr/bin/env python3
"""Tests for the context-window handling in audit_lib (no models, no network).

These cover the failure that motivated them, which was silent and total: an
OpenAI-compatible server that truncates the prompt still answers HTTP 200 with
plausible prose, so a run goes green while the model has seen almost none of
the document it is being audited against. Measured against Ollama 0.34.0
started at a 2048-token window: a ~16k-token prompt came back reporting 1026
prompt tokens and answered from the tail it had kept.

Everything here is a pure function on dicts so the guards can be checked
without a server. The one thing these cannot cover is whether Ollama's native
endpoint really honours num_ctx while the OpenAI one ignores it -- that was
established by live probe and is recorded in ollama_native_chat_url's
docstring.
"""

import audit_lib


def _messages(chars: int) -> list:
    return [{"role": "user", "content": "x" * chars}]


class TestEstimateTokens:
    def test_counts_every_message(self):
        msgs = [{"role": "system", "content": "a" * 400}, {"role": "user", "content": "b" * 400}]
        # 800 characters at the four-characters-per-token heuristic.
        assert audit_lib.estimate_tokens(msgs) == 200

    def test_never_returns_zero(self):
        # A zero would make the truncation ratio meaningless rather than safe.
        assert audit_lib.estimate_tokens([{"role": "user", "content": ""}]) == 1

    def test_tolerates_missing_content(self):
        assert audit_lib.estimate_tokens([{"role": "user"}]) == 1


class TestContextWindowFor:
    def test_small_exchange_gets_the_floor(self):
        assert audit_lib.context_window_for(_messages(100), 512) == audit_lib.CONTEXT_FLOOR

    def test_rounds_up_to_the_next_2048(self):
        # 4000 chars -> 1000 tokens, plus 16384 reply and 512 headroom = 17896,
        # which must round up to 18432 rather than doubling to 32768.
        assert audit_lib.context_window_for(_messages(4000), 16384) == 18432

    def test_never_exceeds_the_ceiling(self):
        assert audit_lib.context_window_for(_messages(500_000), 16384) == audit_lib.CONTEXT_CEILING

    def test_reserves_the_whole_reply_budget(self):
        # A window that cannot hold the worst-case reply truncates mid-answer,
        # so the budget is reserved even though most replies are shorter.
        small = audit_lib.context_window_for(_messages(4000), 1024)
        large = audit_lib.context_window_for(_messages(4000), 16384)
        assert large > small


class TestOllamaTranslation:
    def test_payload_carries_the_window_and_reply_budget(self):
        payload = {
            "model": "llama3.1:8b",
            "messages": _messages(10),
            "temperature": 0.1,
            "max_tokens": 4096,
            "repeat_penalty": 1.15,
        }
        native = audit_lib._to_ollama_payload(payload, 20480)
        assert native["options"]["num_ctx"] == 20480
        assert native["options"]["num_predict"] == 4096
        assert native["options"]["repeat_penalty"] == 1.15
        assert native["stream"] is False

    def test_repeat_penalty_is_omitted_when_absent(self):
        native = audit_lib._to_ollama_payload(
            {"model": "m", "messages": [], "max_tokens": 8}, 4096
        )
        assert "repeat_penalty" not in native["options"]

    def test_response_becomes_openai_shaped(self):
        data = audit_lib._from_ollama_response(
            {
                "model": "llama3.1:8b",
                "message": {"role": "assistant", "content": "hello"},
                "done_reason": "stop",
                "prompt_eval_count": 120,
                "eval_count": 30,
            }
        )
        assert data["choices"][0]["message"]["content"] == "hello"
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"] == {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        }

    def test_hitting_the_reply_budget_maps_to_finish_reason_length(self):
        # _unusable_reply already treats finish_reason "length" as a truncated
        # and therefore unusable answer; the native path must speak that too.
        data = audit_lib._from_ollama_response(
            {"message": {"content": "half an ans"}, "done_reason": "length"}
        )
        assert data["choices"][0]["finish_reason"] == "length"
        assert audit_lib._unusable_reply(data) is not None

    def test_thinking_is_mapped_to_reasoning_content(self):
        data = audit_lib._from_ollama_response(
            {"message": {"content": "", "thinking": "let me consider"}, "done_reason": "stop"}
        )
        assert data["choices"][0]["message"]["reasoning_content"] == "let me consider"
        # No answer, only monologue: must not be treated as a usable reply.
        assert audit_lib._unusable_reply(data) is not None

    def test_missing_counts_do_not_crash(self):
        data = audit_lib._from_ollama_response({"message": {"content": "hi"}})
        assert data["usage"]["prompt_tokens"] == 0


class TestTruncationGuard:
    def test_flags_a_server_that_dropped_most_of_the_prompt(self):
        # The observed real case: ~16k tokens sent, 1026 accepted.
        msgs = _messages(65_000)
        data = {"usage": {"prompt_tokens": 1026}}
        assert audit_lib._truncated_prompt(msgs, data) is not None

    def test_accepts_a_full_prompt(self):
        msgs = _messages(4000)
        data = {"usage": {"prompt_tokens": 1000}}
        assert audit_lib._truncated_prompt(msgs, data) is None

    def test_tolerates_a_wrong_heuristic(self):
        # The estimate is characters/4. A server reporting somewhat fewer
        # tokens than that is normal for efficiently tokenised text and must
        # not raise: real truncation is an order of magnitude, not a fraction.
        msgs = _messages(4000)
        data = {"usage": {"prompt_tokens": 700}}
        assert audit_lib._truncated_prompt(msgs, data) is None

    def test_silent_when_the_server_reports_no_usage(self):
        # Nothing to compare against, so the guard must abstain rather than
        # guess -- llama.cpp reports timings instead of usage.
        assert audit_lib._truncated_prompt(_messages(65_000), {}) is None
        assert audit_lib._truncated_prompt(_messages(65_000), {"usage": {}}) is None


class TestHostedEndpointDetection:
    def test_recognises_hosted_services(self):
        assert audit_lib.is_hosted_endpoint("https://integrate.api.nvidia.com/v1/chat/completions")
        assert audit_lib.is_hosted_endpoint("https://api.openai.com/v1/chat/completions")
        assert audit_lib.is_hosted_endpoint("http://127.0.0.1:8788/v1/chat/completions")

    def test_treats_a_local_server_as_local(self):
        # Must be local for the Ollama probe to fire at all; a hosted endpoint
        # is never probed, since a speculative /api/version against someone's
        # paid service is pointless.
        assert not audit_lib.is_hosted_endpoint("http://127.0.0.1:11434/v1/chat/completions")
        assert not audit_lib.is_hosted_endpoint("http://localhost:1234/v1/chat/completions")


class TestPreflightContextWindow:
    """The preflight's job is to fail fast, but only on evidence."""

    def test_passes_when_the_server_accepts_the_prompt(self, monkeypatch):
        import run_project

        monkeypatch.setattr(
            "audit_lib.measure_context_window",
            lambda cfg, role="analyst": {
                "ok": True, "asked": 6000, "accepted": 5800,
                "native": True, "window": 8192, "error": "",
            },
        )
        run_project._preflight_context_window({})  # must not raise

    def test_aborts_when_the_window_is_measurably_too_small(self, monkeypatch):
        import pytest
        import run_project

        monkeypatch.setattr(
            "audit_lib.measure_context_window",
            lambda cfg, role="analyst": {
                "ok": False, "asked": 6000, "accepted": 1026,
                "native": False, "window": 0, "error": "",
            },
        )
        with pytest.raises(RuntimeError) as excinfo:
            run_project._preflight_context_window({})
        message = str(excinfo.value)
        # The message has to tell an operator what to change, per server.
        assert "1026" in message
        assert "-c 32768" in message
        assert "OLLAMA_CONTEXT_LENGTH" in message

    def test_a_failed_probe_only_warns(self, monkeypatch):
        # A transient blip must not block a run: the per-call guard in
        # audit_lib still aborts if prompts really are being truncated.
        import run_project

        monkeypatch.setattr(
            "audit_lib.measure_context_window",
            lambda cfg, role="analyst": {
                "ok": False, "asked": 6000, "accepted": 0,
                "native": False, "window": 0, "error": "connection refused",
            },
        )
        run_project._preflight_context_window({})  # must not raise

    def test_an_exception_in_the_probe_only_warns(self, monkeypatch):
        import run_project

        def boom(cfg, role="analyst"):
            raise OSError("socket closed")

        monkeypatch.setattr("audit_lib.measure_context_window", boom)
        run_project._preflight_context_window({})  # must not raise


class TestOutOfMemoryDetection:
    def test_recognises_a_window_that_does_not_fit(self):
        assert audit_lib._out_of_memory(500, "model requires more system memory than available")
        assert audit_lib._out_of_memory(500, "CUDA out of memory")

    def test_ignores_unrelated_failures(self):
        assert not audit_lib._out_of_memory(400, "unsupported parameter: repeat_penalty")
        assert not audit_lib._out_of_memory(401, "invalid api key")

    def test_ignores_statuses_that_are_not_server_faults(self):
        # A 429 is a rate limit and has its own backoff path; shrinking the
        # context window in response would be the wrong remedy.
        assert not audit_lib._out_of_memory(429, "out of memory")
