#!/usr/bin/env python3
"""PreToolUse hook (#322, check 3, part 3): catch a push made after an edit
`make check` never saw.

Two pushes on #254 failed CI this way — a lint error and a tsc arity error,
both introduced after the last local `make check` run. Asks rather than
denies: the marker granularity is "some watched file changed", which can be
broader than what the push actually carries (a stash, a second worktree),
so a human override is cheaper than a hard block on every false positive.
"""

from __future__ import annotations

import json
import re
import sys

import staleness

_PUSH_OR_PR = re.compile(r"\bgit\s+push\b|\bgh\s+pr\s+create\b")


def is_push_or_pr_create(command: str) -> bool:
    return bool(_PUSH_OR_PR.search(command))


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not is_push_or_pr_create(command):
        return 0
    if not staleness.is_stale(staleness.DIRTY_MARKER, staleness.CHECK_PASSED_MARKER):
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        "Watched source (src/, tests/, web/src/, perseus/, scripts/) "
                        "changed since make check last passed (#254's failure mode) — "
                        "run make check again before pushing or opening the PR."
                    ),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
