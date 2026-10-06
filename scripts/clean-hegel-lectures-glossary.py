#!/usr/bin/env python3
"""Remove the OCR'd German→English glossary word-lists from Hegel's
*Lectures on the History of Philosophy*.

Each of the three Brown/Stewart volumes ends with a bilingual
German–English glossary — an alphabetical run of bare vocabulary with
no sentences:

    Trennung Trieb Übergang übergehen übergreifen überhaupt Überzeugung …
    existieren fassen Form für sich Fürsich Fürsichsein Gebiet Gedächtnis …
    bloß Boden darstellen Darstellung Dasein Denkbestimmung denken …
    Vollendung vorhanden vorstellen vorstellend Vorstellung wahr …

The PDF text-extraction ingests each glossary page as a content chunk
(``section='¶2'``), mangled by OCR (``iibergehen`` for *übergehen*,
``Obergang`` for *Übergang*, ``Reali tat`` for *Realität*). Because the
lists pack the exact technical vocabulary — *Darstellung*, *Vorstellung*,
*Begriff* — into a few hundred characters, BM25 ranks them at the very
top for any question about those terms. A 2026-06 chat about the
Vorstellung/Darstellung distinction surfaced two of these pages as its
top citations instead of Hegel's actual prose.

These chunks are PDF-derived, so (unlike the source-text cleaners for
Marx/Cicero/etc.) there's no raw file to scrub — the fix lives at the
DB level and must be re-run after any re-ingest of the Lectures.

Signature (precise, prose-safe):
  * author = Hegel, work LIKE '%Lectures%', section = '¶2'
  * 120 ≤ length < 700   (real ¶2 prose chunks are ≥ 1200 chars; the
    120 floor skips sub-retrieval title/TOC fragments, a separate
    junk class the 60-char retrieval floor already hides)
  * ≤ 1 sentence break ('. ')   — the discriminator: glossary lists
    carry 0–1, genuine prose of this length carries ≥ 6. This is what
    keeps the rule from ever matching real content.

Idempotent: a cleaned index matches zero rows on the next run.
Deletion runs with foreign keys ON, so embeddings + chunk_lemmas
cascade and the FTS triggers keep ``chunks_fts`` in sync; the
concordance ``lemma_counts`` aggregate is rebuilt afterwards.

Usage:
    python scripts/clean-hegel-lectures-glossary.py            # dry run
    python scripts/clean-hegel-lectures-glossary.py --apply    # delete
    python scripts/clean-hegel-lectures-glossary.py --db path/to/index.sqlite

Always snapshot first: ``scripts/snapshot-db.sh <reason>``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "index.sqlite"


def resolve_db_path() -> Path:
    """The index to clean: ``$MINERVA_DB`` if set, else the repo default.

    Environment variable rather than a ``--db`` flag, matching
    ``corpus-quality-audit.py``. SonarCloud's ``pythonsecurity:S8706``
    fails a PR when a CLI argument reaches ``sqlite3.connect`` and judges
    new code only, so the next PR touching the connect line would have
    inherited a red rating for a pre-existing pattern (#179).

    This script *deletes chunks*, so it matters more here than in the
    read-only auditor that the target is stated deliberately rather than
    defaulted into. Point it at a snapshot with:

        MINERVA_DB=data/snapshots/index.2026-08-05.sqlite \\
            scripts/clean-hegel-lectures-glossary.py --apply
    """

    override = os.environ.get("MINERVA_DB")
    return Path(override) if override else DEFAULT_DB


# WHERE predicate selecting the glossary word-list chunks, evaluated
# against the chunks_full view. The ``(len - len_without('. ')) / 2``
# expression counts sentence breaks without a UDF, so this runs on a
# bare sqlite3 connection.
_GLOSSARY_PREDICATE = """
    author = 'Hegel'
    AND work LIKE '%Lectures%'
    AND section = '¶2'
    AND length(text) BETWEEN 120 AND 700
    AND (length(text) - length(replace(text, '. ', ''))) / 2 <= 1
"""


def _find(conn: sqlite3.Connection) -> list[tuple[str, str, int, str]]:
    """Return ``(chunk_id, work, length, preview)`` for each glossary chunk."""

    rows = conn.execute(
        f"""
        SELECT chunk_id, work, length(text),
               substr(replace(text, char(10), ' '), 1, 66)
        FROM chunks_full
        WHERE {_GLOSSARY_PREDICATE}
        ORDER BY work, length(text) DESC
        """
    ).fetchall()
    return [(r[0], r[1], int(r[2]), r[3]) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Remove Hegel Lectures glossary junk chunks.",
        epilog="Set MINERVA_DB to target an index other than data/index.sqlite.",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Perform the deletion. Without it, only report (dry run).",
    )
    args = ap.parse_args()

    db_path = resolve_db_path()
    if not db_path.is_file():
        print(f"index not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        matches = _find(conn)
        if not matches:
            print("No Hegel Lectures glossary chunks found — index is clean.")
            return 0

        print(f"Matched {len(matches)} glossary word-list chunk(s):", file=sys.stderr)
        for _cid, work, n, preview in matches:
            vol = work.split("—")[-1].strip() if "—" in work else work
            print(f"  [{n:>3}c] {vol[:34]:34s} | {preview}", file=sys.stderr)

        if not args.apply:
            print(
                f"\nDry run — pass --apply to delete these {len(matches)} chunks "
                "(embeddings + chunk_lemmas cascade, FTS stays in sync).",
                file=sys.stderr,
            )
            return 0

        ids = [m[0] for m in matches]
        placeholders = ",".join("?" * len(ids))
        conn.execute("PRAGMA foreign_keys = ON")
        emb = conn.execute(
            f"SELECT COUNT(*) FROM embeddings WHERE chunk_id IN ({placeholders})", ids
        ).fetchone()[0]
        lem = conn.execute(
            f"SELECT COUNT(*) FROM chunk_lemmas WHERE chunk_id IN ({placeholders})", ids
        ).fetchone()[0]

        with conn:  # transaction: commit on success, rollback on error
            conn.execute(f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})", ids)
        print(
            f"\nDeleted {len(ids)} chunks (cascaded {emb} embeddings + {lem} lemmas).",
            file=sys.stderr,
        )

        # The concordance leaderboard reads a materialized aggregate;
        # rebuild it so the removed lemmas drop out of the counts.
        from minerva.concordance import aggregate

        aggregate.build(conn)
        conn.commit()
        print("Rebuilt lemma_counts aggregate.", file=sys.stderr)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
