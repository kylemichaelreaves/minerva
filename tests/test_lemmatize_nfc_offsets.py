"""The NFC rewrite is the lemmatizer's, so the offsets are mapped (#311).

``terms lemmatize`` handed the pipeline ``unicodedata.normalize("NFC",
text)`` and then stored the resulting ``surface_start``/``surface_end``
against ``chunks.text``, which is not NFC for 16,032 chunks. Where
composition shortens the string, every token after the first composed
character is short by the accumulated delta — the same defect class as
#307, one layer above the fix that landed in PR #310.

The normalization itself has to stay: fed the stored, decomposed text,
``grc_dep_web_sm`` produces materially worse lemmas (2,313 differences
over 51,549 tokens on 300 live chunks — ``λέγων`` left as itself instead
of ``λέγω``, ``κατηγορίας·`` complete with the ano teleia). So the
rewrite moves into :class:`~minerva.lemmatize.Lemmatizer`, beside the
tokenizer rewrite it already maps back, and the caller's string stays the
one the offsets index.

These tests use fake pipelines — no spaCy, no Stanza, no model download.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from conftest import make_chunk
from test_lemmatize_source_offsets import _fake_doc

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.cli.terms import lemmatize as lemmatize_mod
from minerva.lemmatize import Lemmatizer

# A real grc shape, and the same string as the corpus stores it: every
# accent a separate combining mark, so NFC is four characters shorter
# and every word after the first sits at a different offset in the two.
COMPOSED = "βούτυρον καὶ μέλι φάγεται"
DECOMPOSED = unicodedata.normalize("NFD", COMPOSED)
# Word starts:  composed 0, 9, 13, 18 — stored 0, 10, 15, 21.


def test_the_sample_really_is_two_normalizations_of_one_string():
    # Guards the fixture, not the code: were DECOMPOSED equal to
    # COMPOSED every test below would stay green while exercising the
    # unrewritten fast path only.
    assert DECOMPOSED != COMPOSED
    assert unicodedata.normalize("NFC", DECOMPOSED) == COMPOSED
    assert len(DECOMPOSED) == len(COMPOSED) + 4


class _RecordingNlp:
    """Callable + ``.pipe`` duck type recording what it was fed."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, text: str):
        self.seen.append(text)
        return _fake_doc(text)

    def pipe(self, items, *, batch_size, n_process, as_tuples):
        del batch_size, n_process, as_tuples
        for text, ctx in items:
            self.seen.append(text)
            yield _fake_doc(text), ctx


def _spacy_lemmatizer(nlp) -> Lemmatizer:
    lm = Lemmatizer.__new__(Lemmatizer)  # no model load
    lm.lang = "grc"
    lm._backend = "spacy"
    lm._nlp = nlp
    return lm


def test_tokens_feed_the_pipeline_nfc_and_index_the_caller_text():
    nlp = _RecordingNlp()
    toks = list(_spacy_lemmatizer(nlp).tokens(DECOMPOSED))

    assert nlp.seen == [COMPOSED]
    assert [t.surface for t in toks] == DECOMPOSED.split(" ")
    for t in toks:
        assert DECOMPOSED[t.start : t.end] == t.surface


def test_batch_pipe_feeds_the_pipeline_nfc_and_indexes_the_caller_text():
    nlp = _RecordingNlp()
    out = list(
        _spacy_lemmatizer(nlp).batch_pipe(
            [(DECOMPOSED, "c1")], batch_size=4, n_process=1
        )
    )

    assert nlp.seen == [COMPOSED]
    ((toks, ctx),) = out
    assert ctx == "c1"
    for t in toks:
        assert DECOMPOSED[t.start : t.end] == t.surface
    # The drift the issue measured, made explicit: the second word begins
    # at 9 in the string the pipeline saw and at 10 in the stored text,
    # and the gap widens with every later accent.
    assert (toks[1].start, toks[1].end) == (10, 14)
    assert (toks[3].start, toks[3].end) == (21, 29)


def test_the_lemma_still_comes_from_the_composed_form():
    # The offsets follow the corpus text; the lemma does not. Feeding the
    # pipeline decomposed text is what degrades it, and that is the whole
    # reason the normalization stays.
    nlp = _RecordingNlp()
    toks = list(_spacy_lemmatizer(nlp).tokens(DECOMPOSED))
    assert [t.lemma for t in toks] == [w.lower() for w in COMPOSED.split(" ")]


# --- Stanza backend -------------------------------------------------
# heb/ara have no non-NFC chunks today, so nothing here is a live
# repair. It is the same rewrite through the same door: leaving this
# path un-normalized would change what those models are fed, and
# normalizing it without the map would re-file this issue for heb/ara.


class _FakeWord:
    def __init__(self, text, start_char, end_char, *, parent=None):
        self.text = text
        self.start_char = start_char
        self.end_char = end_char
        self.parent = parent
        self.lemma = text.lower()
        self.upos = "NOUN"
        self.feats = None


class _FakeStanzaDoc:
    def __init__(self, text: str, words: list[_FakeWord]) -> None:
        self.text = text
        self.sentences = [type("S", (), {"words": words})()]


def _stanza_doc_over(text: str) -> _FakeStanzaDoc:
    words = []
    pos = 0
    for word in text.split(" "):
        words.append(_FakeWord(word, pos, pos + len(word)))
        pos += len(word) + 1
    return _FakeStanzaDoc(text, words)


def test_stanza_tokens_index_the_caller_text():
    lm = Lemmatizer.__new__(Lemmatizer)
    toks = list(lm._tokens_from_stanza_doc(_stanza_doc_over(COMPOSED), DECOMPOSED))
    assert [t.surface for t in toks] == DECOMPOSED.split(" ")
    for t in toks:
        assert DECOMPOSED[t.start : t.end] == t.surface


def test_stanza_tokens_route_through_the_pipeline_on_the_composed_form():
    seen: list[str] = []

    def _pipeline(text: str):
        seen.append(text)
        return _stanza_doc_over(text)

    lm = Lemmatizer.__new__(Lemmatizer)
    lm.lang = "ara"
    lm._backend = "stanza"
    lm._nlp = _pipeline
    toks = list(lm.tokens(DECOMPOSED))

    assert seen == [COMPOSED]
    for t in toks:
        assert DECOMPOSED[t.start : t.end] == t.surface


def test_stanza_multiword_subwords_keep_their_own_surface():
    # A clitic expansion has no span of its own and inherits its
    # parent's, which several sub-words share. Slicing the source for
    # its surface would hand every clitic the whole parent word — so the
    # documented MWT exception survives the mapping.
    source = unicodedata.normalize("NFD", "καὶμελι")
    parent = _FakeWord("καὶμελι", 0, 7)
    doc = _FakeStanzaDoc(
        "καὶμελι",
        [_FakeWord("καὶ", None, None, parent=parent), _FakeWord("μελι", 3, 7)],
    )
    lm = Lemmatizer.__new__(Lemmatizer)
    toks = list(lm._tokens_from_stanza_doc(doc, source))
    assert [t.surface for t in toks] == ["καὶ", "μελι"]
    # The inherited span is mapped like any other, so it still addresses
    # the stored text — one character longer here — rather than the
    # composed one.
    assert (toks[0].start, toks[0].end) == (0, 8)
    assert (toks[1].start, toks[1].end) == (4, 8)


def test_stanza_tokens_without_any_usable_span_are_skipped():
    doc = _FakeStanzaDoc(COMPOSED, [_FakeWord("μέλι", None, None)])
    lm = Lemmatizer.__new__(Lemmatizer)
    assert list(lm._tokens_from_stanza_doc(doc, DECOMPOSED)) == []


def test_stanza_batch_pipe_pairs_each_doc_with_its_own_source(monkeypatch):
    # The bulk loop batches texts and zips contexts back on afterwards,
    # so the source string has to ride through it beside the context or
    # a doc gets mapped against its neighbour's text. `stanza` is not
    # installed in CI (`[dev,hegel,embed]`, no `[lemma]`) and the import
    # is function-local, so a stub in sys.modules is what makes this
    # branch reachable at all.
    monkeypatch.setitem(
        sys.modules,
        "stanza",
        SimpleNamespace(Document=lambda sentences, text: SimpleNamespace(text=text)),
    )

    class _Bulk:
        def bulk_process(self, batch):
            return [_stanza_doc_over(d.text) for d in batch]

    lm = Lemmatizer.__new__(Lemmatizer)
    lm.lang = "ara"
    lm._backend = "stanza"
    lm._nlp = _Bulk()
    out = list(
        lm.batch_pipe(
            [(DECOMPOSED, "c1"), (COMPOSED, "c2")], batch_size=2, n_process=1
        )
    )

    assert [ctx for _, ctx in out] == ["c1", "c2"]
    for toks, ctx in out:
        # "c2" is already NFC, so it takes the whole-string-equality fast
        # path and "c1" does not — both are exercised here.
        source = DECOMPOSED if ctx == "c1" else COMPOSED
        assert [t.surface for t in toks] == source.split(" ")
        for t in toks:
            assert source[t.start : t.end] == t.surface


def test_stanza_tokens_are_skipped_when_the_map_refuses():
    # Word counts differ, so `_SourceOffsets` refuses every span rather
    # than guessing one — the #307 rule, applied on this path too.
    doc = _FakeStanzaDoc("μέλι φάγεται", [_FakeWord("μέλι", 0, 4)])
    lm = Lemmatizer.__new__(Lemmatizer)
    assert list(lm._tokens_from_stanza_doc(doc, "μέλι")) == []


# --- the CLI end of it ----------------------------------------------


class _RecordingLemmatizer:
    """Real ``batch_pipe`` / ``_tokens_from_spacy_doc`` over a fake
    pipeline, so the whole chain from the SELECT to the INSERT runs."""

    instances: ClassVar[list[_RecordingLemmatizer]] = []

    def __init__(self, lang: str) -> None:
        self.nlp = _RecordingNlp()
        self._real = _spacy_lemmatizer(self.nlp)
        self._real.lang = lang
        type(self).instances.append(self)

    def batch_pipe(self, items, **kwargs):
        return self._real.batch_pipe(items, **kwargs)


def test_the_cli_hands_the_lemmatizer_the_stored_text(tmp_path: Path):
    db = tmp_path / "nfc.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="g1", lang="grc", text=DECOMPOSED)))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))

    args = argparse.Namespace(
        db=db, lang="grc", edition_id=None, all=False, dry_run=False,
        skip_aggregate=True, batch_size=4, n_process=1,
    )
    _RecordingLemmatizer.instances = []
    with patch.object(lemmatize_mod, "Lemmatizer", _RecordingLemmatizer), \
         patch.object(lemmatize_mod, "is_supported", lambda lang: True):
        assert lemmatize_mod.cmd_terms_lemmatize(args) == 0

    # What reached the pipeline is composed; what reached the table is
    # addressed to the stored, decomposed text.
    assert _RecordingLemmatizer.instances[0].nlp.seen == [COMPOSED]

    conn = store.open_db(db)
    try:
        rows = conn.execute(
            "SELECT c.text, l.surface_form, l.surface_start, l.surface_end "
            "FROM chunk_lemmas l JOIN chunks c USING (chunk_id) "
            "ORDER BY l.token_index"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 4
    for text, surface, start, end in rows:
        assert text == DECOMPOSED
        assert text[start:end] == surface


# --- #314: the fast path must take surface from the source too --------
#
# `surface = source[start:end]` sat inside `if offsets is not None`, so it ran
# only when the pipeline text differed from the caller's. For `ara` the two are
# always equal today, so that branch was never entered and `surface` stayed
# `w.text` — the token text the *pipeline* produced. Stanza's Arabic tokenizer
# rewrites it: hamza and alif variants folded, shadda dropped. Measured on the
# live index, 214 rows in 210 chunks store a string that is neither the corpus
# slice nor a sub-word of it, e.g. `حرُم` stored against a span reading `حُرُمٌ`.
#
# The condition that matters is whether the word has a span of its OWN, not
# whether the text needed mapping. Those are independent, and conflating them
# is the defect.


def test_stanza_surface_comes_from_the_source_even_when_no_mapping_is_needed():
    # doc.text == source, so the mapped branch is skipped entirely — the
    # `ara` case. The pipeline "rewrote" the word (dropped a diacritic); the
    # stored surface must still be what the edition prints.
    source = "حُرُمٌ"          # حُرُمٌ
    rewritten = "حرُم"                    # حرُم
    doc = _FakeStanzaDoc(source, [_FakeWord(rewritten, 0, len(source))])

    lm = Lemmatizer.__new__(Lemmatizer)
    (tok,) = list(lm._tokens_from_stanza_doc(doc, source))

    assert tok.surface == source
    assert source[tok.start : tok.end] == tok.surface


def test_stanza_fast_path_keeps_an_inherited_span_on_its_own_surface():
    # The MWT exception has to survive on the fast path as well: sub-words
    # sharing the parent's span must NOT each be handed the whole parent.
    source = "والكتاب"     # والكتاب
    parent = _FakeWord(source, 0, len(source))
    doc = _FakeStanzaDoc(
        source,
        [
            _FakeWord("و", None, None, parent=parent),
            _FakeWord("الكتاب", None, None, parent=parent),
        ],
    )

    lm = Lemmatizer.__new__(Lemmatizer)
    toks = list(lm._tokens_from_stanza_doc(doc, source))

    assert [t.surface for t in toks] == ["و", "الكتاب"]
    assert all((t.start, t.end) == (0, len(source)) for t in toks)


def test_stanza_subword_with_a_real_span_is_sliced_from_the_source():
    # #314 asks whether Stanza can hand an expanded sub-word a real span, and
    # notes the code keys on "did `start_char` come back None". It does, and
    # that is the correct key either way: a word with a span of its own is
    # addressed by that span, whether or not it has a parent. Pinned so the
    # answer is defined rather than assumed.
    source = "والكتاب"     # والكتاب
    parent = _FakeWord(source, 0, len(source))
    doc = _FakeStanzaDoc(source, [_FakeWord("REWRITTEN", 1, len(source), parent=parent)])

    lm = Lemmatizer.__new__(Lemmatizer)
    (tok,) = list(lm._tokens_from_stanza_doc(doc, source))

    assert tok.surface == source[1:]
