#!/usr/bin/env python3
"""Verify every `PR #N` this repo cites in prose is actually a PR (#335).

WHY PROSE AND NOT THE WORKED EXAMPLES

#335 was filed about worked examples — `make check-pr-link PR=328` and friends,
four of them wrong across two files. Gating those was the obvious fix and is the
wrong one: sweeping the repo showed all four runnable examples already correct,
because an example is self-correcting. You paste it, it fails, you fix it. Three
of the original four were found exactly that way.

The same sweep found `PR #297` in a test docstring and in a design spec, both
attributing issues #297 and #300 to it — when #297 is an issue and PR #315 is
the PR. A sentence is never executed, so nothing was ever going to catch it. A
gate over the examples would have passed on the day it was written.

WHY IT REFUSES RATHER THAN REPORTING ZERO

`gh` returning nothing is not the same as the repo having no PRs, and an empty
set would silently call every citation in the tree a defect. Every "no data"
path raises instead, because an inert gate is worse than no gate (#116).

WHY EXEMPTIONS ARE ENTRIES AND NOT A PATTERN

A sentence *reporting* a wrong citation has to contain one. The discriminator
cannot be backticks — #293 settled that formatting is no defence — so it is a
hand-written entry with a reason, and a fixed one must be removed. Same division
of labour as `granularity.known_coarse`: policy hand-edited, measurement
generated (#176).

Usage:
    scripts/check_pr_citations.py     # or: make check-pr-citations
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REPO = Path(__file__).resolve().parent.parent

#: `PR #N` or `PRs #N`, the form this repo uses to attribute work to a PR.
_PR_CITATION = re.compile(r"\bPRs?\s+#(\d+)")


def scan_pr_citations(text: str) -> set[int]:
    """Every number `text` attributes to a pull request."""
    return {int(m.group(1)) for m in _PR_CITATION.finditer(text)}


@dataclass(frozen=True)
class Citation:
    """One `PR #N` occurrence, located well enough to fix without searching."""

    path: str
    line: int
    number: int


def scan_paths(paths: list[Path], *, root: Path) -> list[Citation]:
    """Every `PR #N` in `paths`, located by repo-relative path and line.

    Line-by-line rather than whole-file, because the only useful thing a gate
    over prose can say is *which sentence* — a bare number sends the reader
    grepping for a form that appears dozens of times legitimately.
    """
    cites: list[Citation] = []
    for path in sorted(paths):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            cites.extend(
                Citation(path=rel, line=lineno, number=n)
                for n in sorted(scan_pr_citations(line))
            )
    return cites


@dataclass(frozen=True)
class Failure:
    """One independent defect. `check` is a stable slug for tests and hooks;
    `detail` is what a human needs in order to fix it."""

    check: str
    detail: str


#: Numbers at or above this are test fixtures, not claims about the repo. The
#: convention predates this gate — `tests/test_check_pr_link.py` says so in its
#: own docstring — and no repo reaches seven figures of PRs. Checking them would
#: fail every test file that documents its numbering, which is the sanctioned
#: form, and a gate that fires on the sanctioned form gets overridden (#330).
_FIXTURE_FLOOR = 999_000


#: Citations that name a non-PR *on purpose*, because the sentence is about the
#: wrong number rather than relying on it. Hand-maintained policy, never
#: generated — the same division that keeps `granularity.known_coarse` from
#: blessing its own violations (#176). Removing a fixed entry is enforced.
#:
#: Backticks are not the discriminator and must not become one: #293 established
#: that formatting is no defence, so an exemption is an argued entry with a
#: reason attached, not something a writer can obtain by quoting.
_EXEMPT: dict[tuple[str, int], str] = {
    ("docs/backlog-closeout-plan.md", 320): (
        "8-ter's own account of the defect. The sentence reports that a row cited "
        "issue #320 where PR #323 was meant, so it has to contain the wrong "
        "citation in order to describe it. Rewriting the narrative to satisfy the "
        "gate would destroy the record; this is what the escape hatch is for "
        "(#335)."
    ),
}


def evaluate(
    *,
    citations: list[Citation],
    real_prs: set[int],
    exempt: dict[tuple[str, int], str],
) -> list[Failure]:
    """Every citation that names a number GitHub does not know as a PR."""
    failures: list[Failure] = []

    for cite in citations:
        if (
            cite.number >= _FIXTURE_FLOOR
            or cite.number in real_prs
            or (cite.path, cite.number) in exempt
        ):
            continue
        failures.append(
            Failure(
                "not-a-pr",
                f"{cite.path}:{cite.line} cites `PR #{cite.number}`, which is not a "
                "pull request in this repo. The usual cause is an issue number "
                "standing in for the PR that closed it — check with "
                f"`gh issue view {cite.number}` and cite the PR instead. If the "
                "sentence is *about* a wrong number rather than using one, exempt "
                "it in `_EXEMPT` with a reason.",
            )
        )

    present = {(c.path, c.number) for c in citations}
    for path, number in sorted(exempt.keys() - present):
        failures.append(
            Failure(
                "stale-exemption",
                f"`_EXEMPT` excuses `PR #{number}` in {path}, which no longer cites "
                "it. An excused violation that has been fixed must lose its entry, "
                "or the baseline stops describing the repo and starts describing "
                "its own history — the enforcement `granularity.known_coarse` gets "
                "for the same reason (#176).",
            )
        )

    return failures


class Problem(Exception):
    """A refusal. Distinct from a failed check: this is the script being unable
    to answer, which must never be reported as a pass (#116)."""


class GitHubReader(Protocol):
    """The one read this check needs, and the seam that makes it testable."""

    def merged_pr_numbers(self) -> set[int]: ...


class GitHubCLI:
    """`GitHubReader` over the real `gh`.

    One list call, not one lookup per citation. The repo cites a couple of dozen
    distinct PR numbers and holds ~200 PRs, so asking for the whole set once is
    both fewer round trips and a stabler thing to assert against — a per-number
    `gh pr view` reports "not a PR" identically for a number that is an issue
    and for a network blip, which is the inert-gate failure of #116.
    """

    def merged_pr_numbers(self) -> set[int]:
        proc = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", "1000", "--json", "number"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        label = "gh pr list --state all --limit 1000 --json number"
        if proc.returncode != 0:
            raise Problem(f"`{label}` failed: {proc.stderr.strip()}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise Problem(f"`{label}` returned non-JSON: {exc}") from None
        numbers = {int(row["number"]) for row in payload}
        if not numbers:
            raise Problem(
                f"`{label}` returned no pull requests. Refusing to call every "
                "citation in the repo wrong on the strength of an empty answer."
            )
        return numbers


def run(
    *,
    github: GitHubReader,
    root: Path,
    paths: list[Path],
    exempt: dict[tuple[str, int], str] | None = None,
) -> int:
    """The whole check, minus argument parsing. Returns the process exit code."""
    citations = scan_paths(paths, root=root)
    try:
        real_prs = github.merged_pr_numbers()
    except Problem as exc:
        print(f"check-pr-citations: {exc}", file=sys.stderr)
        return 1

    failures = evaluate(
        citations=citations,
        real_prs=real_prs,
        exempt=exempt if exempt is not None else _EXEMPT,
    )

    print(
        f"check-pr-citations: {len(citations)} citation(s) across "
        f"{len(paths)} file(s), against {len(real_prs)} known PR(s)"
    )

    if failures:
        for f in failures:
            print(f"  [{f.check}] {f.detail}", file=sys.stderr)
        print(
            f"check-pr-citations: FAILED — {len(failures)} defect(s). "
            "This is a bug in the prose, not in the check.",
            file=sys.stderr,
        )
        return 1

    print("check-pr-citations: ok")
    return 0


#: Files whose prose attributes work to a PR. Deliberately not the whole tree:
#: this scans what a reader is expected to trust, which is documentation, the
#: gate scripts, and the comments in the tests that justify them.
_SCANNED_GLOBS = ("docs/**/*.md", "*.md", "scripts/*.py", "tests/*.py", ".claude/**/*.md")


def tracked_paths(root: Path) -> list[Path]:
    """Every file the citation gate reads, deduplicated and ordered."""
    found: set[Path] = set()
    for glob in _SCANNED_GLOBS:
        found.update(p for p in root.glob(glob) if p.is_file())
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify every `PR #N` cited in this repo's prose is really a PR."
    )
    ap.parse_args()
    return run(github=GitHubCLI(), root=REPO, paths=tracked_paths(REPO))


if __name__ == "__main__":
    sys.exit(main())
