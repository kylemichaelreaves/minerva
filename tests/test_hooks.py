"""Tests for the three Claude Code hooks that replace #322's prose checks.

Each hook wraps a pure, testable function; `main()` is thin stdin/subprocess
glue around it, exercised in the `TestMain*` classes with monkeypatching
rather than a real subprocess, so the tests stay fast and hermetic.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# The hook scripts import each other (`staleness`, `check_pr_link`) the way
# they do when Claude Code invokes them directly — `python scripts/hook_x.py`
# auto-adds `scripts/` to sys.path. importlib-loading them here does not, so
# it's added explicitly, once, before any _load() call below.
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


staleness = _load("staleness")
commit_hazard = _load("hook_commit_hazard")
mark_dirty = _load("hook_mark_dirty")
mark_check_passed = _load("hook_mark_check_passed")
require_fresh_check = _load("hook_require_fresh_check")
pr_link_autocheck = _load("hook_pr_link_autocheck")


class TestIsStale:
    def test_no_dirty_marker_is_not_stale(self, tmp_path: Path):
        assert staleness.is_stale(tmp_path / "dirty", tmp_path / "passed") is False

    def test_dirty_with_no_passed_marker_is_stale(self, tmp_path: Path):
        dirty = tmp_path / "dirty"
        dirty.touch()
        assert staleness.is_stale(dirty, tmp_path / "passed") is True

    def test_dirty_newer_than_passed_is_stale(self, tmp_path: Path):
        passed = tmp_path / "passed"
        passed.touch()
        dirty = tmp_path / "dirty"
        dirty.touch()
        import os

        os.utime(dirty, (passed.stat().st_mtime + 10, passed.stat().st_mtime + 10))
        assert staleness.is_stale(dirty, passed) is True

    def test_passed_newer_than_dirty_is_not_stale(self, tmp_path: Path):
        dirty = tmp_path / "dirty"
        dirty.touch()
        passed = tmp_path / "passed"
        passed.touch()
        import os

        os.utime(passed, (dirty.stat().st_mtime + 10, dirty.stat().st_mtime + 10))
        assert staleness.is_stale(dirty, passed) is False


class TestCommitHazardShouldFire:
    def test_fires_on_git_commit(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'x'"}}
        assert commit_hazard.should_fire(payload) is True

    def test_ignores_non_bash_tools(self):
        payload = {"tool_name": "Edit", "tool_input": {"command": "git commit -m 'x'"}}
        assert commit_hazard.should_fire(payload) is False

    def test_ignores_unrelated_bash_commands(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        assert commit_hazard.should_fire(payload) is False

    def test_ignores_failed_commit(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'x'"},
            "tool_response": {"success": False},
        }
        assert commit_hazard.should_fire(payload) is False

    def test_fires_on_chained_commit(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git add -A && git commit -m 'x'"},
        }
        assert commit_hazard.should_fire(payload) is True


class TestCommitHazardBuildOutput:
    def test_no_hits_returns_none(self):
        assert commit_hazard.build_output([]) is None

    def test_hits_produce_advisory_context(self):
        output = commit_hazard.build_output([176, 42])
        assert output is not None
        assert "176" in output["systemMessage"]
        assert "42" in output["systemMessage"]
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "176" in output["hookSpecificOutput"]["additionalContext"]
        # Advisory only: never blocks.
        assert "decision" not in output
        assert output.get("continue", True) is not False


class TestCommitHazardMain:
    def test_prints_advisory_for_hazardous_message(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'x'"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        monkeypatch.setattr(commit_hazard, "latest_commit_message", lambda: "closes #99")
        assert commit_hazard.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hookSpecificOutput"]["additionalContext"].count("99") >= 1

    def test_silent_when_not_a_commit(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert commit_hazard.main() == 0
        assert capsys.readouterr().out == ""

    def test_silent_when_message_has_no_hazard(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'x'"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        monkeypatch.setattr(commit_hazard, "latest_commit_message", lambda: "unrelated change")
        assert commit_hazard.main() == 0
        assert capsys.readouterr().out == ""


class TestIsWatchedPath:
    @pytest.mark.parametrize(
        "path",
        [
            "src/minerva/retrieve.py",
            "tests/test_retrieve.py",
            "web/src/App.tsx",
            "perseus/scrape.py",
            "scripts/check_pr_link.py",
        ],
    )
    def test_watched_prefixes(self, path: str):
        assert mark_dirty.is_watched_path(path) is True

    @pytest.mark.parametrize(
        "path", ["docs/README.md", "data/authors/manifest.yaml", ".claude/settings.json"]
    )
    def test_unwatched_prefixes(self, path: str):
        assert mark_dirty.is_watched_path(path) is False


class TestMarkDirtyMain:
    def test_touches_marker_for_watched_edit(self, tmp_path: Path, monkeypatch):
        marker = tmp_path / "dirty"
        monkeypatch.setattr(staleness, "DIRTY_MARKER", marker)
        monkeypatch.setattr(mark_dirty, "staleness", staleness)
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/minerva/retrieve.py"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert mark_dirty.main() == 0
        assert marker.exists()

    def test_does_not_touch_marker_for_unwatched_edit(self, tmp_path: Path, monkeypatch):
        marker = tmp_path / "dirty"
        monkeypatch.setattr(staleness, "DIRTY_MARKER", marker)
        monkeypatch.setattr(mark_dirty, "staleness", staleness)
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "docs/README.md"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert mark_dirty.main() == 0
        assert not marker.exists()


class TestIsMakeCheck:
    @pytest.mark.parametrize("command", ["make check", "make check ", "cd /repo && make check"])
    def test_matches_bare_make_check(self, command: str):
        assert mark_check_passed.is_make_check(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "make check-pr-link PR=1",
            "make check-diff-coverage",
            "make check-authors",
            "make coverage",
        ],
    )
    def test_does_not_match_other_targets(self, command: str):
        assert mark_check_passed.is_make_check(command) is False


class TestMarkCheckPassedMain:
    def test_touches_marker_on_success(self, tmp_path: Path, monkeypatch):
        marker = tmp_path / "passed"
        monkeypatch.setattr(staleness, "CHECK_PASSED_MARKER", marker)
        monkeypatch.setattr(mark_check_passed, "staleness", staleness)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "make check"},
            "tool_response": {"success": True},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert mark_check_passed.main() == 0
        assert marker.exists()

    def test_ignores_failed_run(self, tmp_path: Path, monkeypatch):
        marker = tmp_path / "passed"
        monkeypatch.setattr(staleness, "CHECK_PASSED_MARKER", marker)
        monkeypatch.setattr(mark_check_passed, "staleness", staleness)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "make check"},
            "tool_response": {"success": False},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert mark_check_passed.main() == 0
        assert not marker.exists()


class TestIsPushOrPrCreate:
    @pytest.mark.parametrize(
        "command", ["git push", "git push origin main", "gh pr create --title x"]
    )
    def test_matches(self, command: str):
        assert require_fresh_check.is_push_or_pr_create(command) is True

    @pytest.mark.parametrize("command", ["git status", "gh pr view 1", "gh pr list"])
    def test_does_not_match(self, command: str):
        assert require_fresh_check.is_push_or_pr_create(command) is False


class TestRequireFreshCheckMain:
    def test_asks_when_stale(self, tmp_path: Path, monkeypatch, capsys):
        dirty = tmp_path / "dirty"
        dirty.touch()
        monkeypatch.setattr(staleness, "DIRTY_MARKER", dirty)
        monkeypatch.setattr(staleness, "CHECK_PASSED_MARKER", tmp_path / "passed")
        monkeypatch.setattr(require_fresh_check, "staleness", staleness)
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert require_fresh_check.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_silent_when_fresh(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setattr(staleness, "DIRTY_MARKER", tmp_path / "dirty")
        monkeypatch.setattr(staleness, "CHECK_PASSED_MARKER", tmp_path / "passed")
        monkeypatch.setattr(require_fresh_check, "staleness", staleness)
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert require_fresh_check.main() == 0
        assert capsys.readouterr().out == ""

    def test_silent_when_command_unrelated(self, tmp_path: Path, monkeypatch, capsys):
        dirty = tmp_path / "dirty"
        dirty.touch()
        monkeypatch.setattr(staleness, "DIRTY_MARKER", dirty)
        monkeypatch.setattr(staleness, "CHECK_PASSED_MARKER", tmp_path / "passed")
        monkeypatch.setattr(require_fresh_check, "staleness", staleness)
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert require_fresh_check.main() == 0
        assert capsys.readouterr().out == ""


class TestExtractPrNumber:
    def test_extracts_from_gh_output(self):
        stdout = "https://github.com/kylemichaelreaves/minerva/pull/440\n"
        assert pr_link_autocheck.extract_pr_number(stdout) == 440

    def test_none_when_no_url(self):
        assert pr_link_autocheck.extract_pr_number("no url here") is None


class TestPrLinkAutocheckShouldFire:
    def test_fires_on_gh_pr_create(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --title x --body y"},
        }
        assert pr_link_autocheck.should_fire(payload) is True

    def test_ignores_other_commands(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "gh pr view 1"}}
        assert pr_link_autocheck.should_fire(payload) is False
