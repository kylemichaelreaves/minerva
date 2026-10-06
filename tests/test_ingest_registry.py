"""Tests for ingest registry helpers."""

from __future__ import annotations

from minerva.ingest.registry import INGEST_ID_TO_CORPUS, corpus_slugs_for_ingest_ids


def test_corpus_slugs_for_ingest_ids_maps_dual_parser_sources():
    slugs = corpus_slugs_for_ingest_ids({"lxx", "nt", "kant_en", "cicero_en", "plato"})
    assert slugs == {"septuagint", "new_testament", "kant", "cicero", "plato"}


def test_ingest_id_to_corpus_covers_documented_mismatches():
    # Guard against regressions in the incremental re-ingest workflow.
    assert INGEST_ID_TO_CORPUS["marx_mew"] == "marx"
    assert INGEST_ID_TO_CORPUS["hobbes_la"] == "hobbes"
    assert INGEST_ID_TO_CORPUS["descartes_fr"] == "descartes"


def test_every_ingest_source_resolves_to_a_registered_corpus():
    # The completeness check the three sentinels above are not (#502): a new
    # source whose id differs from its corpus slug and is missing from the map
    # falls through to its own id, which scopes `--only` / incremental
    # re-index to a corpus that does not exist.
    from minerva.corpus_registry import corpus_ids
    from minerva.ingest.registry import INGEST_SOURCES

    registered = set(corpus_ids())
    unresolved = {
        s.id: INGEST_ID_TO_CORPUS.get(s.id, s.id)
        for s in INGEST_SOURCES
        if INGEST_ID_TO_CORPUS.get(s.id, s.id) not in registered
    }
    assert unresolved == {}


def test_ingest_id_map_has_no_stale_entries():
    from minerva.corpus_registry import corpus_ids
    from minerva.ingest.registry import INGEST_SOURCES

    source_ids = {s.id for s in INGEST_SOURCES}
    assert set(INGEST_ID_TO_CORPUS) <= source_ids
    assert set(INGEST_ID_TO_CORPUS.values()) <= set(corpus_ids())
