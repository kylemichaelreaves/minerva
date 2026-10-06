"""#723: `check.yml` decides which suites a PR needs from the paths it changes.

Every mistake in one direction costs runner time. Every mistake in the other
lets a PR merge without running a check it needed. So the classifier is
asymmetric on purpose: a path it doesn't recognise runs everything.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ci_scope  # noqa: E402

BOTH = {"python": True, "web": True}
PYTHON = {"python": True, "web": False}
WEB = {"python": False, "web": True}
NEITHER = {"python": False, "web": False}


@pytest.mark.parametrize(
    "paths, expected",
    [
        (["README.md", "docs/CONTRIBUTING.md", "LICENSE"], NEITHER),
        ([".claude/skills/close-out/SKILL.md"], NEITHER),
        (["src/minerva/retrieve.py", "tests/test_retrieve.py"], PYTHON),
        (["scripts/check_pr_link.py", "perseus/fetch.py", "uv.lock"], PYTHON),
        (["pyproject.toml", ".python-version"], PYTHON),
        (["web/src/Reader/index.tsx", "web/tests/Lines.test.tsx"], WEB),
        (["web/package-lock.json", "web/eslint.config.js"], WEB),
        (["src/minerva/retrieve.py", "web/src/Reader/index.tsx"], BOTH),
        # A Markdown file beside the code it documents doesn't make the PR
        # docs-only.
        (["web/src/Reader/index.tsx", "docs/FRONTEND.md"], WEB),
        # Markdown under a test tree may be fixture input, so it counts as
        # that stack's code rather than as documentation.
        (["tests/fixtures/hobbes_la/README.md"], PYTHON),
        (["web/tests/fixtures/notes.md"], WEB),
        # Generated from scripts/ and diffed by the python job's
        # `generate_scripts_index.py --check` (#505), so a hand-edit to it
        # must run that job.
        (["docs/SCRIPTS.md"], PYTHON),
    ],
)
def test_paths_map_to_the_suites_they_can_break(paths, expected):
    assert ci_scope.scope(paths) == expected


@pytest.mark.parametrize(
    "path",
    [
        # Neither stack owns these, and each is read by both.
        ".github/workflows/check.yml",
        "Makefile",
        "sonar-project.properties",
        "data/authors/manifest.yaml",
        "data/authors/work_slugs.json",
        # Unknown by construction.
        "some/new/top-level/thing.txt",
    ],
)
def test_unrecognised_or_shared_paths_run_everything(path):
    assert ci_scope.scope([path]) == BOTH


@pytest.mark.parametrize(
    "path",
    [
        # check_api_types.py (python job) diffs these against the fixtures.
        "web/src/api/types/reader.ts",
        "web/src/api/concordanceApi.ts",
        "tests/fixtures/api/work_range.json",
        # generate_author_artifacts.py --check (python job) owns these.
        "web/src/data/atlasData.ts",
        "web/src/utils/dominantPhil.ts",
        "src/minerva/corpus_registry.py",
        "src/minerva/author_ordering.py",
        # test_node_version_pin.py (python job) reads both.
        "web/package.json",
        ".nvmrc",
    ],
)
def test_paths_read_across_stacks_run_both(path):
    assert ci_scope.scope([path]) == BOTH


def test_an_empty_diff_runs_everything():
    """An empty list means the diff failed or compared the wrong refs, not
    that nothing changed. Skipping on it would green-light a PR untested."""

    assert ci_scope.scope([]) == BOTH


def test_main_prints_github_output_lines(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Lines(["web/src/App.tsx", ""]))

    assert ci_scope.main() == 0
    assert capsys.readouterr().out.splitlines() == ["python=false", "web=true"]


class _Lines:
    def __init__(self, lines: list[str]):
        self._text = "\n".join(lines)

    def read(self) -> str:
        return self._text
