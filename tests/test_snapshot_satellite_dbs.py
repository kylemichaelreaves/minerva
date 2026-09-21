"""`scripts/snapshot-db.sh` takes the satellite databases too, WAL-safely.

`metrics.sqlite` moved to WAL in #630 and inherited the hazard the
snapshot script's header describes at length for `index.sqlite` — a
filesystem copy of the main file alone reads as a valid database that is
quietly short of every commit still sitting in the `-wal` sibling. The
script knew about that for one database and snapshotted only that one
(#639).
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "snapshot-db.sh"


def _wal_db_with_uncheckpointed_rows(path: Path, n: int) -> sqlite3.Connection:
    """A database whose committed rows live in the -wal, not the main file.

    `wal_autocheckpoint=0` holds them there, which is what a busy writer
    looks like between checkpoints — the window the hazard lives in.

    The connection is returned rather than closed, and the caller must
    keep it open: SQLite checkpoints and deletes the -wal when the last
    connection closes, so a closed database has no hazard to reproduce.
    That is also the real shape of it — the window is open precisely
    while `serve` is holding the database.
    """

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"r{i}",) for i in range(n)])
    conn.commit()
    return conn


def _rows(path: Path) -> int:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def data_dir(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    held = [
        _wal_db_with_uncheckpointed_rows(d / "index.sqlite", 10),
        _wal_db_with_uncheckpointed_rows(d / "metrics.sqlite", 5000),
    ]
    try:
        yield d
    finally:
        for conn in held:
            conn.close()


def _run(data_dir: Path, reason: str = "test") -> Path:
    if not shutil.which("sqlite3"):
        pytest.skip("sqlite3 CLI not installed")
    # Checked BEFORE invoking, not after. A script that ignores
    # MINERVA_DATA_DIR falls back to the repo's own data/, where it
    # writes an 8.4 GB snapshot and then silently rotates real ones
    # away — which is exactly what happened while this test was red.
    # Asserting on the output afterwards is too late to prevent it.
    if "MINERVA_DATA_DIR" not in SCRIPT.read_text(encoding="utf-8"):
        pytest.fail(
            "snapshot-db.sh does not honour MINERVA_DATA_DIR; refusing to "
            "run it, as it would snapshot the live corpus"
        )
    res = subprocess.run(
        [str(SCRIPT), reason],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "MINERVA_DATA_DIR": str(data_dir)},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    snaps = sorted((data_dir / "snapshots").iterdir())
    assert len(snaps) == 1, f"expected one snapshot, got {snaps}"
    return snaps[0]


def test_the_snapshot_includes_the_satellite_databases(data_dir: Path) -> None:
    snap = _run(data_dir)
    assert (snap / "metrics.sqlite").exists(), "metrics.sqlite was not snapshotted"


def test_the_satellite_copy_carries_its_uncheckpointed_commits(data_dir: Path) -> None:
    """The point of the whole exercise: a `cp` of metrics.sqlite here
    would produce a readable database missing all 5,000 rows."""

    # The wrong way first, and the order matters: `.backup` checkpoints
    # the source, so a cp taken *after* the script has run would succeed
    # and the contrast would silently prove nothing.
    naive = data_dir / "naive.sqlite"
    shutil.copy(data_dir / "metrics.sqlite", naive)
    with pytest.raises(sqlite3.DatabaseError):
        _rows(naive)

    snap = _run(data_dir)
    assert _rows(snap / "metrics.sqlite") == 5000


def test_a_missing_satellite_is_not_an_error(data_dir: Path) -> None:
    """Only `index.sqlite` is required; the satellites are optional and a
    fresh checkout has none of them."""

    (data_dir / "metrics.sqlite").unlink()
    for sibling in data_dir.glob("metrics.sqlite-*"):
        sibling.unlink()
    snap = _run(data_dir)
    assert (snap / "index.sqlite").exists()
    assert not (snap / "metrics.sqlite").exists()
