"""#547: a frontend test written under `web/src` instead of `web/tests`
is analysed by SonarCloud as production source with 0% coverage, and
fails the required new-code coverage gate for a reason that has nothing
to do with the code under review.

Measured on PR #546: two colocated files, 85 lines of test code counted
as uncovered production code, `new_coverage ERROR threshold 80 actual
65.2`. After moving them, with no change to any assertion, 93.4%.

`make check`'s `check-diff-coverage` cannot catch this: it reads the
vitest lcov report, which excludes test files by nature, so the local
gate and the remote gate disagree with no local signal at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_test_location as ctl  # noqa: E402


def test_a_clean_tree_passes(tmp_path: Path, capsys):
    (tmp_path / "web" / "src" / "Reader").mkdir(parents=True)
    (tmp_path / "web" / "src" / "Reader" / "Lines.tsx").write_text("export const x = 1;")
    (tmp_path / "web" / "tests").mkdir(parents=True)
    (tmp_path / "web" / "tests" / "Lines.test.tsx").write_text("test('x', () => {});")

    assert ctl.main([str(tmp_path)]) == 0
    assert "ok" in capsys.readouterr().out


def test_a_colocated_test_file_fails(tmp_path: Path, capsys):
    (tmp_path / "web" / "src" / "Reader" / "components").mkdir(parents=True)
    stray = tmp_path / "web" / "src" / "Reader" / "components" / "Lines.test.tsx"
    stray.write_text("test('x', () => {});")

    assert ctl.main([str(tmp_path)]) != 0
    err = capsys.readouterr().err
    assert "Lines.test.tsx" in err
    assert "web/tests" in err


def test_both_test_extensions_are_caught(tmp_path: Path):
    """`.test.ts` as well as `.test.tsx` — the gate keys on file
    location, and a non-component test is just as invisible to the lcov
    report and just as visible to Sonar."""

    (tmp_path / "web" / "src" / "utils").mkdir(parents=True)
    (tmp_path / "web" / "src" / "utils" / "greek.test.ts").write_text("test('x', () => {});")

    assert ctl.main([str(tmp_path)]) != 0


def test_a_spec_file_is_caught_too(tmp_path: Path):
    """Vitest picks up `*.spec.*` as readily as `*.test.*`, so a guard
    that only knows about `.test.` leaves the same hole one rename away."""

    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / "src" / "greek.spec.ts").write_text("test('x', () => {});")

    assert ctl.main([str(tmp_path)]) != 0


def test_the_real_repository_is_clean():
    """The tree this guard is landing on must already pass it — the two
    files that prompted #547 were moved during PR #546."""

    assert ctl.main([]) == 0
