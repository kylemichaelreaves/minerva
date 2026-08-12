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

WHY IT READS THE LINK MORE THAN ONCE

`closingIssuesReferences` is eventually consistent after a body edit, so a
single read reports a missing link on a PR whose body is correct. That is the
one verdict here the API can fabricate, so it is the only one retried (#331).

Usage:
    scripts/check_pr_link.py <pr> [issue ...]

    scripts/check_pr_link.py 315 297 300   # must close exactly 297 and 300
    scripts/check_pr_link.py 327           # must close nothing (a Refs-only PR)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: GitHub's closing keywords, exactly as documented. `closing` and `fixing` are
#: deliberately absent because GitHub does not act on them, and matching them
#: would fail correctly-written PRs.
_KEYWORDS = r"close[sd]?|fix(?:e[sd])?|resolve[sd]?"

#: Up to three non-letter characters — a space, a colon, a backtick.
#:
#: This class is what makes the scan BACKTICK-BLIND, and that is the whole
#: point. Narrowing it to bare prose — stripping code spans, requiring a plain
#: space — reintroduces exactly the bug this catches. See the module docstring.
_GAP = r"[^A-Za-z]{0,3}"

#: An optional `owner/repo` qualifying the number, as in GitHub's own example
#: `Fixes octo-org/octo-repo#100`. Documented closing syntax, and unmatchable by
#: `_GAP` alone: stopping at any letter is what keeps the scan backtick-blind,
#: and it is the same property that stops it at the `o` of `octo-org` (#330).
_QUALIFIER = r"(?:[\w.-]+/[\w.-]+)?"

#: Keyword, a gap, then an optionally repo-qualified #N.
#:
#: NO INTERVENING WORD, measured rather than assumed (#330). Admitting one so
#: that `closes issue #N` matches is defensible in the abstract: this scan feeds
#: the `hazard` check and nothing else, so over-matching costs a rewritten
#: sentence while under-matching is #176. What that argument never prices is
#: what over-matching actually costs. Measured across every PR text in the repo
#: — 760 titles, bodies and commit messages over 194 PRs — a one-word filler
#: matches 6 texts this pattern does not, all 6 false positives, against zero
#: real occurrences of `closes issue #N`. Two of the six shapes recur here
#: constantly: a `Refs #N` line after a sentence ending in "fixed.", and
#: `/close-out (#N)`. Flagging the sanctioned non-closing form is how a gate
#: gets overridden, which is the corrosion #331 is about.
_CLOSING_REF = re.compile(
    rf"\b(?:{_KEYWORDS})\b{_GAP}{_QUALIFIER}#(\d+)", re.IGNORECASE
)


def scan_closing_refs(text: str) -> set[int]:
    """Issue numbers a GitHub closing keyword points at anywhere in `text`."""
    return {int(m.group(1)) for m in _CLOSING_REF.finditer(text)}


#: How many times to read `closingIssuesReferences` before believing a link is
#: absent, and the pause between reads. The field is eventually consistent after
#: a body edit, so one read can report `[missing]` for a link that registers a
#: moment later (#331). A genuinely missing link costs these seconds; a false
#: failure costs the gate its credibility.
_LINK_ATTEMPTS = 3
_LINK_RETRY_DELAY = 1.0


def resolve_closing_refs(
    fetch: Callable[[], set[int]],
    expected: set[int],
    *,
    attempts: int = _LINK_ATTEMPTS,
    delay: float = _LINK_RETRY_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[set[int], int]:
    """Read the resolved closing refs, re-reading while one is still missing.

    Returns the last answer and how many reads it took, so the caller can say
    what it waited for rather than implying the first read was the only one.

    Retries ONLY on a missing link, which is the one defect the propagation lag
    can fabricate. An `unexpected` link is already registered and will not
    un-register, and a `hazard` is read from text that does not change between
    attempts — re-reading for either would mask a real defect rather than
    outwait a race.
    """
    resolved: set[int] = set()
    for attempt in range(1, attempts + 1):
        resolved = fetch()
        if not expected - resolved:
            return resolved, attempt
        if attempt < attempts:
            sleep(delay)
    return resolved, attempts


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
                "its own keyword: `Closes #1, #2` links only the first. If the body "
                "plainly carries a keyword next to each number, the link may simply "
                "not have registered yet — `closingIssuesReferences` is eventually "
                "consistent after a body edit — so re-query with `gh pr view` before "
                "editing anything (#331).",
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


def failure_summary(failures: list[Failure], pr: int) -> str:
    """The line printed under the defect list.

    Asserting "this is a bug in the PR, not in the check" is true of every
    defect here except one: `missing` is the only verdict the propagation lag
    can fabricate, and it is fabricated on a *correct* PR (#331). So a
    `missing`-only run hedges and hands over the command that settles it, and
    every other combination — including `missing` alongside a second defect,
    where the PR is broken whatever the API says — keeps the flat claim.
    """
    hedge = [f.check for f in failures] == ["missing"]
    verdict = (
        "the link may not have propagated yet. Re-query before editing: "
        f"`gh pr view {pr} --json closingIssuesReferences`"
        if hedge
        else "This is a bug in the PR, not in the check."
    )
    return f"check-pr-link: FAILED — {len(failures)} defect(s). {verdict}"


class Problem(Exception):
    """A refusal. Distinct from a failed check: this is the script being
    unable to answer, which must never be reported as a pass."""


#: Upper bound on a GitHub PR or issue number. Arbitrary but generous — this
#: repo is in the hundreds — and the point is the bound, not its exact value.
_MAX_GITHUB_NUMBER = 1_000_000


def require_github_number(kind: str, value: object) -> int:
    """Return `value` as a validated GitHub number, or raise `Problem`.

    The PR number is the ONLY value this script takes from the command line
    that reaches an OS command — it is the single non-literal element in the
    `gh` argv built below. `argparse(type=int)` already rejects non-numeric
    input, but that constrains the type and not the value, and a type
    constraint is not a validation: a negative number or an absurd one is a
    typo worth catching before it becomes a subprocess argument rather than
    after.

    Pure and importable, which is what makes it testable — unlike the
    subprocess calls it guards.
    """
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        raise Problem(f"{kind} {value!r} is not a number") from None
    if number <= 0 or number > _MAX_GITHUB_NUMBER:
        raise Problem(
            f"{kind} {number} is out of range — GitHub numbers are positive "
            f"and below {_MAX_GITHUB_NUMBER}. Refusing to pass it to `gh`."
        )
    return number


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


def _commit_texts(commits: list[dict]) -> dict[str, str]:
    """Every commit GitHub has recorded for the PR, labelled by short oid.

    Sourced from `gh pr view --json commits`, which returns exactly the set
    of commits that becomes the merge commit — no local `git` invocation, and
    no gap between what has been pushed and what this scans (#329). Each
    commit's headline and body are joined so a keyword in either is scanned;
    dropping the body would silently narrow the check.
    """
    out: dict[str, str] = {}
    for commit in commits:
        oid = commit["oid"][:7]
        headline = commit.get("messageHeadline") or ""
        body = commit.get("messageBody") or ""
        out[f"commit {oid}"] = f"{headline}\n{body}"
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

    try:
        expected = {require_github_number("issue number", n) for n in args.issues}
    except Problem as exc:
        print(f"check-pr-link: {exc}", file=sys.stderr)
        return 1

    try:
        pr_number = str(require_github_number("PR number", args.pr))
        pr_proc = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                pr_number,
                "--json",
                "baseRefName,headRefName,title,body,commits,closingIssuesReferences",
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
            **_commit_texts(pr["commits"]),
        }

        # The call above already read the field once, so only a retry goes back
        # to the network — and it re-reads nothing else, because the title, the
        # body and the commits cannot change between attempts.
        first_read = {r["number"] for r in pr["closingIssuesReferences"]}
        reads = 0

        def fetch_resolved() -> set[int]:
            nonlocal reads
            reads += 1
            if reads == 1:
                return first_read
            label = f"gh pr view {pr_number} --json closingIssuesReferences"
            proc = subprocess.run(
                ["gh", "pr", "view", pr_number, "--json", "closingIssuesReferences"],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            return {r["number"] for r in _parse_gh(proc, label)["closingIssuesReferences"]}

        resolved, attempts_used = resolve_closing_refs(fetch_resolved, expected)
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
    waited = f"; read the link {attempts_used}x" if attempts_used > 1 else ""
    print(
        f"check-pr-link: PR #{args.pr} should {claim}; "
        f"scanned {len(scanned)} text(s){waited}"
    )

    if failures:
        for f in failures:
            print(f"  [{f.check}] {f.detail}", file=sys.stderr)
        print(failure_summary(failures, args.pr), file=sys.stderr)
        return 1

    print("check-pr-link: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
