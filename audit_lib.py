"""Shared helpers for the Crystallize curriculum auditor (Layer 0→1→2 pipeline)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

from doc_extract import extract_with_meta
from doc_extract import iter_source_files as _iter_source_files_recursive
import loom_keys
from loom_paths import DATA_DIR, INSTALL_DIR
from schema_validate import (
    raise_on_errors,
    validate_manifest,
    validate_unit_calendar,
)

# Where the program is. Pipeline stages, checklists and tools resolve against
# this, and it must not move when the user's data does.
BASE_DIR = INSTALL_DIR
# Where the user's stuff is. On a developer checkout these are the same
# directory; on an installed copy they are not. See loom_paths.
CONFIG_PATH = DATA_DIR / "config.yaml"
LOG_DIR = DATA_DIR / "logs"
SLUG_ID_RE = re.compile(r"^[a-z0-9.]+(?:-[a-z0-9.]+)*$")

_logger = logging.getLogger("crystallize.audit")
_logging_ready = False


def load_config() -> dict:
    """Load YAML config. Override path with ``LOOM_CONFIG`` (A/B / NIM queues)."""
    path = Path(os.environ["LOOM_CONFIG"]) if os.environ.get("LOOM_CONFIG") else CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"empty YAML: {path}")
    return data


def load_manifest(path: Path) -> dict:
    """Load manifest.yaml with structural validation."""
    data = load_yaml(path)
    raise_on_errors(validate_manifest(data), f"manifest {path}")
    return data


def load_unit_calendar(path: Path) -> dict:
    """Load units/<id>/calendar.yaml with structural validation."""
    data = load_yaml(path)
    raise_on_errors(validate_unit_calendar(data), f"calendar {path}")
    return data


def _init_logging() -> None:
    global _logging_ready
    if _logging_ready:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("[audit] %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / "audit.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    _logger.handlers.clear()
    _logger.setLevel(logging.INFO)
    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)
    _logger.propagate = False
    _logging_ready = True


def log(msg: str) -> None:
    _init_logging()
    _logger.info(msg)


def validate_slug_id(value: str, label: str) -> str:
    """Reject shell metacharacters in ids passed to subprocess argv."""
    if not value or not SLUG_ID_RE.match(value):
        raise ValueError(
            f"invalid {label} {value!r} — use lowercase letters, digits, and hyphens only"
        )
    return value


def parse_model_json(text: str, *, context: str = "model response") -> dict:
    """Parse JSON from model output: markdown fences, raw JSON, or embedded object."""
    if not text or not str(text).strip():
        raise ValueError(f"{context}: empty model response")

    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    # strict=False: models occasionally emit a literal raw newline/tab inside a
    # quoted string (e.g. while quoting multi-line source text) instead of a
    # properly escaped \n. That is invalid per strict JSON but unambiguous to
    # parse, and json.loads's strict=False flag exists specifically for this.
    # Rejecting it outright is a self-inflicted, deterministic parse failure —
    # retrying does nothing since a low-temperature model reproduces it exactly.
    try:
        data = json.loads(raw, strict=False)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1], strict=False)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            raise ValueError(f"{context}: invalid JSON ({exc})") from exc

    raise ValueError(f"{context}: no JSON object found; starts with {raw[:120]!r}")


def is_unit_report_success(report_text: str) -> bool:
    """True when unit REPORT.md marks a successful audit (not substring 'SUCCESS')."""
    if re.search(r"\*\*Status:\*\*\s*FAILED", report_text, re.IGNORECASE):
        return False
    return bool(re.search(r"\*\*Status:\*\*\s*SUCCESS", report_text, re.IGNORECASE))


def _retry_after_seconds(resp) -> int | None:
    """Seconds to wait per the service's Retry-After header, if it sent one.

    Supports the delay-seconds form; the HTTP-date form is ignored rather than
    parsed, since a wrong date parse would produce a nonsense sleep and every
    service worth rate-limiting against sends the integer.
    """
    try:
        raw = (resp.headers.get("Retry-After") or "").strip() if resp is not None else ""
    except Exception:
        return None
    if not raw.isdigit():
        return None
    return max(0, min(300, int(raw)))


def _unusable_reply(data: dict) -> str | None:
    """Why this reply cannot be used as an answer, or None if it is fine.

    Reasoning models make a 200 OK response an unreliable signal of success.
    Nemotron 3.5 Lightning emits several hundred tokens of internal monologue
    before its answer, and when the token ceiling cuts that off, NVIDIA's API
    returns the monologue in ``content`` -- non-empty, plausible-looking prose
    that is not an answer to anything.

    Nothing downstream can spot that. ``report_delivery`` writes ``content``
    straight into a teacher-facing synthesis file, and its only failure test
    is whether an exception was raised. Observed live at the 400-token ceiling
    that call site used to set: the report received "Here's a thinking
    process: 1. Analyze the Request..." in place of the summary.
    """
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = (msg.get("content") or "").strip()
    reasoning = (msg.get("reasoning_content") or "").strip()
    if ch.get("finish_reason") == "length":
        return "hit the max_tokens ceiling mid-reply"
    if reasoning and not content:
        return "spent its whole budget reasoning and returned no answer"
    if reasoning and content == reasoning:
        return "returned its reasoning instead of an answer"
    return None


# Layer 0 hands over a whole document plus the rules and JSON schema, then asks
# for a large structured reply, so the window has to cover both halves of the
# exchange. These bracket what we will ask a server for.
CONTEXT_FLOOR = 4096
CONTEXT_CEILING = 32768


def estimate_tokens(messages: list) -> int:
    """Approximate token count for a chat payload.

    Deliberately a heuristic. Loading a tokenizer per model family would add a
    heavy dependency to answer a question we only need roughly, and the guards
    built on this all leave wide margin for it being wrong. Four characters per
    token is the usual figure for English prose.
    """
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    return max(1, chars // 4)


def context_window_for(messages: list, max_tokens: int) -> int:
    """Context window to request: the prompt, the reply, and a little headroom.

    Derived from the actual exchange rather than fixed, because num_ctx sizes
    the KV cache and that memory is not free -- an 8B model at 16384 fills an
    8GB card almost exactly, so demanding the ceiling on every call would put a
    school laptop into swap for no benefit. Too small silently truncates.

    Rounded up to the next 2048 rather than to the next power of two. Doubling
    overshoots by up to 2x, and measured on llama3.1:8b that was not free:
    a Layer 0 call needing ~20k tokens got a 32768 window and took 243s, where
    the same call in a 16384 window took 84s. The whole reply budget is
    reserved even though most replies are far shorter, since a window that
    cannot hold the worst case truncates mid-answer.
    """
    need = estimate_tokens(messages) + int(max_tokens) + 512
    if need <= CONTEXT_FLOOR:
        return CONTEXT_FLOOR
    block = 2048
    window = ((need + block - 1) // block) * block
    return min(window, CONTEXT_CEILING)


_OLLAMA_PROBE_CACHE: dict[str, str | None] = {}


def ollama_native_chat_url(url: str) -> str | None:
    """Native ``/api/chat`` URL if this endpoint is an Ollama server, else None.

    Worth detecting because Ollama's OpenAI-compatible endpoint silently
    discards the context-window setting. Verified against 0.34.0 with the
    server started at 2048: passing ``num_ctx`` as ``options.num_ctx`` and as a
    top-level field both left ``prompt_tokens`` pinned at 1026, while the same
    value on ``/api/chat`` raised it to 12253.

    That matters more than it sounds. Ollama truncates from the *front*, which
    is exactly where Layer 0's rules and schema sit, so the default window
    leaves the model filling in a schema it was never shown -- and the run
    still returns 200 OK with plausible-looking output. Routing local Ollama
    traffic through the native endpoint is what lets Loom guarantee the window
    itself, instead of asking every district to set an environment variable.

    Cached per URL: this costs an HTTP round trip and the answer cannot change
    within a run.
    """
    if url in _OLLAMA_PROBE_CACHE:
        return _OLLAMA_PROBE_CACHE[url]
    native: str | None = None
    try:
        base = url.split("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]
        base = base.rstrip("/")
        resp = requests.get(f"{base}/api/version", timeout=5)
        if resp.ok and (resp.json() or {}).get("version"):
            native = f"{base}/api/chat"
    except Exception:
        # Not an Ollama server, or not reachable. Either way the OpenAI path
        # stays in use and the truncation guard below remains the safety net.
        native = None
    _OLLAMA_PROBE_CACHE[url] = native
    return native


def _to_ollama_payload(payload: dict, num_ctx: int) -> dict:
    """Translate an OpenAI-shaped payload into Ollama's native form."""
    options = {
        "temperature": payload.get("temperature", 0.1),
        "num_predict": int(payload.get("max_tokens", 8192)),
        "num_ctx": int(num_ctx),
    }
    if "repeat_penalty" in payload:
        options["repeat_penalty"] = payload["repeat_penalty"]
    return {
        "model": payload["model"],
        "messages": payload["messages"],
        "stream": False,
        "options": options,
    }


def _from_ollama_response(data: dict) -> dict:
    """Normalise Ollama's native reply into the OpenAI shape.

    Done here and nowhere else: the unusable-reply check, usage recording and
    every caller reading ``choices[0].message.content`` all speak OpenAI, so
    one translation at the boundary keeps the native endpoint an implementation
    detail rather than a second dialect running through the codebase.
    """
    message = data.get("message") or {}
    # Ollama reports "length" when it stops at num_predict -- the same
    # condition OpenAI calls finish_reason "length", which _unusable_reply
    # already treats as a truncated and therefore unusable answer.
    reason = data.get("done_reason") or "stop"
    prompt_tokens = int(data.get("prompt_eval_count") or 0)
    completion_tokens = int(data.get("eval_count") or 0)
    normalised = {
        "role": message.get("role") or "assistant",
        "content": message.get("content") or "",
    }
    # Newer Ollama returns a reasoning model's monologue separately, as NVIDIA
    # does; map it to the field _unusable_reply already knows to look at.
    if message.get("thinking"):
        normalised["reasoning_content"] = message["thinking"]
    return {
        "model": data.get("model"),
        "choices": [{"message": normalised, "finish_reason": reason}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# A server that quietly drops most of the prompt is the worst failure mode
# available to an audit tool: it returns 200 OK, the run goes green, and the
# report cites a document the model barely read. Flagged at half the estimate
# so a wrong characters-per-token guess cannot cause a false alarm -- real
# truncation is an order-of-magnitude shortfall, not a rounding error.
_TRUNCATION_RATIO = 0.5


def _truncated_prompt(messages: list, data: dict) -> str | None:
    """Message explaining that the server dropped part of the prompt, or None."""
    counted = int((data.get("usage") or {}).get("prompt_tokens") or 0)
    if not counted:
        return None  # Server reports no usage; nothing to compare against.
    sent = estimate_tokens(messages)
    if counted >= sent * _TRUNCATION_RATIO:
        return None
    return (
        f"the server accepted only ~{counted} tokens of an estimated ~{sent} "
        f"sent, so most of the prompt was discarded before the model saw it"
    )


def _out_of_memory(status: int, body: str) -> bool:
    """Whether a server error looks like it could not fit the context window."""
    if status not in (400, 500, 503):
        return False
    return bool(re.search(r"memory|out of memory|requires more|cuda|vram", body, re.I))


def is_hosted_endpoint(url: str) -> bool:
    """Whether this endpoint is a hosted service rather than a local server.

    Extracted so the preflight probe and the real calls cannot drift: a probe
    that decided "local" where model_chat decides "hosted" would measure a
    different request path than the run actually uses, which is worse than not
    measuring at all.
    """
    return any(
        x in str(url)
        for x in (
            "8787",
            "8788",
            "integrate.api.nvidia.com",
            "nvidia.com",
            "api.openai.com",
            "api.x.ai",
        )
    )


def measure_context_window(cfg: dict, role: str = "analyst") -> dict:
    """Ask the server to read a prompt of known size and report what it kept.

    Meant to run before a long audit rather than during one. A server that
    truncates still answers 200 OK with plausible prose, so without this the
    failure surfaces as a disappointing report hours later instead of an
    error. For LM Studio, llama.cpp and vLLM -- where the window is fixed when
    the server starts and Loom cannot change it -- this is the only way to find
    out before committing to the run.

    Cheap by construction: the reply budget is 16 tokens, so it measures how
    much the server will *accept* without waiting for it to generate anything.
    On a local server it also warms the model.

    The probe is sized to just clear the dangerous defaults (2048 and 4096)
    rather than to match the largest prompt a run will send. Measuring the
    full 20k-token case took 191s here -- a window that big spilled past an
    8GB card -- and three minutes of waiting before every run is too high a
    price for an early warning. A prompt this size still catches every server
    left at its default, and audit_lib's per-call guard remains the backstop
    for a window that is large enough for the probe but not for the run.

    Returns a dict rather than raising, so a caller can decide whether a small
    window is fatal. ``accepted``/``asked`` are token counts, and
    ``recalled_marker`` independently confirms the front of the prompt
    survived -- the half that gets dropped first, and where Layer 0 keeps its
    rules and schema.
    """
    key = "analyst" if role == "analyst" else "verifier"
    url = str(cfg["models"][f"{key}_url"])
    model = str(cfg["models"][f"{key}_model"])
    timeout = cfg["models"]["timeout_seconds"]

    marker = "ZEPHYR"
    filler = " ".join(f"Line {i}: curriculum pacing evidence." for i in range(1, 640))
    prompt = (
        f"REMEMBER THIS WORD: {marker}.\n\n{filler}\n\n"
        "What word were you told to remember? Reply with only that word."
    )
    messages = [{"role": "user", "content": prompt}]
    asked = estimate_tokens(messages)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 16,
    }

    native = None if is_hosted_endpoint(url) else ollama_native_chat_url(url)
    # Sized the same way a real call would be, so the number reported is the
    # number the run will actually get.
    num_ctx = context_window_for(messages, 16) if native else 0
    headers = loom_keys.auth_headers(url, cfg)

    result = {
        "ok": False,
        "asked": asked,
        "accepted": 0,
        "recalled_marker": False,
        "native": bool(native),
        "window": num_ctx,
        "error": "",
    }
    try:
        if native:
            target, body = native, _to_ollama_payload(payload, num_ctx)
        else:
            target, body = url, payload
        resp = requests.post(target, json=body, headers=headers or None, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if native:
            data = _from_ollama_response(data)
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
        return result

    result["accepted"] = int((data.get("usage") or {}).get("prompt_tokens") or 0)
    reply = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    result["recalled_marker"] = marker in reply.upper()
    # A server reporting no usage at all cannot be measured this way, so fall
    # back to the marker: llama.cpp reports timings instead of usage.
    if result["accepted"]:
        result["ok"] = result["accepted"] >= asked * _TRUNCATION_RATIO
    else:
        result["ok"] = result["recalled_marker"]
    return result


def model_chat(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 8192,
    retries: int = 2,
    enable_thinking: bool | None = None,
) -> dict:
    """POST to analyst/verifier; retry only transient errors (not 4xx client failures).

    Best practice: every Loom model call goes through here so token usage is
    captured once (see usage_lib). Prefer server `usage` / llama.cpp `timings`;
    estimate only when both are absent.

    ``enable_thinking``: for local llama.cpp Nemotron templates that support
    ``chat_template_kwargs.enable_thinking``. Use ``False`` for structured-JSON
    steps so reasoning tokens cannot exhaust ``max_tokens`` and leave
    ``content`` empty (seen with Nemotron 3.5 Lightning on Pass 2 connect).
    """
    from usage_lib import monotonic_ms, record_model_call  # local import: avoid cycles

    key = "analyst" if role == "analyst" else "verifier"
    url = cfg["models"][f"{key}_url"]
    model = cfg["models"][f"{key}_model"]
    timeout = cfg["models"]["timeout_seconds"]
    # Cloud / bridge / NIM: more attempts on 429 worker limits.
    cloudish = is_hosted_endpoint(url)
    if cloudish:
        retries = max(retries, 6)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Confirmed live (2026-07-07, region10): llama.cpp can hang on repetitive
    # sources without repeat_penalty. NVIDIA NIM / OpenAI / Cursor bridge reject
    # that field (HTTP 400 Unsupported parameter), so only send it to llama.cpp.
    if not cloudish:
        payload["repeat_penalty"] = 1.15
        # Nemotron 3.5 Lightning (and Nano) honor this; ignored harmlessly if not.
        if enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}
    # Bearer token for hosted endpoints. This used to fire only for the Cursor
    # bridge on :8788, which meant any other authenticated service -- NVIDIA's
    # build API, for one -- got no Authorization header at all and came back
    # 401 with nothing in the logs to explain why.
    #
    # loom_keys scopes each key to the endpoint's host, so a credential saved
    # for a hosted provider cannot be attached to a request aimed at a local
    # model. It also still honours the old config.yaml and CURSOR_API_KEY
    # paths, so existing setups behave exactly as before.
    headers = loom_keys.auth_headers(str(url), cfg)

    # Only local servers are probed for Ollama: a hosted provider is never
    # Ollama, and firing a speculative /api/version at someone's paid endpoint
    # is rude and pointless.
    native_url = None if cloudish else ollama_native_chat_url(str(url))
    num_ctx = context_window_for(messages, max_tokens) if native_url else 0
    if native_url:
        log(
            f"{step}: using Ollama's native endpoint with a "
            f"{num_ctx}-token context window"
        )

    last_err: Exception | None = None
    t0 = monotonic_ms()

    # Raising the ceiling after a truncated reply is not a failed attempt, so
    # it gets its own allowance rather than eating the retry budget. Two
    # quadruplings covers the gap between a budget sized for a plain model and
    # what a reasoning model needs for the same answer.
    max_escalations = 2
    escalations = 0
    failures = 0
    # Shrinking the window after the server says it cannot fit it is a third
    # independent budget, for the same reason escalation has its own: a machine
    # too small for 16384 tokens should step down, not spend the retry
    # allowance discovering that repeatedly.
    max_shrinks = 3
    shrinks = 0
    # An explicit loop with two independent budgets, rather than one range
    # covering both. Sharing a single count let HTTP failures spend the
    # escalation allowance, which meant a rate-limited service got extra
    # requests with no backoff between them -- the opposite of what a 429 is
    # asking for. Every path below returns, raises, or advances a bounded
    # counter, so this cannot spin.
    while True:
        try:
            if native_url:
                target, body = native_url, _to_ollama_payload(payload, num_ctx)
            else:
                target, body = url, payload
            resp = requests.post(target, json=body, headers=headers or None, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if native_url:
                data = _from_ollama_response(data)

            # Checked before anything reads the reply: if the server dropped
            # most of the prompt, the answer is about a document that was never
            # fully shown, and no amount of retrying the same prompt changes
            # that. RuntimeError rather than ValueError deliberately -- the
            # parse-retry wrappers in layer0/layer1 swallow ValueError and
            # would grind through a whole corpus producing confident nonsense.
            dropped = _truncated_prompt(messages, data)
            if dropped:
                record_model_call(
                    role=role,
                    step=step,
                    model=str(data.get("model") or model),
                    messages=messages,
                    resp=data,
                    elapsed_ms=monotonic_ms() - t0,
                    ok=False,
                    error=f"prompt truncated: {dropped}",
                )
                raise RuntimeError(
                    f"{step}: {dropped}. The context window at {url} is too "
                    f"small for this run. For llama.cpp start the server with "
                    f"-c {CONTEXT_CEILING}; for LM Studio raise the context "
                    f"length in the model's load settings; for Ollama set "
                    f"OLLAMA_CONTEXT_LENGTH={CONTEXT_CEILING} and restart it."
                )

            problem = _unusable_reply(data)
            if problem:
                if escalations < max_escalations:
                    escalations += 1
                    ceiling = int(payload["max_tokens"])
                    payload["max_tokens"] = min(ceiling * 4, 32768)
                    log(
                        f"WARN: {step} reply {problem} at max_tokens={ceiling}; "
                        f"retrying with {payload['max_tokens']}"
                    )
                    continue
                record_model_call(
                    role=role,
                    step=step,
                    model=str(data.get("model") or model),
                    messages=messages,
                    resp=data,
                    elapsed_ms=monotonic_ms() - t0,
                    ok=False,
                    error=f"unusable reply: {problem}",
                )
                # ValueError, not RuntimeError: the parse-retry wrappers in
                # layer0/layer1 catch ValueError, so a bad generation is
                # retried there instead of aborting the whole run.
                raise ValueError(
                    f"{step}: the model {problem} "
                    f"(max_tokens={payload['max_tokens']}). This model needs a "
                    f"larger ceiling for this step."
                )

            record_model_call(
                role=role,
                step=step,
                model=str(data.get("model") or model),
                messages=messages,
                resp=data,
                elapsed_ms=monotonic_ms() - t0,
                ok=True,
            )
            return data
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = (e.response.text[:300] if e.response is not None else "") or str(e)
            # A machine that cannot hold the window we asked for should be
            # offered a smaller one, not told the run has failed: a 4GB card
            # still does useful work at 4096 tokens. Only reachable on the
            # native path, because that is the only one where we set the
            # window at all. If the smaller window then cannot hold the
            # prompt, the truncation guard above says so plainly rather than
            # letting a half-read document through.
            if (
                native_url
                and shrinks < max_shrinks
                and num_ctx > CONTEXT_FLOOR
                and _out_of_memory(status, body)
            ):
                shrinks += 1
                previous = num_ctx
                num_ctx = max(CONTEXT_FLOOR, num_ctx // 2)
                log(
                    f"WARN: {step} server could not fit a {previous}-token "
                    f"context window; retrying at {num_ctx}"
                )
                continue
            # 429/503 = rate limit / worker exhaustion — retry with backoff.
            # Other 4xx are client errors and should not be blindly retried.
            if status in (429, 503, 529):
                last_err = e
                if failures >= retries:
                    break
                # Honour Retry-After when the service sends it. Guessing a
                # backoff against a service that has told us exactly how long
                # to wait is how a free tier turns into a ban. Taken as a
                # floor, not a replacement, so a service asking for 1s cannot
                # talk us into hammering it.
                wait = min(120, 5 * (2**failures))
                hinted = _retry_after_seconds(e.response)
                if hinted is not None:
                    wait = min(300, max(wait, hinted))
                log(
                    f"WARN: {step} HTTP {status} (rate/capacity) attempt "
                    f"{failures + 1}; retry in {wait}s"
                )
                failures += 1
                time.sleep(wait)
                continue
            if 400 <= status < 500:
                record_model_call(
                    role=role,
                    step=step,
                    model=model,
                    messages=messages,
                    resp=None,
                    elapsed_ms=monotonic_ms() - t0,
                    ok=False,
                    error=f"HTTP {status}: {body}",
                )
                raise RuntimeError(
                    f"{step}: HTTP {status} (not retrying): {body}"
                ) from e
            last_err = e
            if failures >= retries:
                break
            wait = 2**failures
            log(
                f"WARN: {step} HTTP {status} attempt {failures + 1}; retry in {wait}s"
            )
            failures += 1
            time.sleep(wait)
        except (requests.ConnectionError, requests.Timeout, TimeoutError) as e:
            last_err = e
            if failures >= retries:
                break
            wait = 2**failures
            log(
                f"WARN: {step} attempt {failures + 1} failed ({e}); retry in {wait}s"
            )
            failures += 1
            time.sleep(wait)
    record_model_call(
        role=role,
        step=step,
        model=model,
        messages=messages,
        resp=None,
        elapsed_ms=monotonic_ms() - t0,
        ok=False,
        error=str(last_err),
    )
    raise RuntimeError(f"{step}: {last_err}") from last_err


_WS_RE = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs (incl. newlines) to a single space, lowercased.

    Source documents wrap mid-sentence; models quote the same words but join them
    with a single space. Without this, a correct verbatim citation gets flagged
    as UNCITED purely because of a newline the model never saw as meaningful.
    """
    return _WS_RE.sub(" ", text).strip().lower()


def excerpt_cited_in(excerpt: str, content: str, min_len: int = 10) -> bool:
    """Whitespace-normalized substring check: is `excerpt` verbatim (mod whitespace) in `content`?"""
    if not excerpt or not content:
        return False
    norm_excerpt = normalize_ws(excerpt)
    if len(norm_excerpt) < min_len:
        return True  # too short to meaningfully check
    return norm_excerpt in normalize_ws(content)


def atomic_write(path: Path, content: str) -> None:
    # Best practice: use os.replace so the temp→final swap works on Windows
    # (Path.rename fails with WinError 183 when the destination already exists).
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def project_dir(project_id: str) -> Path:
    """Resolve the writable project root.

    Best practice: E2E is canonical. ``run_project`` sets LOOM_E2E_RUN so Layer 0 /
    output / graph land under projects/<id>/e2e/runs/<run_id>/ and never clobber
    the golden curriculum tree (see tools/e2e_run_lib.py). Bare projects/<id>/
    is for --allow-live-root / overnight golden refresh only.

    Resolves under DATA_DIR, not the install directory, so a district's
    curricula never land inside the program's own folder.
    """
    base = DATA_DIR / "projects" / project_id
    run = (os.environ.get("LOOM_E2E_RUN") or "").strip()
    if run:
        safe = re.sub(r"[^\w.\-]+", "-", run).strip("-._")[:80]
        if not safe:
            raise ValueError("LOOM_E2E_RUN is empty after sanitization")
        return base / "e2e" / "runs" / safe
    return base


def resolve_sources_dir(manifest: dict, root_override: Path | None = None) -> Path:
    sd = manifest.get("sources_dir")
    if sd:
        # New format: sources_dir relative to project root
        # root_override is the project root path
        p = Path(sd)
        if not p.is_absolute():
            p = (root_override or Path()).resolve() / p
        return p
    # Flat format: default to <project>/sources/
    if root_override:
        return root_override / "sources"
    return Path("sources")


def resolve_unit_paths(project_id: str, unit_id: str) -> tuple[Path, dict, dict, Path]:
    """Return (project_root, manifest, unit_entry, output_dir)."""
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    if unit_id not in manifest["units"]:
        raise KeyError(f"Unknown unit '{unit_id}' in project '{project_id}'")
    unit = manifest["units"][unit_id]
    out = root / "output" / unit_id
    return root, manifest, unit, out


SUPPORTED_EXTS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".odt",
    ".txt",
    ".md",
    ".html",
    ".rtf",
    ".doc",
}


def iter_source_files(sources: Path) -> list[Path]:
    """Iterate source directory for supported curriculum files, sorted.

    Delegates to doc_extract.iter_source_files (recursive, via rglob) rather
    than maintaining a second, divergent implementation. This used to be a
    flat, top-level-only `sources.glob(f"*{ext}")` — silently correct for the
    Dallas corpus (flat directory of 110 files) but a real, silent data-loss
    bug the moment a corpus nests files in subfolders: confirmed live
    (2026-07-07) against the region10 corpus, which stores each unit's actual
    content one level down in `unit-N/planning-guides/`. The non-recursive
    version dropped all 12 of those files with no warning — Layer 0 reported
    "5 documents" processed out of 17 real source files. Bet 1 says never
    truncate a document's content; this was the same failure one level up,
    silently truncating the *document set* itself before Layer 0 ever saw it.
    """
    return sorted(_iter_source_files_recursive(sources))


def doc_id_from_filename(name: str) -> str:
    base = os.path.basename(name)
    m = re.match(r"^doc_([a-f0-9]+)_", base)
    if m:
        return m.group(1)
    return base.replace(".txt", "")


# Hand-checked live on the Dallas corpus (docs/BETS.md Bet 12): a document's own
# elements agreeing on ONE alternate unit at least this often is corroborated
# enough to trust as a real MISMATCH signal. Shared by layer1 REPORT.md and
# synthesize/teacher plates so HIGH vs low confidence never diverges.
CONCENTRATION_MIN_COUNT = 3


def is_corroborated(row: dict) -> bool:
    """High-confidence MISMATCH requires document-internal corroboration AND
    (if an independent recheck ran) that the recheck reproduced the finding.

    A MISMATCH the second same-model pass did NOT reproduce (recheck_agreed is
    False) is demoted to low-confidence regardless of corroboration — see
    layer1.recheck_mismatches() and docs/BETS.md Bet 5. recheck_agreed is None
    (recheck errored) or missing (older ledger, pre-recheck) both fall through
    to corroboration alone.
    """
    if row.get("recheck_performed") and row.get("recheck_agreed") is False:
        return False
    return (row.get("mismatch_corroboration") or {}).get(
        "same_target_count", 0
    ) >= CONCENTRATION_MIN_COUNT


DOC_TYPES = frozenset(
    {
        "lesson_plan",
        "lesson_content",
        "exit_ticket",
        "quiz",
        "answer_key",
        "rubric",
        "worksheet",
        "project_work",
        "presentation",
        "game_activity",
        "lab_activity",
        "flex_day",
        "other",
    }
)

VALID_SLOT_ROLES = frozenset(
    {
        "lesson_plan",
        "lesson_content",
        "exit_ticket",
        "quiz",
        "answer_key",
        "rubric",
        "worksheet",
        "project_work",
        "presentation",
        "game_activity",
        "lab_activity",
        "flex_day",
        "other",
    }
)


def classify_doc_type(filename: str) -> str:
    """Infer artifact type from filename — deterministic, no model."""
    n = filename.lower()
    # Path G lens — match early so syllabus filenames don't fall through to other.
    # Keep "sylibuis" as typo alias for early stub filenames.
    if "syllabus" in n or "sylibuis" in n:
        return "syllabus"
    # Hyphen form (answer-key) is common in web/Word CTE exports.
    if "answer_key" in n or "answer key" in n or "answer-key" in n:
        return "answer_key"
    if "exit_ticket" in n or "exit ticket" in n:
        return "exit_ticket"
    if "quizizz" in n or "quiz" in n:
        return "quiz"
    # CTE final / CFU assessments (not answer keys — those matched above).
    if "final-assessment" in n or "final_assessment" in n:
        return "quiz"
    if "check-for-understanding" in n or "check_for_understanding" in n:
        return "quiz"
    if re.search(r"(?:^|__)assessment(?:[_\s.-]|\.|$)", n):
        return "quiz"
    if "lesson_plan" in n or "lesson plan" in n:
        return "lesson_plan"
    if "slides" in n or "powerpoint" in n or n.endswith(".pptx") or n.endswith(".ppt"):
        return "lesson_content"
    if re.search(r"_lesson\.(txt|docx?|pdf)$", n) or n.endswith("_lesson.txt"):
        return "lesson_content"
    if "worksheet" in n or n.endswith(".xlsx"):
        return "worksheet"
    if "rubric" in n:
        return "rubric"
    if "bingo" in n or "game" in n or "code card" in n:
        return "game_activity"
    if "presentation" in n or "pitch" in n or "slide show" in n:
        return "presentation"
    if "project" in n or "menu" in n or "flyer" in n or "commercial" in n:
        return "project_work"
    if "lab" in n or "experiment" in n:
        return "lab_activity"
    if "flex" in n or "choice" in n or "catch" in n:
        return "flex_day"
    if "student note" in n or "notes" in n:
        return "project_work"
    return "other"


def dedupe_table_line(line: str) -> str:
    """PDF/table exports often repeat the same cell 3× separated by ' | '."""
    if " | " not in line:
        return line
    parts = [p.strip() for p in line.split(" | ")]
    if not parts:
        return line
    # Keep first segment when all non-empty parts are identical
    non_empty = [p for p in parts if p]
    if non_empty and all(p == non_empty[0] for p in non_empty):
        return non_empty[0]
    # Collapse consecutive duplicates
    out = []
    for p in parts:
        if p and (not out or out[-1] != p):
            out.append(p)
    return " | ".join(out) if len(out) > 1 else (out[0] if out else line)


def clean_document_text(raw: str) -> str:
    lines = [dedupe_table_line(ln.rstrip()) for ln in raw.splitlines()]
    cleaned = []
    prev = None
    for ln in lines:
        stripped = ln.strip()
        if stripped == prev and stripped:
            continue
        cleaned.append(ln)
        prev = stripped
    return "\n".join(cleaned).strip()


def extract_day_hints(text: str) -> list[int]:
    days = {int(m.group(1)) for m in re.finditer(r"\bDay\s*(\d+)\b", text, re.I)}
    return sorted(days)


def extract_unit_length_days(text: str) -> int | None:
    m = re.search(r"Estimated\s+Day\(s\):\s*(\d+)", text, re.I)
    return int(m.group(1)) if m else None


def extract_standards_refs(text: str) -> list[str]:
    refs = set()
    for m in re.finditer(r"(TEKS[^|\n]{0,120})", text):
        refs.add(m.group(1).strip())
    for m in re.finditer(r"(NGSS\s+[A-Z0-9\.\-]+)", text):
        refs.add(m.group(1).strip())
    return sorted(refs)[:20]


def extract_title(text: str, filename: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        if line.lower().startswith("day "):
            continue
        if len(line) > 8:
            return line[:200]
    return os.path.basename(filename).replace(".txt", "").replace("_", " ")


def scrub_document(path: Path) -> dict:
    """Turn one source file into structured evidence. Extracts text from any supported format."""
    meta = extract_with_meta(path)
    if meta.get("extraction_error"):
        return {
            "source_file": meta["source_file"],
            "doc_id": doc_id_from_filename(meta["source_file"]),
            "doc_type": classify_doc_type(meta["source_file"]),
            "source_format": meta.get("source_format"),
            "extraction_method": meta.get("extraction_method"),
            "extraction_error": meta.get("extraction_error"),
            "title": meta["source_file"],
            "char_count_raw": 0,
            "char_count_clean": 0,
            "day_hints": [],
            "unit_length_days_hint": None,
            "standards_refs": [],
            "content_clean": "",
            "excerpt_head": "",
        }

    raw = meta["raw_text"]
    cleaned = clean_document_text(raw)
    fname = path.name
    return {
        "source_file": fname,
        "doc_id": doc_id_from_filename(fname),
        "doc_type": classify_doc_type(fname),
        "source_format": meta.get("source_format"),
        "extraction_method": meta.get("extraction_method"),
        "title": extract_title(cleaned, fname),
        "char_count_raw": len(raw),
        "char_count_clean": len(cleaned),
        "day_hints": extract_day_hints(cleaned),
        "unit_length_days_hint": extract_unit_length_days(cleaned),
        "standards_refs": extract_standards_refs(cleaned),
        "content_clean": cleaned,
        "excerpt_head": cleaned[:500],
    }
