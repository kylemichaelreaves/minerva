"""The registry's silent defaults (#498).

Three places where a forgotten or unknown value used to resolve to a plausible
default instead of failing: a ``CorpusWork`` with no ``corpus``/``author`` was
filed under Hegel, ``make_find_work``'s two branches disagreed about which work
wins a shared filename, and an unregistered corpus id became a paragraph-cited
English corpus on the ingest write path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva import corpus_registry, store
from minerva.corpus_works import CorpusWork, make_find_work
from minerva.migrations import runtime_helpers
from minerva.store.chunks import _resolve_work_refs

_BASE = {"code": "w", "translator": "", "edition_year": "", "fmt": "txt", "locator": "paragraph"}


def _work(title: str, *filenames: str) -> CorpusWork:
    return CorpusWork(**_BASE, filenames=filenames, title=title, corpus="x", author="X")


def test_corpus_work_requires_corpus_and_author():
    with pytest.raises(TypeError, match="corpus"):
        CorpusWork(**_BASE, filenames=("a.txt",), title="T", author="A")  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="author"):
        CorpusWork(**_BASE, filenames=("a.txt",), title="T", corpus="c")  # type: ignore[call-arg]


@pytest.mark.parametrize("case_insensitive", [False, True])
def test_find_work_branches_agree_last_declared_wins(case_insensitive):
    # A multi-work source file (one Gregor PDF holds twelve Kant works) is a
    # supported declaration; the singular lookup resolves it to the LAST work
    # declared, on both branches.
    works = (
        _work("A", "shared.txt"),
        _work("B", "Shared.txt" if case_insensitive else "shared.txt"),
    )
    find = make_find_work(works, case_insensitive=case_insensitive)
    assert find("shared.txt").title == "B"


def test_case_insensitive_find_work_matches_any_case():
    find = make_find_work((_work("A", "Foo.TXT"),), case_insensitive=True)
    assert find("foo.txt").title == "A"
    assert find("bar.txt") is None


def test_unknown_corpus_raises_when_strict():
    with pytest.raises(corpus_registry.UnknownCorpusError, match="no_such_corpus"):
        corpus_registry.citation_system_for_corpus("no_such_corpus", strict=True)
    with pytest.raises(corpus_registry.UnknownCorpusError, match="no_such_corpus"):
        corpus_registry.original_language_for_corpus("no_such_corpus", strict=True)


def test_unknown_corpus_stays_permissive_by_default():
    # Migrations replay against databases that may hold a since-renamed
    # corpus; runtime_helpers keeps the old fallback for them.
    assert corpus_registry.citation_system_for_corpus("no_such_corpus") == "paragraph"
    assert corpus_registry.original_language_for_corpus("no_such_corpus") == "eng"
    assert runtime_helpers.citation_system_for_corpus("no_such_corpus") == "paragraph"
    assert (
        runtime_helpers.original_language_for_corpus(
            "no_such_corpus", translator=None, this_lang="eng"
        )
        == "eng"
    )


def test_known_corpus_resolves_when_strict():
    assert corpus_registry.original_language_for_corpus("hegel", strict=True) == "deu"
    assert corpus_registry.citation_system_for_corpus("hegel", strict=True)


def test_ingest_write_path_rejects_unknown_corpus(tmp_path: Path):
    conn = store.open_db(tmp_path / "refs.sqlite")
    with pytest.raises(corpus_registry.UnknownCorpusError):
        _resolve_work_refs(
            conn,
            corpus="no_such_corpus",
            author="Nobody",
            work="Nothing",
            lang="eng",
            translator=None,
            edition_year=None,
        )
