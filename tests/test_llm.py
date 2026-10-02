"""Tests for `minerva.llm` — stream parsers and backend wire formats."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from minerva import llm as llm_mod
from minerva.llm import (
    AnthropicBackend,
    LLMError,
    Message,
    NullBackend,
    OllamaBackend,
    OpenAIBackend,
    _iter_ndjson_lines,
    _iter_sse_data_lines,
    _redact,
)


class _ByteStream:
    """Minimal response body stand-in for parser unit tests."""

    def __init__(self, body: bytes) -> None:
        self._lines = [ln + b"\n" for ln in body.split(b"\n") if ln]

    def __iter__(self):
        yield from self._lines

    def close(self) -> None:
        pass


def test_redact_strips_api_key_when_present():
    body = '{"error": {"message": "bad header sk-test-12345"}}'
    assert _redact(body, "sk-test-12345") == '{"error": {"message": "bad header ***"}}'


def test_redact_no_op_when_key_is_falsy():
    body = "OpenAI HTTP 401: invalid"
    assert _redact(body, None) == body
    assert _redact(body, "") == body


def test_iter_sse_data_lines_parses_openai_chunks():
    body = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    lines = list(_iter_sse_data_lines(_ByteStream(body)))
    assert len(lines) == 2
    assert json.loads(lines[0])["choices"][0]["delta"]["content"] == "Hel"


def test_iter_ndjson_lines_parses_ollama_chunks():
    body = (
        b'{"message":{"content":"Hi"},"done":false}\n{"message":{"content":" there"},"done":true}\n'
    )
    chunks = list(_iter_ndjson_lines(_ByteStream(body)))
    assert chunks[0]["message"]["content"] == "Hi"
    assert chunks[1]["done"] is True


def test_null_backend_stream_yields_nothing():
    backend = NullBackend()
    assert list(backend.stream_complete([Message("user", "hi")])) == []


def test_openai_stream_complete_yields_deltas(monkeypatch):
    backend = OpenAIBackend(api_key="sk-test", base_url="https://api.example.com/v1")
    body = (
        b'data: {"choices":[{"delta":{"content":"The"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" cave"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    class FakeResp:
        def __init__(self, data: bytes) -> None:
            self._fp = io.BytesIO(data)

        def __iter__(self):
            for line in self._fp.read().split(b"\n"):
                if line:
                    yield line + b"\n"

        def close(self) -> None:
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResp(body)

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    out = list(backend.stream_complete([Message("user", "q")]))
    assert out == ["The", " cave"]


def test_openai_complete_retries_transient_429(monkeypatch):
    # Shared retry now covers OpenAI, not just Anthropic (issue #57):
    # a transient 429 is retried rather than raised on the first hit.
    backend = OpenAIBackend(api_key="sk-test", base_url="https://api.example.com/v1")
    calls = {"n": 0}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(b"slow down"))
        return FakeResp()

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    assert backend.complete([Message("user", "q")]) == "ok"
    assert calls["n"] == 2


def test_openai_stream_wraps_midstream_error_as_llmerror(monkeypatch):
    # A dropped connection mid-iteration must surface as LLMError, not a
    # raw ConnectionResetError the handler mislabels (issue #59).
    backend = OpenAIBackend(api_key="sk-test", base_url="https://api.example.com/v1")

    class BoomResp:
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n'
            raise ConnectionResetError("dropped")

        def close(self):
            pass

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", lambda req, timeout=None: BoomResp())
    with pytest.raises(LLMError):
        list(backend.stream_complete([Message("user", "q")]))


def test_ollama_complete_retries_transient_503(monkeypatch):
    # #57 wired the shared retry into OpenAI but skipped Ollama, so a
    # long batched run still died on the first blip. Ollama is arguably
    # the most likely backend to drop one: a local daemon reloading a
    # model or getting OOM-killed returns exactly this (#119).
    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"message":{"content":"ok"}}'

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 503, "unavailable", {}, io.BytesIO(b"loading model")
            )
        return FakeResp()

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    assert backend.complete([Message("user", "q")]) == "ok"
    assert calls["n"] == 2


def test_ollama_complete_retries_connection_reset(monkeypatch):
    """The mid-run reset #57 was filed for — a daemon restart."""

    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"message":{"content":"ok"}}'

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionResetError("daemon restarted")
        return FakeResp()

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    assert backend.complete([Message("user", "q")]) == "ok"
    assert calls["n"] == 3


def test_ollama_connection_refused_is_fatal_and_keeps_the_hint(monkeypatch):
    """A refused connection means the daemon isn't running. Retrying it
    for 30s just delays the one message that actually helps, so it stays
    fatal and keeps the `ollama serve` hint."""

    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    with pytest.raises(LLMError, match="ollama serve"):
        backend.complete([Message("user", "q")])
    assert calls["n"] == 1, "refused connection must not be retried"


def test_ollama_bare_connection_refused_is_also_fatal(monkeypatch):
    """`urlopen` raises ConnectionRefusedError directly as often as it
    raises it wrapped in URLError, depending on where the connect
    fails. Both paths run through the fatal-error check, so both are
    pinned — the wrapped-only test would leave half the guard untested.
    """

    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    with pytest.raises(LLMError, match="ollama serve"):
        backend.complete([Message("user", "q")])
    assert calls["n"] == 1


def test_ollama_gives_up_after_max_attempts(monkeypatch):
    """A daemon that never comes back must surface as LLMError once the
    retry budget is spent, not retry forever."""

    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise ConnectionResetError("still down")

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    with pytest.raises(LLMError, match="after retries"):
        backend.complete([Message("user", "q")])
    assert calls["n"] == llm_mod._MAX_RETRY_ATTEMPTS


def test_ollama_stream_retries_transient_503(monkeypatch):
    """The streaming path needs the same treatment — it opened the
    connection with a bare urlopen too."""

    backend = OllamaBackend(host="http://localhost:11434")
    calls = {"n": 0}

    class FakeResp:
        def __iter__(self):
            yield b'{"message":{"content":"A"},"done":true}\n'

        def close(self):
            pass

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 503, "unavailable", {}, io.BytesIO(b"loading")
            )
        return FakeResp()

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)

    assert list(backend.stream_complete([Message("user", "q")])) == ["A"]
    assert calls["n"] == 2


def test_ollama_stream_complete_yields_deltas(monkeypatch):
    backend = OllamaBackend(host="http://localhost:11434")
    body = b'{"message":{"content":"A"},"done":false}\n{"message":{"content":"B"},"done":true}\n'

    class FakeResp:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._pos = 0

        def read(self, n=-1):
            if n == -1:
                rest = self._data[self._pos :]
                self._pos = len(self._data)
                return rest
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
            return chunk

        def __iter__(self):
            for line in self._data.split(b"\n"):
                if line:
                    yield line + b"\n"

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "minerva.llm.urllib.request.urlopen", lambda req, timeout=None: FakeResp(body)
    )
    out = list(backend.stream_complete([Message("user", "q")]))
    assert out == ["A", "B"]


def test_anthropic_stream_complete_yields_text_deltas(monkeypatch):
    backend = AnthropicBackend(api_key="sk-ant", base_url="https://api.example.com/v1")
    body = (
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"!"}}\n\n'
    )

    class FakeResp:
        def __init__(self, data: bytes) -> None:
            self._lines = [ln + b"\n" for ln in data.split(b"\n") if ln]

        def __iter__(self):
            yield from self._lines

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "minerva.llm.urllib.request.urlopen", lambda req, timeout=None: FakeResp(body)
    )
    out = list(backend.stream_complete([Message("user", "q")]))
    assert out == ["Hi", "!"]


def _capture_anthropic_body(monkeypatch, backend, payload):
    sent: dict = {}

    class FakeResp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        sent.update(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    return sent


_OK = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}


def test_anthropic_default_model_omits_temperature(monkeypatch):
    # Sonnet 5.5 400s on any non-default temperature; callers still pass one.
    backend = AnthropicBackend(api_key="sk-ant", base_url="https://api.example.com/v1")
    sent = _capture_anthropic_body(monkeypatch, backend, _OK)
    assert backend.complete([Message("user", "q")], temperature=0.1) == "ok"
    assert sent["model"] == "claude-sonnet-5-5"
    assert "temperature" not in sent


def test_anthropic_older_model_still_sends_temperature(monkeypatch):
    backend = AnthropicBackend(
        api_key="sk-ant", base_url="https://api.example.com/v1", model="claude-sonnet-4-6"
    )
    sent = _capture_anthropic_body(monkeypatch, backend, _OK)
    backend.complete([Message("user", "q")], temperature=0.1)
    assert sent["temperature"] == 0.1


def test_anthropic_refusal_raises_with_category(monkeypatch):
    backend = AnthropicBackend(api_key="sk-ant", base_url="https://api.example.com/v1")
    payload = {"content": [], "stop_reason": "refusal", "stop_details": {"category": "cyber"}}
    _capture_anthropic_body(monkeypatch, backend, payload)
    with pytest.raises(LLMError, match=r"declined.*cyber"):
        backend.complete([Message("user", "q")])
