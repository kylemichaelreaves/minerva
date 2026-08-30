"""``chunk_lemmas`` surface offsets must index the corpus text (#307).

``Token.start``/``end`` were ``spacy.Token.idx`` and ``idx + len(text)``,
which index ``doc.text`` — the string the *tokenizer* produced, not the
string we handed it. For ``lat`` those differ on nearly every chunk:
``la_core_web_sm`` installs a ``LatinTokenizer`` whose ``preprocess()``
runs ``separate_ligatures / remove_macrons / remove_accents / norm_v_j /
lowercase_line_initials / norm_spacing`` over the raw string *before*
tokenizing, and two of those change length (``Æ``→``Ae``; a combining
mark dropped; every run of whitespace collapsed to one space).

Measured on ``data/index.sqlite`` 2026-08-09, 1,205 lat chunks through
the live model: 0 of 127,539 token spans landed on the source text
without the mapping below, and 127,539 of 127,539 with it.

The tests here pin the mapping itself — no spaCy, no model download.
The one test that needs a ``Doc`` builds a fake with the same duck type
``_tokens_from_spacy_doc`` consumes.
"""

from __future__ import annotations

import pytest

from minerva.lemmatize import Lemmatizer, _SourceOffsets


def _map(processed: str, source: str) -> _SourceOffsets:
    return _SourceOffsets(processed, source)


def test_identical_texts_map_to_themselves():
    src = "Gallia est omnis divisa in partes tres"
    m = _map(src, src)
    assert m.usable
    assert m.span(11, 16) == (11, 16)
    assert src[11:16] == "omnis"


def test_collapsed_whitespace_shifts_every_later_token():
    # norm_spacing() turns "\n\n" into a single space, so the processed
    # offset of every word after the break is short by one per newline.
    source = "Iuxta\n\nnumerum   prouinciarum"
    processed = "Iuxta numerum prouinciarum"
    m = _map(processed, source)
    assert m.usable
    assert m.span(6, 13) == (7, 14)
    assert source[7:14] == "numerum"
    assert m.span(14, 26) == (17, 29)
    assert source[17:29] == "prouinciarum"


def test_leading_and_trailing_whitespace_is_stripped():
    m = _map("Iuxta", "  Juxta  ")
    assert m.span(0, 5) == (2, 7)


def test_ligature_expansion_lengthens_the_processed_word():
    # Æ is one character in the corpus and two after separate_ligatures().
    m = _map("Aegypto uenit", "Ægypto venit")
    assert m.usable
    assert m.span(0, 7) == (0, 6)
    assert m.span(8, 13) == (7, 12)


def test_combining_mark_shortens_the_processed_word():
    # remove_accents() decomposes then drops Mn, so a source "ë" written
    # as e + U+0308 -- NOT the precomposed U+00EB -- loses a character.
    source = "Israe\u0308l dixit"
    m = _map("Israel dixit", source)
    assert m.usable
    assert m.span(0, 6) == (0, 7)
    assert source[0:7] == "Israe\u0308l"
    assert m.span(7, 12) == (8, 13)


def test_substitution_inside_a_word_keeps_the_span_exact():
    m = _map("uirumque cano", "virumque cano")
    assert m.span(0, 8) == (0, 8)


def test_sub_token_of_a_split_word_maps_to_its_own_slice():
    # enclitic_splitter cuts "uirumque" into "uirum" + "que" after the
    # tokenizer ran, so both sub-tokens are spans inside one source word.
    source = "virumque cano"
    m = _map("uirumque cano", source)
    assert m.span(0, 5) == (0, 5)
    assert source[0:5] == "virum"
    assert m.span(5, 8) == (5, 8)
    assert source[5:8] == "que"


def test_word_count_mismatch_refuses_rather_than_guesses():
    # Nothing in LatinCy's preprocess() merges or splits words, so a
    # differing word count means an assumption of this map is broken.
    # Guessing a span would write a plausible wrong offset, which is
    # exactly the failure #307 is about.
    m = _map("una duo tres", "una duo")
    assert not m.usable
    assert m.span(0, 3) is None


def test_span_outside_any_word_is_refused():
    m = _map("Iuxta numerum", "Juxta\nnumerum")
    assert m.span(5, 6) is None


def test_span_straddling_a_word_boundary_is_refused():
    m = _map("Iuxta numerum", "Juxta\nnumerum")
    assert m.span(3, 9) is None


class _FakeToken:
    def __init__(self, text: str, idx: int) -> None:
        self.text = text
        self.idx = idx
        self.is_space = not text.strip()
        self.is_punct = text in {".", ",", ";"}
        self.lemma_ = text.lower()
        self.pos_ = "NOUN"
        self.morph = ""


class _FakeDoc:
    """Duck type of the bits ``_tokens_from_spacy_doc`` reads."""

    def __init__(self, text: str, tokens: list[_FakeToken]) -> None:
        self.text = text
        self._tokens = tokens

    def __iter__(self):
        return iter(self._tokens)


def _fake_doc(processed: str) -> _FakeDoc:
    """One token per space-delimited word, plus the space tokens spaCy
    emits for runs it did not attach — both of the skip branches in
    ``_tokens_from_spacy_doc`` are on this path."""

    toks: list[_FakeToken] = []
    i = 0
    for word in processed.split(" "):
        if word:
            toks.append(_FakeToken(word.rstrip(".,;"), i))
            if word[-1] in ".,;":
                toks.append(_FakeToken(word[-1], i + len(word) - 1))
        else:
            toks.append(_FakeToken(" ", i))
        i += len(word) + 1
    return _FakeDoc(processed, toks)


def test_tokens_from_doc_report_source_spans_and_source_surfaces():
    lm = Lemmatizer.__new__(Lemmatizer)  # no model load
    source = "Ægypto\nvenit"
    toks = list(lm._tokens_from_spacy_doc(_fake_doc("Aegypto uenit"), source))
    assert [(t.surface, t.start, t.end) for t in toks] == [
        ("Ægypto", 0, 6),
        ("venit", 7, 12),
    ]
    # The lemma still comes from the pipeline's normalized form.
    assert [t.lemma for t in toks] == ["aegypto", "uenit"]
    for t in toks:
        assert source[t.start : t.end] == t.surface


def test_grc_lemma_ascii_prefix_is_fixed_only_for_the_grc_backend():
    """#456: wiring, not just the standalone function — a `grc`-tagged
    Lemmatizer repairs an ASCII-confusable lemma on a clean Greek
    surface; the same token through a Lemmatizer with no `.lang` set
    (the `__new__`-bypass tests elsewhere in this file) is untouched."""

    source = "νησαίων"
    tok = _FakeToken(source, 0)
    tok.lemma_ = "Nησαῖος"
    doc = _FakeDoc(source, [tok])

    lm = Lemmatizer.__new__(Lemmatizer)
    lm.lang = "grc"
    (fixed,) = list(lm._tokens_from_spacy_doc(doc, source))
    assert fixed.lemma == "Νησαῖος"

    lm_no_lang = Lemmatizer.__new__(Lemmatizer)
    (unfixed,) = list(lm_no_lang._tokens_from_spacy_doc(doc, source))
    assert unfixed.lemma == "Nησαῖος"


def test_tokens_from_doc_skip_when_the_source_cannot_be_mapped():
    lm = Lemmatizer.__new__(Lemmatizer)
    # Processed text has a word the source does not — the map refuses,
    # and no row is written rather than a wrong one.
    toks = list(lm._tokens_from_spacy_doc(_fake_doc("una duo tres"), "una duo"))
    assert toks == []


def test_tokens_from_doc_take_the_fast_path_when_nothing_was_rewritten():
    lm = Lemmatizer.__new__(Lemmatizer)
    source = "una duo  tres."
    toks = list(lm._tokens_from_spacy_doc(_fake_doc(source), source))
    # The trailing "." and the doubled space are dropped as punctuation
    # and whitespace before any offset work happens.
    assert [(t.surface, t.start, t.end) for t in toks] == [
        ("una", 0, 3),
        ("duo", 4, 7),
        ("tres", 9, 13),
    ]


@pytest.mark.parametrize(
    ("processed", "source"),
    [
        ("Iuxta numerum prouinciarum", "Juxta\n\nnumerum   provinciarum"),
        ("Aegypto uenit", "Ægypto venit"),
        ("Israel dixit", "Israe\u0308l dixit"),
    ],
)
def test_every_word_round_trips_to_a_span_of_the_same_word(processed, source):
    m = _map(processed, source)
    assert m.usable
    offset = 0
    for word in processed.split(" "):
        span = m.span(offset, offset + len(word))
        assert span is not None
        assert source[span[0] : span[1]].split() == [source[span[0] : span[1]].strip()]
        offset += len(word) + 1
