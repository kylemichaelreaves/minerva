#!/usr/bin/env python3
"""Decide which `check.yml` suites a PR needs, from the paths it changes (#723).

Reads changed paths on stdin, one per line, and prints `python=<bool>` and
`web=<bool>` in `$GITHUB_OUTPUT` form. The workflow gates the `python` job on
the first, the `web` and `web-lint` jobs on the second, and `web · e2e` on
either.

This is not a workflow-level `paths:` filter, deliberately. A workflow that
never starts leaves its required checks unreported, and the PR can't merge. A
job skipped by a job-level `if:` reports success.

The classifier is asymmetric. Wrongly running a suite costs a few runner
minutes. Wrongly skipping one lets a PR merge without a check it needed. So:

* A path in neither stack's list runs both. That covers `.github/`, `Makefile`,
  `data/` and anything added later.
* An empty diff runs both. It means the diff went wrong, not that nothing
  changed.
* `_CROSS_STACK` lists the paths one stack's gates read from the other's tree.
  When you add a gate or test that reads across, add its paths here.
  Pushes to `main` run everything, so a cross-read missing from this list
  fails on `main` rather than never.

Role: workflow
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch

#: Documentation: no suite reads it. Markdown under a test tree is excluded,
#: because there it may be fixture input.
_DOCS = ("*.md", "LICENSE")
_TEST_TREES = ("tests/", "web/tests/")
#: Markdown a python-job gate generates and diffs, so it is not just prose.
#: `scripts/generate_scripts_index.py --check` owns docs/SCRIPTS.md (#505).
_GENERATED_DOCS = ("docs/SCRIPTS.md",)

_PYTHON = (
    "src/*",
    "tests/*",
    "scripts/*",
    "perseus/*",
    *_GENERATED_DOCS,
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
_WEB = ("web/*",)

#: Paths read by the other stack's gates. Each one runs both suites.
_CROSS_STACK = (
    # scripts/check_api_types.py (python job) checks fixture keys against
    # the TS wire types.
    "web/src/api/*",
    "tests/fixtures/api/*",
    # scripts/generate_author_artifacts.py --check (python job) regenerates
    # these from data/authors/manifest.yaml and diffs them.
    "web/src/data/atlasData.ts",
    "web/src/utils/dominantPhil.ts",
    "src/minerva/corpus_registry.py",
    "src/minerva/author_ordering.py",
    # tests/test_node_version_pin.py (python job).
    "web/package.json",
    ".nvmrc",
)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, p) for p in patterns)


def _is_docs(path: str) -> bool:
    return (
        _matches(path, _DOCS) and not path.startswith(_TEST_TREES) and path not in _GENERATED_DOCS
    )


def scope(paths: list[str]) -> dict[str, bool]:
    """Which suites `paths` can break."""

    if not paths:
        return {"python": True, "web": True}

    python = web = False
    for path in paths:
        if _is_docs(path):
            continue
        if _matches(path, _CROSS_STACK):
            return {"python": True, "web": True}
        if _matches(path, _PYTHON):
            python = True
        elif _matches(path, _WEB):
            web = True
        else:
            return {"python": True, "web": True}
    return {"python": python, "web": web}


def main() -> int:
    paths = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    for suite, needed in scope(paths).items():
        print(f"{suite}={str(needed).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
