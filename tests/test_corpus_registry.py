"""Corpus registry invariants."""

from __future__ import annotations

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


def test_corpus_to_dominant_covers_all():
    for e in corpus_registry.CORPORA:
        assert corpus_registry.CORPUS_TO_DOMINANT[e.id] == e.dominant_code
