"""The Stanza parse must run outside the corpus lock (#340).

Holding `corpus_lock` across the parse made an unrelated work-range request
take 1,433.6 ms against a 355.5 ms baseline, and 4,499 ms the first time a
process loaded the model. These tests pin the property that fixes it: while
the parser is running, the lock is free.

No Stanza here — CI installs `.[dev,hegel,embed]`, not `[lemma]`. The parser
is monkeypatched, which is also what lets a test observe the lock state from
inside the parse.
"""

from __future__ import annotations

import threading

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.syntax import _handle_chunk_syntax, _handle_syntax_correction_create
from minerva.http.serve import _start_syntax_warmup
from minerva.syntax import parse as parse_mod
from minerva.syntax import queries as q

# German: the parser is `deu`-only (`queries.SUPPORTED_LANG`).
CHUNK = "hegel-p17"
ENGLISH_CHUNK = "rep-509d"


def fake_tokens() -> list[q.SyntaxToken]:
    def t(tok_id: int, form: str, head: int, deprel: str) -> q.SyntaxToken:
        return q.SyntaxToken(
            sent_ord=0,
            tok_id=tok_id,
            form=form,
            lemma=form.lower(),
            upos="X",
            xpos=None,
            feats=None,
            misc=None,
            head=head,
            deprel=deprel,
            surface_start=tok_id,
            surface_end=tok_id + len(form),
        )

    return [t(1, "Der", 2, "det"), t(2, "Geist", 3, "nsubj"), t(3, "entwickelt", 0, "root")]


def test_parse_runs_with_the_lock_released(populated_db, monkeypatch: pytest.MonkeyPatch):
    """The whole point: the lock is free while the parser works."""

    lock = threading.Lock()
    observed: list[bool] = []

    def fake_parse_text(text: str) -> list[q.SyntaxToken]:
        # `acquire(blocking=False)` from the same thread that would hold the
        # lock: True proves it is not held, and a non-reentrant Lock cannot
        # give a false positive here.
        got = lock.acquire(blocking=False)
        observed.append(got)
        if got:
            lock.release()
        return fake_tokens()

    monkeypatch.setattr("minerva.syntax.parse.parse_text", fake_parse_text)
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")

    tokens = q.load_or_parse_locked(populated_db, CHUNK, lock)

    assert observed == [True], "parse ran while the corpus lock was held"
    assert [t.form for t in tokens] == ["Der", "Geist", "entwickelt"]
    # And the lock is left free afterwards.
    assert lock.acquire(blocking=False)
    lock.release()


def test_cached_chunk_never_reaches_the_parser(populated_db, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_parse_text(text: str) -> list[q.SyntaxToken]:
        calls.append(text)
        return fake_tokens()

    monkeypatch.setattr("minerva.syntax.parse.parse_text", fake_parse_text)
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")
    lock = threading.Lock()

    q.load_or_parse_locked(populated_db, CHUNK, lock)
    q.load_or_parse_locked(populated_db, CHUNK, lock)

    assert len(calls) == 1


def test_unknown_chunk_returns_none(populated_db):
    assert q.load_or_parse_locked(populated_db, "no-such-chunk", threading.Lock()) is None


def test_wrong_language_is_refused_before_the_parser_loads(
    populated_db, monkeypatch: pytest.MonkeyPatch
):
    """The guard has to fire before the import that pulls Stanza in."""

    def explode(text: str) -> list[q.SyntaxToken]:
        raise AssertionError("parser reached for a non-German chunk")

    monkeypatch.setattr("minerva.syntax.parse.parse_text", explode)

    with pytest.raises(q.UnsupportedSyntaxLanguage):
        q.load_or_parse_locked(populated_db, ENGLISH_CHUNK, threading.Lock())


def test_a_parse_stored_during_the_window_wins(populated_db, monkeypatch: pytest.MonkeyPatch):
    """Two requests can parse one chunk at once now that the lock is released.

    The second writer must not clobber the first: whoever finishes the parse
    last should find the stored copy and return it untouched.
    """

    rival = [
        q.SyntaxToken(
            sent_ord=0,
            tok_id=1,
            form="Rival",
            lemma="rival",
            upos="X",
            xpos=None,
            feats=None,
            misc=None,
            head=0,
            deprel="root",
            surface_start=0,
            surface_end=5,
        )
    ]

    def fake_parse_text(text: str) -> list[q.SyntaxToken]:
        # Simulate the other request finishing while this one parses.
        q.save_parse(populated_db, CHUNK, rival, parser="rival-parser")
        return fake_tokens()

    monkeypatch.setattr("minerva.syntax.parse.parse_text", fake_parse_text)
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")

    tokens = q.load_or_parse_locked(populated_db, CHUNK, threading.Lock())

    assert [t.form for t in tokens] == ["Rival"]
    stored = populated_db.execute(
        "SELECT parser FROM chunk_syntax_state WHERE chunk_id = ?", (CHUNK,)
    ).fetchone()[0]
    assert stored == "rival-parser", "the later parse overwrote a stored one"


@pytest.fixture
def deps(populated_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("minerva.syntax.parse.parse_text", lambda text: fake_tokens())
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")
    return make_deps(populated_db, StubBackend())


def test_get_handler_releases_the_lock(deps):
    """Regression guard: both handlers dropped `@with_corpus_lock`, so a
    stale decorator would deadlock rather than merely slow things down."""

    body = _handle_chunk_syntax(deps, CHUNK)

    assert body["chunk_id"] == CHUNK
    assert deps.corpus_lock.acquire(blocking=False)
    deps.corpus_lock.release()


def test_correction_create_releases_the_lock(deps):
    """The correction path parses too, and used to hold the lock across it."""

    body = _handle_syntax_correction_create(
        deps, CHUNK, {"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "amod"}
    )

    assert body["token"]["deprel"] == "amod"
    assert deps.corpus_lock.acquire(blocking=False)
    deps.corpus_lock.release()


def test_warm_pipeline_reports_failure_instead_of_raising(monkeypatch: pytest.MonkeyPatch):
    """Startup must survive a missing `[lemma]` extra or an absent model."""

    def no_stanza() -> object:
        raise ImportError("No module named 'stanza'")

    monkeypatch.setattr(parse_mod, "_pipeline", no_stanza)

    assert parse_mod.warm_pipeline() is False


def test_warm_pipeline_reports_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(parse_mod, "_pipeline", lambda: object())

    assert parse_mod.warm_pipeline() is True


def test_startup_warms_the_parser_off_the_serving_thread(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(parse_mod, "warm_pipeline", lambda: True)

    thread = _start_syntax_warmup()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert thread.daemon, "a warm-up in flight must not hold the process open at ctrl-c"
    assert "syntax: parser ready." in capsys.readouterr().out


def test_startup_stays_quiet_when_the_parser_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """No Stanza is the CI case, and the normal case for anyone who has not
    installed the extra. It must not look like an error."""

    monkeypatch.setattr(parse_mod, "warm_pipeline", lambda: False)

    _start_syntax_warmup().join(timeout=5)

    assert capsys.readouterr().out == ""
