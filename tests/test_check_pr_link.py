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

    def test_a_repo_qualified_reference_is_matched(self):
        """`KEYWORD OWNER/REPOSITORY#N` is documented closing syntax — the
        second row of GitHub's own syntax table, and `Fixes
        octo-org/octo-repo#100` is their worked example. The original separator
        class could not match it: `[^A-Za-z]{0,3}` is what makes the scan
        backtick-blind, and stopping at any letter is the same property that
        made it stop at the `o` of `octo-org` (#330)."""

        assert cpl.scan_closing_refs("Fixes octo-org/octo-repo#100") == {100}

    def test_an_intervening_word_is_not_matched_and_this_was_measured(self):
        """#330 asks whether the separator should admit a filler word, so that
        `closes issue #N` matches. MEASURED, and the answer is no.

        The argument for admitting it is that this scan feeds the `hazard` check
        and nothing else, so over-matching costs a rewritten sentence while
        under-matching is #176. That is sound and still incomplete: it never
        prices the over-matching. Priced against every PR text in the repo — 760
        titles, bodies and commit messages across 194 PRs — a one-word filler
        matches 6 texts the shipped scanner does not, and all 6 are false
        positives, while `closes issue #N` occurs zero times.

        Two of the six shapes are endemic here, which is what settles it:

            "Both defects are now fixed.\\n\\nRefs #N"   -> matches
            "point the prose sources at /close-out (#N)" -> matches

        The first breaks `Refs #N`, the documented way to reference an issue
        WITHOUT closing it, whenever the preceding sentence ends in a keyword.
        The second fires on this repo's own command name. A gate that flags the
        sanctioned form teaches people to override it, which is the same
        corrosion #331 is about.

        Whether GitHub's parser acts on `closes issue #N` remains unmeasured and
        is now beside the point: the scan declines the form because matching it
        costs more here than the form is worth, not because GitHub ignores it."""

        assert cpl.scan_closing_refs("closes issue #999001") == set()
        assert cpl.scan_closing_refs("Both defects are now fixed.\n\nRefs #999001") == set()
        assert cpl.scan_closing_refs("point the prose sources at /close-out (#999001)") == set()
        assert cpl.scan_closing_refs("`lemmatize.py` all close correctly. #999001") == set()

    def test_the_documented_syntax_forms_github_acts_on(self):
        """GitHub's documented closing syntax, matched form by form, replacing
        an earlier docstring that recorded the question as open (#330).

        Measured 2026-08-11 against both doc pages. "Linking a pull request to
        an issue" gives the syntax table; "Using keywords in issues and pull
        requests" gives the worked cross-repo example. Neither documents a
        full-URL form, and neither documents a filler word — the form above is
        matched on the asymmetry argument, not on evidence GitHub acts on it."""

        assert cpl.scan_closing_refs("Closes #999001") == {999001}
        assert cpl.scan_closing_refs("Closes: #999001") == {999001}
        assert cpl.scan_closing_refs("CLOSES: #999001") == {999001}
        assert cpl.scan_closing_refs("Fixes octo-org/octo-repo#100") == {100}
        assert cpl.scan_closing_refs(
            "Fixes kylemichaelreaves/minerva#999001"
        ) == {999001}


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

    def test_the_missing_detail_names_the_lag_and_the_requery(self):
        """A `missing` result has two causes with opposite fixes — a body that
        lacks the keyword, and a body that has it that the API has not caught up
        with (#331). The detail has to name the second and hand over the command
        that settles which one it is."""

        failures = _evaluate(resolved=set())
        assert [f.check for f in failures] == ["missing"]
        assert "eventually consistent" in failures[0].detail
        assert "gh pr view" in failures[0].detail

    def test_multi_issue_pr_reports_only_the_dropped_number(self):
        """The case a single-issue check cannot see. PR #315 carried two
        issues, #297 and #300; a batch PR silently dropping one is the failure
        this exists for."""

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


class TestResolveClosingRefs:
    """`closingIssuesReferences` is eventually consistent after a body edit, so
    reading it once and reporting `[missing]` is a false failure on a correct
    PR (#331). Measured on PR #328: the check failed immediately after
    `gh pr edit` installed a body whose first line carried the keyword, and
    seconds later, with nothing changed, the API resolved the link.

    A false failure is less dangerous than the false pass of #329, but it is
    corrosive in its own way — the gate's message asserts the PR is broken, and
    a gate that cries wolf teaches people to override it.

    `sleep` and `fetch` are injected so these run in no time and assert on real
    behaviour rather than on a mock's call log."""

    @staticmethod
    def _fetch_returning(*results):
        """A fetch that yields each result in turn, recording its calls."""
        calls: list[int] = []

        def fetch() -> set[int]:
            calls.append(len(calls))
            return results[min(len(calls) - 1, len(results) - 1)]

        return fetch, calls

    def test_retries_until_the_link_appears(self):
        """The #331 shape. The first read is empty and the second is not, with
        nothing edited in between."""

        fetch, calls = self._fetch_returning(set(), {999001})
        slept: list[float] = []

        resolved, attempts = cpl.resolve_closing_refs(
            fetch, {999001}, sleep=slept.append
        )

        assert resolved == {999001}
        assert attempts == 2
        assert len(calls) == 2
        assert len(slept) == 1

    def test_a_link_already_registered_costs_no_wait(self):
        """The overwhelmingly common case, and the one that must not get
        slower. Every green run of this gate goes through here."""

        fetch, calls = self._fetch_returning({999001})
        slept: list[float] = []

        resolved, attempts = cpl.resolve_closing_refs(
            fetch, {999001}, sleep=slept.append
        )

        assert (resolved, attempts) == ({999001}, 1)
        assert len(calls) == 1
        assert slept == []

    def test_a_genuinely_missing_link_gives_up_and_reports_it(self):
        """The retry must not turn a real defect into a hang or a pass. Three
        reads, two waits, and the empty answer is still returned."""

        fetch, calls = self._fetch_returning(set())
        slept: list[float] = []

        resolved, attempts = cpl.resolve_closing_refs(
            fetch, {999001}, attempts=3, sleep=slept.append
        )

        assert (resolved, attempts) == (set(), 3)
        assert len(calls) == 3
        assert len(slept) == 2

    def test_a_pr_that_claims_nothing_is_not_waited_on(self):
        """A `Refs`-only PR expects no link, so there is no lag to outwait.
        Sleeping here would tax every doc-only round for nothing."""

        fetch, calls = self._fetch_returning(set())
        slept: list[float] = []

        assert cpl.resolve_closing_refs(fetch, set(), sleep=slept.append) == (set(), 1)
        assert len(calls) == 1
        assert slept == []

    def test_an_unexpected_link_is_not_retried(self):
        """Deliberately narrow. An `unexpected` link is already registered and
        will not un-register, so re-reading cannot change the answer — it would
        only spend seconds before reporting the same real defect."""

        fetch, calls = self._fetch_returning({999001, 999002})
        slept: list[float] = []

        resolved, attempts = cpl.resolve_closing_refs(
            fetch, {999001}, sleep=slept.append
        )

        assert (resolved, attempts) == ({999001, 999002}, 1)
        assert len(calls) == 1
        assert slept == []

    def test_the_delay_is_passed_through_to_sleep(self):
        """The wait has to actually be the configured one. A hard-coded sleep
        would pass every other test in this class."""

        fetch, _ = self._fetch_returning(set())
        slept: list[float] = []

        cpl.resolve_closing_refs(
            fetch, {999001}, attempts=2, delay=0.25, sleep=slept.append
        )

        assert slept == [0.25]


class TestFailureSummary:
    """The line printed under the defect list. It used to assert flatly that
    "This is a bug in the PR, not in the check" — true for every defect except
    the one the propagation lag can fabricate, and a gate that says that while
    crying wolf teaches people to override it, which is how #158's required
    check stops meaning anything (#331)."""

    def test_a_missing_only_failure_does_not_assert_the_pr_is_broken(self):
        summary = cpl.failure_summary([cpl.Failure("missing", "d")], 328)
        assert "not in the check" not in summary
        assert "gh pr view 328" in summary

    def test_any_other_defect_still_asserts_the_pr_is_broken(self):
        """The softening is scoped to `missing`. A `hazard` is read from text
        that does not change between reads, so hedging it would be a lie."""

        summary = cpl.failure_summary([cpl.Failure("hazard", "d")], 328)
        assert "not in the check" in summary

    def test_missing_alongside_another_defect_is_not_softened(self):
        """If anything else is wrong, the PR is broken regardless of whether the
        link has propagated, and the run should say so."""

        summary = cpl.failure_summary(
            [cpl.Failure("base", "d"), cpl.Failure("missing", "d")], 328
        )
        assert "not in the check" in summary

    def test_the_defect_count_is_reported(self):
        summary = cpl.failure_summary(
            [cpl.Failure("base", "d"), cpl.Failure("hazard", "d")], 328
        )
        assert "2 defect(s)" in summary


class TestRequireGithubNumber:
    """The PR number is the only command-line value that reaches an OS command
    — the single non-literal element in the `gh` argv. `argparse(type=int)`
    constrains its type; these tests cover constraining its value."""

    def test_an_ordinary_number_passes_through(self):
        assert cpl.require_github_number("PR number", 328) == 328

    def test_a_numeric_string_is_normalised_to_int(self):
        assert cpl.require_github_number("PR number", "328") == 328

    def test_zero_and_negatives_are_rejected(self):
        for bad in (0, -1, -328):
            with pytest.raises(cpl.Problem):
                cpl.require_github_number("PR number", bad)

    def test_an_absurd_number_is_rejected(self):
        with pytest.raises(cpl.Problem):
            cpl.require_github_number("PR number", 10_000_000)

    def test_a_non_number_is_rejected(self):
        for bad in ("not-a-number", None, "12; rm -rf /"):
            with pytest.raises(cpl.Problem):
                cpl.require_github_number("PR number", bad)

    def test_the_message_names_the_kind_and_the_value(self):
        with pytest.raises(cpl.Problem) as exc:
            cpl.require_github_number("issue number", -5)
        assert "issue number" in str(exc.value)
        assert "-5" in str(exc.value)


class TestCommitTexts:
    """`_commit_texts` is what makes the hazard scan see commit messages at
    all. Its failure mode is silent: a wrong key or a dropped body narrows the
    check without changing any visible behaviour."""

    def test_labels_each_commit_by_short_oid(self):
        out = cpl._commit_texts([{"oid": "0123456789abcdef", "messageHeadline": "x"}])
        assert list(out) == ["commit 0123456"]

    def test_scans_the_body_as_well_as_the_headline(self):
        """The one that matters. A closing keyword lives in a commit *body*
        far more often than in its subject line, so dropping the body would
        quietly halve the check's reach."""

        out = cpl._commit_texts(
            [
                {
                    "oid": "abcdef1234",
                    "messageHeadline": "chore: something",
                    "messageBody": "incidentally mentions `Closes #999001`",
                }
            ]
        )
        assert cpl.scan_closing_refs(out["commit abcdef1"]) == {999001}

    def test_a_missing_or_null_body_is_not_an_error(self):
        """`gh` omits messageBody for a single-line commit, and returns null
        for some. Either must not crash the run."""

        out = cpl._commit_texts(
            [
                {"oid": "aaaaaaa1", "messageHeadline": "no body key"},
                {"oid": "bbbbbbb2", "messageHeadline": "null body", "messageBody": None},
            ]
        )
        assert out["commit aaaaaaa"] == "no body key\n"
        assert out["commit bbbbbbb"] == "null body\n"

    def test_no_commits_yields_no_texts(self):
        assert cpl._commit_texts([]) == {}


class FakeGitHub:
    """A stand-in for the two `gh` reads, recording what was asked of it.

    `later_refs` is what a *re-read* returns, which is the whole point: the real
    reader answers the first attempt from the value the big `pull_request` call
    already carried, and only a retry goes to the network. A fake that cannot
    tell those apart could not catch the branch this class exists to test.
    """

    def __init__(self, *, pr, default_branch="main", later_refs=None):
        self._pr = pr
        self._default_branch = default_branch
        self._later_refs = later_refs if later_refs is not None else set()
        self.calls: list[str] = []

    def pull_request(self, pr_number):
        self.calls.append(f"pull_request({pr_number})")
        if isinstance(self._pr, Exception):
            raise self._pr
        return self._pr

    def closing_refs(self, pr_number):
        self.calls.append(f"closing_refs({pr_number})")
        return self._later_refs

    def default_branch(self):
        self.calls.append("default_branch()")
        if isinstance(self._default_branch, Exception):
            raise self._default_branch
        return self._default_branch


def _pr_payload(*, body="Closes #999001", resolved=(999001,), base="main", commits=()):
    """The shape `gh pr view --json ...` returns, with only what `run` reads."""
    return {
        "baseRefName": base,
        "title": "fix: something",
        "body": body,
        "commits": list(commits),
        "closingIssuesReferences": [{"number": n} for n in resolved],
    }


class TestRun:
    """`run` is `main()` without the argument parsing — the seam #334 asked for.

    Before it existed, nothing tested any of this: not the cache-then-network
    branch in the retry, not the refusal paths, not `default_branch`. The gap was
    demonstrated rather than argued — mutating that branch to return the cached
    value on every call left all 40 tests passing while the live run printed
    `read the link 3x` having issued exactly one query.
    """

    def test_the_second_attempt_performs_a_real_read(self):
        """THE test #334 exists for. The first attempt is answered from the
        payload already fetched; the link is absent there and present on a
        re-read, which is the #331 lag. If a retry ever stopped going to the
        network, this is the only assertion that would notice."""

        gh = FakeGitHub(pr=_pr_payload(resolved=()), later_refs={999001})

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        assert code == 0
        assert gh.calls == [
            "pull_request(332)",
            "default_branch()",
            "closing_refs(332)",
        ]

    def test_a_retry_is_announced_in_the_summary(self, capsys):
        """A run that waited must say so. Silence here is the shape of the
        mutation that made the retry inert while still looking like it ran."""

        gh = FakeGitHub(pr=_pr_payload(resolved=()), later_refs={999001})

        cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        assert "read the link 2x" in capsys.readouterr().out

    def test_a_sound_pr_never_goes_back_to_the_network(self, capsys):
        """The common case. The link is already in the payload, so the narrow
        read must not happen at all — every green run of this gate is this
        path, and a wasted round-trip here is paid on every PR."""

        gh = FakeGitHub(pr=_pr_payload())

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        assert code == 0
        assert "closing_refs(332)" not in gh.calls
        out = capsys.readouterr().out
        assert "check-pr-link: ok" in out
        assert "read the link" not in out

    def test_a_read_that_cannot_answer_is_a_refusal_not_a_pass(self, capsys):
        """The #116 rule at the seam. A `gh` that fails must exit non-zero with
        its own message, and must NOT be reported as a defect count — a refusal
        is the check being unable to answer, not the PR being wrong."""

        gh = FakeGitHub(pr=cpl.Problem("`gh pr view 332 --json ...` failed: boom"))

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        captured = capsys.readouterr()
        assert code == 1
        assert "boom" in captured.err
        assert "defect(s)" not in captured.err
        assert "check-pr-link: ok" not in captured.out

    def test_a_failure_to_resolve_the_default_branch_is_a_refusal(self, capsys):
        """The second read has the same rule as the first. Its own docstring
        calls a repo whose default branch cannot be resolved a "no data" path
        that must never read as fine."""

        gh = FakeGitHub(
            pr=_pr_payload(), default_branch=cpl.Problem("gh repo view failed: nope")
        )

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        assert code == 1
        assert "nope" in capsys.readouterr().err

    def test_the_default_branch_comes_from_the_reader_not_a_literal(self, capsys):
        """A hard-coded `"main"` would pass every other test in this class. Here
        the repo's default branch is `trunk`, so a PR based on `main` is the
        stacked-PR defect and must be reported as one."""

        gh = FakeGitHub(pr=_pr_payload(base="main"), default_branch="trunk")

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        captured = capsys.readouterr()
        assert code == 1
        assert "[base]" in captured.err
        assert "trunk" in captured.err

    def test_a_malformed_payload_is_a_refusal_not_a_crash(self, capsys):
        """The `KeyError` arm of `run`'s handler. Unreachable via a `--json`
        typo — `gh` rejects an unknown field outright, which is the claim in
        #334 that turned out to be false — so this covers the case it IS
        insurance against: the API returning a shape the code does not expect."""

        gh = FakeGitHub(pr={"title": "no other keys"})

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        assert code == 1
        assert "check-pr-link:" in capsys.readouterr().err

    def test_an_out_of_range_pr_number_never_reaches_github(self, capsys):
        """`require_github_number` guards the only command-line value that
        becomes a subprocess argument, so it has to run before any read."""

        gh = FakeGitHub(pr=_pr_payload())

        code = cpl.run(pr=-1, issues=[], github=gh, sleep=lambda _: None)

        assert code == 1
        assert gh.calls == []
        assert "out of range" in capsys.readouterr().err

    def test_a_hazard_in_a_commit_message_reaches_the_report(self, capsys):
        """End-to-end wiring of `_commit_texts` through `evaluate`. The unit
        tests cover each half; this covers that `run` actually joins them, which
        is where the #293 shape would go unnoticed."""

        gh = FakeGitHub(
            pr=_pr_payload(
                commits=[
                    {
                        "oid": "abcdef1234",
                        "messageHeadline": "docs: something",
                        "messageBody": "mentions `Closes #999002` in passing",
                    }
                ]
            )
        )

        code = cpl.run(pr=332, issues=[999001], github=gh, sleep=lambda _: None)

        captured = capsys.readouterr()
        assert code == 1
        assert "[hazard]" in captured.err
        assert "commit abcdef1" in captured.err
