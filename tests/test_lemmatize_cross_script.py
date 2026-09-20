"""Integration test for the cross-script lemmatize dispatch (#430).

Non-Greek text inside `grc` works was lemmatized under the Greek model,
entering `lemma_counts` as though it were Greek vocabulary. The fix:
mask cross-script runs out of the text the primary model sees, and
lemmatize each run separately under its own alternate-language model,
writing an explicit `chunk_lemmas.lang` only for those rows (NULL means
"this row's language is its chunk's language", per migration 0032).

The stub lemmatizer stands in for both spaCy models here: `batch_pipe`
plays the primary pass, `tokens` plays a secondary one constructed for
an alternate language mid-run — same two methods a real `Lemmatizer`
exposes, so `cmd_terms_lemmatize`'s own code is exercised, only the
model underneath is fake.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.cli.terms import lemmatize as lemmatize_mod
from minerva.lemmatize import Token

_WORD_RE = re.compile(r"\S+")


class _WhitespaceLemmatizer:
    """One Token per whitespace-separated word; lemma = lowercased
    surface. Records every (lang, text) it was actually asked to
    process, so a test can assert the primary pass saw MASKED text and
    the secondary pass saw only the extracted alternate-script run."""
    # The real Lemmatizer exposes these, and the pipeline-stats key is
    # built from them. A stub without them is an incomplete stand-in.
    backend = "stub"
    model = "stub"

    calls: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, lang: str) -> None:
        self.lang = lang

    @classmethod
    def _tokenize(cls, text: str) -> list[Token]:
        return [
            Token(surface=m.group(), start=m.start(), end=m.end(), lemma=m.group().lower())
            for m in _WORD_RE.finditer(text)
        ]

    def batch_pipe(self, items, *, batch_size, n_process):
        for text, ctx in items:
            type(self).calls.append((self.lang, text))
            yield self._tokenize(text), ctx

    def tokens(self, text: str) -> list[Token]:
        type(self).calls.append((self.lang, text))
        return self._tokenize(text)


def _args(db: Path, lang: str, **over) -> argparse.Namespace:
    base = {
        "db": db,
        "lang": lang,
        "edition_id": None,
        "all": False,
        "dry_run": False,
        "skip_aggregate": True,
        "batch_size": 4,
        "n_process": 1,
    }
    base.update(over)
    return argparse.Namespace(**base)


def _seed(tmp_path: Path, chunk_id: str, lang: str, text: str) -> Path:
    db = tmp_path / "cross_script.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id=chunk_id, lang=lang, text=text)))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def _run(db: Path, lang: str) -> int:
    with (
        patch.object(lemmatize_mod, "Lemmatizer", _WhitespaceLemmatizer),
        patch.object(lemmatize_mod, "is_supported", lambda l: True),  # noqa: E741
    ):
        return lemmatize_mod.cmd_terms_lemmatize(_args(db, lang))


def _lemma_rows(db: Path) -> list[tuple[str, str, str | None]]:
    conn = store.open_db(db)
    try:
        return conn.execute(
            "SELECT surface_form, lemma, lang FROM chunk_lemmas ORDER BY token_index"
        ).fetchall()
    finally:
        conn.close()


def test_embedded_latin_run_gets_lat_tagged_rows_in_a_grc_chunk(tmp_path: Path):
    text = "λόγος PLUT quaestio texere σοφία"
    db = _seed(tmp_path, "grc1", "grc", text)

    _WhitespaceLemmatizer.calls = []
    assert _run(db, "grc") == 0

    rows = _lemma_rows(db)
    by_surface = {surface: lang for surface, lemma, lang in rows}
    assert by_surface["λόγος"] is None
    assert by_surface["σοφία"] is None
    assert by_surface["PLUT"] == "lat"
    assert by_surface["quaestio"] == "lat"
    assert by_surface["texere"] == "lat"


def test_primary_pass_never_sees_the_masked_latin_run(tmp_path: Path):
    """The whole point of masking, not just re-tagging after the fact:
    the Greek model must never tokenize the Latin content at all."""

    text = "λόγος PLUT quaestio σοφία"
    db = _seed(tmp_path, "grc1", "grc", text)

    _WhitespaceLemmatizer.calls = []
    assert _run(db, "grc") == 0

    primary_calls = [t for lang, t in _WhitespaceLemmatizer.calls if lang == "grc"]
    assert len(primary_calls) == 1
    assert "PLUT" not in primary_calls[0]
    assert "quaestio" not in primary_calls[0]
    assert "λόγος" in primary_calls[0]
    assert "σοφία" in primary_calls[0]


def test_secondary_pass_receives_only_the_extracted_run(tmp_path: Path):
    text = "λόγος PLUT quaestio σοφία"
    db = _seed(tmp_path, "grc1", "grc", text)

    _WhitespaceLemmatizer.calls = []
    assert _run(db, "grc") == 0

    secondary_calls = [t for lang, t in _WhitespaceLemmatizer.calls if lang == "lat"]
    assert secondary_calls == ["PLUT quaestio"]


def test_an_alt_lang_with_no_registered_lemmatizer_is_skipped_not_fatal(tmp_path: Path):
    """Defensive: if the alternate language ever has no lemmatizer
    registered, the cross-script run is left unlemmatized rather than
    failing the whole pass over it."""

    from minerva.lemmatize import UnsupportedLanguageError

    text = "λόγος PLUT quaestio σοφία"
    db = _seed(tmp_path, "grc1", "grc", text)

    class _RefusingLemmatizer(_WhitespaceLemmatizer):
        def __init__(self, lang: str) -> None:
            if lang == "lat":
                raise UnsupportedLanguageError("no lemmatizer for lat in this test")
            super().__init__(lang)

    _WhitespaceLemmatizer.calls = []
    with (
        patch.object(lemmatize_mod, "Lemmatizer", _RefusingLemmatizer),
        patch.object(lemmatize_mod, "is_supported", lambda l: True),  # noqa: E741
    ):
        assert lemmatize_mod.cmd_terms_lemmatize(_args(db, "grc")) == 0

    rows = _lemma_rows(db)
    by_surface = {surface: lang for surface, lemma, lang in rows}
    assert by_surface["λόγος"] is None
    assert by_surface["σοφία"] is None
    assert "PLUT" not in by_surface
    assert "quaestio" not in by_surface


def test_a_chunk_with_no_cross_script_content_is_untouched(tmp_path: Path):
    """The overwhelming majority case: no alternate-language pass is
    even constructed, and every row's lang stays NULL."""

    text = "λόγος σοφία ἀρετή"
    db = _seed(tmp_path, "grc1", "grc", text)

    _WhitespaceLemmatizer.calls = []
    assert _run(db, "grc") == 0

    rows = _lemma_rows(db)
    assert all(lang is None for _surface, _lemma, lang in rows)
    assert all(lang == "grc" for lang, _t in _WhitespaceLemmatizer.calls)


def test_embedded_greek_run_gets_grc_tagged_rows_in_an_eng_chunk(tmp_path: Path):
    """The mirror direction (#427's eng mirror): a Greek quotation
    inside a non-grc edition gets lemmatized under the Greek model
    instead of producing garbage under the chunk's own language."""

    text = "he called it εὐδαιμονία in the text"
    db = _seed(tmp_path, "eng1", "eng", text)

    _WhitespaceLemmatizer.calls = []
    assert _run(db, "eng") == 0

    rows = _lemma_rows(db)
    by_surface = {surface: lang for surface, lemma, lang in rows}
    assert by_surface["he"] is None
    assert by_surface["text"] is None
    assert by_surface["εὐδαιμονία"] == "grc"

    secondary_calls = [t for lang, t in _WhitespaceLemmatizer.calls if lang == "grc"]
    assert secondary_calls == ["εὐδαιμονία"]
    primary_calls = [t for lang, t in _WhitespaceLemmatizer.calls if lang == "eng"]
    assert "εὐδαιμονία" not in primary_calls[0]
