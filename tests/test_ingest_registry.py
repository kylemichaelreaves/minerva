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
