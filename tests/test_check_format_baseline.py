"""Tests for `scripts/check_format_baseline.py` (#483).

The gate is baseline-pinned, the same shape as `granularity.known_coarse`
in `data/authors/manifest.yaml`: the baseline is *policy*, hand-edited,
and the measurement is generated. Both directions are enforced —
un-baselined drift fails, and so does a baseline entry whose file has
since been formatted, because a baseline that only ever grows is not a
baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_format_baseline as mod  # noqa: E402


def _write(tmp_path, text: str):
    p = tmp_path / ".prettier-baseline"
    p.write_text(text, encoding="utf-8")
    return p


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


def test_main_exits_zero_when_baseline_matches(monkeypatch, capsys):
    monkeypatch.setattr(mod, "unformatted_files", lambda: {"src/App.tsx"})
    monkeypatch.setattr(mod, "read_baseline", lambda path=None: {"src/App.tsx"})
    assert mod.main() == 0
    assert "ok" in capsys.readouterr().out


def test_main_names_the_new_file_and_the_fix(monkeypatch, capsys):
    monkeypatch.setattr(mod, "unformatted_files", lambda: {"src/New.tsx"})
    monkeypatch.setattr(mod, "read_baseline", lambda path=None: set())
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "src/New.tsx" in out
    # The message has to say what to run; a gate that only says "no" costs
    # the reader a search through the Makefile.
    assert "prettier --write" in out


def test_main_names_a_stale_pin_and_says_to_remove_it(monkeypatch, capsys):
    monkeypatch.setattr(mod, "unformatted_files", lambda: set())
    monkeypatch.setattr(mod, "read_baseline", lambda path=None: {"src/Fixed.tsx"})
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "src/Fixed.tsx" in out
    assert "remove" in out.lower()


def test_the_committed_baseline_has_no_stale_entries():
    # Guards the real file, not a fixture: every pinned path must still
    # exist. A rename leaves a pin that matches nothing, and the gate
    # would never notice because prettier simply never reports it.
    missing = [p for p in mod.read_baseline() if not (mod._WEB / p).exists()]
    assert missing == [], f"baseline pins paths that no longer exist: {missing}"


def test_format_scope_matches_package_json():
    # The gate measures what `npm run format` would fix. If the two drift
    # apart, the gate either polices files the formatter will not touch or
    # ignores files it would — both silent.
    import json

    scripts = json.loads((mod._WEB / "package.json").read_text())["scripts"]
    fmt = scripts["format"].split()
    assert fmt[:2] == ["prettier", "--write"], fmt
    assert tuple(fmt[2:]) == mod._TARGETS


def test_baseline_pins_nothing_prettier_would_refuse_to_parse():
    # A file Prettier cannot parse makes `--list-different` exit 2, which the
    # gate raises on rather than silently treating as "nothing drifted".
    # `termcard.css` ended mid-comment from the initial commit until #483,
    # so this is a regression guard, not a hypothetical.
    assert mod.unformatted_files() == mod.read_baseline()
