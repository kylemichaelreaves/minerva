#!/usr/bin/env python3
"""PostToolUse hook (#322, check 1): warn when a just-made commit puts a
closing keyword next to an issue number.

Advisory only — never blocks. `Closes #N` is the common, *correct* case, and
only a human (or Claude, reading the surrounding sentence) can tell it apart
from the #176 kind of accident, where a paragraph *discussing* the convention
carried the same hazard aimed at the same open issue. `make check-pr-link`
is the gate that actually fails a bad PR before merge; this just surfaces the
same scan a few minutes earlier, when it is cheaper to notice.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from check_pr_link import scan_closing_refs

_GIT_COMMIT = re.compile(r"(?:^|[;&|]|&&)\s*git\s+commit\b")


def should_fire(payload: dict) -> bool:
    if payload.get("tool_name") != "Bash":
        return False
    command = payload.get("tool_input", {}).get("command", "")
    if not _GIT_COMMIT.search(command):
        return False
    response = payload.get("tool_response") or {}
    return response.get("success") is not False


def latest_commit_message() -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def build_output(hits: list[int]) -> dict | None:
    if not hits:
        return None
    return {
        "systemMessage": (
            f"This commit's message closes {hits} — confirm that's intended "
            "before it reaches a PR into main (#176)."
        ),
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"The commit just made puts a GitHub closing keyword next to "
                f"issue number(s) {hits}. Double-check this is deliberate — "
                "`make check-pr-link` verifies it before merge, but catching "
                "it now is cheaper."
            ),
        },
    }


def main() -> int:
    payload = json.load(sys.stdin)
    if not should_fire(payload):
        return 0
    hits = sorted(scan_closing_refs(latest_commit_message()))
    output = build_output(hits)
    if output is not None:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
