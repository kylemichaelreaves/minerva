"""#345: `pyproject.toml`'s coverage `omit` and `sonar-project.
properties`'s `sonar.coverage.exclusions` must agree on `src/minerva/`
entries, or a file omitted from one but not the other gets a
manufactured 0% from Sonar's blocking gate — exactly what happened to
`src/minerva/migrations/*` (#339) and `src/minerva/cli/__init__.py`
(#345) before either was noticed.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_coverage_exclusions as cce  # noqa: E402


def _write_pyproject(tmp_path: Path, omit: list[str]) -> Path:
    items = ",\n    ".join(f'"{o}"' for o in omit)
    path = tmp_path / "pyproject.toml"
    path.write_text(
        "[tool.coverage.run]\n"
        'source = ["src/minerva"]\n'
        f"omit = [\n    {items}\n]\n" if omit else
        "[tool.coverage.run]\n"
        'source = ["src/minerva"]\n'
        "omit = []\n"
    )
    return path


def _write_sonar_properties(tmp_path: Path, exclusions: list[str]) -> Path:
    path = tmp_path / "sonar-project.properties"
    body = ",\\\n  ".join(exclusions)
    path.write_text(f"sonar.coverage.exclusions=\\\n  {body}\n" if exclusions else "sonar.coverage.exclusions=\n")
    return path


def test_the_repos_own_files_agree():
    """Regression guard on the real files, not fixtures — this is the
    thing #345 asks for."""

    assert cce.main([]) == 0


def test_matching_lists_pass(tmp_path: Path):
    pyproject = _write_pyproject(tmp_path, ["src/minerva/cli/__init__.py"])
    sonar = _write_sonar_properties(tmp_path, ["src/minerva/cli/__init__.py"])
    assert cce.pyproject_omit(pyproject) == {"src/minerva/cli/__init__.py"}
    assert cce.sonar_coverage_exclusions(sonar) == {"src/minerva/cli/__init__.py"}


def test_an_entry_only_in_pyproject_is_a_mismatch(tmp_path: Path, capsys):
    pyproject = _write_pyproject(tmp_path, ["src/minerva/cli/__init__.py"])
    sonar = _write_sonar_properties(tmp_path, [])
    omit = cce.pyproject_omit(pyproject)
    excl = cce.sonar_coverage_exclusions(sonar)
    assert omit - excl == {"src/minerva/cli/__init__.py"}


def test_an_entry_only_in_sonar_is_a_mismatch(tmp_path: Path):
    pyproject = _write_pyproject(tmp_path, [])
    sonar = _write_sonar_properties(tmp_path, ["src/minerva/migrations/**"])
    omit = cce.pyproject_omit(pyproject)
    excl = {e for e in cce.sonar_coverage_exclusions(sonar) if e.startswith("src/minerva/")}
    assert excl - omit == {"src/minerva/migrations/**"}


def test_entries_outside_src_minerva_are_irrelevant(tmp_path: Path):
    # scripts/** and perseus/** are outside coverage.run's `source`, so
    # they can never appear in coverage.xml and have nothing to agree
    # with — the check must not flag them.
    sonar = _write_sonar_properties(
        tmp_path, ["scripts/**", "perseus/**", "web/src/**/*.stories.tsx"]
    )
    excl = {
        e
        for e in cce.sonar_coverage_exclusions(sonar)
        if e.startswith("src/minerva/")
    }
    assert excl == set()


def test_main_exits_nonzero_on_mismatch(tmp_path: Path, monkeypatch, capsys):
    pyproject = _write_pyproject(tmp_path, ["src/minerva/cli/__init__.py"])
    sonar = _write_sonar_properties(tmp_path, [])
    monkeypatch.setattr(cce, "_PYPROJECT", pyproject)
    monkeypatch.setattr(cce, "_SONAR_PROPERTIES", sonar)

    rc = cce.main([])

    assert rc == 1
    err = capsys.readouterr().err
    assert "src/minerva/cli/__init__.py" in err


def test_main_exits_zero_when_both_empty(tmp_path: Path, monkeypatch):
    pyproject = _write_pyproject(tmp_path, [])
    sonar = _write_sonar_properties(tmp_path, ["scripts/**"])
    monkeypatch.setattr(cce, "_PYPROJECT", pyproject)
    monkeypatch.setattr(cce, "_SONAR_PROPERTIES", sonar)

    assert cce.main([]) == 0
