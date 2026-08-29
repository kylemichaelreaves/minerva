#!/usr/bin/env python3
"""PostToolUse hook (#322, check 3, part 1): mark watched source dirty.

Runs after Write/Edit/MultiEdit. Records that source `make check` actually
covers has changed since the last passing run, so `hook_require_fresh_check`
can catch a push made after an edit `make check` never saw (#254).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import staleness

_WATCHED_PREFIXES = ("src/", "tests/", "web/src/", "perseus/", "scripts/")


def is_watched_path(path: str) -> bool:
    """`path` may be repo-relative (as in tests) or absolute (as the hook
    receives it) — relativize against the repo root when it is absolute and
    inside it; an absolute path outside the repo matches nothing."""
    p = Path(path)
    if p.is_absolute():
        try:
            path = p.relative_to(staleness.REPO).as_posix()
        except ValueError:
            return False
    return path.startswith(_WATCHED_PREFIXES)


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0
    path = payload.get("tool_input", {}).get("file_path", "")
    if is_watched_path(path):
        staleness.touch(staleness.DIRTY_MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
