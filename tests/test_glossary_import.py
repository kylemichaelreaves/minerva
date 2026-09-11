"""Regression tests for `minerva.glossary_import` internals — the
IN-list batching in `_chunk_rows` (works >999 chunks, e.g. Psalms)
and the dry-run term-id sentinel."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import store
from minerva.glossary_import import _chunk_rows, _ensure_term
from minerva.glossary_spec import Term


@pytest.fixture
def big_work_db(tmp_path: Path) -> tuple[sqlite3.Connection, list[str]]:
    """A work with 1,050 chunks — past SQLite's historical 999
    bound-variable cap that the unbatched IN-list used to blow."""

    conn = store.open_db(tmp_path / "g.sqlite")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO works(id, author, title, original_language, citation_system) "
        "VALUES (1, 'Anon', 'Psalmi', 'lat', 'paragraph')"
    )
    cur = conn.execute(
        "INSERT INTO editions(work_id, name, language, year) VALUES (1, 'Vulgata', 'lat', 1592)"
    )
    eid = int(cur.lastrowid)
    n = 1050
    conn.executemany(
        # `work_id` mirrors the edition's, as `insert_chunks` writes it —
        # `chunks_full` inner-joins `works` on it since migration 0030 (#339).
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, work_id, lang, section, "
        "source_file, text, ord) VALUES (?,?,?,?,?,?,?,?,?)",
        [(f"ps-{i:04d}", eid, None, 1, "lat", f"§{i}", "x", f"text {i}", i) for i in range(n)],
    )
    conn.commit()
    return conn, [f"ps-{i:04d}" for i in range(n)]


def test_chunk_rows_batches_past_sqlite_variable_cap(big_work_db) -> None:
    conn, ids = big_work_db
    # Pin the per-statement bound-variable cap to the historical 999 so
    # the regression reproduces even on modern SQLite builds (~32k cap).
    conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
    out = _chunk_rows(conn, ids)
    assert len(out) == len(ids)
    # ord ordering must hold across batch boundaries.
    assert [r[0] for r in out] == ids
    assert out[0][1] == "§0" and out[-1][1] == "§1049"


def test_chunk_rows_empty_input(big_work_db) -> None:
    conn, _ids = big_work_db
    assert _chunk_rows(conn, []) == []


def test_dry_run_term_sentinels_negative_unique_and_non_writing(tmp_path: Path) -> None:
    """The dry-run sentinel must never collide with a real (positive)
    PK — the old `-abs(hash(...)) | 1` could yield -1 == a plausible id
    space collision at hash()==0 and varied under hash randomization."""

    conn = store.open_db(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    seen: set[int] = set()
    for form in ("λόγος", "ψυχή", "ἀρετή"):
        term = Term(lemma=form, source_form=form, short_gloss="g", long_description="d")
        tid = _ensure_term(conn, "grc", term, dry_run=True)
        assert tid < 0
        seen.add(tid)
    assert len(seen) == 3
    assert conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0] == 0


def test_dry_run_returns_real_id_for_existing_term(tmp_path: Path) -> None:
    conn = store.open_db(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    term = Term(lemma="λόγος", source_form="λόγος", short_gloss="g", long_description="d")
    real_id = _ensure_term(conn, "grc", term, dry_run=False)
    assert real_id > 0
    assert _ensure_term(conn, "grc", term, dry_run=True) == real_id


# ---------- #543 / #556: section shapes the parser chain refuses ----------


def test_note_sibling_sections_parse_to_a_locator():
    """#543: the page-furniture pass emits editors' footnotes as sibling
    chunks with `section` = "<heading>, ¶N.note". `_HEGEL_SECTION_RE`
    anchors after the digits, so every one of them returned None and was
    skipped — 301 chunks in the live corpus, measured 2026-09-11.

    The `¶N.note` shape is deliberate: `section` feeds `_make_chunk_id`,
    so numbering notes into the ¶ sequence would re-id every chunk after
    each insertion.
    """

    from minerva.glossary_import import _section_payload

    got = _section_payload("paragraph", "Editorial Introduction, ¶1.note")
    assert got is not None
    assert got["payload"]["paragraph"] == 1
    assert got["payload"]["section"] == "Editorial Introduction"


def test_over_cap_paragraph_pieces_parse_to_a_locator():
    """The same anchor refused `¶N.k`, the pre-existing convention for
    an over-cap paragraph split into pieces — 32 chunks live. #543
    flagged this as likely but unverified; it reproduces."""

    from minerva.glossary_import import _section_payload

    got = _section_payload("paragraph", "May It Please Your Lordship, ¶1.2")
    assert got is not None
    assert got["payload"]["paragraph"] == 1


def test_note_sibling_sorts_after_its_own_paragraph_and_before_the_next():
    """A note belongs to its paragraph, so it must sort inside it —
    otherwise the locator parses but orders wrongly, which is worse than
    refusing."""

    from minerva.glossary_import import _section_payload

    keys = [
        _section_payload("paragraph", f"Intro, {s}")["sort_key"]
        for s in ("¶1", "¶1.note", "¶2")
    ]
    assert keys == sorted(keys), keys
    assert len(set(keys)) == 3


def test_an_out_of_range_verse_is_skipped_not_raised():
    """#556: `_section_payload` documents "returns None when no parser
    matches", and its caller has no try/except. `format_sort_key` sits
    outside the try that catches LocationError, so a section the parser
    accepts but the encoder rejects escapes as an exception and aborts
    the whole glossary import. One chunk in the corpus does this:
    `Lam 3:711` (#557)."""

    from minerva.glossary_import import _section_payload

    assert _section_payload("bcv", "Lam 3:711") is None


def test_bekker_sections_still_resolve_through_the_bekker_branch():
    """#556 moved `format_sort_key` inside the bekker branch's try, so
    the success path through it needs pinning."""

    from minerva.glossary_import import _section_payload

    got = _section_payload("bekker", "1094a13")
    assert got is not None
    assert got["payload"]["kind"] == "bekker"
    assert got["sort_key"]


def test_declared_system_parser_resolves_when_no_fallback_matches():
    """`A47` matches neither paragraph-local, bekker, nor the Hegel
    shape, so it is the declared-system parser at the end of the chain
    that resolves it — the branch #556 split in two.

    Note `stephanus`/`514a` does *not* work as an example here: the
    bekker fallback claims it first and returns a bekker payload, which
    is worth knowing before writing a test against this chain.
    """

    from minerva.glossary_import import _section_payload

    got = _section_payload("kant_ab", "A47")
    assert got is not None
    assert got["payload"]["kind"] == "kant_ab"
    assert got["payload"]["page"] == 47


def test_a_section_no_parser_matches_returns_none_silently(capsys):
    """The ordinary skip: 56,675 chunks corpus-wide. It must stay silent
    — #556 names only the malformed-locator case, and naming this one
    would print once per skipped chunk."""

    from minerva.glossary_import import _section_payload

    assert _section_payload("stephanus", "not a locator at all") is None
    assert capsys.readouterr().out == ""
