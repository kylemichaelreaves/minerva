#!/usr/bin/env python3
"""Verify a PR's closing links registered — and that none registered by accident (#321).

Three documented failure modes, each hit in this repo, and all three silent:

* A PR based on anything other than the default branch registers no closing
  link, however many `Closes` lines its body carries.
* The body is parsed when it is written, not when the base changes. Retargeting
  a stacked PR afterwards does not backfill; the body has to be edited again.
* The parser reads prose. A closing keyword next to an issue number fires
  whether the sentence is *using* the keyword or *talking about* it.

WHY A CLEAN `closingIssuesReferences` IS NOT ENOUGH

GitHub runs two parsers and they disagree. PR #293's `closingIssuesReferences`
was **empty** — its PR-body parser exempted a backticked reference — and its
merge commit closed #176 anyway, because the commit-message parser does not
exempt backticks and a squash merge turns the body into the message. So this
script does not merely read the API's answer; it also scans the text destined
for that commit, backtick-blind, before the commit exists.

WHY IT REFUSES RATHER THAN REPORTING ZERO

Every "no data" path is an error. A PR that cannot be fetched, a repo whose
default branch cannot be resolved — a naive implementation calls each of those
"nothing to report, fine", and an inert gate is worse than no gate (#116).

Usage:
    scripts/check_pr_link.py <pr> [issue ...]

    scripts/check_pr_link.py 330 297 300   # must close exactly 297 and 300
    scripts/check_pr_link.py 328           # must close nothing (a Refs-only PR)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: GitHub's closing keywords, exactly as documented. `closing` and `fixing` are
#: deliberately absent because GitHub does not act on them, and matching them
#: would fail correctly-written PRs.
_KEYWORDS = r"close[sd]?|fix(?:e[sd])?|resolve[sd]?"

#: Keyword, then up to three non-letter characters, then #N.
#:
#: The separator class is what makes this BACKTICK-BLIND, and that is the whole
#: point. Narrowing it to bare prose — stripping code spans, requiring a plain
#: space — reintroduces exactly the bug this catches. See the module docstring.
_CLOSING_REF = re.compile(
    rf"\b(?:{_KEYWORDS})\b[^A-Za-z]{{0,3}}#(\d+)", re.IGNORECASE
)


def scan_closing_refs(text: str) -> set[int]:
    """Issue numbers a GitHub closing keyword points at anywhere in `text`."""
    return {int(m.group(1)) for m in _CLOSING_REF.finditer(text)}


#: A conservative git ref-name pattern — deliberately narrower than git's real
#: grammar (`git check-ref-format` also permits `@{`, a trailing `.lock`, and
#: more). `baseRefName`/`headRefName` come back from the GitHub API, and
#: whoever opens the PR controls their own branch name, so this is untrusted
#: input reaching `git` (via `_commit_messages`). Refusing a legal-but-weird
#: ref here is the correct failure mode; trying to enumerate everything git
#: accepts and guessing at the edge cases is not. Mirrors the spirit of
#: `_REF_RE` in check_diff_coverage.py, narrowed further because this checker
#: never needs to accept `HEAD~3`-style refs, only ordinary branch/tag names.
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")

def require_safe_ref(kind: str, ref: str) -> None:
    """Raise `Problem` unless `ref` looks like a plausible git ref name.

    `kind` names what is being checked (e.g. "base ref") so the message says
    which value is bad; `ref` is the value under test. Pure and importable —
    this is the logic worth unit testing, unlike the subprocess calls it
    guards.
    """
    if not _SAFE_REF_RE.match(ref):
        raise Problem(f"{kind} {ref!r} is not a plausible git ref — refusing to pass it to git")


@dataclass(frozen=True)
class Failure:
    """One independent defect. `check` is a stable slug for tests and hooks;
    `detail` is what a human needs in order to fix it."""

    check: str
    detail: str


def evaluate(
    *,
    base_ref: str,
    default_branch: str,
    resolved: set[int],
    expected: set[int],
    scanned_text: dict[str, str],
) -> list[Failure]:
    """Every way this PR's closing links are wrong, in a fixed order.

    `scanned_text` maps a label to text that will reach the merge commit — the
    PR title, its body, and the branch's commit messages. All of it is scanned
    backtick-blind, because the commit-message parser is.
    """
    failures: list[Failure] = []

    if base_ref != default_branch:
        failures.append(
            Failure(
                "base",
                f"base is {base_ref!r}, not {default_branch!r}. GitHub registers a "
                "closing link only for PRs targeting the default branch, so every "
                "closing line in this PR is inert. Retargeting is not enough on its "
                "own: the body is parsed when written, so it must be edited again "
                "afterwards to re-trigger the scan.",
            )
        )

    if missing := expected - resolved:
        failures.append(
            Failure(
                "missing",
                f"expected to close {sorted(expected)}, GitHub resolved "
                f"{sorted(resolved)} — missing {sorted(missing)}. Each number needs "
                "its own keyword: `Closes #1, #2` links only the first.",
            )
        )

    if unexpected := resolved - expected:
        failures.append(
            Failure(
                "unexpected",
                f"GitHub resolved {sorted(unexpected)}, which this PR does not claim "
                "to close. A closing keyword next to an issue number anywhere in the "
                "body is enough, including inside a sentence about the convention.",
            )
        )

    for label, text in scanned_text.items():
        if hazards := scan_closing_refs(text) - expected:
            failures.append(
                Failure(
                    "hazard",
                    f"{label} puts a closing keyword next to {sorted(hazards)}, which "
                    "this PR does not claim to close. On a squash merge the body "
                    "becomes the commit message, and the commit-message parser does "
                    "not exempt backticks — this is how #176 closed while the "
                    "paragraph doing it explained the issue had to stay open. "
                    "Rewrite it to keep the keyword away from the number.",
                )
            )

    return failures


class Problem(Exception):
    """A refusal. Distinct from a failed check: this is the script being
    unable to answer, which must never be reported as a pass."""


def _parse_gh(proc: subprocess.CompletedProcess[str], label: str) -> dict:
    """Turn a finished `gh` invocation into its parsed JSON, or raise `Problem`.

    `label` is the command as a human would write it (e.g. `"gh pr view 328
    --json ..."`), used only for the error message — the invocation itself has
    already happened by the time this runs. This is the part of the old
    `_gh_json` worth sharing: response handling, not the `subprocess.run` call
    itself, which Sonar's S8705 flags when a variable-length argv is spread
    into it. Each call site now builds a fully literal argv instead.
    """
    if proc.returncode != 0:
        raise Problem(f"`{label}` failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Problem(f"`{label}` returned non-JSON: {exc}") from None


def _commit_messages(base_ref: str, head_ref: str) -> dict[str, str]:
    """Every commit on the branch, labelled by short sha.

    Uses the remote refs rather than the working tree so the answer does not
    depend on which branch happens to be checked out.
    """
    require_safe_ref("base ref", base_ref)
    require_safe_ref("head ref", head_ref)
    proc = subprocess.run(
        [
            "git", "log", "--format=%h%x00%B%x1e",
            "--end-of-options", f"origin/{base_ref}..origin/{head_ref}",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise Problem(
            f"could not read commits for origin/{head_ref}: {proc.stderr.strip()}. "
            "Push the branch first — this reads the remote, not the working tree."
        )
    out: dict[str, str] = {}
    for record in proc.stdout.split("\x1e"):
        if "\x00" not in record:
            continue
        sha, message = record.split("\x00", 1)
        out[f"commit {sha.strip()}"] = message
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a PR's closing links registered, and only the intended ones."
    )
    ap.add_argument("pr", type=int, help="pull request number")
    ap.add_argument(
        "issues",
        nargs="*",
        type=int,
        help="issue numbers this PR must close; omit to assert it closes none",
    )
    args = ap.parse_args()

    expected = set(args.issues)

    try:
        pr_number = str(int(args.pr))
        pr_proc = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                pr_number,
                "--json",
                "baseRefName,headRefName,title,body,closingIssuesReferences",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        pr = _parse_gh(pr_proc, f"gh pr view {pr_number} --json ...")

        repo_proc = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        repo = _parse_gh(repo_proc, "gh repo view --json defaultBranchRef")
        default_branch = repo["defaultBranchRef"]["name"]
        scanned = {
            "PR title": pr["title"] or "",
            "PR body": pr["body"] or "",
            **_commit_messages(pr["baseRefName"], pr["headRefName"]),
        }
        resolved = {r["number"] for r in pr["closingIssuesReferences"]}
    except (Problem, KeyError, TypeError) as exc:
        print(f"check-pr-link: {exc}", file=sys.stderr)
        return 1

    failures = evaluate(
        base_ref=pr["baseRefName"],
        default_branch=default_branch,
        resolved=resolved,
        expected=expected,
        scanned_text=scanned,
    )

    claim = f"close {sorted(expected)}" if expected else "close nothing"
    print(f"check-pr-link: PR #{args.pr} should {claim}; scanned {len(scanned)} text(s)")

    if failures:
        for f in failures:
            print(f"  [{f.check}] {f.detail}", file=sys.stderr)
        print(
            f"check-pr-link: FAILED — {len(failures)} defect(s). "
            "This is a bug in the PR, not in the check.",
            file=sys.stderr,
        )
        return 1

    print("check-pr-link: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
