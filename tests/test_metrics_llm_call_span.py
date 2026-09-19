"""`llm_call` must time the whole call, not the time to headers (#586).

`sub_span("llm_call")` wrapped `urlopen` alone, which returns as soon as
headers arrive. For the non-streaming callers the provider withholds headers
until generation finishes, so the number was roughly honest. For the streaming
chat route — the one route where the breakdown matters — headers arrive in
milliseconds and tokens follow for seconds, so the sub-span accounted for
almost none of the request it was meant to explain.

Time is injected, never slept: a threshold on a real clock is a flaky test.
"""

from __future__ import annotations

import json

import pytest

from minerva.llm import AnthropicBackend, LLMError, Message, OllamaBackend, OpenAIBackend
from minerva.metrics import recorder as recorder_mod
from minerva.metrics.recorder import Recorder

HEADER_TICK = 1.0  # clock units consumed before headers return
BODY_TICK = 10.0  # clock units consumed while the body is read


class FakeClock:
    """A clock the test advances by hand."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _sse(lines: list[str]) -> list[bytes]:
    return [f"data: {json.dumps(o)}\n\n".encode() for o in lines]


class FakeResp:
    """A response whose body costs BODY_TICK to consume."""

    def __init__(self, clock: FakeClock, payload: bytes, stream: list[bytes] | None):
        self._clock = clock
        self._payload = payload
        self._stream = stream or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        self._clock.advance(BODY_TICK)
        return self._payload

    def __iter__(self):
        for chunk in self._stream:
            # Cost is spread across the stream, as a real one is.
            self._clock.advance(BODY_TICK / len(self._stream))
            yield chunk

    def close(self):
        return None


def _install(monkeypatch, clock, payload, stream):
    def fake_urlopen(req, timeout=None):
        clock.advance(HEADER_TICK)
        return FakeResp(clock, payload, stream)

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)
    # `sub_span`'s `clock` default is bound at import, so patching
    # `time.perf_counter` afterwards would not reach it. Bind the fake at the
    # call site instead — `llm.py` holds its own reference to the name.
    monkeypatch.setattr(
        "minerva.llm.sub_span",
        lambda name: recorder_mod.sub_span(name, clock=clock),
    )


def _llm_call_ms(span) -> float:
    entries = [ms for name, ms in span._subs if name == "llm_call"]
    assert entries, f"no llm_call sub-span recorded; got {span._subs}"
    assert len(entries) == 1, f"expected one llm_call entry, got {entries}"
    return entries[0]


OPENAI_STREAM = _sse([{"choices": [{"delta": {"content": t}}]} for t in ("a", "b", "c")])
# One LINE per item: `_iter_sse_data_lines` treats each iteration of the
# response as a single line, so a blob containing "\n" is not two lines to it.
ANTHROPIC_STREAM = [
    b"event: content_block_delta\n",
    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"a"}}\n',
    b"\n",
    b"event: content_block_delta\n",
    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"b"}}\n',
    b"\n",
]
OLLAMA_STREAM = [b'{"message":{"content":"a"}}\n', b'{"message":{"content":"b"}}\n']

STREAMING = [
    pytest.param(
        lambda: OpenAIBackend(api_key="k", model="m"), OPENAI_STREAM, b"", id="openai"
    ),
    pytest.param(
        lambda: AnthropicBackend(api_key="k", model="m"), ANTHROPIC_STREAM, b"", id="anthropic"
    ),
    pytest.param(
        lambda: OllamaBackend(host="http://localhost:11434"), OLLAMA_STREAM, b"", id="ollama"
    ),
]


@pytest.mark.parametrize("make_backend,stream,payload", STREAMING)
def test_llm_call_covers_the_streamed_body(monkeypatch, make_backend, stream, payload):
    clock = FakeClock()
    _install(monkeypatch, clock, payload, stream)
    rec = Recorder(None, now=lambda: 0.0, clock=clock)

    with rec.record("chat", "POST") as span:
        tokens = list(make_backend().stream_complete([Message("user", "q")]))

    # Without this the fixture could yield nothing and the span assertion
    # below would still pass — it would be timing a stream that never was.
    assert tokens == ["a", "b", "c"][: len(tokens)] and tokens, (
        f"fixture produced no tokens: {tokens}"
    )
    ms = _llm_call_ms(span)
    expected = (HEADER_TICK + BODY_TICK) * 1000.0
    assert ms == pytest.approx(expected), (
        f"llm_call measured {ms}ms; time-to-headers alone is "
        f"{HEADER_TICK * 1000.0}ms and the full call is {expected}ms"
    )


class ExplodingResp(FakeResp):
    """A response whose stream dies partway through, as a dropped link does."""

    def __iter__(self):
        self._clock.advance(BODY_TICK)
        raise ConnectionResetError("peer went away")


@pytest.mark.parametrize("make_backend,stream,payload", STREAMING)
def test_an_interrupted_stream_is_still_timed(monkeypatch, make_backend, stream, payload):
    """A stream that dies mid-flight must surface as LLMError AND still record
    the time it burned. Timing only successful calls hides the slow failures,
    which are the ones worth seeing in a latency breakdown."""

    clock = FakeClock()

    def fake_urlopen(req, timeout=None):
        clock.advance(HEADER_TICK)
        return ExplodingResp(clock, payload, stream)

    monkeypatch.setattr("minerva.llm.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("minerva.llm.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "minerva.llm.sub_span", lambda name: recorder_mod.sub_span(name, clock=clock)
    )
    rec = Recorder(None, now=lambda: 0.0, clock=clock)

    with rec.record("chat", "POST") as span, pytest.raises(LLMError, match="stream interrupted"):
        list(make_backend().stream_complete([Message("user", "q")]))

    assert _llm_call_ms(span) == pytest.approx((HEADER_TICK + BODY_TICK) * 1000.0)


@pytest.mark.parametrize("make_backend,stream,payload", STREAMING)
def test_abandoning_a_stream_still_records_what_it_cost(
    monkeypatch, make_backend, stream, payload
):
    """`_send_sse`'s `finally: it.close()` is what closes the generator when a
    client disconnects — and closing it is what ends the span (#609). Without
    that contract this measurement would be best-effort."""

    clock = FakeClock()
    _install(monkeypatch, clock, payload, stream)
    rec = Recorder(None, now=lambda: 0.0, clock=clock)

    with rec.record("chat", "POST") as span:
        gen = make_backend().stream_complete([Message("user", "q")])
        next(gen)          # one token, then the client goes away
        gen.close()        # exactly what _send_sse's finally does

    ms = _llm_call_ms(span)
    assert ms > HEADER_TICK * 1000.0, "an abandoned stream recorded only connect time"
    assert ms < (HEADER_TICK + BODY_TICK) * 1000.0, "recorded more than it actually spent"
