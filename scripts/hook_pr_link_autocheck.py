#!/usr/bin/env python3
"""PostToolUse hook (#322, check 2): run the PR-link gate right after `gh pr
create`, instead of relying on someone remembering to type the make target.

Derives the expected closing-issue set from the PR body's own closing
keywords (the same scan `check_pr_link.evaluate` uses to compute `hazard`)
and feeds it straight to `scripts/check_pr_link.py`, so a broken link is
visible in this turn rather than at the next `/close-out` phase 5.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from check_pr_link import scan_closing_refs

_GH_PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b")
_PR_URL = re.compile(r"github\.com/[^/\s]+/[^/\s]+/pull/(\d+)")


def should_fire(payload: dict) -> bool:
    if payload.get("tool_name") != "Bash":
        return False
    command = payload.get("tool_input", {}).get("command", "")
    if not _GH_PR_CREATE.search(command):
        return False
    response = payload.get("tool_response") or {}
    return response.get("success") is not False


def extract_pr_number(stdout: str) -> int | None:
    match = _PR_URL.search(stdout)
    return int(match.group(1)) if match else None


def _pr_body(pr: int) -> str:
    result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", "body", "--jq", ".body"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def main() -> int:
    payload = json.load(sys.stdin)
    if not should_fire(payload):
        return 0
    stdout = (payload.get("tool_response") or {}).get("stdout", "")
    pr = extract_pr_number(stdout)
    if pr is None:
        return 0

    body = _pr_body(pr)
    issues = sorted(scan_closing_refs(body))
    result = subprocess.run(
        [sys.executable, "scripts/check_pr_link.py", str(pr), *map(str, issues)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "systemMessage": f"check-pr-link failed for PR #{pr} — see additionalContext.",
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            f'`make check-pr-link PR={pr} ISSUES="{" ".join(map(str, issues))}"` '
                            f"failed:\n{result.stdout}{result.stderr}"
                        ),
                    },
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
