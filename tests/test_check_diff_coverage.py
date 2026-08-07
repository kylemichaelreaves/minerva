"""Tests for the changed-line coverage gate (#255).

The gate exists because a whole-project coverage number can be green while
SonarCloud's changed-line gate is red. Its own failure mode is worse than
that: every way this can go wrong — a missing report, an unresolvable base
ref, a path prefix that does not line up — produces "0 changed lines, all
covered, fine" from a naive implementation. An inert gate is worse than no
gate (#116), so most of what is under test here is that it *refuses*.

Both prefix traps below were hit for real while measuring by hand before the
script existed: Cobertura keys paths relative to its `<source>` and lcov keys
them relative to `web/`, and neither matches git's repo-relative paths.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_diff_coverage", REPO / "scripts" / "check_diff_coverage.py"
)
assert _spec and _spec.loader
cdc = importlib.util.module_from_spec(_spec)
sys.modules["check_diff_coverage"] = cdc
_spec.loader.exec_module(cdc)


def write_xml(path: Path, *, source: str, filename: str, lines: str) -> None:
    path.write_text(
        f"""<?xml version="1.0" ?>
<coverage><sources><source>{source}</source></sources>
<packages><package><classes>
<class filename="{filename}"><lines>{lines}</lines></class>
</classes></package></packages></coverage>
"""
    )


class TestPythonReader:
    def test_keys_paths_by_the_source_prefix_not_a_hard_coded_one(self, tmp_path):
        """The `<source>` element is what makes `cli/x.py` into
        `src/minerva/cli/x.py`. Assuming the prefix would silently yield zero
        changed lines the day the source root moved."""

        xml = tmp_path / "coverage.xml"
        write_xml(
            xml,
            source=str(REPO / "src" / "minerva"),
            filename="cli/stats_cmd.py",
            lines='<line number="13" hits="1"/><line number="14" hits="0"/>',
        )

        out = cdc.read_python_xml(xml)

        assert "src/minerva/cli/stats_cmd.py" in out
        assert out["src/minerva/cli/stats_cmd.py"][13][0] == 1
        assert out["src/minerva/cli/stats_cmd.py"][14][0] == 0

    def test_carries_condition_coverage_through(self, tmp_path):
        """Sonar counts branches. A statements-only reading called a 3/4 guard
        green on #250."""

        xml = tmp_path / "coverage.xml"
        write_xml(
            xml,
            source=str(REPO / "src" / "minerva"),
            filename="tei.py",
            lines='<line number="504" hits="3" condition-coverage="50% (1/2)"/>',
        )

        _hits, cond = cdc.read_python_xml(xml)["src/minerva/tei.py"][504]
        assert cond == "50% (1/2)"

    def test_a_missing_report_is_an_error_not_an_empty_pass(self, tmp_path):
        with pytest.raises(cdc.Problem, match="no Python coverage"):
            cdc.read_python_xml(tmp_path / "absent.xml")

    def test_a_report_with_no_files_is_an_error(self, tmp_path):
        xml = tmp_path / "coverage.xml"
        xml.write_text('<?xml version="1.0" ?><coverage><sources/><packages/></coverage>')
        with pytest.raises(cdc.Problem, match="no measured files"):
            cdc.read_python_xml(xml)


class TestWebReader:
    def test_prefixes_relative_sf_paths_with_web(self, tmp_path):
        """lcov writes `SF:src/Syntax/x.tsx`; git calls it
        `web/src/Syntax/x.tsx`."""

        lcov = tmp_path / "lcov.info"
        lcov.write_text("TN:\nSF:src/Syntax/index.tsx\nDA:10,1\nDA:11,0\nend_of_record\n")

        out = cdc.read_web_lcov(lcov)

        assert "web/src/Syntax/index.tsx" in out
        assert out["web/src/Syntax/index.tsx"][11][0] == 0

    def test_folds_brda_records_into_condition_coverage(self, tmp_path):
        lcov = tmp_path / "lcov.info"
        lcov.write_text(
            "TN:\nSF:src/x.ts\nDA:5,2\n"
            "BRDA:5,0,0,2\nBRDA:5,0,1,-\n"
            "end_of_record\n"
        )

        _hits, cond = cdc.read_web_lcov(lcov)["web/src/x.ts"][5]
        assert cond == "50% (1/2)"

    def test_a_missing_report_is_an_error(self, tmp_path):
        with pytest.raises(cdc.Problem, match="no web coverage"):
            cdc.read_web_lcov(tmp_path / "absent.info")


#: hits + condition-coverage per line, as the readers return them.
_COV: dict[str, dict[int, tuple[int, str | None]]] = {
    "src/minerva/a.py": {
        1: (1, None),
        2: (0, None),
        3: (5, "50% (1/2)"),
        4: (2, "100% (2/2)"),
    }
}


class TestTally:
    COV = _COV

    def test_counts_only_lines_coverage_measured(self):
        # Line 99 is a comment: absent from the report, and not held to the bar.
        t = cdc.tally({"src/minerva/a.py": [1, 2, 99]}, self.COV)["src/minerva/a.py"]

        assert (t.lines_covered, t.lines_total) == (1, 2)
        assert t.uncovered_lines == [2]

    def test_counts_branches_as_well_as_statements(self):
        t = cdc.tally({"src/minerva/a.py": [3]}, self.COV)["src/minerva/a.py"]

        # One covered statement plus one of two conditions.
        assert (t.covered, t.total) == (2, 3)
        assert t.percent == pytest.approx(200 / 3)
        assert t.partial_branches == [(3, 1, 2)]

    def test_a_fully_covered_line_with_both_branches_is_three_of_three(self):
        t = cdc.tally({"src/minerva/a.py": [4]}, self.COV)["src/minerva/a.py"]
        assert (t.covered, t.total) == (3, 3)
        assert t.percent == 100.0

    def test_a_file_absent_from_coverage_is_skipped_not_counted_as_zero(self):
        """A `.md` or a coverage-omitted migration must not drag the number
        down — but it must not be silently counted as covered either."""

        assert cdc.tally({"src/minerva/migrations/0026_x.py": [1, 2]}, self.COV) == {}


class TestChangedLines:
    def test_an_unresolvable_base_ref_is_an_error(self):
        with pytest.raises(cdc.Problem, match="does not resolve"):
            cdc.changed_lines("no/such/ref/at/all")


class TestGatedPrefixes:
    def test_holds_src_and_web_src_to_the_bar(self):
        assert cdc.GATED_PREFIXES == ("src/minerva/", "web/src/")

    def test_excludes_the_trees_sonar_excludes(self):
        # `scripts/**` and `perseus/**` are in sonar.coverage.exclusions, so a
        # diff touching only those must not be gated.
        for excluded in ("scripts/", "perseus/", "tests/", "web/tests/"):
            assert not any(excluded.startswith(p) for p in cdc.GATED_PREFIXES), excluded
