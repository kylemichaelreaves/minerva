"""Pluggable LLM backends.

Supports four modes so the agent works in any setup the user has:

* ``none``      — no model call; the agent just renders retrieved passages.
* ``openai``    — OpenAI Chat Completions over HTTPS (uses ``OPENAI_API_KEY``).
* ``anthropic`` — Anthropic Messages API over HTTPS (uses ``ANTHROPIC_API_KEY``).
* ``ollama``    — local Ollama daemon at ``http://localhost:11434``.

All HTTP clients are implemented with stdlib ``urllib`` so no extra
dependencies are required.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import Any


@dataclass
class Message:
    role: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class LLMError(RuntimeError):
    pass


def _redact(detail: str, api_key: str | None) -> str:
    """Strip a verbatim API key from an upstream error body.

    Some providers echo the offending request (rate-limit replies that
    quote headers, debug proxies, etc.). The body would otherwise flow
    into our LLMError, then on into server-side logs. Redaction is
    cheap defense-in-depth.
    """

    if not api_key:
        return detail
    return detail.replace(api_key, "***")


def _iter_sse_data_lines(resp: HTTPResponse) -> Iterator[str]:
    """Yield JSON payloads from ``data:`` lines in an SSE response body."""

    for raw in resp:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line.startswith("data:"):
            continue
        payload = line[5:].lstrip()
        if payload == "[DONE]":
            return
        if payload:
            yield payload


_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
_MAX_RETRY_ATTEMPTS = 5


def _urlopen_with_retry(
    req: urllib.request.Request,
    *,
    timeout: float,
    api_key: str | None,
    provider: str,
    fatal_errors: tuple[type[BaseException], ...] = (),
    fatal_hint: str = "",
) -> HTTPResponse:
    """Open ``req`` with bounded exponential backoff for transient
    failures, returning the (still-open) response.

    Shared by every HTTP backend so retry behavior is consistent —
    previously only Anthropic retried, and an OpenAI/Ollama run died on
    the first 429 or mid-run ConnectionResetError (issues #57, #119).
    Five tries, doubling waits from 2s to 32s, then surface as
    ``LLMError``.

    ``fatal_errors`` names connection failures that must NOT be retried
    even though they'd otherwise look transient, with ``fatal_hint``
    appended to the message. Ollama uses it for ``ConnectionRefused``:
    against a local daemon that means "not running", and backing off for
    30s only delays the one message that helps. A remote API is
    different — a refused connection there can be a transient proxy
    blip — so the default retries it.
    """

    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRY_ATTEMPTS):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRYABLE_STATUS and attempt + 1 < _MAX_RETRY_ATTEMPTS:
                last_exc = exc
                time.sleep(min(32.0, 2.0 * (2**attempt)))
                continue
            detail = _redact(exc.read().decode("utf-8", errors="replace"), api_key)
            raise LLMError(f"{provider} HTTP {exc.code}: {detail}") from exc
        except (ConnectionResetError, ConnectionError, TimeoutError) as exc:
            if fatal_errors and isinstance(exc, fatal_errors):
                raise LLMError(
                    f"{provider} connection error{fatal_hint}: {exc}"
                ) from exc
            if attempt + 1 < _MAX_RETRY_ATTEMPTS:
                last_exc = exc
                time.sleep(min(32.0, 2.0 * (2**attempt)))
                continue
            raise LLMError(f"{provider} connection reset after retries: {exc}") from exc
        except urllib.error.URLError as exc:
            # URLError wraps a variety of socket-layer issues; treat the
            # ones that look transient (reset / refused / DNS blip) as
            # retryable, the rest as fatal.
            reason = getattr(exc, "reason", None)
            if fatal_errors and isinstance(reason, fatal_errors):
                raise LLMError(
                    f"{provider} connection error{fatal_hint}: {exc}"
                ) from exc
            transient = isinstance(
                reason,
                (ConnectionResetError, ConnectionError, socket.timeout, TimeoutError),
            )
            if transient and attempt + 1 < _MAX_RETRY_ATTEMPTS:
                last_exc = exc
                time.sleep(min(32.0, 2.0 * (2**attempt)))
                continue
            raise LLMError(f"{provider} connection error: {exc}") from exc
    raise LLMError(f"{provider} call failed after retries: {last_exc!r}")


def _iter_ndjson_lines(resp: HTTPResponse) -> Iterator[dict]:
    """Yield parsed JSON objects from newline-delimited response bodies."""

    buf = ""
    for raw in resp:
        buf += raw.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
    tail = buf.strip()
    if tail:
        yield json.loads(tail)


class LLMBackend:
    name: str = "base"

    def complete(self, messages: list[Message], *, temperature: float = 0.2) -> str:
        raise NotImplementedError

    def stream_complete(
        self, messages: list[Message], *, temperature: float = 0.2
    ) -> Iterator[str]:
        """Yield text fragments as they arrive from the provider."""
        raise NotImplementedError


class NullBackend(LLMBackend):
    name = "none"

    def complete(self, messages: list[Message], *, temperature: float = 0.2) -> str:
        return ""

    def stream_complete(
        self, messages: list[Message], *, temperature: float = 0.2
    ) -> Iterator[str]:
        return iter(())


class OpenAIBackend(LLMBackend):
    name = "openai"

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMError("OpenAI backend requires OPENAI_API_KEY in the environment.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, messages: list[Message], *, temperature: float = 0.2) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [m.to_dict() for m in messages],
                "temperature": temperature,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with _urlopen_with_retry(
            req, timeout=self.timeout, api_key=self.api_key, provider="OpenAI"
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI response: {payload!r}") from exc
        if not isinstance(content, str):
            raise LLMError(f"Unexpected OpenAI response: {payload!r}")
        return content.strip()

    def stream_complete(
        self, messages: list[Message], *, temperature: float = 0.2
    ) -> Iterator[str]:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [m.to_dict() for m in messages],
                "temperature": temperature,
                "stream": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        resp = _urlopen_with_retry(
            req, timeout=self.timeout, api_key=self.api_key, provider="OpenAI"
        )
        try:
            for data_line in _iter_sse_data_lines(resp):
                chunk = json.loads(data_line)
                # `or [{}]` guards chunks with an empty choices list
                # (some proxies emit usage-only frames that way).
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield text
        except (ConnectionResetError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            # A failure mid-iteration (dropped connection, truncated
            # frame) must surface as LLMError, not a raw exception that
            # the handler reports as a generic "server error" (issue #59).
            raise LLMError(f"OpenAI stream interrupted: {exc}") from exc
        finally:
            resp.close()


class AnthropicBackend(LLMBackend):
    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        max_tokens: int = 4096,
        timeout: float = 60.0,
        enable_prompt_cache: bool | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("Anthropic backend requires ANTHROPIC_API_KEY in the environment.")
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Prompt caching defaults on. Opt out via POIETES_DISABLE_PROMPT_CACHE=1
        # for debugging cost-attribution issues or A/B comparing.
        if enable_prompt_cache is None:
            self.enable_prompt_cache = os.environ.get("POIETES_DISABLE_PROMPT_CACHE", "") not in (
                "1",
                "true",
                "True",
            )
        else:
            self.enable_prompt_cache = enable_prompt_cache
        # Per-thread usage block surfaced by complete(). Read by callers
        # that want to log cache_read_input_tokens / cache_creation_input_tokens
        # for observability. Non-streaming only; SSE responses aggregate
        # usage in their message_delta events.
        self._usage_tls = threading.local()

    @property
    def last_usage(self) -> dict[str, Any] | None:
        return getattr(self._usage_tls, "usage", None)

    @last_usage.setter
    def last_usage(self, value: dict[str, Any] | None) -> None:
        self._usage_tls.usage = value

    def _build_body(
        self,
        messages: list[Message],
        *,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        """Compose the Anthropic Messages API body. Centralises the
        system-prompt lift + the prompt-caching cache_control markers
        so non-streaming and streaming paths stay in lockstep."""

        # Anthropic's Messages API takes the system prompt as a top-level
        # field, not a message with role=system. Lift any system messages
        # out and join them.
        system_parts = [m.content for m in messages if m.role == "system"]
        chat: list[dict[str, Any]] = [m.to_dict() for m in messages if m.role != "system"]
        body_dict: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "messages": chat,
        }
        if stream:
            body_dict["stream"] = True
        if system_parts:
            joined_system = "\n\n".join(system_parts)
            if self.enable_prompt_cache:
                # Mark the system block ephemeral. Only engages caching
                # when the system itself is ≥1024 tokens (Sonnet/Opus
                # minimum); below that the directive is silently ignored
                # by the API.
                body_dict["system"] = [
                    {
                        "type": "text",
                        "text": joined_system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                body_dict["system"] = joined_system

        # Multi-turn chat caching: mark the last *history* message
        # (chat[-2] when chat[-1] is the new user turn) as a cache
        # breakpoint. The prefix system+all-prior-turns gets cached, so
        # the next turn in the same conversation reads it back. A short
        # conversation may not cross the 1024-token floor; once it
        # does, every subsequent turn pays the cheap read cost.
        if self.enable_prompt_cache and len(chat) >= 2:
            target = chat[-2]
            content = target.get("content")
            if isinstance(content, str):
                target["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
        return body_dict

    def _urlopen_with_retry(self, req: urllib.request.Request) -> HTTPResponse:
        """Thin wrapper over the shared :func:`_urlopen_with_retry`
        (issue #57). Long-running batched jobs (refs llm-verify) hit
        Anthropic for hundreds of calls and routinely catch a
        ConnectionResetError or 429/5xx mid-run; retry keeps the job
        alive. Shared by ``complete`` and ``stream_complete``."""

        return _urlopen_with_retry(
            req, timeout=self.timeout, api_key=self.api_key, provider="Anthropic"
        )

    def complete(self, messages: list[Message], *, temperature: float = 0.2) -> str:
        # Reset up front so a failed call can't surface the previous
        # call's usage block to observability readers.
        self.last_usage = None
        body = json.dumps(self._build_body(messages, temperature=temperature, stream=False)).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.base_url}/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with self._urlopen_with_retry(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        try:
            blocks = payload["content"]
            text_parts = [b["text"] for b in blocks if b.get("type") == "text"]
            joined = "".join(text_parts).strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Anthropic response: {payload!r}") from exc
        # Surface the usage block for cache-hit observability. Callers
        # can read backend.last_usage to log cache_read_input_tokens /
        # cache_creation_input_tokens after each non-streaming call.
        self.last_usage = payload.get("usage") if isinstance(payload, dict) else None
        if not joined:
            raise LLMError(f"Anthropic returned no text content: {payload!r}")
        return joined

    def stream_complete(
        self, messages: list[Message], *, temperature: float = 0.2
    ) -> Iterator[str]:
        # Streaming never populates last_usage; clear it so readers
        # don't attribute the previous non-streaming call's usage here.
        self.last_usage = None
        body = json.dumps(self._build_body(messages, temperature=temperature, stream=True)).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.base_url}/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        resp = self._urlopen_with_retry(req)
        try:
            for data_line in _iter_sse_data_lines(resp):
                event = json.loads(data_line)
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield text
        except (ConnectionResetError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            # Mid-stream failure → LLMError, not a raw exception the
            # handler would mislabel as a generic "server error" (#59).
            raise LLMError(f"Anthropic stream interrupted: {exc}") from exc
        finally:
            resp.close()


# Ollama talks to a daemon on localhost, so a refused connection is a
# definitive "not running" rather than a blip worth backing off for.
_OLLAMA_FATAL_ERRORS: tuple[type[BaseException], ...] = (ConnectionRefusedError,)
_OLLAMA_DOWN_HINT = " (is `ollama serve` running?)"


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(
        self,
        *,
        model: str = "llama3.1",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, messages: list[Message], *, temperature: float = 0.2) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [m.to_dict() for m in messages],
                "stream": False,
                "options": {"temperature": temperature},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urlopen_with_retry(
            req,
            timeout=self.timeout,
            api_key=None,
            provider="Ollama",
            fatal_errors=_OLLAMA_FATAL_ERRORS,
            fatal_hint=_OLLAMA_DOWN_HINT,
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        try:
            return payload["message"]["content"].strip()
        except KeyError as exc:
            raise LLMError(f"Unexpected Ollama response: {payload!r}") from exc

    def stream_complete(
        self, messages: list[Message], *, temperature: float = 0.2
    ) -> Iterator[str]:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [m.to_dict() for m in messages],
                "stream": True,
                "options": {"temperature": temperature},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = _urlopen_with_retry(
            req,
            timeout=self.timeout,
            api_key=None,
            provider="Ollama",
            fatal_errors=_OLLAMA_FATAL_ERRORS,
            fatal_hint=_OLLAMA_DOWN_HINT,
        )
        try:
            for chunk in _iter_ndjson_lines(resp):
                msg = chunk.get("message") or {}
                text = msg.get("content")
                if text:
                    yield text
                if chunk.get("done"):
                    break
        except (ConnectionResetError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            # Mid-stream failure → LLMError, not a raw exception (#59).
            raise LLMError(f"Ollama stream interrupted: {exc}") from exc
        finally:
            resp.close()


def make_backend(
    kind: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMBackend:
    kind = (kind or "none").lower()
    if kind == "none":
        return NullBackend()
    if kind == "openai":
        return OpenAIBackend(
            model=model or "gpt-4o-mini",
            base_url=base_url or "https://api.openai.com/v1",
        )
    if kind == "anthropic":
        return AnthropicBackend(
            model=model or "claude-sonnet-4-6",
            base_url=base_url or "https://api.anthropic.com/v1",
        )
    if kind == "ollama":
        return OllamaBackend(
            model=model or "llama3.1",
            host=base_url or "http://localhost:11434",
        )
    raise LLMError(f"Unknown LLM backend: {kind!r}")
