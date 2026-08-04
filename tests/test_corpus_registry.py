"""Corpus registry invariants."""

from __future__ import annotations

import pytest

from minerva import corpus_registry


def test_every_corpus_has_metadata():
    for e in corpus_registry.CORPORA:
        assert e.original_lang
        assert e.citation_system
        assert e.dominant_code
        assert len(e.dominant_code) == 1


def test_quran_and_hebrew_mt_present():
    ids = corpus_registry.corpus_ids()
    assert "quran" in ids
    assert "hebrew_mt" in ids
    assert "quran" in corpus_registry.AUTHOR_KEYWORDS.values()
    assert "koran" in corpus_registry.AUTHOR_KEYWORDS
    assert "surah" in corpus_registry.AUTHOR_KEYWORDS


def test_no_keyword_collisions():
    corpus_registry.validate_keywords()


def test_no_dominant_code_collisions():
    """Five pairs (hume/cicero, hobbes/boulainvilliers, rousseau/renan,
    aquinas/theognis, septuagint/gobineau) once shared a glyph; the
    gutter glyph must be unambiguous."""
    corpus_registry.validate_dominant_codes()
    codes = [e.dominant_code for e in corpus_registry.CORPORA]
    assert len(codes) == len(set(codes))


def test_validate_keywords_detects_synthetic_collision(monkeypatch):
    """Regression: the old validator iterated AUTHOR_KEYWORDS, which had
    already collapsed duplicates by dict overwrite — it could never fire."""
    e1, e2 = corpus_registry.CORPORA[0], corpus_registry.CORPORA[1]
    clash1 = corpus_registry.CorpusEntry(
        e1.id, e1.original_lang, e1.citation_system, e1.dominant_code, ("samekw",)
    )
    clash2 = corpus_registry.CorpusEntry(
        e2.id, e2.original_lang, e2.citation_system, e2.dominant_code, ("samekw",)
    )
    monkeypatch.setattr(corpus_registry, "CORPORA", (clash1, clash2))
    with pytest.raises(ValueError, match="samekw"):
        corpus_registry.validate_keywords()


def test_validate_dominant_codes_detects_synthetic_collision(monkeypatch):
    e1, e2 = corpus_registry.CORPORA[0], corpus_registry.CORPORA[1]
    clash = corpus_registry.CorpusEntry(
        e2.id, e2.original_lang, e2.citation_system, e1.dominant_code, e2.keywords
    )
    monkeypatch.setattr(corpus_registry, "CORPORA", (e1, clash))
    with pytest.raises(ValueError, match="dominant_code"):
        corpus_registry.validate_dominant_codes()


def test_corpus_to_dominant_covers_all():
    for e in corpus_registry.CORPORA:
        assert corpus_registry.CORPUS_TO_DOMINANT[e.id] == e.dominant_code


# ---------- corpus id vs works.author (#174) ----------


def test_corpus_authors_defaults_to_the_id():
    # The 33 single-author corpora: the id *is* the author, lowercased.
    assert corpus_registry.corpus_authors("plato") == ("plato",)
    assert corpus_registry.corpus_authors("nietzsche") == ("nietzsche",)


def test_corpus_authors_resolves_slug_ids():
    # Retrieval filters on LOWER(works.author); binding the id here
    # matched zero chunks and the agent abstained.
    assert corpus_registry.corpus_authors("marcus_aurelius") == ("marcus aurelius",)
    assert corpus_registry.corpus_authors("kjv") == ("king james bible",)
    assert corpus_registry.corpus_authors("hebrew_mt") == ("hebrew bible",)


def test_corpus_authors_is_one_to_many():
    authors = corpus_registry.corpus_authors("presocratic")
    assert "heraclitus" in authors
    assert "zeno of elea" in authors
    assert len(authors) > 1  # a rename could never have expressed this


def test_corpus_authors_is_empty_for_no_filtering():
    assert corpus_registry.corpus_authors(None) == ()
    assert corpus_registry.corpus_authors("any") == ()


def test_corpus_authors_passes_through_an_unknown_id():
    # Callers that hand over a raw works.author value still filter on it.
    assert corpus_registry.corpus_authors("Marcus Aurelius") == ("marcus aurelius",)


def test_every_declared_author_is_claimed_once():
    seen: dict[str, str] = {}
    for entry in corpus_registry.CORPORA:
        for author in corpus_registry.corpus_authors(entry.id):
            assert author not in seen, f"{author!r} claimed by {seen.get(author)} and {entry.id}"
            seen[author] = entry.id
