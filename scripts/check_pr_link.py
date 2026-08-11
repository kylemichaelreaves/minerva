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

import re

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
