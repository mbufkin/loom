"""Shared helpers for the Crystallize curriculum auditor (Layer 0→1→2 pipeline)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
import yaml

from doc_extract import extract_with_meta
from doc_extract import iter_source_files as _iter_source_files_recursive
from schema_validate import (
    raise_on_errors,
    validate_manifest,
    validate_unit_calendar,
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOG_DIR = BASE_DIR / "logs"
SLUG_ID_RE = re.compile(r"^[a-z0-9.]+(?:-[a-z0-9.]+)*$")

# Log rotation (F008): an overnight/long-corpus run must not grow audit.log without
# bound. Cap each file at 10 MB and keep 5 rolled backups (audit.log.1 … .5) — a
# ~60 MB ceiling that survives long runs while staying trivially greppable.
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

# Single source of truth for the "large model call" timeout (F025): layer0 and
# layer1 both need the longer budget for content-dense JSON responses, and having
# two copies drift is a latent bug. Import this constant instead of redefining it.
LARGE_CALL_TIMEOUT_SECONDS = 900

_logger = logging.getLogger("crystallize.audit")
_logging_ready = False


def load_config() -> dict:
    # LOOM_CONFIG lets an experiment point the whole pipeline at an ALTERNATE config
    # (e.g. config.zen.yaml → a hosted API) without editing the committed config.yaml
    # or disturbing the local-model default. Unset → the normal config.yaml.
    path = os.environ.get("LOOM_CONFIG", str(CONFIG_PATH))
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
    # RotatingFileHandler (not plain FileHandler): bounds disk use on long runs.
    file_handler = RotatingFileHandler(
        LOG_DIR / "audit.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
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


class RateGate:
    """Sliding-window RPM gatekeeper for hosted model APIs.

    WHY THIS EXISTS
    Free / shared backends (NVIDIA NIM ~40 RPM, OpenRouter, etc.) reject bursts with
    HTTP 429. Loom is usually sequential and stays under the cap by latency alone, but
    a gate makes the contract EXPLICIT: before every model call we wait until the last
    `window_seconds` has fewer than `max_rpm` recorded calls. Local llama-server leaves
    max_rpm unset → gate is a no-op.

    Thread-safe enough for a future --concurrency flag (lock around the deque). Tests
    inject `clock` / `sleeper` so we never sleep for real wall-clock time offline.
    """

    def __init__(
        self,
        *,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._times: list[float] = []
        self._lock = __import__("threading").Lock()

    def wait(self, max_rpm: int | None, *, step: str = "model", window_seconds: float = 60.0) -> float:
        """Block until a call slot is free. Returns seconds slept (0 if clear)."""
        if not max_rpm or max_rpm <= 0:
            return 0.0
        slept_total = 0.0
        while True:
            with self._lock:
                now = self._clock()
                cutoff = now - window_seconds
                # Drop timestamps outside the window.
                self._times = [t for t in self._times if t > cutoff]
                if len(self._times) < max_rpm:
                    self._times.append(now)
                    return slept_total
                # Oldest call in the window expires after (oldest + window) - now.
                oldest = self._times[0]
                wait_s = max(0.05, (oldest + window_seconds) - now + 0.05)
            log(
                f"rate-gate: {step} at {max_rpm} RPM — waiting {wait_s:.1f}s "
                f"({len(self._times)} calls in last {window_seconds:.0f}s)"
            )
            self._sleeper(wait_s)
            slept_total += wait_s

    def reset(self) -> None:
        """Clear history (tests / after switching backends)."""
        with self._lock:
            self._times.clear()

    @property
    def recent_count(self) -> int:
        with self._lock:
            return len(self._times)


# Process-wide gate: every model_chat goes through the same window so Layer 0 +
# quality + curriculum_review share one RPM budget (matches how NVIDIA counts keys).
_rate_gate = RateGate()


def _messages_to_cursor_prompt(messages: list) -> str:
    """Flatten OpenAI-style chat messages into one Agent.prompt string.

    Transport only: layers still build the same `messages` list; Cursor's Agent
    API takes a single string, so we concatenate with role labels. No new
    instructional content is added — prompts stay owned by the callers.
    """
    parts: list[str] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _normalize_cursor_model_params(params: object) -> list[dict]:
    """Accept dict ({effort: high}) or list ([{id, value}]) → Cursor param list."""
    if not params:
        return []
    if isinstance(params, list):
        out: list[dict] = []
        for item in params:
            if not isinstance(item, dict):
                raise RuntimeError(
                    f"models.*_model_params list items must be {{id, value}} dicts, "
                    f"got {item!r}"
                )
            pid = item.get("id")
            if not pid:
                raise RuntimeError(f"model param missing id: {item!r}")
            val = item.get("value")
            if isinstance(val, bool):
                val = "true" if val else "false"
            out.append({"id": str(pid), "value": str(val)})
        return out
    if isinstance(params, dict):
        out = []
        for pid, val in params.items():
            if isinstance(val, bool):
                val = "true" if val else "false"
            out.append({"id": str(pid), "value": str(val)})
        return out
    raise RuntimeError(
        f"model params must be a dict or list, got {type(params).__name__}"
    )


def resolve_cursor_model_selection(models_cfg: dict, role_key: str) -> dict:
    """Build Cursor ModelSelection JSON from config — easy to swap models.

    Supported shapes (first match wins for the model id):
      - analyst_model: "grok-4.5"  + shared model_params: {effort: high, fast: true}
      - analyst_model: {id: grok-4.5, params: {effort: high, fast: true}}
      - per-role override: analyst_model_params: {effort: medium}

    Best practice: keep the model id and effort/fast knobs in YAML so operators
    can change backends without touching Python.
    """
    raw = models_cfg.get(f"{role_key}_model")
    shared = models_cfg.get("model_params") or {}
    role_params = models_cfg.get(f"{role_key}_model_params")
    if isinstance(raw, dict):
        mid = raw.get("id") or raw.get("model")
        if not mid:
            raise RuntimeError(
                f"models.{role_key}_model dict needs an 'id' (got {raw!r})"
            )
        # Inline params override shared; per-role *_model_params override both.
        merged: dict | list = dict(shared) if isinstance(shared, dict) else shared
        inline = raw.get("params")
        if inline:
            if isinstance(merged, dict) and isinstance(inline, dict):
                merged = {**merged, **inline}
            else:
                merged = inline
        if role_params:
            if isinstance(merged, dict) and isinstance(role_params, dict):
                merged = {**merged, **role_params}
            else:
                merged = role_params
        return {"id": str(mid), "params": _normalize_cursor_model_params(merged)}
    if not raw:
        raise RuntimeError(f"models.{role_key}_model is required for provider=cursor_sdk")
    merged2: dict | list = dict(shared) if isinstance(shared, dict) else shared
    if role_params:
        if isinstance(merged2, dict) and isinstance(role_params, dict):
            merged2 = {**merged2, **role_params}
        else:
            merged2 = role_params
    return {"id": str(raw), "params": _normalize_cursor_model_params(merged2)}


def resolve_cursor_api_key(models_cfg: dict, step: str) -> str:
    """CURSOR_API_KEY env (or api_key_env), then Pi ~/.pi/agent/auth.json fallback.

    Best practice: keep the secret out of YAML. Prefer the env var in CI; Pi auth
    is a convenient local fallback. Inline read so this works even when the
    create/ draft package is not on the branch.
    """
    env_name = models_cfg.get("api_key_env") or "CURSOR_API_KEY"
    key = (os.environ.get(str(env_name)) or "").strip()
    if key:
        return key
    # Optional shared helper when create-after-audit is present.
    try:
        from create.auth import cursor_api_key

        return cursor_api_key()
    except Exception:
        pass
    auth_path = Path.home() / ".pi" / "agent" / "auth.json"
    if auth_path.is_file():
        try:
            data = json.loads(auth_path.read_text(encoding="utf-8"))
            pi_key = ((data.get("cursor") or {}).get("key") or "").strip()
            if pi_key:
                return pi_key
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"{step}: unreadable ~/.pi/agent/auth.json: {e}"
            ) from e
    raise RuntimeError(
        f"{step}: no Cursor API key. Export {env_name}=... or configure "
        f"~/.pi/agent/auth.json (OpenCode does not store the Cursor key)."
    )


def _model_chat_cursor_sdk(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    retries: int,
    timeout_seconds: float | None,
) -> dict:
    """Run one Cursor Agent.prompt and reshape the result like chat/completions.

    Why a separate provider: Cursor's Agent API is not OpenAI Chat Completions.
    Loom's layers all call model_chat → extract_content, so we keep that contract
    and swap only the transport when models.provider is cursor_sdk / cursor.
    """
    models_cfg = cfg.get("models", {}) or {}
    role_key = "analyst" if role == "analyst" else "verifier"
    selection = resolve_cursor_model_selection(models_cfg, role_key)
    api_key = resolve_cursor_api_key(models_cfg, step)
    prompt = _messages_to_cursor_prompt(messages)
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else float(models_cfg.get("timeout_seconds") or 300)
    )
    max_rpm = models_cfg.get("max_rpm")
    if max_rpm is not None:
        try:
            max_rpm = int(max_rpm)
        except (TypeError, ValueError) as e:
            raise RuntimeError(
                f"{step}: models.max_rpm must be an int, got {max_rpm!r}"
            ) from e

    try:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions
    except ImportError as e:
        raise RuntimeError(
            f"{step}: cursor-sdk not installed — "
            f"`pip install cursor-sdk` into the Loom venv, then retry"
        ) from e

    # Scratch cwd: never point the agent at the Loom repo root (avoids tool edits).
    import tempfile

    cwd = models_cfg.get("cursor_cwd") or tempfile.mkdtemp(prefix="loom-cursor-")
    Path(cwd).mkdir(parents=True, exist_ok=True)

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        _rate_gate.wait(max_rpm, step=step)
        try:
            # mode=plan: prefer analysis over file-editing agent behavior.
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=api_key,
                    model=selection,
                    local=LocalAgentOptions(cwd=str(cwd)),
                    mode="plan",
                ),
            )
        except CursorAgentError as err:
            last_err = err
            retryable = bool(getattr(err, "is_retryable", False))
            if retryable and attempt < retries:
                wait_s = max(2.0, 2 ** (attempt + 1))
                log(
                    f"WARN: {step} Cursor retryable error attempt {attempt + 1}; "
                    f"retry in {wait_s}s ({getattr(err, 'message', err)})"
                )
                time.sleep(wait_s)
                continue
            raise RuntimeError(
                f"{step}: Cursor SDK error: {getattr(err, 'message', err)}"
            ) from err
        except Exception as err:
            # Timeouts / bridge flakes — retry like HTTP transport errors.
            last_err = err
            if attempt < retries:
                wait_s = max(2.0, 2 ** (attempt + 1))
                log(
                    f"WARN: {step} Cursor attempt {attempt + 1} failed ({err}); "
                    f"retry in {wait_s}s"
                )
                time.sleep(wait_s)
                continue
            raise RuntimeError(f"{step}: {err}") from err

        status = getattr(result, "status", None)
        text = getattr(result, "result", None) or ""
        if status == "error" or not str(text).strip():
            last_err = RuntimeError(
                f"Cursor run failed (status={status}, id={getattr(result, 'id', None)})"
            )
            if attempt < retries:
                wait_s = max(2.0, 2 ** (attempt + 1))
                log(
                    f"WARN: {step} empty/error Cursor result attempt {attempt + 1}; "
                    f"retry in {wait_s}s"
                )
                time.sleep(wait_s)
                continue
            raise RuntimeError(f"{step}: {last_err}") from last_err

        # Preserve OpenAI-shaped envelope so extract_content / parse_model_json work.
        return {
            "choices": [{"message": {"role": "assistant", "content": str(text)}}],
            "model": selection,
            "cursor_run_id": getattr(result, "id", None),
            "cursor_status": status,
            "_loom_timeout_budget": timeout,
        }

    raise RuntimeError(f"{step}: {last_err}") from last_err


def model_chat(
    cfg: dict,
    role: str,
    messages: list,
    step: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 8192,
    retries: int = 2,
    timeout_seconds: float | None = None,
) -> dict:
    """POST to analyst/verifier; retry only transient errors (not 4xx client failures).

    timeout_seconds: optional per-call override. Use a longer value for Layer 0
    chunks / Layer 1 ORGANIZE batches without raising the global config default
    (keeps small Dallas-shaped calls at the normal 300s budget).

    Tail tolerance (Dean & Barroso / LLM gateway practice):
      - 502/503/504 get longer exponential backoff than generic errors.
      - Optional models.hedge_after_seconds: on long calls (timeout≥300s), if the
        first POST is still outstanding past that delay, fire a second identical
        request and take the first success (capped by max_rpm). Off by default.
      - models.transient_retries overrides the retries= kwarg when set.

    Cursor SDK: set models.provider to cursor_sdk (or cursor). That path ignores
    analyst_url and uses Agent.prompt with models.model_params (effort/fast).
    Swap models by editing analyst_model / model_params in the YAML only.
    """
    models_cfg_early = cfg.get("models", {}) or {}
    if models_cfg_early.get("transient_retries") is not None:
        try:
            retries = int(models_cfg_early["transient_retries"])
        except (TypeError, ValueError) as e:
            raise RuntimeError(
                f"{step}: models.transient_retries must be an int, got "
                f"{models_cfg_early.get('transient_retries')!r}"
            ) from e

    provider = str(models_cfg_early.get("provider") or "").strip().lower()
    if provider in ("cursor_sdk", "cursor"):
        # temperature / max_tokens are Chat Completions knobs; Cursor Agent
        # selection uses model_params (effort/fast) instead — documented in YAML.
        return _model_chat_cursor_sdk(
            cfg,
            role,
            messages,
            step,
            retries=retries,
            timeout_seconds=timeout_seconds,
        )

    key = "analyst" if role == "analyst" else "verifier"
    url = cfg["models"][f"{key}_url"]
    model = cfg["models"][f"{key}_model"]
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else cfg["models"]["timeout_seconds"]
    )
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # repeat_penalty is a llama.cpp sampling knob (NOT OpenAI schema): confirmed live
    # (2026-07-07, region10 corpus) to stop the local model falling into a repetition
    # loop and burning the full timeout on link/list-heavy docs. llama.cpp accepts it
    # as a passthrough extra field, but a STRICT gateway (e.g. OpenCode Zen) may 400 on
    # an unknown field — so it's gated by config and defaults ON for the local server.
    models_cfg = cfg.get("models", {})
    if models_cfg.get("send_repeat_penalty", True):
        payload["repeat_penalty"] = 1.15

    # Provider-agnostic auth for ANY OpenAI-Chat-Completions-compatible API. The KEY
    # itself never lives in config — config only names the ENV VAR holding it
    # (api_key_env), so no secret is ever committed. Everything else is configurable so
    # one code path serves OpenAI, OpenRouter, Groq, Together, OpenCode Zen, Azure, a
    # local llama-server, etc.:
    #   api_key_env   env var holding the token (omit → no auth, e.g. local server)
    #   auth_header   header name           (default "Authorization")
    #   auth_scheme   token prefix          (default "Bearer"; set "" for a raw key,
    #                                         e.g. Azure's `api-key: <key>`)
    #   extra_headers static headers dict   (e.g. OpenRouter's HTTP-Referer / X-Title)
    # Local llama-server sets none of these → no headers → byte-identical to before.
    headers = dict(models_cfg.get("extra_headers") or {})
    api_key_env = models_cfg.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{step}: config sets api_key_env={api_key_env!r} but that env var is "
                f"empty. Export it first, e.g. export {api_key_env}=sk-..."
            )
        header_name = models_cfg.get("auth_header", "Authorization")
        scheme = models_cfg.get("auth_scheme", "Bearer")
        headers[header_name] = f"{scheme} {api_key}" if scheme else api_key

    # Optional RPM gate (models.max_rpm). Unset / 0 → local default, no waiting.
    # NVIDIA free ~40 RPM; we default to that when max_rpm is set but leave local
    # config.yaml alone so overnight local runs never sleep for a rate limit.
    max_rpm = models_cfg.get("max_rpm")
    if max_rpm is not None:
        try:
            max_rpm = int(max_rpm)
        except (TypeError, ValueError) as e:
            raise RuntimeError(f"{step}: models.max_rpm must be an int, got {max_rpm!r}") from e

    hedge_after = models_cfg.get("hedge_after_seconds")
    if hedge_after is not None:
        try:
            hedge_after = float(hedge_after)
        except (TypeError, ValueError) as e:
            raise RuntimeError(
                f"{step}: models.hedge_after_seconds must be a number, got {hedge_after!r}"
            ) from e
        if hedge_after <= 0:
            hedge_after = None

    def _one_post() -> dict:
        """Single gated POST — shared by retry loop and optional hedge twin."""
        _rate_gate.wait(max_rpm, step=step)
        resp = requests.post(url, json=payload, timeout=timeout, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _post_maybe_hedged() -> dict:
        # Hedging only on long calls (Layer 0 / large budgets). Short Dallas calls
        # stay single-flight so free-tier RPM is not doubled for every tiny prompt.
        # shutdown(wait=False): do not block on the losing twin (it may still be
        # mid-HTTP); the OS reaps the worker when the response arrives.
        if hedge_after is None or float(timeout) < 300:
            return _one_post()
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            primary = pool.submit(_one_post)
            done, _ = wait([primary], timeout=hedge_after, return_when=FIRST_COMPLETED)
            if done:
                return primary.result()
            log(
                f"WARN: {step} still pending after {hedge_after:.0f}s — "
                f"hedging a second request (Tail at Scale)"
            )
            hedge = pool.submit(_one_post)
            finished, _ = wait([primary, hedge], return_when=FIRST_COMPLETED)
            winner = next(iter(finished))
            try:
                return winner.result()
            except Exception:
                other = hedge if winner is primary else primary
                return other.result()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        # Gate BEFORE every attempt (including retries) so a 429 backoff doesn't
        # immediately re-burst once the sleep ends. (Hedged posts also gate.)
        try:
            return _post_maybe_hedged()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = (e.response.text[:300] if e.response is not None else "") or str(e)
            # 429 Too Many Requests is the rate-limit signal: retry with backoff
            # (and Prefer Retry-After when the gateway sends it). Other 4xx stay
            # non-retryable — those are client/config mistakes, not load.
            if status == 429:
                last_err = e
                if attempt < retries:
                    retry_after = None
                    if e.response is not None:
                        ra = e.response.headers.get("Retry-After")
                        if ra:
                            try:
                                retry_after = float(ra)
                            except ValueError:
                                retry_after = None
                    wait_s = (
                        retry_after
                        if retry_after is not None
                        else max(5.0, 2 ** (attempt + 2))
                    )
                    log(
                        f"WARN: {step} HTTP 429 (rate limited) attempt {attempt + 1}; "
                        f"backoff {wait_s:.1f}s"
                    )
                    time.sleep(wait_s)
                continue
            if 400 <= status < 500:
                raise RuntimeError(
                    f"{step}: HTTP {status} (not retrying): {body}"
                ) from e
            last_err = e
            if attempt < retries:
                # Gateway timeouts (504) / upstream overload need longer cool-down
                # than a generic 5xx blip — otherwise we immediately re-hammer NIM.
                if status in (502, 503, 504):
                    wait_s = max(4.0, 2 ** (attempt + 2))
                else:
                    wait_s = 2**attempt
                log(
                    f"WARN: {step} HTTP {status} attempt {attempt + 1}; "
                    f"retry in {wait_s}s"
                )
                time.sleep(wait_s)
        except (requests.ConnectionError, requests.Timeout, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                wait_s = max(2.0, 2 ** (attempt + 1))
                log(
                    f"WARN: {step} attempt {attempt + 1} failed ({e}); "
                    f"retry in {wait_s}s"
                )
                time.sleep(wait_s)
    raise RuntimeError(f"{step}: {last_err}") from last_err


def extract_content(response: dict) -> str:
    """Pull the assistant text out of an OpenAI-compatible chat response.

    Single source of truth (F009): layer0/layer1/ingest each had a byte-identical
    copy of this one-liner. They now import this instead. (Their `model_call`
    wrappers deliberately differ — max_tokens/temperature — so those stay local.)
    """
    return response["choices"][0]["message"]["content"]


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
    """Write `content` to `path` atomically and durably.

    The rename is what makes the swap atomic (readers see either the old file or the
    complete new one, never a half-written file). The two fsyncs (F018) make it
    durable across power loss: without fsyncing the temp file BEFORE the rename, a
    crash can leave the rename pointing at an empty/partial file; fsyncing the parent
    DIRECTORY after the rename ensures the directory entry itself is on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Write + flush the file's own bytes to disk before we swap it into place.
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.rename(path)
    # Persist the directory entry created by the rename (best-effort: not all
    # platforms allow opening a directory for fsync, so never let it break a write).
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def project_dir(project_id: str) -> Path:
    return BASE_DIR / "projects" / project_id


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
    # A multi-lesson Teacher Edition is a CONTAINER of many lessons, not a single
    # artifact — it must be fanned into per-lesson children before Path A can score
    # it (see te_prepass.py). Detected by name here; the TE pre-pass confirms with a
    # "Lesson N" density signal from Layer 0. Checked first so a "..._Teacher_Edition"
    # never mis-buckets as lesson_plan on an incidental keyword.
    if "teacher_edition" in n or "teacher edition" in n:
        return "teacher_edition_multi_lesson"
    if "answer_key" in n or "answer key" in n:
        return "answer_key"
    if "exit_ticket" in n or "exit ticket" in n:
        return "exit_ticket"
    if "quizizz" in n or "quiz" in n:
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
