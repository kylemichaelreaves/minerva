"""Rotation in `scripts/snapshot-db.sh` says what it deletes, and can be
told not to.

Rotation exists because the snapshot directory reached 128 GB. It prunes
by timestamp alone, so the newest snapshot always evicts the oldest
regardless of which is worth more — and it `rm -rf`s ~8.8 GB rollback
points with no confirmation. On 2026-09-21 three stray invocations
destroyed the three oldest real snapshots, one of which an issue comment
cited as the pre-repair state of a data fix (#653).
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "snapshot-db.sh"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    conn = sqlite3.connect(d / "index.sqlite")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return d


def _fake_snapshot(data_dir: Path, name: str, *, protected: bool = False) -> Path:
    """An existing snapshot directory, as a previous run would have left it."""

    d = data_dir / "snapshots" / name
    d.mkdir(parents=True)
    (d / "manifest.txt").write_text(f"reason: {name.split('-', 1)[1]}\n")
    (d / "index.sqlite").write_bytes(b"")
    if protected:
        (d / "KEEP").touch()
    return d


def _run(data_dir: Path, reason: str = "new", **env_extra) -> subprocess.CompletedProcess:
    if not shutil.which("sqlite3"):
        pytest.skip("sqlite3 CLI not installed")
    if "MINERVA_DATA_DIR" not in SCRIPT.read_text(encoding="utf-8"):
        pytest.fail("snapshot-db.sh does not honour MINERVA_DATA_DIR; refusing to run")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "MINERVA_DATA_DIR": str(data_dir),
        **env_extra,
    }
    res = subprocess.run([str(SCRIPT), reason], env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res


def _names(data_dir: Path) -> set[str]:
    return {p.name for p in (data_dir / "snapshots").iterdir()}


def test_pruning_names_each_snapshot_it_deletes(data_dir: Path) -> None:
    """A count is not enough. `(pruned 3 older snapshots)` is what the
    script said while it was destroying the three this issue is about —
    true, and useless for noticing which."""

    for name in ("20260101T000000Z-pre-alpha", "20260102T000000Z-pre-beta"):
        _fake_snapshot(data_dir, name)

    res = _run(data_dir, "pre-gamma", MINERVA_SNAPSHOT_KEEP="1")

    assert "20260101T000000Z-pre-alpha" in res.stderr
    assert "20260102T000000Z-pre-beta" in res.stderr
    # And the reason tag, which is what makes a name mean something.
    assert "pre-alpha" in res.stderr


def test_a_protected_snapshot_survives_rotation(data_dir: Path) -> None:
    """The `before-0035-post-apparatus` case: a snapshot someone wrote
    down as the baseline for a data repair, evicted by a stray run."""

    _fake_snapshot(data_dir, "20260101T000000Z-before-0035", protected=True)
    _fake_snapshot(data_dir, "20260102T000000Z-pre-beta")

    _run(data_dir, "pre-gamma", MINERVA_SNAPSHOT_KEEP="1")

    assert "20260101T000000Z-before-0035" in _names(data_dir)
    assert "20260102T000000Z-pre-beta" not in _names(data_dir)


def test_protected_snapshots_do_not_consume_the_keep_budget(data_dir: Path) -> None:
    """Otherwise protecting one snapshot silently shortens how far back
    the unprotected history reaches, which is a second surprise deletion
    caused by trying to prevent the first."""

    _fake_snapshot(data_dir, "20260101T000000Z-before-0035", protected=True)
    _fake_snapshot(data_dir, "20260102T000000Z-pre-beta")
    _fake_snapshot(data_dir, "20260103T000000Z-pre-delta")

    _run(data_dir, "pre-gamma", MINERVA_SNAPSHOT_KEEP="2")

    survivors = _names(data_dir)
    assert "20260101T000000Z-before-0035" in survivors, "protected must survive"
    # keep=2 counts only unprotected: the new one + pre-delta.
    assert "20260103T000000Z-pre-delta" in survivors
    assert "20260102T000000Z-pre-beta" not in survivors


def test_dry_run_writes_nothing_and_deletes_nothing(data_dir: Path) -> None:
    before = {"20260101T000000Z-pre-alpha", "20260102T000000Z-pre-beta"}
    for name in before:
        _fake_snapshot(data_dir, name)

    res = _run(data_dir, "pre-gamma", MINERVA_SNAPSHOT_KEEP="1", MINERVA_SNAPSHOT_DRY_RUN="1")

    assert _names(data_dir) == before, "dry run must not create or delete"
    assert "20260101T000000Z-pre-alpha" in res.stdout + res.stderr
    assert "would prune" in (res.stdout + res.stderr).lower()


def test_dry_run_lists_protected_snapshots_separately(data_dir: Path) -> None:
    """Under their own heading. Printed in the same flat list they read
    as things about to be deleted, which is the opposite of the message."""

    _fake_snapshot(data_dir, "20260101T000000Z-before-0035", protected=True)
    _fake_snapshot(data_dir, "20260102T000000Z-pre-beta")

    out = _run(
        data_dir, "pre-gamma", MINERVA_SNAPSHOT_KEEP="1", MINERVA_SNAPSHOT_DRY_RUN="1"
    ).stderr
    prune_at = out.index("would prune")
    protected_at = out.index("protected, never pruned")
    assert prune_at < protected_at
    assert out.index("20260102T000000Z-pre-beta") < protected_at, "prunable listed above"
    assert out.index("20260101T000000Z-before-0035") > protected_at, "protected below"
