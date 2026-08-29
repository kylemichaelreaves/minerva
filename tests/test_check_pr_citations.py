"""Tests for the prose PR-citation gate (#335).

The gate exists because the population that decays is NOT the one #335 named.
Its four wrong numbers were all worked examples — `make check-pr-link PR=328` —
and worked examples are the self-correcting minority: you paste one, it fails,
you fix it. That is how three of those four were found.

The citations with no feedback path are the narrative ones. Sweeping every
`PR #N` in the repo found issue #297 cited as though it were a pull request,
live in `tests/test_check_pr_link.py` and in a design spec — both attributing
issues #297 and #300 to it, when PR #315 is the one that carried them. Nothing
would ever have run that sentence.

So this scans prose, not examples. A gate over the examples #335 proposed
gating would have passed on the day it was written.

Two fixture ranges, and the split is load-bearing. 999000+ is the repo's
established inert range, which this gate deliberately skips as fixtures — so
any test that must exercise the flagging path uses 998xxx instead: still far
beyond a real PR number here, but below the floor, and therefore checked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_pr_citations", REPO / "scripts" / "check_pr_citations.py"
)
assert _spec is not None
assert _spec.loader is not None
cpc = importlib.util.module_from_spec(_spec)
sys.modules["check_pr_citations"] = cpc
_spec.loader.exec_module(cpc)


def _citation(
    number: int, path: str = "docs/x.md", line: int = 1, kind: str = "pr"
) -> cpc.Citation:
    return cpc.Citation(path=path, line=line, number=number, kind=kind)


class TestScanPrCitations:
    def test_singular_citation(self):
        assert cpc.scan_pr_citations("landed as PR #999123, cleanly") == {999123}


class TestScanIssueCitations:
    """The mirror of `scan_pr_citations` (#337): a PR number standing in for
    the issue it closed is the same confusion in the other direction."""

    def test_singular_citation(self):
        assert cpc.scan_issue_citations("filed as Issue #999123, cleanly") == {999123}

    def test_plural_keyword(self):
        assert cpc.scan_issue_citations("Issues #999123 and #999124") == {999123}


class TestEvaluate:
    def test_number_that_is_not_a_pr_is_reported(self):
        failures = cpc.evaluate(
            citations=[_citation(998297)],
            real_prs={999315},
            exempt={},
        )

        assert [f.check for f in failures] == ["not-a-pr"]
        assert "998297" in failures[0].detail

    def test_citations_that_are_all_real_prs_pass(self):
        failures = cpc.evaluate(
            citations=[_citation(999315), _citation(999293)],
            real_prs={999315, 999293},
            exempt={},
        )

        assert failures == []


class TestEvaluateMirror:
    """The mirror direction (#337): a PR number cited as though it were an
    issue. Reuses `real_prs` rather than a separate issue-number fetch — a
    number cited as an issue is wrong precisely when it *is* a known PR."""

    def test_pr_number_cited_as_issue_is_reported(self):
        failures = cpc.evaluate(
            citations=[_citation(998315, kind="issue")],
            real_prs={998315},
            exempt={},
        )

        assert [f.check for f in failures] == ["not-an-issue"]
        assert "998315" in failures[0].detail

    def test_issue_citation_that_is_not_a_pr_passes(self):
        failures = cpc.evaluate(
            citations=[_citation(998182, kind="issue")],
            real_prs={998315},
            exempt={},
        )

        assert failures == []


class TestFixtureNumbers:
    """999000+ is this repo's established fixture range — `test_check_pr_link`
    uses it for the same reason — and no repo reaches it. Flagging fixtures
    would make every test file that documents its own numbering fail the gate,
    which is how #330's one-word filler earned its removal: a check that fires
    on the sanctioned form is one people learn to override.
    """

    def test_fixture_number_is_not_flagged(self):
        failures = cpc.evaluate(
            citations=[_citation(999297)],
            real_prs=set(),
            exempt={},
        )

        assert failures == []

    def test_a_real_looking_number_just_below_the_floor_is_still_checked(self):
        failures = cpc.evaluate(
            citations=[_citation(998999)],
            real_prs=set(),
            exempt={},
        )

        assert [f.check for f in failures] == ["not-a-pr"]


class TestExemptions:
    """The gate has to survive the sentence that describes the bug.

    `docs/backlog-closeout-plan.md` records that a row once cited issue #320 as
    the PR number when PR #323 is the one — a true sentence that necessarily
    contains the false citation it is reporting.
    Flagging it is how a gate teaches people to pass `--no-verify`, which is the
    corrosion #331 records. Backticks are not the discriminator: this repo
    established in #293 that formatting is no defence, so the exemption is an
    explicit, reasoned entry rather than an inference from punctuation.
    """

    def test_exempt_citation_is_not_flagged(self):
        failures = cpc.evaluate(
            citations=[_citation(999320, path="docs/plan.md")],
            real_prs=set(),
            exempt={("docs/plan.md", 999320): "the sentence describing the error"},
        )

        assert failures == []

    def test_exemption_for_a_citation_that_no_longer_exists_is_reported(self):
        """Same enforcement `granularity.known_coarse` gets: a baseline entry
        that has been fixed must be removed, or the baseline becomes a fossil
        nobody re-measures."""

        failures = cpc.evaluate(
            citations=[],
            real_prs=set(),
            exempt={("docs/gone.md", 999320): "no longer present"},
        )

        assert [f.check for f in failures] == ["stale-exemption"]
        assert "docs/gone.md" in failures[0].detail


class TestScanPaths:
    def test_citation_carries_its_line_and_repo_relative_path(self, tmp_path):
        doc = tmp_path / "docs" / "note.md"
        doc.parent.mkdir()
        doc.write_text("first\nsecond\nlanded as PR #999123 finally\n")

        cites = cpc.scan_paths([doc], root=tmp_path)

        assert cites == [cpc.Citation(path="docs/note.md", line=3, number=999123)]

    def test_a_file_citing_the_same_pr_twice_reports_both_lines(self, tmp_path):
        doc = tmp_path / "note.md"
        doc.write_text("PR #999123 did it\nand PR #999123 again\n")

        assert [c.line for c in cpc.scan_paths([doc], root=tmp_path)] == [1, 2]

    def test_pr_and_issue_citations_on_the_same_line_are_both_kept(self, tmp_path):
        doc = tmp_path / "note.md"
        doc.write_text("Issue #999124 was closed by PR #999123\n")

        cites = cpc.scan_paths([doc], root=tmp_path)

        assert sorted((c.kind, c.number) for c in cites) == [
            ("issue", 999124),
            ("pr", 999123),
        ]


class TestTrackedPaths:
    """#337: the gate's own globs missed `src/**`, `web/src/**`, `perseus/**`
    and `.github/**` — three live citations sat outside it, one more than the
    issue measured (a `PR #347` in `web/src/routes/ReaderRoute.tsx` landed
    after the issue was filed)."""

    def test_widened_globs_reach_previously_blind_trees(self, tmp_path):
        (tmp_path / "src" / "minerva").mkdir(parents=True)
        (tmp_path / "src" / "minerva" / "x.py").write_text("# PR #1\n")
        (tmp_path / "web" / "src").mkdir(parents=True)
        (tmp_path / "web" / "src" / "X.tsx").write_text("// PR #2\n")
        (tmp_path / "perseus").mkdir()
        (tmp_path / "perseus" / "x.py").write_text("# PR #3\n")
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "dependabot.yml").write_text("# PR #4\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "x.sh").write_text("# PR #5\n")

        found = {p.relative_to(tmp_path).as_posix() for p in cpc.tracked_paths(tmp_path)}

        assert "src/minerva/x.py" in found
        assert "web/src/X.tsx" in found
        assert "perseus/x.py" in found
        assert ".github/dependabot.yml" in found
        assert "scripts/x.sh" in found


class _FakeGitHub:
    """A `GitHubReader` that counts its calls.

    #334's lesson, one file over: the seam exists so the real caller is
    watched. Mutating `run` to skip the network entirely must break a test, not
    merely go unnoticed.
    """

    def __init__(self, numbers: set[int]):
        self._numbers = numbers
        self.calls = 0

    def merged_pr_numbers(self) -> set[int]:
        self.calls += 1
        return self._numbers


class TestRun:
    def test_clean_tree_exits_zero_after_one_query(self, tmp_path, capsys):
        (tmp_path / "note.md").write_text("landed as PR #999315\n")
        github = _FakeGitHub({999315})

        code = cpc.run(github=github, root=tmp_path, paths=[tmp_path / "note.md"], exempt={})

        assert code == 0
        assert github.calls == 1
        assert "ok" in capsys.readouterr().out

    def test_bad_citation_exits_one_and_names_the_line(self, tmp_path, capsys):
        (tmp_path / "note.md").write_text("x\nPR #998297 carried it\n")
        github = _FakeGitHub({999315})

        code = cpc.run(github=github, root=tmp_path, paths=[tmp_path / "note.md"], exempt={})

        assert code == 1
        assert "note.md:2" in capsys.readouterr().err

    def test_a_reader_that_cannot_answer_fails_rather_than_passing(self, tmp_path, capsys):
        """ "No data" must never read as "nothing wrong" (#116). An empty PR set
        would otherwise call every citation in the repo a defect, or — worse, if
        the comparison were inverted — call none of them one."""

        class _Broken:
            def merged_pr_numbers(self) -> set[int]:
                raise cpc.Problem("`gh pr list ...` failed: not authenticated")

        (tmp_path / "note.md").write_text("landed as PR #999315\n")

        code = cpc.run(github=_Broken(), root=tmp_path, paths=[tmp_path / "note.md"], exempt={})

        assert code == 1
        assert "not authenticated" in capsys.readouterr().err
