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

import pytest

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
            "close",
            "closes",
            "closed",
            "fix",
            "fixes",
            "fixed",
            "resolve",
            "resolves",
            "resolved",
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


def _evaluate(**overrides):
    """A sound PR, with named overrides. Every test states only its defect."""
    kwargs = {
        "base_ref": "main",
        "default_branch": "main",
        "resolved": {999001},
        "expected": {999001},
        "scanned_text": {"PR body": "Closes #999001"},
    }
    kwargs.update(overrides)
    return cpl.evaluate(**kwargs)


class TestEvaluate:
    def test_a_sound_pr_produces_no_failures(self):
        assert _evaluate() == []

    def test_base_other_than_the_default_branch_fails(self):
        """A stacked PR registers nothing. This has to fail even when the body
        is perfect and `closingIssuesReferences` looks plausible, because the
        link is what does not exist."""

        failures = _evaluate(base_ref="feat/other", resolved=set())
        assert [f.check for f in failures] == ["base", "missing"]
        assert "feat/other" in failures[0].detail

    def test_an_expected_issue_that_did_not_register_fails(self):
        failures = _evaluate(resolved=set())
        assert [f.check for f in failures] == ["missing"]
        assert "999001" in failures[0].detail

    def test_multi_issue_pr_reports_only_the_dropped_number(self):
        """The case a single-issue check cannot see. PR #297 carried two
        issues; a batch PR silently dropping one is the failure this exists
        for."""

        failures = _evaluate(
            resolved={999001},
            expected={999001, 999002},
            scanned_text={"PR body": "Closes #999001. Closes #999002."},
        )
        assert [f.check for f in failures] == ["missing"]
        assert "999002" in failures[0].detail
        assert "[999002]" in failures[0].detail

    def test_an_issue_that_registered_but_was_not_claimed_fails(self):
        failures = _evaluate(resolved={999001, 999002})
        assert [f.check for f in failures] == ["unexpected"]
        assert "999002" in failures[0].detail

    def test_the_293_shape_a_backticked_keyword_with_an_empty_resolved_list(self):
        """THE headline case. PR #293 was doc-only, deliberately Refs-only, and
        its resolved list was correctly empty — and it still closed an open
        issue on merge. Checks 1-3 all pass here. Only the scan catches it, and
        a naive implementation ships without this test passing."""

        failures = _evaluate(
            resolved=set(),
            expected=set(),
            scanned_text={"PR body": "part 2's PR is the one carrying `Closes #999001`."},
        )
        assert [f.check for f in failures] == ["hazard"]
        assert "999001" in failures[0].detail
        assert "PR body" in failures[0].detail

    def test_a_hazard_in_a_commit_message_is_caught(self):
        """`closingIssuesReferences` is computed from the body and cannot see
        this at all."""

        failures = _evaluate(
            scanned_text={
                "PR body": "Closes #999001",
                "commit 4153e4c": "chore: mention `Fixes #999002` in passing",
            }
        )
        assert [f.check for f in failures] == ["hazard"]
        assert "999002" in failures[0].detail
        assert "commit 4153e4c" in failures[0].detail

    def test_the_prs_own_closing_lines_are_not_hazards(self):
        """The body of a correct PR is full of closing keywords next to the
        numbers it claims. Flagging those would make the gate unusable."""

        assert (
            _evaluate(
                resolved={999001, 999002},
                expected={999001, 999002},
                scanned_text={"PR body": "Closes #999001. Closes #999002."},
            )
            == []
        )

    def test_reports_every_independent_defect_at_once(self):
        """One run, one full list. Fixing them one CI round at a time is the
        cost this replaces."""

        failures = _evaluate(
            base_ref="feat/other",
            resolved={999003},
            expected={999001},
            scanned_text={"PR body": "Closes #999004"},
        )
        assert [f.check for f in failures] == [
            "base",
            "missing",
            "unexpected",
            "hazard",
        ]


class TestRequireSafeRef:
    """`require_safe_ref` guards `_commit_messages`'s two GitHub-supplied refs
    before they reach `git log` (#321, Sonar pythonsecurity:S8705). Pure logic,
    so it is tested directly rather than through the subprocess boundary."""

    def test_an_ordinary_branch_name_passes(self):
        assert cpl.require_safe_ref("head ref", "feat/321-close-out-command") is None

    def test_a_shell_metacharacter_is_rejected(self):
        with pytest.raises(cpl.Problem):
            cpl.require_safe_ref("head ref", "main; rm -rf /")

    def test_a_space_is_rejected(self):
        with pytest.raises(cpl.Problem):
            cpl.require_safe_ref("head ref", "main branch")

    def test_a_leading_dash_is_rejected(self):
        """The `git log` argv trap: a leading `-` reads as an option, not a
        ref — `--output=/tmp/x` would have git write a file."""

        with pytest.raises(cpl.Problem):
            cpl.require_safe_ref("base ref", "--output=/tmp/x")

    def test_an_empty_ref_is_rejected(self):
        with pytest.raises(cpl.Problem):
            cpl.require_safe_ref("base ref", "")

    def test_an_over_long_ref_is_rejected(self):
        with pytest.raises(cpl.Problem):
            cpl.require_safe_ref("head ref", "a" * 256)

    def test_the_message_names_the_kind_and_the_value(self):
        with pytest.raises(cpl.Problem, match=r"head ref.*main branch"):
            cpl.require_safe_ref("head ref", "main branch")
