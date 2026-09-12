#!/usr/bin/env python3
"""Fail when a frontend test sits under `web/src` instead of `web/tests` (#547).

`sonar-project.properties` declares `sonar.tests=tests,web/tests` and
`sonar.sources=src,web/src,scripts,perseus`. A test file written beside
its component is therefore analysed as **production source with 0%
coverage**, and the required new-code coverage gate fails for a reason
with nothing to do with the code under review. Measured on PR #546: two
colocated files, 85 lines counted as uncovered production code, gate
`new_coverage ERROR threshold 80 actual 65.2`; after moving them, with
no change to any assertion, 93.4%.

This gate exists because `make check` cannot otherwise see it.
`check-diff-coverage` reads the vitest lcov report, which excludes test
files by nature, so the local gate and the remote gate disagree and the
local one stays green — a full CI round trip to discover a misplaced
file.

The convention is otherwise implicit: it lives in the shape of the
directory and one line of `sonar-project.properties`, and the wider JS
ecosystem's majority convention is the opposite, so an author following
habit lands in the failure. The second cost is worse than the gate
failure: a colocated duplicate is invisible from beside the component.
`web/tests/Lines.test.tsx` already existed when PR #546 added a second
`Lines.test.tsx` under `web/src`, and both the implementer and the
reviewer reported that no such file existed — each had looked only in
one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

#: Vitest collects `*.spec.*` as readily as `*.test.*`, so a guard that
#: knows only about `.test.` leaves the same hole one rename away.
_PATTERNS = ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx")


def misplaced_tests(root: Path) -> list[Path]:
    """Every test-shaped file under `web/src`, sorted for stable output."""

    src = root / "web" / "src"
    if not src.is_dir():
        return []
    found: set[Path] = set()
    for pattern in _PATTERNS:
        found.update(src.rglob(pattern))
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else _ROOT

    stray = misplaced_tests(root)
    if not stray:
        print("check-test-location: ok (no test files under web/src)")
        return 0

    print(
        "check-test-location: test files must live in web/tests, not beside the component",
        file=sys.stderr,
    )
    for path in stray:
        print(f"  {path.relative_to(root)}", file=sys.stderr)
    print(
        "\nSonar analyses web/src as production source (sonar.sources), so these are\n"
        "scored as uncovered production code and will fail the new-code coverage gate.\n"
        "Move them to web/tests/ — no change to any assertion is needed.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
