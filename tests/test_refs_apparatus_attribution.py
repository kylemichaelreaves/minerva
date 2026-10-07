"""#710: a citation in an editor's note is credited to the editor.

Owner decision 2026-10-07: relabel, don't filter. Every view that credits a
cross-reference to a source author reads ``COALESCE(c.attributed_to,
works.author)``, so Shorey's footnote citing Aristotle counts as Shorey's
citation — not Plato's, and not nobody's.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import llm, store
from minerva.refs import llm_verify
from minerva.refs import schema as refs_schema
from minerva.refs.list_queries import references_list, references_sources
from minerva.refs.network_queries import network_summary
from minerva.refs.review_queries import review_queue

SHOREY = "Plato in Twelve Volumes, Vols. 5 & 6 translated by Paul Shorey"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    chunks = [
        make_chunk(chunk_id="rep-body", translator=SHOREY, text="x " * 60),
        make_chunk(
            chunk_id="rep-note",
            translator=SHOREY,
            block_type="note",
            section="509d n.1",
            text="Cf. Aristotle, Eth. Nic. 1097b. " * 4,
        ),
        make_chunk(
            chunk_id="ne-1097b",
            corpus="aristotle",
            author="Aristotle",
            work="Nicomachean Ethics",
            section="1097b",
            book=None,
            text="The good of any thing is found by attending to its function.",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    c = store.open_db(tmp_path / "t.sqlite")
    store.insert_chunks(c, jsonl)
    target = refs_schema.ensure_target(
        c, canonical_author="Aristotle", canonical_work="Nicomachean Ethics"
    )
    for chunk_id in ("rep-body", "rep-note"):
        refs_schema.insert_cross_reference(
            c,
            source_chunk_id=chunk_id,
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="cites",
            source_form_snapshot="Aristotle",
            confidence=0.9,
            source_method="rule_weak",
            curator_status="auto",
        )
    c.commit()
    yield c
    c.close()


def _ids_by_chunk(conn: sqlite3.Connection) -> dict[str, int]:
    return dict(conn.execute("SELECT source_chunk_id, id FROM cross_references"))


class TestNetworkSummary:
    def test_the_matrix_counts_only_the_authors_own_citation(
        self, conn: sqlite3.Connection
    ) -> None:
        body = network_summary(conn, {})
        names = [a["name"] for a in body["matrix"]["authors"]]
        cell = {(names[x["r"]], names[x["c"]]): x["n"] for x in body["matrix"]["cells"]}
        assert cell[("Plato", "Aristotle")] == 1

    def test_the_editor_is_credited_in_the_verification_breakdown(
        self, conn: sqlite3.Connection
    ) -> None:
        body = network_summary(conn, {})
        totals = {row["author"]: row["total"] for row in body["verification"]}
        assert totals == {"Plato": 1, "Paul Shorey": 1}

    def test_apparatus_sources_names_the_editor_and_the_host(
        self, conn: sqlite3.Connection
    ) -> None:
        body = network_summary(conn, {})
        assert body["apparatus_sources"] == [
            {"name": "Paul Shorey", "host_author": "Plato", "n": 1}
        ]

    @pytest.mark.parametrize(("who", "n"), [("Plato", 1), ("Paul Shorey", 1)])
    def test_the_source_author_filter_selects_the_credited_person(
        self, conn: sqlite3.Connection, who: str, n: int
    ) -> None:
        assert network_summary(conn, {"source_author": who})["totals"]["xrefs"] == n


class TestReferencesApi:
    def test_list_rows_name_the_editor_as_source(self, conn: sqlite3.Connection) -> None:
        rows = references_list(conn, {"min_confidence": "0"})["references"]
        by_chunk = {r["source_chunk_id"]: r["source"]["author"] for r in rows}
        assert by_chunk == {"rep-body": "Plato", "rep-note": "Paul Shorey"}

    def test_list_filters_on_the_credited_person(self, conn: sqlite3.Connection) -> None:
        rows = references_list(conn, {"min_confidence": "0", "source_author": "Paul Shorey"})[
            "references"
        ]
        assert [r["source_chunk_id"] for r in rows] == ["rep-note"]

    def test_the_source_picker_offers_the_editor(self, conn: sqlite3.Connection) -> None:
        assert set(references_sources(conn, {"min_confidence": "0"})["sources"]) == {
            "Plato",
            "Paul Shorey",
        }

    def test_the_review_queue_names_the_editor(self, conn: sqlite3.Connection) -> None:
        rows = review_queue(conn, {"limit": "5"})["references"]
        assert {r["source_chunk_id"]: r["source"]["author"] for r in rows} == {
            "rep-body": "Plato",
            "rep-note": "Paul Shorey",
        }

    def test_refs_list_credits_the_editor(self, conn: sqlite3.Connection) -> None:
        rows = refs_schema.list_references(conn, source_author="Paul Shorey")
        assert [(r["source_chunk_id"], r["source_author"]) for r in rows] == [
            ("rep-note", "Paul Shorey")
        ]


class _Capture(llm.LLMBackend):
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.name = "capture"

    def complete(self, messages: list[llm.Message], *, temperature: float = 0.2) -> str:
        rows = json.loads(messages[-1].content)
        self.rows.extend(rows)
        return json.dumps(
            [{"id": r["id"], "references": True, "type": "cites", "confidence": 0.9} for r in rows]
        )


def test_the_llm_judge_is_told_who_wrote_the_note(conn: sqlite3.Connection) -> None:
    backend = _Capture()
    llm_verify.verify_rows_with_llm(conn, backend, skip_short_chunks=False)
    ids = _ids_by_chunk(conn)
    got = {r["id"]: r["source_author"] for r in backend.rows}
    assert got == {ids["rep-body"]: "Plato", ids["rep-note"]: "Paul Shorey"}


def test_llm_verify_scope_stays_the_corpus(conn: sqlite3.Connection) -> None:
    # --source-author scopes an operator pass to a corpus; it is not an
    # attribution view, so Plato's pass still verifies the notes in Plato.
    backend = _Capture()
    llm_verify.verify_rows_with_llm(conn, backend, skip_short_chunks=False, source_author="Plato")
    assert len(backend.rows) == 2
