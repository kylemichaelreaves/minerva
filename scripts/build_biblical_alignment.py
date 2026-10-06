#!/usr/bin/env -S uv run python
"""Build verse-to-verse alignment cross-references between the four
biblical corpora (Hebrew MT ↔ Septuagint ↔ Vulgate ↔ New Testament).

The four biblical corpora share BCV section locators — ``Gen 1:1`` in
Hebrew MT is the same verse position as ``Gen 1:1`` in the LXX and the
Vulgate. We treat that as a structural relationship and materialize
it as ``translates`` cross_references rows so the Reader's reference
panel surfaces parallel-text counterparts automatically.

Direction follows the historical translation chain (source_chunk_id
is the translator, target_chunk_id is the source):

  LXX     → MT     translates       (Greek translates Hebrew, c. 250 BCE)
  Vulgate → MT     translates       (Jerome's Hebraica Veritas, c. 400 CE)
  Vulgate → LXX    translates       (Old Latin / LXX-only books)
  Vulgate → NT     translates       (Latin NT translates Greek NT)

The Reader's "incoming references" panel on, say, MT Gen 1:1, will
then show two entries: ``LXX Gen 1:1 translates this`` and
``Vulgate Gen 1:1 translates this``. Outgoing on a Vulgate verse will
show its MT and LXX sources where applicable.

Rows are inserted with:

  source_method  = 'manual'    (deterministic alignment, not heuristic)
  curator_status = 'manual'    (no review needed; the section equality
                                IS the evidence)
  confidence     = 1.0
  reference_type = 'translates'

Idempotent: re-runs are no-ops because we dedup on
``(source_chunk_id, target_chunk_id, reference_type)`` before
inserting. Run after a fresh MT or Quran ingest.

Role: workflow
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from minerva import store
from minerva.refs.schema import ensure_target, insert_cross_reference

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _REPO_ROOT / "data" / "index.sqlite"


def _snapshot_before_mutation(db_path: Path) -> None:
    """Snapshot the DB before writing cross_references (issue #68).

    This script commits `curator_status='manual'`, `confidence=1.0` rows
    that bypass review, so a bad `_DIRECTIONS` edit or wrong re-ingest
    has nothing to roll back to without a snapshot. ``snapshot-db.sh``
    only snapshots the default ``data/index.sqlite``; if a custom path
    is passed, refuse the auto-snapshot and require a manual one so we
    never claim to have backed up a DB we didn't."""

    if db_path.resolve() != _DEFAULT_DB.resolve():
        raise SystemExit(
            f"refusing to mutate {db_path} without a snapshot: "
            f"snapshot-db.sh only covers {_DEFAULT_DB}. Snapshot the "
            f"target DB yourself, then re-run with MINERVA_SKIP_SNAPSHOT=1."
        )
    print("snapshotting data/index.sqlite before alignment build…", flush=True)
    subprocess.run(
        [str(_REPO_ROOT / "scripts" / "snapshot-db.sh"), "biblical-alignment"],
        check=True,
    )


# (translator_author, source_author) pairs and the direction. Each
# tuple is: source = translator (chunks doing the translating),
# target = source language being translated. Order matters when we
# query for shared sections — we always join translator to target.
_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("Septuagint", "Hebrew Bible"),  # LXX     → MT
    ("Vulgate", "Hebrew Bible"),  # Vulgate → MT
    ("Vulgate", "Septuagint"),  # Vulgate → LXX
    ("Vulgate", "New Testament"),  # Vulgate → NT
)


def _existing_pairs(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """Return the set of (source_chunk_id, target_chunk_id) pairs that
    already have a translates-typed cross_reference. Used to make the
    sweep idempotent."""

    rows = conn.execute(
        "SELECT source_chunk_id, target_chunk_id FROM cross_references "
        "WHERE reference_type = 'translates' AND target_chunk_id IS NOT NULL"
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def _iter_aligned_pairs(
    conn: sqlite3.Connection,
    *,
    translator_author: str,
    source_author: str,
) -> Iterable[tuple[str, str, str, str, str, str]]:
    """Yield ``(translator_chunk_id, translator_work, translator_section,
    source_chunk_id, source_work, source_section)`` for every shared
    BCV section between two biblical corpora.

    Uses an INNER JOIN on ``section`` (the BCV locator like ``"Gen 1:1"``)
    — that's the canonical cross-corpus key. The join naturally excludes
    sections present in only one corpus.

    If either corpus has multiple chunks at the same section
    (shouldn't happen for biblical corpora, but defensive), the join
    will produce the cartesian product — which is the correct alignment
    even in that edge case (each pair is a valid 'translates this same
    locator' relationship).
    """

    cur = conn.execute(
        """
        SELECT
          t.chunk_id, t.work, t.section,
          s.chunk_id, s.work, s.section
        FROM chunks_full t
        JOIN chunks_full s
          ON s.section = t.section
         AND s.section IS NOT NULL
        WHERE t.author = ?
          AND s.author = ?
        ORDER BY t.work, t.ord
        """,
        (translator_author, source_author),
    )
    yield from cur


def main(db_path: Path) -> int:
    if os.environ.get("MINERVA_SKIP_SNAPSHOT") != "1":
        _snapshot_before_mutation(db_path)
    conn = store.open_db(db_path)
    conn.row_factory = sqlite3.Row

    # Cache existing target_ids per (author, work) so we don't pay
    # ensure_target's lookup cost on every alignment row. The MT has
    # 39 works, Vulgate ~73, LXX ~46, NT 27 — small enough to load
    # eagerly.
    target_cache: dict[tuple[str, str], int] = {}

    def _target_id(author: str, work: str) -> int:
        key = (author, work)
        cached = target_cache.get(key)
        if cached is not None:
            return cached
        target = ensure_target(
            conn,
            canonical_author=author,
            canonical_work=work,
        )
        target_cache[key] = target.id
        return target.id

    existing = _existing_pairs(conn)
    print(f"existing translates pairs: {len(existing):,}")

    grand_total = 0
    grand_inserted = 0
    grand_skipped = 0

    for translator_author, source_author in _DIRECTIONS:
        label = f"{translator_author} → {source_author}"
        t0 = time.monotonic()
        rows = list(
            _iter_aligned_pairs(
                conn,
                translator_author=translator_author,
                source_author=source_author,
            )
        )
        n_pairs = len(rows)
        n_inserted = 0
        n_skipped = 0
        n_self = 0

        for t_chunk, t_work, t_section, s_chunk, s_work, s_section in rows:
            if t_chunk == s_chunk:
                # Same-chunk-self-pair shouldn't happen (different
                # authors), but guard anyway.
                n_self += 1
                continue
            if (t_chunk, s_chunk) in existing:
                n_skipped += 1
                continue

            target_id = _target_id(source_author, s_work)
            insert_cross_reference(
                conn,
                source_chunk_id=t_chunk,
                target_id=target_id,
                target_chunk_id=s_chunk,
                target_locator=s_section,
                reference_type="translates",
                source_form_snapshot=t_section,  # human-readable trace
                confidence=1.0,
                source_method="manual",
                curator_status="manual",
                curator_note=(
                    f"BCV alignment: {translator_author} {t_work} {t_section} "
                    f"translates {source_author} {s_work} {s_section}"
                ),
            )
            existing.add((t_chunk, s_chunk))
            n_inserted += 1

        conn.commit()

        wall = time.monotonic() - t0
        print(
            f"  {label:<35}  pairs={n_pairs:>6,}  "
            f"inserted={n_inserted:>6,}  skipped={n_skipped:>6,}  "
            f"({wall:.1f}s)"
        )
        grand_total += n_pairs
        grand_inserted += n_inserted
        grand_skipped += n_skipped

    print()
    print(f"total pairs examined:  {grand_total:,}")
    print(f"new rows inserted:     {grand_inserted:,}")
    print(f"already-existing skip: {grand_skipped:,}")
    return 0


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/index.sqlite")
    raise SystemExit(main(db))
