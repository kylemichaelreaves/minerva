"""Tests for term-glossary preservation across ``index --reset`` (#192).

Unlike chunk_lemmas and embeddings, the five ``terms*`` tables are not
recomputable — they hold curator prose (``short_gloss``,
``long_description``, translator notes). Before #192 they were absent
from both the snapshot probe and the restore table list, so every
``index --reset`` destroyed the whole glossary silently.

The restore is a POST-insert pass, not a pre-insert one like
cross_references: the glossary references ``editions``/``translations``
by surrogate id, and those rows only exist once ``insert_chunks`` has
run. Rebinding therefore goes through natural keys (author + title +
edition name / translator name), which is also why a reshuffled id
space (#193) cannot silently reattach Aristotle's vocabulary to Homer.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    args = argparse.Namespace(db=db, input=jsonl, reset=reset)
    rc = cmd_index(args)
    assert rc == 0


def _write(path: Path, chunks: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(c) for c in chunks))


# The seed corpus: one Greek edition chunk and one English translation
# chunk of the same work, which is what a real glossary hangs off of.
def _seed_chunks() -> list[dict]:
    return [
        make_chunk(
            chunk_id="grc1",
            corpus="aristotle",
            author="Aristotle",
            work="Categories",
            lang="grc",
            section="1.¶1",
            text="ὁμώνυμα λέγεται",
        ),
        make_chunk(
            chunk_id="eng1",
            corpus="aristotle",
            author="Aristotle",
            work="Categories",
            lang="eng",
            section="1.¶1",
            translator="Edghill",
            edition_year="1928",
            text="Things are said to be named equivocally",
        ),
    ]


# A second JSONL that inserts an unrelated work FIRST, so `works`,
# `editions` and `translations` all hand out different surrogate ids on
# the rebuild. This is the id reshuffle #193 documents, reproduced — and
# with the same cast: the ids Aristotle's glossary used become Homer's.
# Both a decoy edition and a decoy translation are needed, since the two
# id spaces are independent.
def _reshuffling_chunks() -> list[dict]:
    return [
        make_chunk(
            chunk_id="decoy_grc",
            corpus="homer",
            author="Homer",
            work="Iliad",
            lang="grc",
            section="1.¶1",
            text="μῆνιν ἄειδε",
        ),
        make_chunk(
            chunk_id="decoy_eng",
            corpus="homer",
            author="Homer",
            work="Iliad",
            lang="eng",
            section="1.¶1",
            translator="Murray",
            edition_year="1924",
            text="The wrath sing, goddess",
        ),
        *_seed_chunks(),
    ]


def _plant_glossary(db: Path) -> dict[str, int]:
    """Write one term with a rendering, an occurrence and an occurrence
    rendering — the full five-table shape a curator produces."""

    conn = store.open_db(db)
    ed = conn.execute(
        "SELECT e.id, e.work_id FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.author = 'Aristotle' AND e.language = 'grc'"
    ).fetchone()
    tr = conn.execute(
        "SELECT t.id FROM translations t JOIN works w ON w.id = t.work_id "
        "WHERE w.author = 'Aristotle' AND t.translator_name = 'Edghill'"
    ).fetchone()
    assert ed is not None and tr is not None

    term_id = conn.execute(
        "INSERT INTO terms (source_form, source_language, transliteration, lemma, "
        "short_gloss, long_description) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "ὁμώνυμα",
            "grc",
            "homonyma",
            "ὁμώνυμον",
            "homonyms; things sharing only a name",
            "Aristotle's term for things that share a name but not the account.",
        ),
    ).lastrowid
    other_id = conn.execute(
        "INSERT INTO terms (source_form, source_language, short_gloss, long_description) "
        "VALUES (?, ?, ?, ?)",
        ("λόγος", "grc", "account", "The explanatory account."),
    ).lastrowid
    conn.execute(
        "INSERT INTO term_relations (term_id, related_term_id, relation_kind, notes) "
        "VALUES (?, ?, ?, ?)",
        (term_id, other_id, "contrast", "paired in Categories 1"),
    )
    conn.execute(
        "INSERT INTO term_renderings (term_id, translation_id, default_rendering, "
        "translator_note) VALUES (?, ?, ?, ?)",
        (term_id, tr["id"], "things equivocally named", "Edghill says 'equivocals'."),
    )
    occ_id = conn.execute(
        "INSERT INTO term_occurrences (term_id, edition_id, work_id, source_chunk_id, "
        "source_start, source_end, context_snippet, location_kind, location_payload, "
        "location_sort_key, tradition, source_form_snapshot, instance_index) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            term_id,
            ed["id"],
            ed["work_id"],
            "grc1",
            0,
            8,
            "ὁμώνυμα λέγεται",
            "paragraph",
            '{"kind": "paragraph", "chapter": 1, "paragraph": 1}',
            "v0:paragraph:0001.0001",
            "peripatetic",
            "ὁμώνυμα",
            1,
        ),
    ).lastrowid
    conn.execute(
        "INSERT INTO occurrence_renderings (occurrence_id, translation_id, "
        "translation_chunk_id, translation_start, translation_end, rendered_text, "
        "notes, source_locator_sort_key, rendered_form_snapshot, instance_index) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            occ_id,
            tr["id"],
            "eng1",
            22,
            41,
            "named equivocally",
            "Edghill's phrasing.",
            "v0:paragraph:0001.0001",
            "named equivocally",
            1,
        ),
    )
    conn.commit()
    planted = {"edition_id": ed["id"], "translation_id": tr["id"], "term_id": term_id}
    conn.close()
    return planted


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in (
            "terms",
            "term_relations",
            "term_renderings",
            "term_occurrences",
            "occurrence_renderings",
        )
    }


def test_glossary_survives_reset_and_rebinds_to_new_ids(tmp_path: Path):
    """The whole five-table glossary comes back after ``--reset``, and
    every surrogate FK points at the REBUILT row, not the stale id."""

    db = tmp_path / "glossary.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    planted = _plant_glossary(db)

    # Re-index with the decoy work first, so ids shift underneath.
    jsonl2 = tmp_path / "seed2.jsonl"
    _write(jsonl2, _reshuffling_chunks())
    _run_index(db, jsonl2, reset=True)

    conn = store.open_db(db)
    assert _counts(conn) == {
        "terms": 2,
        "term_relations": 1,
        "term_renderings": 1,
        "term_occurrences": 1,
        "occurrence_renderings": 1,
    }

    # Curator prose survived verbatim.
    row = conn.execute(
        "SELECT short_gloss, long_description, transliteration FROM terms WHERE source_form = ?",
        ("ὁμώνυμα",),
    ).fetchone()
    assert row["short_gloss"] == "homonyms; things sharing only a name"
    assert row["transliteration"] == "homonyma"

    # The ids DID move — otherwise this test proves nothing.
    ed = conn.execute(
        "SELECT e.id, e.work_id FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.author = 'Aristotle' AND e.language = 'grc'"
    ).fetchone()
    tr = conn.execute(
        "SELECT t.id FROM translations t JOIN works w ON w.id = t.work_id "
        "WHERE w.author = 'Aristotle' AND t.translator_name = 'Edghill'"
    ).fetchone()
    assert ed["id"] != planted["edition_id"], "id reshuffle not reproduced"
    assert tr["id"] != planted["translation_id"], "id reshuffle not reproduced"

    occ = conn.execute(
        "SELECT edition_id, work_id, source_chunk_id, tradition FROM term_occurrences"
    ).fetchone()
    assert occ["edition_id"] == ed["id"], "occurrence rebound to a stale edition id"
    assert occ["work_id"] == ed["work_id"]
    assert occ["source_chunk_id"] == "grc1"
    assert occ["tradition"] == "peripatetic"

    rend = conn.execute("SELECT translation_id, default_rendering FROM term_renderings").fetchone()
    assert rend["translation_id"] == tr["id"], "rendering rebound to a stale translation id"
    assert rend["default_rendering"] == "things equivocally named"

    orend = conn.execute(
        "SELECT translation_id, translation_chunk_id, rendered_text FROM occurrence_renderings"
    ).fetchone()
    assert orend["translation_id"] == tr["id"]
    assert orend["translation_chunk_id"] == "eng1"
    assert orend["rendered_text"] == "named equivocally"

    # And the relation still joins two live term rows.
    rel = conn.execute(
        "SELECT ta.source_form AS a, tb.source_form AS b, r.relation_kind "
        "FROM term_relations r JOIN terms ta ON ta.id = r.term_id "
        "JOIN terms tb ON tb.id = r.related_term_id"
    ).fetchone()
    assert (rel["a"], rel["b"], rel["relation_kind"]) == (
        "ὁμώνυμα",
        "λόγος",
        "contrast",
    )

    for table in (
        "terms",
        "term_relations",
        "term_renderings",
        "term_occurrences",
        "occurrence_renderings",
    ):
        bad = conn.execute(f"PRAGMA foreign_key_check({table})").fetchall()
        assert bad == [], f"FK violations in {table} after reset: {bad}"


def test_glossary_only_db_gets_snapshotted(tmp_path: Path):
    """A DB carrying nothing but curated terms must still be backed up.
    The probe used to require xrefs/lemmas/embeddings, so a curator's
    first reset — before any embed pass — took the glossary with it."""

    db = tmp_path / "glossary-only.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)

    conn = store.open_db(db)
    for table in ("cross_references", "chunk_lemmas", "embeddings"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    conn.close()

    _run_index(db, jsonl, reset=True)

    assert (tmp_path / "glossary-only.sqlite.bak.pre-index").exists()
    conn = store.open_db(db)
    assert _counts(conn)["terms"] == 2
    assert _counts(conn)["term_occurrences"] == 1


def test_occurrences_whose_chunk_text_changed_are_dropped_loudly(tmp_path: Path, capsys):
    """An occurrence carries character offsets into a specific chunk. If
    that chunk's text changed, its content-hashed id changed too and the
    offsets are meaningless — drop the row, but report the count. The
    term itself (curator prose) still survives."""

    db = tmp_path / "glossary-drift.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)

    # Greek chunk re-ingested under a new content hash; English one stable.
    drifted = [
        make_chunk(
            chunk_id="grc1_v2",
            corpus="aristotle",
            author="Aristotle",
            work="Categories",
            lang="grc",
            section="1.¶1",
            text="ὁμώνυμα λέγεται τὰ",
        ),
        _seed_chunks()[1],
    ]
    jsonl2 = tmp_path / "seed2.jsonl"
    _write(jsonl2, drifted)
    _run_index(db, jsonl2, reset=True)

    err = capsys.readouterr().err
    assert "term_occurrences" in err and "chunks whose text changed" in err

    conn = store.open_db(db)
    counts = _counts(conn)
    assert counts["terms"] == 2, "curator prose must survive an offset drift"
    assert counts["term_renderings"] == 1
    assert counts["term_occurrences"] == 0
    # The occurrence rendering cascades with its parent occurrence.
    assert counts["occurrence_renderings"] == 0
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert bad == [], f"FK violations after drop: {bad}"


def test_occurrences_whose_work_left_the_corpus_are_reported_separately(tmp_path: Path, capsys):
    """A dropped or renamed work is a different failure from an edited
    chunk, and the operator should be able to tell them apart — the
    first is a corpus change worth a second look, the second is routine.
    """

    db = tmp_path / "glossary-gone.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)

    # The Greek chunk keeps its id (so the chunk join succeeds) but the
    # work is renamed, so no rebuilt edition answers to the old name.
    renamed = [
        make_chunk(
            chunk_id="grc1",
            corpus="aristotle",
            author="Aristotle",
            work="Katēgoriai",
            lang="grc",
            section="1.¶1",
            text="ὁμώνυμα λέγεται",
        ),
    ]
    jsonl2 = tmp_path / "seed2.jsonl"
    _write(jsonl2, renamed)
    _run_index(db, jsonl2, reset=True)

    err = capsys.readouterr().err
    assert "absent from the rebuilt corpus" in err

    conn = store.open_db(db)
    counts = _counts(conn)
    assert counts["terms"] == 2
    assert counts["term_occurrences"] == 0


def test_nonreset_index_sweeps_occurrences_whose_chunk_changed(tmp_path: Path):
    """A re-index WITHOUT --reset never touches the snapshot path, so the
    glossary is not rebuilt — it is mutated in place. ``insert_chunks``
    deletes chunk rows with foreign keys off, so an occurrence anchored
    to a chunk whose text changed survives the delete and is left
    pointing at nothing: FK-invalid, and its character offsets address a
    chunk that no longer exists.
    """

    db = tmp_path / "glossary-nonreset.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)

    drifted = [
        make_chunk(
            chunk_id="grc1_v2",
            corpus="aristotle",
            author="Aristotle",
            work="Categories",
            lang="grc",
            section="1.¶1",
            text="ὁμώνυμα λέγεται τὰ",
        ),
        _seed_chunks()[1],
    ]
    jsonl2 = tmp_path / "seed2.jsonl"
    _write(jsonl2, drifted)
    _run_index(db, jsonl2, reset=False)

    conn = store.open_db(db)
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert bad == [], f"non-reset re-index left FK-orphan glossary rows: {bad}"
    counts = _counts(conn)
    assert counts["term_occurrences"] == 0
    assert counts["occurrence_renderings"] == 0
    assert counts["terms"] == 2, "curator prose must survive"


def test_incremental_index_does_not_resurrect_a_deleted_term(tmp_path: Path):
    """Incremental runs never take a snapshot, so the newest one on disk
    can predate a curator's deletion. Restoring from it would undo their
    edit — so incremental skips the restore entirely. It has nothing to
    restore anyway: it does not wipe the glossary."""

    db = tmp_path / "glossary-incremental.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)
    # A full run to leave a snapshot on disk holding both terms.
    _run_index(db, jsonl, reset=True)

    conn = store.open_db(db)
    conn.execute("DELETE FROM terms WHERE source_form = ?", ("λόγος",))
    conn.commit()
    conn.close()

    args = argparse.Namespace(
        db=db, input=jsonl, reset=False, incremental=True, corpora="aristotle"
    )
    assert cmd_index(args) == 0

    conn = store.open_db(db)
    forms = [r[0] for r in conn.execute("SELECT source_form FROM terms ORDER BY source_form")]
    assert forms == ["ὁμώνυμα"], f"deleted term came back: {forms!r}"
    # The kept term's own occurrence is untouched by the incremental pass.
    assert _counts(conn)["term_occurrences"] == 1


def test_repeated_nonreset_index_does_not_duplicate_glossary(tmp_path: Path):
    """The restore is additive (INSERT OR IGNORE on the natural keys), so
    running it against an already-populated glossary is a no-op rather
    than a UNIQUE-constraint crash."""

    db = tmp_path / "glossary-idem.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, _seed_chunks())
    _run_index(db, jsonl, reset=False)
    _plant_glossary(db)

    _run_index(db, jsonl, reset=False)
    _run_index(db, jsonl, reset=True)
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    assert _counts(conn) == {
        "terms": 2,
        "term_relations": 1,
        "term_renderings": 1,
        "term_occurrences": 1,
        "occurrence_renderings": 1,
    }
