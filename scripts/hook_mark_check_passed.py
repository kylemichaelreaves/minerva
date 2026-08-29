#!/usr/bin/env python3
"""PostToolUse hook (#322, check 3, part 2): mark `make check` as passed.

Runs after Bash. Records the last time `make check` itself succeeded, so
`hook_require_fresh_check` can compare it against `hook_mark_dirty`'s marker.
"""

from __future__ import annotations

import json
import re
import sys

import staleness

#: `make check`, not `make check-pr-link` / `check-diff-coverage` / etc. —
#: `(?!-)` after `check` is what keeps those out.
_MAKE_CHECK = re.compile(r"\bmake\s+check(?!-)\b")


def is_make_check(command: str) -> bool:
    return bool(_MAKE_CHECK.search(command))


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not is_make_check(command):
        return 0
    response = payload.get("tool_response") or {}
    if response.get("success") is False:
        return 0
    staleness.touch(staleness.CHECK_PASSED_MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
