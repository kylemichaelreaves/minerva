"""Reader edition/translation scoping (#50).

Builds a work with one Greek edition and TWO English translations that
share a (work_id, lang) — the collision the old work_range concatenated.
Locks the fix: the range is scoped to a single edition, the switcher
lists them all, and switching + position-remap behave.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.errors import NotFoundError
from minerva.reader.queries import work_range


def _grc(section: str, i: int) -> dict:
    return make_chunk(
        chunk_id=f"grc-{i}", lang="grc", section=section, translator=None,
        edition_year=None, text=f"greek {section}", book=None,
    )


def _trans(translator: str, year: str, section: str, i: int) -> dict:
    return make_chunk(
        chunk_id=f"{translator[:3].lower()}-{i}", lang="eng", section=section,
        translator=translator, edition_year=year, book=None,
        text=f"{translator} {section}",
    )


@pytest.fixture
def editions_db(tmp_path: Path) -> sqlite3.Connection:
    # Republic: Greek (Burnet edition, no translator) + Jowett 1892 +
    # Shorey 1930. Both English translations share (work_id, lang=eng).
    chunks = [
        _grc("327a", 1), _grc("327b", 2), _grc("327c", 3),
        _trans("Benjamin Jowett", "1892", "327a", 1),
        _trans("Benjamin Jowett", "1892", "327b", 2),
        _trans("Paul Shorey", "1930", "327a", 1),
        _trans("Paul Shorey", "1930", "327b", 2),
        _trans("Paul Shorey", "1930", "327c", 3),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "index.sqlite")
    store.insert_chunks(conn, jsonl)
    return conn


class TestEditionScoping:
    def test_default_is_scoped_to_one_edition_not_the_merge(self, editions_db):
        # lang=eng has two translations; the range must NOT return all 5
        # eng chunks concatenated — it picks the most-recent (Shorey, 3).
        r = work_range(editions_db, "Republic", {"lang": "eng", "limit": "50"})
        assert r["total"] == 3  # Shorey only, not 2 + 3 merged
        assert r["lang"] == "eng"
        sel = r["edition"]
        # every returned chunk belongs to the same edition
        assert all(c["text"].startswith("Paul Shorey") for c in r["chunks"])
        # the switcher lists all three editions
        selectors = {e["selector"] for e in r["editions"]}
        assert len(r["editions"]) == 3
        assert sel in selectors

    def test_default_prefers_most_recent_translation(self, editions_db):
        r = work_range(editions_db, "Republic", {"lang": "eng"})
        current = next(e for e in r["editions"] if e["selector"] == r["edition"])
        assert current["year"] == 1930
        assert current["short"] == "Shorey"

    def test_switch_by_selector(self, editions_db):
        base = work_range(editions_db, "Republic", {"lang": "eng"})
        jowett = next(e for e in base["editions"] if e["short"] == "Jowett")
        r = work_range(editions_db, "Republic", {"edition": jowett["selector"]})
        assert r["edition"] == jowett["selector"]
        assert r["total"] == 2
        assert all(c["text"].startswith("Benjamin Jowett") for c in r["chunks"])

    def test_original_edition_listed_and_selectable(self, editions_db):
        base = work_range(editions_db, "Republic", {"lang": "eng"})
        grc = next(e for e in base["editions"] if e["is_original"])
        assert grc["lang"] == "grc"
        assert grc["short"] == "Greek"
        r = work_range(editions_db, "Republic", {"edition": grc["selector"]})
        assert r["lang"] == "grc"
        assert r["total"] == 3

    def test_at_section_preserves_position_across_switch(self, editions_db):
        base = work_range(editions_db, "Republic", {"lang": "eng"})  # Shorey
        jowett = next(e for e in base["editions"] if e["short"] == "Jowett")
        # Switch to Jowett, keeping place at 327b → window centers there.
        r = work_range(
            editions_db,
            "Republic",
            {"edition": jowett["selector"], "at_section": "327b", "limit": "1"},
        )
        assert r["offset"] == 1  # 327b is the 2nd Jowett chunk (index 1)

    def test_at_section_absent_from_edition_falls_back_to_top(self, editions_db):
        base = work_range(editions_db, "Republic", {"lang": "eng"})
        jowett = next(e for e in base["editions"] if e["short"] == "Jowett")
        # Jowett has no 327c; remap falls back to the top.
        r = work_range(
            editions_db,
            "Republic",
            {"edition": jowett["selector"], "at_section": "327c"},
        )
        assert r["offset"] == 0

    def test_around_scopes_to_the_chunks_own_edition(self, editions_db):
        r = work_range(editions_db, "Republic", {"around": "pau-2"})
        assert r["edition"].startswith("t")
        assert all(c["text"].startswith("Paul Shorey") for c in r["chunks"])

    def test_unknown_selector_raises(self, editions_db):
        with pytest.raises(NotFoundError):
            work_range(editions_db, "Republic", {"edition": "t9999"})
