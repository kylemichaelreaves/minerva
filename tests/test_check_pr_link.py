"""Tests for the PR-to-issue link gate (#321).

The gate exists because three documented failure modes are all silent: a
stacked PR registers no link however many closing lines it carries, retargeting
to main does not backfill, and a closing keyword merely *discussed* in prose
still fires. The third one shut #176 three minutes after the same paragraph
said it must stay open.

The measurement that shaped this file: PR #293's `closingIssuesReferences` was
EMPTY and its merge commit closed #176 anyway. GitHub's PR-body parser exempted
a backticked reference and its commit-message parser did not, and on a squash
merge the body becomes the message. So a clean resolved-reference list is not
evidence of safety, and the scanner must not exempt backticks.

Fixture issue numbers are all 999000+. They are inert in a file — GitHub parses
commit messages and PR bodies, not tree contents — but live the moment anyone
pastes them into either.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_pr_link", REPO / "scripts" / "check_pr_link.py"
)
assert _spec is not None
assert _spec.loader is not None
cpl = importlib.util.module_from_spec(_spec)
sys.modules["check_pr_link"] = cpl
_spec.loader.exec_module(cpl)


class TestScanClosingRefs:
    def test_plain_keyword_and_number(self):
        assert cpl.scan_closing_refs("Closes #999001") == {999001}

    def test_backticks_are_not_an_escape(self):
        """The #293 shape, and the reason this function exists. GitHub's
        commit-message parser acted on exactly this text while the PR-body
        parser did not. A scanner that strips or skips code spans reintroduces
        the bug it was written to catch."""

        body = "part 2's PR is the one carrying `Closes #999001`."
        assert cpl.scan_closing_refs(body) == {999001}

    def test_is_case_insensitive(self):
        assert cpl.scan_closing_refs("CLOSES #999001") == {999001}
        assert cpl.scan_closing_refs("closed #999002") == {999002}

    def test_matches_every_keyword_github_acts_on(self):
        """GitHub's documented set, exactly. Getting this wrong in either
        direction is a defect: a missing keyword is a hole in the gate, an
        extra one is a false positive that trains people to ignore it."""

        for kw in (
            "close", "closes", "closed",
            "fix", "fixes", "fixed",
            "resolve", "resolves", "resolved",
        ):
            assert cpl.scan_closing_refs(f"{kw} #999001") == {999001}, kw

    def test_ignores_words_github_does_not_act_on(self):
        """`Refs` is the documented way to reference without closing, and
        `closing`/`fixing` are not in GitHub's set. Matching them would fail
        PRs that are correctly written."""

        assert cpl.scan_closing_refs("Refs #999001") == set()
        assert cpl.scan_closing_refs("See #999001") == set()
        assert cpl.scan_closing_refs("closing #999001") == set()
        assert cpl.scan_closing_refs("fixing #999001") == set()

    def test_finds_every_reference_not_just_the_first(self):
        text = "Closes #999001. Fixes #999002.\nresolved #999003"
        assert cpl.scan_closing_refs(text) == {999001, 999002, 999003}

    def test_requires_the_number_to_be_adjacent(self):
        """A keyword and a number in the same paragraph but not next to each
        other is ordinary prose. Flagging it would make the gate noise."""

        assert cpl.scan_closing_refs("This closes the loop. See #999001.") == set()

    def test_known_gap_an_intervening_word_is_not_matched(self):
        """DOCUMENTED LIMITATION, asserted so it is recorded rather than
        assumed. Whether GitHub itself acts on `closes issue #N` has not been
        verified against the API; if it does, this is a hole and widening the
        separator is the fix. Check 3 (`evaluate`, Task 2) is the backstop for
        anything GitHub actually resolves from the PR body — but NOT for a
        commit message, which is where the gap would bite."""

        assert cpl.scan_closing_refs("closes issue #999001") == set()
