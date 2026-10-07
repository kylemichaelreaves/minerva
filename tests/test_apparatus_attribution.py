"""#710: apparatus chunks are credited to whoever wrote them.

A citation in Shorey's footnote to the *Republic* is Shorey's citation, not
Plato's. Owner decision 2026-10-07: relabel rather than filter — the chunk
carries its real author in ``chunks.attributed_to`` and every view that
credits a citation to a source author reads it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import store
from minerva.apparatus_attribution import (
    ATTRIBUTION_OVERRIDES,
    UNIDENTIFIED_EDITOR,
    attribute_chunk,
)
from minerva.block_types import APPARATUS_TYPES


class TestAttributeChunk:
    @pytest.mark.parametrize("block_type", [None, "remark", "addition", "objection"])
    def test_the_authors_own_text_is_not_relabelled(self, block_type: str | None) -> None:
        assert (
            attribute_chunk(
                block_type=block_type,
                author="Plato",
                source_file="perseus_09_republic_en.xml",
                responsible="Plato in Twelve Volumes, Vols. 5 & 6 translated by Paul Shorey",
            )
            is None
        )

    @pytest.mark.parametrize("block_type", ["note", "editorial", "cast"])
    def test_apparatus_goes_to_the_translator_named_in_the_bibliography(
        self, block_type: str
    ) -> None:
        assert (
            attribute_chunk(
                block_type=block_type,
                author="Plato",
                source_file="perseus_09_republic_en.xml",
                responsible="Plato in Twelve Volumes, Vols. 5 & 6 translated by Paul Shorey",
            )
            == "Paul Shorey"
        )

    def test_an_edited_original_goes_to_its_editor(self) -> None:
        assert (
            attribute_chunk(
                block_type="note",
                author="Aristotle",
                source_file="perseus_aristotle_01_athenian_constitution_gr.xml",
                responsible="Athenaion Politeia, ed. Kenyon",
            )
            == "ed. Kenyon"
        )

    @pytest.mark.parametrize(
        ("blob", "name"),
        [
            # Initials used to defeat the editor pattern, and the whole
            # blob then passed as an "already clean" name.
            ("ed. J. Bywater, Aristotle's Ethica Nicomachea", "ed. J. Bywater"),
            ("Platonis Opera, ed. John Burnet", "ed. John Burnet"),
            ("Athenaion Politeia, ed. Kenyon", "ed. Kenyon"),
        ],
    )
    def test_an_editors_initials_are_kept_and_the_title_dropped(self, blob: str, name: str) -> None:
        assert (
            attribute_chunk(
                block_type="note", author="Aristotle", source_file="f", responsible=blob
            )
            == name
        )

    def test_a_source_file_override_beats_the_bibliography(self) -> None:
        # The Perseus header's monogr title is not a name; the respStmt
        # names Higginson, and the override records that.
        assert (
            attribute_chunk(
                block_type="note",
                author="Epictetus",
                source_file="discourses_en.xml",
                responsible="The Works of Epictetus: His Discourses, in Four Books, "
                "the Enchiridion, and Fragments",
            )
            == "Thomas Wentworth Higginson"
        )

    def test_the_host_author_is_never_the_answer(self) -> None:
        # Leviathan's transcriber's notes carry translator "Thomas Hobbes";
        # crediting them to Hobbes is the misattribution being removed.
        assert (
            attribute_chunk(
                block_type="editorial",
                author="Hobbes",
                source_file="some_unlisted_file.txt",
                responsible="Thomas Hobbes",
            )
            == UNIDENTIFIED_EDITOR
        )

    @pytest.mark.parametrize("responsible", [None, "(Original)", "(uncredited)"])
    def test_no_recoverable_name_is_unidentified_not_the_author(
        self, responsible: str | None
    ) -> None:
        assert (
            attribute_chunk(
                block_type="note",
                author="Cicero",
                source_file="some_unlisted_file.txt",
                responsible=responsible,
            )
            == UNIDENTIFIED_EDITOR
        )

    def test_a_spurious_fragment_is_not_the_editors_either(self) -> None:
        # Diels did not write the fragments he judged doubtful or forged;
        # nobody knows who did. The label says so rather than naming him.
        assert (
            attribute_chunk(
                block_type="spurious",
                author="Heraclitus",
                source_file="diefragmentederv12diel_hocr_searchtext.txt",
                responsible="Hermann Diels",
            )
            == "Heraclitus (doubtful or spurious)"
        )

    def test_every_override_names_a_person_not_a_host_author(self) -> None:
        for source_file, name in ATTRIBUTION_OVERRIDES.items():
            assert name.strip() == name and name, source_file
            assert name not in {"Hobbes", "Thomas Hobbes", "Cicero", "Epictetus"}, source_file

    def test_every_apparatus_type_is_handled(self) -> None:
        for bt in APPARATUS_TYPES:
            assert (
                attribute_chunk(
                    block_type=bt, author="X", source_file="f", responsible="translated by Y"
                )
                is not None
            )


def _ingest(tmp_path: Path, chunks: list[dict]) -> sqlite3.Connection:
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "t.sqlite")
    store.insert_chunks(conn, jsonl)
    return conn


class TestIngestWritesTheColumn:
    def test_insert_chunks_records_attribution(self, tmp_path: Path) -> None:
        shorey = "Plato in Twelve Volumes, Vols. 5 & 6 translated by Paul Shorey"
        conn = _ingest(
            tmp_path,
            [
                make_chunk(chunk_id="body", translator=shorey),
                make_chunk(chunk_id="fn", translator=shorey, block_type="note", section="509d n.1"),
                make_chunk(
                    chunk_id="dk-grc",
                    corpus="presocratic",
                    author="Heraclitus",
                    work="Fragments (DK 22)",
                    lang="grc",
                    source_file="diefragmentederv12diel_hocr_searchtext.txt",
                    block_type="editorial",
                ),
            ],
        )
        try:
            got = dict(conn.execute("SELECT chunk_id, attributed_to FROM chunks"))
        finally:
            conn.close()
        assert got == {"body": None, "fn": "Paul Shorey", "dk-grc": "Hermann Diels"}


class TestMigrationBackfill:
    def test_rows_that_predate_the_column_are_backfilled(self, tmp_path: Path) -> None:
        from minerva import migrations

        conn = _ingest(
            tmp_path,
            [
                make_chunk(chunk_id="body", translator="Walter Miller"),
                make_chunk(
                    chunk_id="fn",
                    translator="Walter Miller",
                    block_type="editorial",
                    section="n.1",
                ),
                make_chunk(
                    chunk_id="dk-grc",
                    corpus="presocratic",
                    author="Heraclitus",
                    work="Fragments (DK 22)",
                    lang="grc",
                    source_file="diefragmentederv12diel_hocr_searchtext.txt",
                    block_type="editorial",
                ),
            ],
        )
        try:
            # Pretend the rows predate 0041: blank the column and forget it ran.
            conn.execute("UPDATE chunks SET attributed_to = NULL")
            conn.execute("DELETE FROM schema_migrations WHERE version = 41")
            conn.commit()
            migrations.apply(conn)
            got = dict(conn.execute("SELECT chunk_id, attributed_to FROM chunks"))
            # The edition of an original-language work is named after the
            # work ("Fragments (DK 22)"); the backfill must not take that
            # title for a person.
            assert got == {"body": None, "fn": "Walter Miller", "dk-grc": "Hermann Diels"}
            # The column is not in the FTS index; the backfill must not
            # leave the FTS triggers dropped.
            triggers = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
            }
            assert {"chunks_ai", "chunks_ad", "chunks_au"} <= triggers
        finally:
            conn.close()
