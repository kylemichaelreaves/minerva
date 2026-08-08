"""#262 — ``terms lemmatize`` must not hand an unpicklable payload to
spaCy's spawn-based multiprocessing.

``la_core_web_sm`` installs a ``Token.set_extension(..., getter=lambda
t: ...)`` at import time (``la_core_web_sm/functions.py:121-126``). That
lambda lands in spaCy's **global** ``Underscore`` extension registry,
which ``Language._multiprocessing_pipe`` passes to every spawned worker
via ``Underscore.get_state()``. A lambda has no qualified name, so
``pickle`` refuses it and ``proc.start()`` raises.

Recovering after the fact is not enough, and that is what these tests
pin. spaCy fills its worker queues (``sender.send()`` twice) *before*
``for proc in procs: proc.start()``, and its cleanup ``try/finally``
only begins after the loop — so a failed spawn leaks ``mp.Queue``
objects whose feeder threads are joined by
``multiprocessing.util._exit_function``. They block forever writing to
a pipe no child will ever drain: catching the ``PicklingError`` still
leaves the process unkillable except by ``kill -9``. The payload has to
be checked *before* the queues exist.
"""

from __future__ import annotations

import pickle
from typing import ClassVar

from minerva.lemmatize import Lemmatizer, Token, _unpicklable_reason

# Mirrors la_core_web_sm's extension getter: a lambda bound at MODULE
# level. That placement is load-bearing for the test — pickling it fails
# with `PicklingError` ("attribute lookup <lambda> ... failed"), the
# error #262 reports, whereas a lambda defined inside a function fails
# with `AttributeError` ("Can't get local object") instead.
_MODULE_LEVEL_LAMBDA = lambda t: t  # noqa: E731


class _StubToken:
    """Minimal stand-in for a spaCy ``Token`` — only the attributes
    ``_tokens_from_spacy_doc`` actually reads."""

    is_space = False
    is_punct = False
    morph = ""

    def __init__(self, text: str) -> None:
        self.text = text
        self.idx = 0
        self.lemma_ = text
        self.pos_ = "NOUN"


class _StubDoc:
    def __init__(self, text: str) -> None:
        self._tokens = [_StubToken(text.split()[0])]

    def __iter__(self):
        return iter(self._tokens)


class _RecordingNlp:
    """Stand-in for a spaCy ``Language`` that records the ``n_process``
    it was asked for.

    When ``picklable=False`` it holds a lambda in an instance attribute
    — unpicklable for exactly the reason LatinCy's extension getter is,
    so the probe under test is exercised for real rather than mocked.
    """

    # Split the way spaCy splits it: `la_core_web_sm` reports
    # lang='la', name='core_web_sm'.
    meta: ClassVar[dict[str, str]] = {"lang": "xx", "name": "core_web_sm"}

    def __init__(self, *, picklable: bool) -> None:
        self.calls: list[int] = []
        self._payload = None if picklable else _MODULE_LEVEL_LAMBDA

    def pipe(self, items, *, batch_size, n_process, as_tuples):
        self.calls.append(n_process)
        for text, ctx in items:
            yield _StubDoc(text), ctx


def _lemmatizer(nlp) -> Lemmatizer:
    """A spaCy-backed ``Lemmatizer`` around ``nlp`` without loading a
    real model (which ``__init__`` would otherwise do)."""

    lm = Lemmatizer.__new__(Lemmatizer)
    lm.lang = "lat"
    lm._backend = "spacy"
    lm._nlp = nlp
    return lm


def test_unpicklable_reason_names_the_offending_lambda():
    reason = _unpicklable_reason({"getter": _MODULE_LEVEL_LAMBDA})
    assert isinstance(reason, pickle.PicklingError)
    assert "lambda" in str(reason)


def test_unpicklable_reason_also_catches_a_locally_defined_lambda():
    """A closure-scoped lambda fails with ``AttributeError`` rather than
    ``PicklingError``. Both are the same defect to an operator, so both
    must be reported rather than escape."""

    def _local():
        return lambda t: t

    reason = _unpicklable_reason({"getter": _local()})
    assert isinstance(reason, AttributeError)


def test_unpicklable_reason_is_none_for_a_plain_payload():
    assert _unpicklable_reason({"a": 1}, [2, 3]) is None


def test_batch_pipe_refuses_parallel_when_the_payload_cannot_be_pickled(capsys):
    nlp = _RecordingNlp(picklable=False)
    lm = _lemmatizer(nlp)

    out = list(
        lm.batch_pipe(
            [("prima chunk", "c1"), ("secunda chunk", "c2")],
            batch_size=8,
            n_process=4,
        )
    )

    # Downgraded to a single process, and every chunk still came out.
    assert nlp.calls == [1]
    assert [ctx for _, ctx in out] == ["c1", "c2"]
    assert [toks[0].lemma for toks, _ in out] == ["prima", "secunda"]
    err = capsys.readouterr().err
    assert "n_process=1" in err
    # Names WHICH model refused. `la_core_web_sm` and `en_core_web_sm`
    # both report name='core_web_sm', so the bare name identifies
    # nothing in a log.
    assert "xx_core_web_sm" in err


def test_model_name_falls_back_to_the_bare_name_without_a_lang(capsys):
    nlp = _RecordingNlp(picklable=False)
    nlp.meta = {"name": "core_web_sm"}
    assert _lemmatizer(nlp).model == "core_web_sm"


def test_batch_pipe_keeps_the_parallel_path_when_the_payload_pickles(capsys):
    nlp = _RecordingNlp(picklable=True)
    lm = _lemmatizer(nlp)

    out = list(lm.batch_pipe([("prima chunk", "c1")], batch_size=8, n_process=4))

    assert nlp.calls == [4]
    assert out[0][1] == "c1"
    assert capsys.readouterr().err == ""


def test_batch_pipe_does_not_probe_when_already_single_process(capsys):
    """``n_process=1`` spawns nothing, so an unpicklable payload is
    irrelevant — probing it would cost a needless model serialization
    on every single-process run."""

    nlp = _RecordingNlp(picklable=False)
    lm = _lemmatizer(nlp)

    out = list(lm.batch_pipe([("prima chunk", "c1")], batch_size=8, n_process=1))

    assert nlp.calls == [1]
    assert isinstance(out[0][0][0], Token)
    assert capsys.readouterr().err == ""
