"""Committed stand-in for the gitignored index's work-slug table (#602).

Reader URLs are `#/r/<authorSlug>/<titleSlug>`, and the pair is resolved back
to a work server-side. Two things can break that, and neither shows up as a
test failure on its own:

* the Python and TypeScript slugifiers drifting apart, so a link the client
  builds is one the server cannot resolve;
* a newly ingested work colliding with an existing pair, so a link resolves to
  the WRONG work.

`data/index.sqlite` is gitignored, so CI cannot check either against the live
corpus. This snapshot is what it checks instead — the `chunk_counts.json`
pattern (#157), for the same reason.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "data" / "authors" / "work_slugs.json"


def build_snapshot(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from minerva.reader.slugs import work_slug_table

    return work_slug_table(conn)


def write_snapshot(snapshot: dict[str, dict[str, str]]) -> None:
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_snapshot() -> dict[str, dict[str, str]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
