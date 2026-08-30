#!/usr/bin/env python3
"""Delete the `cross_references` rows `xref_source_span` flags as
genuinely stale (#407), so a subsequent `refs build` pass can rediscover
them wherever the cited text still exists in the chunk.

Two shapes violate the invariant (`audit_invariants.py`): a span that
runs past the end of its chunk's current text, and a span still in range
whose slice no longer equals `source_form_snapshot`. Underneath both is
#285 — `chunk_id` hashes only `text[:120]`, so a chunk's text can shrink
or shift past that point without its id, or any row keyed on it, noticing.

**Not every violation is a bug.** #414 found 212 of the in-range
mismatches are `Aquinas`/`Augustine` scripture quotes where
`source_form_snapshot` deliberately records the citation formula plus
the quote ("in Psalmo: cor meum ...") while the span covers only the
quote — the span is right, the snapshot is just wider. That population
was closed as *accepted, not a bug*, and reproduces at a difflib ratio
of 0.6 or higher between the snapshot and the actual slice. This script
reuses that exact test rather than re-deriving a threshold, and leaves
those rows untouched.

Dry-run by default — prints what would be deleted. Pass `--execute` to
actually delete. Take a snapshot first::

    scripts/snapshot-db.sh pre-407-xref-repair
    ./.venv/bin/python scripts/repair_stale_xrefs.py
    ./.venv/bin/python scripts/repair_stale_xrefs.py --execute

Run `refs build --strategy rules --source-author <X>` afterward for each
affected author to rediscover whatever the deletion made room for.
`delete_stale_xrefs` drops the touched chunks' `refs_scan_state` rows
alongside their stale xrefs (#459) — a plain `refs build`, no
`--rescan-all` needed, is enough to pick them back up.

This used to say `refs_scan_state.text_hash` would already mismatch the
current text for every chunk this script touches, so the existing skip
cache would re-scan them unprompted. Wrong: that's only true when the
chunk's text is what changed. An in-range snapshot mismatch can be stale
for another reason on a chunk nobody edited, in which case
`refs_scan_state` still reads as current and a plain `refs build` would
have skipped it forever — measured on Aristotle, where a normal build
reported "0 chunks scanned" while `--rescan-all` recovered 58 rows the
skip cache had been silently withholding (#459).
"""

from __future__ import annotations

import argparse
import difflib
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "index.sqlite"

# #414's own threshold for "the snapshot is a wider, deliberate superset
# of the span" — reused rather than re-derived so this script cannot
# silently narrow or widen a population someone already reviewed.
_ACCEPTED_WIDE_SNAPSHOT_RATIO = 0.6


def resolve_db_path() -> Path:
    """The index to repair: ``$MINERVA_DB`` if set, else the repo default.

    Same pattern as `audit_invariants.py` — an environment variable
    rather than a `--db` flag, since a CLI argument reaching
    `sqlite3.connect` fails SonarCloud's `pythonsecurity:S8706` gate.
    """

    override = os.environ.get("MINERVA_DB")
    return Path(override) if override else _DEFAULT_DB


@dataclass(frozen=True)
class StaleXref:
    id: int
    source_chunk_id: str
    reason: str


def _is_accepted_wide_snapshot(snapshot: str, actual: str) -> bool:
    """#414: the span is correct and the snapshot is a deliberately wider
    superset of it (a citation formula plus the quote). Not a violation
    to repair."""

    return difflib.SequenceMatcher(None, snapshot, actual).ratio() >= _ACCEPTED_WIDE_SNAPSHOT_RATIO


def find_stale_xrefs(conn: sqlite3.Connection) -> list[StaleXref]:
    """Every `cross_references` row that violates `xref_source_span` and
    is not #414's accepted wide-snapshot population."""

    stale: list[StaleXref] = []
    rows = conn.execute(
        "SELECT x.id, x.source_chunk_id, x.source_span_start, x.source_span_end, "
        "       x.source_form_snapshot, c.text "
        "FROM cross_references x "
        "JOIN chunks c ON c.chunk_id = x.source_chunk_id "
        "WHERE x.source_span_start IS NOT NULL AND x.source_span_end IS NOT NULL"
    )
    for xref_id, chunk_id, start, end, snapshot, text in rows:
        if end > len(text):
            stale.append(
                StaleXref(id=xref_id, source_chunk_id=chunk_id, reason="span past end of chunk")
            )
            continue
        actual = text[start:end]
        if snapshot is None or actual == snapshot:
            continue
        if _is_accepted_wide_snapshot(snapshot, actual):
            continue
        stale.append(
            StaleXref(id=xref_id, source_chunk_id=chunk_id, reason="snapshot mismatch")
        )
    return stale


def delete_stale_xrefs(conn: sqlite3.Connection, stale: list[StaleXref]) -> None:
    conn.executemany(
        "DELETE FROM cross_references WHERE id = ?", [(s.id,) for s in stale]
    )
    # #459: this module's own docstring used to assume a deleted xref's
    # `refs_scan_state` row would already read as stale — true only when
    # the chunk's *text* changed. An in-range snapshot mismatch can be
    # stale for another reason entirely, on a chunk nobody edited, and
    # then `refs_scan_state` still matches the chunk's current text and
    # rules exactly. Left alone, that row makes `refs build` skip the
    # chunk forever, silently withholding whatever a rescan would
    # rediscover (measured on Aristotle: a normal build reported "0
    # chunks scanned" while `--rescan-all` found 58 rows the skip cache
    # had been withholding). Deleting the marker here removes the
    # reliance on that assumption — the next `refs build` treats every
    # touched chunk as unscanned, whether or not its text moved.
    conn.executemany(
        "DELETE FROM refs_scan_state WHERE chunk_id = ?",
        sorted({(s.source_chunk_id,) for s in stale}),
    )
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the stale rows. Without this, only reports counts.",
    )
    args = ap.parse_args(argv)

    db = resolve_db_path()
    if not db.exists():
        print(f"repair: no database at {db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db)
    if not args.execute:
        conn.execute("PRAGMA query_only = ON")
    try:
        stale = find_stale_xrefs(conn)
        by_reason: dict[str, int] = {}
        for s in stale:
            by_reason[s.reason] = by_reason.get(s.reason, 0) + 1
        print(f"{len(stale)} stale cross_references rows found")
        for reason, count in sorted(by_reason.items()):
            print(f"  {count:6} {reason}")
        if args.execute:
            delete_stale_xrefs(conn, stale)
            print(f"deleted {len(stale)} rows")
        else:
            print("dry run — pass --execute to delete")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
