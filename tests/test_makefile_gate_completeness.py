"""`make check` must reach every frontend suite CI treats as required (#604).

The defect this guards was not that someone forgot a target — both
`test-e2e` and `test-browser` existed in the Makefile. It was that each was
added *beside* the aggregate gate instead of inside it, so `make check` went
green while a required check (`web · e2e`) failed on the same tree.

A hardcoded list of suite names would not have caught that, because the
orphan was new when it was introduced. So the expectation is derived from
the workflow: whatever npm test script CI runs, `make check` must reach.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "check.yml"

_NPM_RUN = re.compile(r"npm(?:\s+--prefix\s+\S+)?\s+run\s+(test:[\w:-]+)")
_MAKE_NPM_RUN = re.compile(r"\$\(NPM\)\s+run\s+(test:[\w:-]+)")


def _parse_makefile(text: str) -> dict[str, tuple[list[str], list[str]]]:
    """target -> (prerequisites, recipe lines). Ignores variables and comments."""
    targets: dict[str, tuple[list[str], list[str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("\t"):
            if current is not None:
                targets[current][1].append(line.strip())
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)\s*(.*)$", line)
        if match:
            current = match.group(1)
            targets.setdefault(current, (match.group(2).split(), []))
        else:
            current = None
    return targets


def _reachable(targets: dict[str, tuple[list[str], list[str]]], root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        if name in seen or name not in targets:
            continue
        seen.add(name)
        stack.extend(targets[name][0])
    return seen


def test_make_check_reaches_every_npm_test_suite_ci_runs() -> None:
    targets = _parse_makefile(MAKEFILE.read_text())
    reached = _reachable(targets, "check")

    run_by_check = {
        script
        for name in reached
        for line in targets[name][1]
        for script in _MAKE_NPM_RUN.findall(line)
    }
    run_by_ci = set(_NPM_RUN.findall(WORKFLOW.read_text()))

    missing = run_by_ci - run_by_check
    assert not missing, (
        f"CI runs {sorted(run_by_ci)} but `make check` only reaches "
        f"{sorted(run_by_check)}. Unreached: {sorted(missing)}. A suite CI "
        f"requires must be inside the local aggregate gate, not beside it (#604)."
    )


def test_npm_test_scripts_quote_their_globs() -> None:
    """An unquoted glob in an npm script is expanded by the SHELL, not by vitest.

    `test:coverage` was `vitest run --exclude tests/e2e/** --coverage`. That
    worked only while `web/tests/e2e/` held exactly one file: `sh` expanded the
    glob in place, so `--exclude` consumed the single path and nothing was left
    over. Adding a second file to that directory made `sh` expand it to two
    paths — `--exclude` took the first and vitest read the second as a
    positional *name filter*, so the unit suite ran that one e2e file and
    reported 0% coverage on 10,315 statements.

    The gate does not fail loudly in that state; it fails as a coverage
    threshold, which reads like a coverage problem.
    """
    import json

    scripts = json.loads((REPO_ROOT / "web" / "package.json").read_text())["scripts"]
    offenders = {
        name: body
        for name, body in scripts.items()
        if name.startswith("test")
        for arg in body.split()
        if "*" in arg and not (arg.startswith(("'", '"')) and arg.endswith(("'", '"')))
    }
    assert not offenders, (
        f"npm test scripts pass an unquoted glob, which the shell expands before "
        f"vitest sees it: {offenders}. Quote it so vitest does its own matching."
    )
