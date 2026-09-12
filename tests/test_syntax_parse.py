"""Stanza → SyntaxToken conversion.

Deliberately does NOT construct a real pipeline. CI installs
`.[dev,hegel,embed]`, not `[lemma]`, so there is no `stanza` package and no
model in stanza's cache — a test that loaded one would pass on a developer
machine and fail everywhere else. The lemmatizer tests set the same
precedent.

What is worth testing here is the conversion, not Stanza: sentence ordinals,
character offsets back into `chunks.text`, and multiword tokens — where German
`zum` is one surface string covering two syntactic words, and both must carry
the *token's* span rather than the word's.
"""

from __future__ import annotations

import pytest

from minerva.syntax import parse as p


class FakeWord:
    def __init__(self, wid, text, lemma, upos, head, deprel, feats=None, xpos=None):
        self.id = wid
        self.text = text
        self.lemma = lemma
        self.upos = upos
        self.xpos = xpos
        self.feats = feats
        self.head = head
        self.deprel = deprel


class FakeToken:
    """Stanza puts character offsets on the *token*; a multiword token holds
    several words that all share its span."""

    def __init__(self, start_char, end_char, words):
        self.start_char = start_char
        self.end_char = end_char
        self.words = words


class FakeSentence:
    def __init__(self, tokens):
        self.tokens = tokens


class FakeDoc:
    def __init__(self, sentences):
        self.sentences = sentences


def one_sentence_doc() -> FakeDoc:
    # "Der Geist entwickelt." with plausible offsets.
    return FakeDoc(
        [
            FakeSentence(
                [
                    FakeToken(0, 3, [FakeWord(1, "Der", "der", "DET", 2, "det")]),
                    FakeToken(
                        4, 9, [FakeWord(2, "Geist", "Geist", "NOUN", 3, "nsubj", feats="Case=Nom")]
                    ),
                    FakeToken(10, 21, [FakeWord(3, "entwickelt", "entwickeln", "VERB", 0, "root")]),
                ]
            )
        ]
    )


def test_converts_words_to_tokens_with_offsets() -> None:
    out = p.doc_to_tokens(one_sentence_doc())

    assert [(t.tok_id, t.form, t.head, t.deprel) for t in out] == [
        (1, "Der", 2, "det"),
        (2, "Geist", 3, "nsubj"),
        (3, "entwickelt", 0, "root"),
    ]
    assert [(t.surface_start, t.surface_end) for t in out] == [(0, 3), (4, 9), (10, 21)]


def test_carries_feats_and_lemma_through() -> None:
    out = p.doc_to_tokens(one_sentence_doc())

    assert out[1].lemma == "Geist"
    assert out[1].feats == "Case=Nom"
    assert out[0].feats is None


def test_numbers_sentences_from_zero() -> None:
    doc = FakeDoc(
        [
            FakeSentence([FakeToken(0, 3, [FakeWord(1, "Eins", "eins", "NUM", 0, "root")])]),
            FakeSentence([FakeToken(5, 9, [FakeWord(1, "Zwei", "zwei", "NUM", 0, "root")])]),
        ]
    )

    out = p.doc_to_tokens(doc)

    assert [(t.sent_ord, t.tok_id, t.form) for t in out] == [
        (0, 1, "Eins"),
        (1, 1, "Zwei"),
    ]


def test_token_ids_restart_in_each_sentence() -> None:
    """CoNLL-U ids are per-sentence, so (sent_ord, tok_id) is the identity a
    correction addresses. Flattening to a chunk-wide index would make every
    correction point at the wrong word in a multi-sentence chunk."""

    doc = FakeDoc(
        [
            FakeSentence(
                [
                    FakeToken(0, 1, [FakeWord(1, "A", "a", "X", 2, "dep")]),
                    FakeToken(2, 3, [FakeWord(2, "B", "b", "X", 0, "root")]),
                ]
            ),
            FakeSentence([FakeToken(4, 5, [FakeWord(1, "C", "c", "X", 0, "root")])]),
        ]
    )

    out = p.doc_to_tokens(doc)

    assert [(t.sent_ord, t.tok_id) for t in out] == [(0, 1), (0, 2), (1, 1)]


def test_multiword_token_words_share_the_surface_span() -> None:
    """German `zum` is one string spanning `zu` + `dem`. Both words point at
    the same characters — there is no narrower span to give them, and the
    Reader aligns by offset."""

    doc = FakeDoc(
        [
            FakeSentence(
                [
                    FakeToken(
                        0,
                        3,
                        [
                            FakeWord(1, "zu", "zu", "ADP", 3, "case"),
                            FakeWord(2, "dem", "der", "DET", 3, "det"),
                        ],
                    ),
                    FakeToken(4, 9, [FakeWord(3, "Markt", "Markt", "NOUN", 0, "root")]),
                ]
            )
        ]
    )

    out = p.doc_to_tokens(doc)

    assert [(t.tok_id, t.form) for t in out] == [(1, "zu"), (2, "dem"), (3, "Markt")]
    assert [(t.surface_start, t.surface_end) for t in out] == [(0, 3), (0, 3), (4, 9)]


def test_empty_document_yields_no_tokens() -> None:
    assert p.doc_to_tokens(FakeDoc([])) == []


# ---------- the pipeline boundary ----------


def test_parse_text_uses_the_pipeline_and_converts(monkeypatch: pytest.MonkeyPatch) -> None:
    """`parse_text` is the seam: everything above is pure conversion, and the
    only Stanza contact is one call through `_pipeline()`."""

    calls: list[str] = []

    def fake_pipeline():
        def run(text: str):
            calls.append(text)
            return one_sentence_doc()

        return run

    monkeypatch.setattr(p, "_pipeline", fake_pipeline)

    out = p.parse_text("Der Geist entwickelt.")

    assert calls == ["Der Geist entwickelt."]
    assert [t.form for t in out] == ["Der", "Geist", "entwickelt"]


def test_blank_text_short_circuits_without_loading_a_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loading the German model costs ~4s. An empty or whitespace-only chunk
    must not pay it."""

    def explode():
        raise AssertionError("pipeline must not be constructed for blank input")

    monkeypatch.setattr(p, "_pipeline", explode)

    assert p.parse_text("   \n  ") == []


def test_parser_id_names_the_model_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stored in `chunk_syntax_state.parser` so a future re-parse can tell
    which trees came from which model."""

    monkeypatch.setattr(p, "_stanza_version", lambda: "1.13.0")

    assert p.parser_id() == "stanza-de-1.13.0"


def test_warm_pipeline_reports_why_it_failed(monkeypatch, capsys):
    """#530: `warm_pipeline` returned False and swallowed the exception,
    and `_start_syntax_warmup` prints only on success — so a missing
    model was invisible until a reader opened the overlay and got a 500.

    Stanza's model cache is keyed to the stanza release
    (`user_cache_dir('stanza', 'StanfordNLP', __resources_version__)`),
    so a version bump does not migrate the model: it starts from an empty
    cache. The operator needs to be told that at startup, when it is
    cheap to fix, not by a reader hitting an error.
    """

    from minerva.syntax import parse as parse_mod

    def boom():
        raise RuntimeError("LanguageNotDownloadedError: de")

    monkeypatch.setattr(parse_mod, "_pipeline", boom)

    assert parse_mod.warm_pipeline() is False
    err = capsys.readouterr().err
    assert "syntax" in err.lower()
    assert "LanguageNotDownloadedError" in err
    assert "stanza.download" in err


def test_warm_pipeline_is_silent_when_it_succeeds(monkeypatch, capsys):
    from minerva.syntax import parse as parse_mod

    monkeypatch.setattr(parse_mod, "_pipeline", lambda: object())

    assert parse_mod.warm_pipeline() is True
    assert capsys.readouterr().err == ""
