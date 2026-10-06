#!/usr/bin/env python3
"""Check that `pyproject.toml`'s coverage `omit` and `sonar-project.
properties`'s `sonar.coverage.exclusions` agree on `src/minerva/` (#345).

`pyproject.toml`'s `[tool.coverage.run].omit` controls what the local
suite (and the `coverage.xml` it uploads) measures; Sonar's
`sonar.coverage.exclusions` controls what the **blocking** coverage
gate measures. Nothing enforces that the two agree, and the failure is
silent in the dangerous direction: a file omitted from one but not the
other is analysed by Sonar, finds no data in `coverage.xml`, and is
scored a manufactured 0% — exactly what happened twice (`src/minerva/
migrations/*`, #339; `src/minerva/cli/__init__.py`, #345) before either
was noticed.

Only `src/minerva/**` entries are compared: `[tool.coverage.run].source
= ["src/minerva"]` scopes Python coverage collection to that tree, so an
entry outside it (`scripts/**`, `web/src/**`) can never affect what
`coverage.xml` reports and has nothing to agree with.

Reporting-only tool this is not — a mismatch here is exactly the
"coverage gate scores real code 0%" failure mode, so this one gates.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _ROOT / "pyproject.toml"
_SONAR_PROPERTIES = _ROOT / "sonar-project.properties"
_SRC_PREFIX = "src/minerva/"


def pyproject_omit(path: Path | None = None) -> set[str]:
    # Read the module attribute at call time, not as a default-argument
    # value — a default is bound once at import, which would ignore a
    # test's `monkeypatch.setattr(module, "_PYPROJECT", ...)` entirely.
    data = tomllib.loads((path or _PYPROJECT).read_text())
    omit = data.get("tool", {}).get("coverage", {}).get("run", {}).get("omit", [])
    return {entry for entry in omit if entry.startswith(_SRC_PREFIX)}


def sonar_coverage_exclusions(path: Path | None = None) -> set[str]:
    """Parse the `.properties` line-continuation format (`key=\\` then
    indented `value,\\` lines) rather than assume the file has exactly
    the shape it has today — the value is what varies, not the syntax.
    """

    text = (path or _SONAR_PROPERTIES).read_text()
    # Join a trailing-backslash continuation onto the next line, the
    # same rule `.properties` files use, before looking for the key.
    joined = re.sub(r"\\\n[ \t]*", "", text)
    for line in joined.splitlines():
        if line.startswith("sonar.coverage.exclusions="):
            value = line[len("sonar.coverage.exclusions=") :]
            return {entry.strip() for entry in value.split(",") if entry.strip()}
    return set()


def main(argv: list[str] | None = None) -> int:
    omit = pyproject_omit()
    sonar = {e for e in sonar_coverage_exclusions() if e.startswith(_SRC_PREFIX)}

    only_pyproject = omit - sonar
    only_sonar = sonar - omit
    if not only_pyproject and not only_sonar:
        print(f"check-coverage-exclusions: ok ({len(omit)} src/minerva/ entries agree)")
        return 0

    print(
        "check-coverage-exclusions: pyproject.toml and sonar-project.properties disagree on src/minerva/",
        file=sys.stderr,
    )
    for entry in sorted(only_pyproject):
        print(
            f"  in pyproject.toml's omit, missing from sonar.coverage.exclusions: {entry}",
            file=sys.stderr,
        )
    for entry in sorted(only_sonar):
        print(
            f"  in sonar.coverage.exclusions, missing from pyproject.toml's omit: {entry}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
