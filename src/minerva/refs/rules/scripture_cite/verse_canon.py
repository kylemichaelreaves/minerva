"""Committed verse-count canon for the four target Bibles (#519).

A scripture rule builds its locator from the numbers it parsed, so a cite
naming an impossible verse ("Apoc. 22-27"; Revelation 22 has 21 verses)
used to be emitted, and stayed unbound. Worse, it was emitted under the
*default* book of an ambiguous abbreviation: "ad Cor. 5-14" became 1 Cor
5:14, which does not exist, while 2 Cor 5:14 does. Knowing how many
verses each chapter has lets the rule refuse the first and resolve the
second.

Why a committed file and not a DB lookup at emit time: rules are
content-pure — ``apply_rules_to_chunk`` is idempotent on chunk input with
no DB state — which is what lets every rule test run without a corpus.
A lookup would keep every test green while that property quietly stopped
being true. So the canon is generated from the index by
``make generate-authors`` into ``verse_counts.json`` beside this module,
and ``make check-authors`` fails locally if it has drifted from the
index (CI has no index, so there it only has to load).

Shape: ``{target_author: {sbl_book: [max_verse_of_ch1, max_verse_of_ch2, …]}}``.
A chapter with no verses in the index records 0.

**The highest verse, not the set of verses.** Sacy's text in the index is
missing 232 verses across 129 chapters (measured 2026-10-07; Vulgate, KJV
and Luther have none missing). Those are gaps in our edition, not in
the canon, and a cite to one is still a real cite — it just cannot bind.
Recording the maximum keeps the check about what the Bible contains
rather than what our copy of it happens to.
"""

from __future__ import annotations

import json
import re
import sqlite3
from functools import cache
from pathlib import Path

CANON_PATH = Path(__file__).with_name("verse_counts.json")

# The rule modules' `target_author` defaults. A target outside this set is
# not checked (see `exists`).
TARGET_BIBLES: tuple[str, ...] = ("Vulgate", "Sacy", "King James Bible", "Luther Bibel 1912")

Canon = dict[str, dict[str, list[int]]]

_SECTION_RE = re.compile(r"(\S+) (\d+):(\d+)")


def build_canon(conn: sqlite3.Connection) -> Canon:
    """Measure the canon from the index: highest verse per chapter."""

    placeholders = ",".join("?" * len(TARGET_BIBLES))
    rows = conn.execute(
        f"SELECT w.author, c.section FROM chunks c JOIN works w ON w.id = c.work_id "
        f"WHERE w.author IN ({placeholders}) AND c.section IS NOT NULL",
        TARGET_BIBLES,
    )
    canon: Canon = {}
    for author, section in rows:
        m = _SECTION_RE.fullmatch(section)
        if m is None:
            continue
        chapters = canon.setdefault(author, {}).setdefault(m[1], [])
        chap, verse = int(m[2]), int(m[3])
        if len(chapters) < chap:
            chapters.extend([0] * (chap - len(chapters)))
        chapters[chap - 1] = max(chapters[chap - 1], verse)
    return canon


def canon_drift(conn: sqlite3.Connection, canon: Canon) -> list[str]:
    """Differences between the committed canon and the index, per Bible."""

    live = build_canon(conn)
    errs = []
    for author in sorted(set(live) | set(canon)):
        if live.get(author) != canon.get(author):
            errs.append(
                f"verse canon for {author!r} differs from the index — run `make generate-authors`"
            )
    return errs


def write_canon(canon: Canon, path: Path = CANON_PATH) -> None:
    # One book per line: diffable without being 130,000 lines long.
    lines = ["{"]
    authors = sorted(canon)
    for i, author in enumerate(authors):
        lines.append(f"  {json.dumps(author, ensure_ascii=False)}: {{")
        books = sorted(canon[author])
        for j, book in enumerate(books):
            sep = "," if j < len(books) - 1 else ""
            lines.append(f"    {json.dumps(book)}: {json.dumps(canon[author][book])}{sep}")
        lines.append("  }" + ("," if i < len(authors) - 1 else ""))
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@cache
def _load(path: Path) -> Canon:
    return json.loads(path.read_text(encoding="utf-8"))


def load_canon(path: Path = CANON_PATH) -> Canon:
    return _load(path)


def exists(canon: Canon, target: str, sbl: str, chap: int, verse: int | None) -> bool | None:
    """Does ``sbl chap[:verse]`` exist in ``target``'s canon?

    ``None`` when the canon does not cover ``target``, or covers it but
    not that book — the caller then has nothing to check against and must
    not filter. The second case is real: the corpus's KJV is the 66-book
    Protestant canon, and Hobbes cites "2 Esdras 14.21" from the
    Apocrypha. That is a cite the edition cannot bind, not an impossible
    one, the same distinction the module docstring draws for Sacy's
    missing verses."""

    chapters = canon.get(target, {}).get(sbl)
    if chapters is None:
        return None
    if not 1 <= chap <= len(chapters):
        return False
    top = chapters[chap - 1]
    return top > 0 if verse is None else 1 <= verse <= top
