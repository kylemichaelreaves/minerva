"""Tests for `scripts/check_format_baseline.py` (#483, #136).

The gate is baseline-pinned, the same shape as `granularity.known_coarse`
in `data/authors/manifest.yaml`: the baseline is *policy*, hand-edited,
and the measurement is generated. Both directions are enforced —
un-baselined drift fails, and so does a baseline entry whose file has
since been formatted, because a baseline that only ever grows is not a
baseline.

Two formatters share it: Prettier over `web/` (#483) and ruff over the
Python trees (#136). Until #136 only Prettier was gated, and a comment on
that issue read the Prettier gate as the Python one — the ruff residue went
from 90 files to 143 while it was believed covered.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_format_baseline as mod  # noqa: E402

FORMATTERS = sorted(mod.FORMATTERS)


def _write(tmp_path, text: str):
    p = tmp_path / ".baseline"
    p.write_text(text, encoding="utf-8")
    return p


def test_both_formatters_are_gated():
    assert FORMATTERS == ["prettier", "ruff"]


def test_read_baseline_ignores_comments_and_blanks(tmp_path):
    path = _write(
        tmp_path,
        "# pinned by #483 — see docs\n"
        "\n"
        "src/App.tsx\n"
        "   \n"
        "tests/Refs.test.tsx   \n"
        "# trailing comment\n",
    )
    assert mod.read_baseline(path) == {"src/App.tsx", "tests/Refs.test.tsx"}


def test_read_baseline_of_missing_file_is_empty(tmp_path):
    assert mod.read_baseline(tmp_path / "nope") == set()


def test_compare_flags_a_file_that_drifted_without_being_pinned():
    added, stale = mod.compare(
        unformatted={"src/App.tsx", "src/New.tsx"},
        baseline={"src/App.tsx"},
    )
    assert added == {"src/New.tsx"}
    assert stale == set()


def test_compare_flags_a_pinned_file_that_is_now_formatted():
    # The baseline must shrink. A file someone cleaned up has to leave the
    # list, or the gate quietly stops covering it forever.
    added, stale = mod.compare(
        unformatted={"src/App.tsx"},
        baseline={"src/App.tsx", "src/Fixed.tsx"},
    )
    assert added == set()
    assert stale == {"src/Fixed.tsx"}


def test_compare_is_clean_when_the_two_agree():
    assert mod.compare(unformatted={"a.ts"}, baseline={"a.ts"}) == (set(), set())


def test_prettier_output_is_one_path_per_line():
    assert mod.PRETTIER.parse("src/App.tsx\n\ntests/X.test.ts\n") == {
        "src/App.tsx",
        "tests/X.test.ts",
    }


def test_ruff_output_is_read_from_the_concise_format():
    out = (
        "perseus/_download.py:34:14: unformatted: File would be reformatted\n"
        "src/minerva/a.py:1:1: unformatted: File would be reformatted\n"
        "2 files would be reformatted, 439 files already formatted\n"
    )
    assert mod.RUFF.parse(out) == {"perseus/_download.py", "src/minerva/a.py"}


def _stub(monkeypatch, *, unformatted, baseline):
    monkeypatch.setattr(mod, "unformatted_files", lambda _fmt: set(unformatted))
    monkeypatch.setattr(mod, "read_baseline", lambda _path: set(baseline))


@pytest.mark.parametrize("name", FORMATTERS)
def test_main_exits_zero_when_baseline_matches(monkeypatch, capsys, name):
    _stub(monkeypatch, unformatted={"a"}, baseline={"a"})
    assert mod.main([name]) == 0
    assert "ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "fix"), [("prettier", "prettier --write"), ("ruff", "ruff format")]
)
def test_main_names_the_new_file_and_the_fix(monkeypatch, capsys, name, fix):
    _stub(monkeypatch, unformatted={"src/New.tsx"}, baseline=set())
    assert mod.main([name]) == 1
    out = capsys.readouterr().out
    assert "src/New.tsx" in out
    # The message has to say what to run; a gate that only says "no" costs
    # the reader a search through the Makefile.
    assert fix in out


@pytest.mark.parametrize("name", FORMATTERS)
def test_main_names_a_stale_pin_and_says_to_remove_it(monkeypatch, capsys, name):
    _stub(monkeypatch, unformatted=set(), baseline={"src/Fixed.tsx"})
    assert mod.main([name]) == 1
    out = capsys.readouterr().out
    assert "src/Fixed.tsx" in out
    assert "remove" in out.lower()


def test_main_with_no_arguments_runs_every_formatter(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(mod, "unformatted_files", lambda fmt: seen.append(fmt.name) or set())
    monkeypatch.setattr(mod, "read_baseline", lambda _path: set())
    assert mod.main([]) == 0
    assert seen == FORMATTERS


def test_main_fails_if_any_formatter_fails(monkeypatch):
    monkeypatch.setattr(
        mod, "unformatted_files", lambda fmt: {"x"} if fmt.name == "ruff" else set()
    )
    monkeypatch.setattr(mod, "read_baseline", lambda _path: set())
    assert mod.main([]) == 1


@pytest.mark.parametrize("name", FORMATTERS)
def test_the_committed_baseline_has_no_stale_entries(name):
    # Guards the real file, not a fixture: every pinned path must still
    # exist. A rename leaves a pin that matches nothing, and the gate
    # would never notice because the formatter simply never reports it.
    fmt = mod.FORMATTERS[name]
    missing = [p for p in mod.read_baseline(fmt.baseline) if not (fmt.cwd / p).exists()]
    assert missing == [], f"baseline pins paths that no longer exist: {missing}"


def test_prettier_scope_matches_package_json():
    # The gate measures what `npm run format` would fix. If the two drift
    # apart, the gate either polices files the formatter will not touch or
    # ignores files it would — both silent.
    import json

    scripts = json.loads((mod.PRETTIER.cwd / "package.json").read_text())["scripts"]
    fmt = scripts["format"].split()
    assert fmt[:2] == ["prettier", "--write"], fmt
    assert tuple(fmt[2:]) == mod.PRETTIER.targets


def test_ruff_scope_matches_make_format_py():
    # Same reasoning for `make format-py`. It used to format `src tests`
    # only, so scripts/ and perseus/ had no formatter at all.
    makefile = (ROOT / "Makefile").read_text()
    (line,) = re.findall(r"^\t\$\(RUFF\) format (.+)$", makefile, re.MULTILINE)
    assert tuple(line.split()) == mod.RUFF.targets


def test_ci_runs_each_formatter_in_the_job_that_installs_it():
    # Prettier needs `npm ci` (web job); ruff needs the locked venv (python
    # job). Running both in either job fails on the missing tool.
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text()
    runs = re.findall(r"run: .*check_format_baseline\.py(.*)$", workflow, re.MULTILINE)
    assert sorted(r.strip() for r in runs) == FORMATTERS


@pytest.mark.parametrize("name", FORMATTERS)
def test_the_baseline_is_exactly_what_the_formatter_reports(name):
    # Runs the real formatter. A file Prettier cannot parse makes it exit 2,
    # which the gate raises on rather than treating as "nothing drifted";
    # `termcard.css` ended mid-comment from the initial commit until #483.
    fmt = mod.FORMATTERS[name]
    assert mod.unformatted_files(fmt) == mod.read_baseline(fmt.baseline)
