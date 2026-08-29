#!/usr/bin/env python3
"""Shared marker-file comparison for the make-check-staleness gate (#322).

Two zero-byte marker files under `.claude/state/` (gitignored, session-local)
record two timestamps: the last time watched source was edited, and the last
time `make check` passed. `is_stale` compares their mtimes. This is the same
shape of bug #254 hit twice: an edit made *after* the last passing run of
`make check` reaches `git push`/`gh pr create` unverified.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = REPO / ".claude" / "state"
DIRTY_MARKER = STATE_DIR / "dirty"
CHECK_PASSED_MARKER = STATE_DIR / "check-passed"


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def is_stale(dirty: Path, check_passed: Path) -> bool:
    """True when watched source changed more recently than `make check` passed.

    No `dirty` marker means nothing watched has changed since the markers
    were last cleared (or ever) — not stale. A `dirty` marker with no
    `check_passed` marker at all is stale: `make check` has never passed
    since the edit.
    """
    if not dirty.exists():
        return False
    if not check_passed.exists():
        return True
    return dirty.stat().st_mtime > check_passed.stat().st_mtime
