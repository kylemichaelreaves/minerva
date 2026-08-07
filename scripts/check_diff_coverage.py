#!/usr/bin/env python3
"""Fail when the lines this diff changed are under-covered (#255).

SonarCloud gates PRs at 80% coverage **of the lines the diff changed** and is a
required status check (#158). `make check` deliberately excludes coverage, and
`make coverage-py` / `make coverage-web` report *whole-project* coverage —
a different question, and one that can be green while the gate is red. On #254
the project sat at 75% while the PR's new code was at 58.5%.

This closes that gap: same threshold, same two inputs Sonar uses, run locally.

WHAT IT MEASURES

Statements **and branches**. Sonar counts conditions, not only lines: a
one-line `if n != self._cur_book:` guard whose false branch had no test scored
75% (3/4) on #250 despite 100% *line* coverage. A statements-only check would
have called that green.

WHY IT REFUSES RATHER THAN REPORTS ZERO

Every "no data" path here is an error, not a pass. A coverage report that is
missing, a base ref that does not resolve, a path prefix that fails to line up
— each of those yields "0 changed lines, 0 uncovered, fine" from a naive
implementation, and an inert gate is worse than no gate (#116). Both prefix
traps below were hit by hand before this script existed:

* `coverage.xml` keys `filename` relative to its `<source>` (`src/minerva`),
  while lcov keys `SF:` relative to `web/`. Neither matches git's
  repo-relative paths.
* `git diff` does not list untracked files, so a brand-new module scores 0/0
  and passes unless it has been staged. Handled by asking `git ls-files
  --others` for them explicitly.

ONE THING IT CANNOT DETECT

That the reports correspond to the working tree. Line numbers from a stale
`coverage.xml` are measured against the current diff without complaint, and the
numbers are then meaningless. `make check` regenerates both immediately before
running this, which is the only reason that is safe; invoking the script by
hand after editing means re-running the suites first.

Usage:
    scripts/check_diff_coverage.py [--base origin/main] [--threshold 80]
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where each half writes its report, and the prefix its paths are relative to.
PY_XML = REPO / "coverage.xml"
WEB_LCOV = REPO / "web" / "coverage" / "lcov.info"

#: Only these trees are held to the bar, matching `sonar.coverage.exclusions`
#: (`scripts/**` and `perseus/**` are analysed for issues but not coverage).
GATED_PREFIXES = ("src/minerva/", "web/src/")


@dataclass
class Tally:
    """Changed-line and changed-branch counts for one file or a whole run."""

    lines_total: int = 0
    lines_covered: int = 0
    branches_total: int = 0
    branches_covered: int = 0
    uncovered_lines: list[int] = field(default_factory=list)
    partial_branches: list[tuple[int, int, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.lines_total + self.branches_total

    @property
    def covered(self) -> int:
        return self.lines_covered + self.branches_covered

    @property
    def percent(self) -> float:
        return 100.0 if self.total == 0 else 100.0 * self.covered / self.total

    def add(self, other: Tally) -> None:
        self.lines_total += other.lines_total
        self.lines_covered += other.lines_covered
        self.branches_total += other.branches_total
        self.branches_covered += other.branches_covered


class Problem(RuntimeError):
    """A reason the check cannot be trusted. Always fatal, never a pass."""


def _rel(path: Path) -> str:
    """Render *path* for a message, repo-relative when it is inside the repo.

    Not `path.relative_to(REPO)` bare: that raises for anything outside, which
    made the *error* paths below crash with a ValueError instead of reporting
    the problem they exist to report.
    """

    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


# ── coverage readers ──────────────────────────────────────────────────


def read_python_xml(path: Path) -> dict[str, dict[int, tuple[int, str | None]]]:
    """`{repo-relative path: {line: (hits, condition-coverage)}}`.

    Cobertura keys `filename` relative to the `<source>` element, so the
    prefix is read from the file rather than assumed — a hard-coded
    `src/minerva/` would break the day the source root moves and would break
    *silently*, as a total of zero changed lines.
    """

    if not path.is_file():
        raise Problem(
            f"no Python coverage at {_rel(path)} — "
            "run `pytest --cov --cov-report=xml` (make check does this)"
        )
    tree = ET.parse(path)
    sources = [s.text or "" for s in tree.iter("source")]
    prefix = ""
    for src in sources:
        rel = Path(src)
        try:
            prefix = str(rel.relative_to(REPO)) + "/"
        except ValueError:
            continue
        break

    out: dict[str, dict[int, tuple[int, str | None]]] = collections.defaultdict(dict)
    for cls in tree.iter("class"):
        fn = cls.get("filename") or ""
        key = f"{prefix}{fn}"
        for line in cls.iter("line"):
            n = int(line.get("number") or 0)
            out[key][n] = (int(line.get("hits") or 0), line.get("condition-coverage"))
    if not out:
        raise Problem(f"{_rel(path)} contained no measured files")
    return out


_BRDA = re.compile(r"^BRDA:(\d+),[^,]*,[^,]*,(.+)$")


def read_web_lcov(path: Path) -> dict[str, dict[int, tuple[int, str | None]]]:
    """Same shape, from lcov. `SF:` paths are relative to `web/`."""

    if not path.is_file():
        raise Problem(
            f"no web coverage at {_rel(path)} — "
            "run `npm --prefix web run test:coverage` (make check does this)"
        )
    lines: dict[str, dict[int, int]] = collections.defaultdict(dict)
    branches: dict[str, dict[int, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    cur: str | None = None
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if raw.startswith("SF:"):
            sf = raw[3:]
            # Absolute in some vitest versions, relative to web/ in others.
            #
            # String handling, not `Path(sf).resolve()`: `sf` is content read
            # out of a file, and resolving it would touch the filesystem on a
            # path this script never opens — it only ever becomes a dict key.
            # Constructing no path at all is both safer and simpler.
            if sf.startswith("/"):
                prefix = f"{REPO}/"
                cur = sf[len(prefix) :] if sf.startswith(prefix) else sf
            else:
                cur = f"web/{sf}"
        elif raw.startswith("DA:") and cur:
            n, hits = raw[3:].split(",")[:2]
            lines[cur][int(n)] = int(hits)
        elif raw.startswith("BRDA:") and cur:
            m = _BRDA.match(raw)
            if m:
                taken = m.group(2).split(",")[0]
                branches[cur][int(m.group(1))].append(0 if taken == "-" else int(taken))

    if not lines:
        raise Problem(f"{_rel(path)} contained no measured files")

    out: dict[str, dict[int, tuple[int, str | None]]] = collections.defaultdict(dict)
    for f, per_line in lines.items():
        for n, hits in per_line.items():
            taken = branches[f].get(n, [])
            cond = None
            if taken:
                cond = f"{100 * sum(1 for t in taken if t > 0) // len(taken)}% ({sum(1 for t in taken if t > 0)}/{len(taken)})"
            out[f][n] = (hits, cond)
        # Branch data can sit on a line lcov did not emit a DA for.
        for n, taken in branches[f].items():
            if n not in out[f] and taken:
                hit = sum(1 for t in taken if t > 0)
                out[f][n] = (1 if hit else 0, f"{100 * hit // len(taken)}% ({hit}/{len(taken)})")
    return out


# ── the diff ──────────────────────────────────────────────────────────

_HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")

#: A conservative superset of what `git check-ref-format` accepts, covering
#: real usage (`origin/main`, `HEAD~3`, `main^2`, `HEAD@{1}`, a bare sha).
#:
#: The leading character must be alphanumeric, and that is the point rather
#: than tidiness: `base` reaches `git diff` as an argv element, and git reads a
#: leading-dash value as an OPTION, not a ref. `--base=--output=/tmp/x` would
#: have git write a file. No shell is involved anywhere here, so this is the
#: whole attack surface — and it is worth closing rather than accepting,
#: because the operator invoking this is increasingly an agent passing along a
#: value it was handed.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}^~-]*$")


def _validate_ref(base: str) -> None:
    """Refuse a base that git could read as an option rather than a ref."""

    if not _REF_RE.match(base):
        raise Problem(
            f"base ref {base!r} is not a plausible git ref — refusing to pass it "
            "to git, which would read a leading '-' as an option"
        )


def changed_lines(base: str) -> dict[str, list[int]]:
    """`{repo-relative path: [added or modified line numbers]}`.

    Committed *and* working-tree changes against *base*, so the answer does not
    depend on what happens to be staged. Untracked files are added explicitly:
    git omits them from `diff`, and a brand-new module is exactly the thing
    most likely to be untested.
    """

    _validate_ref(base)
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", base],
            cwd=REPO,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        raise Problem(
            f"base ref {base!r} does not resolve — `git fetch` it, or pass --base"
        ) from None

    # `--end-of-options` before the ref, and `--` before the pathspecs, so
    # neither can be reinterpreted as an option even if validation ever slips.
    diff = subprocess.run(
        ["git", "diff", "-U0", "--end-of-options", base, "--", *GATED_PREFIXES],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    out: dict[str, list[int]] = collections.defaultdict(list)
    cur: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("@@") and cur:
            m = _HUNK.match(line)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                out[cur].extend(range(start, start + count))

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *GATED_PREFIXES],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path in untracked:
        # git listed these and the pathspec already restricted them to the
        # gated trees, but the containment check is explicit rather than
        # inferred: this is the one place the script opens a file whose name
        # came from a subprocess.
        candidate = (REPO / path).resolve()
        if not candidate.is_relative_to(REPO) or not candidate.is_file():
            continue
        out[path].extend(range(1, len(candidate.read_text().splitlines()) + 1))

    return out


# ── the check ─────────────────────────────────────────────────────────


def tally(
    changed: dict[str, list[int]],
    coverage: dict[str, dict[int, tuple[int, str | None]]],
) -> dict[str, Tally]:
    """Per-file counts, keeping only lines coverage actually measured.

    A changed line absent from the report is not counted either way: comments,
    blank lines, type-only declarations and coverage-omitted trees (migrations)
    are all in that set, and holding a diff to a bar for them would be noise.
    """

    per_file: dict[str, Tally] = {}
    for path, line_numbers in sorted(changed.items()):
        measured = coverage.get(path)
        if not measured:
            continue
        t = Tally()
        for n in line_numbers:
            entry = measured.get(n)
            if entry is None:
                continue
            hits, cond = entry
            t.lines_total += 1
            if hits > 0:
                t.lines_covered += 1
            else:
                t.uncovered_lines.append(n)
            if cond:
                m = re.match(r"\d+% \((\d+)/(\d+)\)", cond)
                if m:
                    covered, total = int(m.group(1)), int(m.group(2))
                    t.branches_total += total
                    t.branches_covered += covered
                    if covered != total:
                        t.partial_branches.append((n, covered, total))
        if t.total:
            per_file[path] = t
    return per_file


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/main", help="ref to diff against")
    ap.add_argument("--threshold", type=float, default=80.0, help="percent required")
    args = ap.parse_args()

    try:
        changed = changed_lines(args.base)
        if not changed:
            print(f"diff coverage: no changes under {', '.join(GATED_PREFIXES)} vs {args.base}")
            return 0
        coverage = {**read_python_xml(PY_XML), **read_web_lcov(WEB_LCOV)}
    except Problem as exc:
        print(f"check-diff-coverage: {exc}", file=sys.stderr)
        return 1

    per_file = tally(changed, coverage)
    if not per_file:
        # Changed files exist but none carried a measurable line. Possible
        # (a docstring-only diff) but also what every prefix bug looks like,
        # so say which files were considered rather than printing "OK".
        print(
            "check-diff-coverage: no measurable changed lines in "
            f"{len(changed)} changed file(s): {', '.join(sorted(changed)[:6])}"
        )
        return 0

    overall = Tally()
    for t in per_file.values():
        overall.add(t)

    width = max(len(p) for p in per_file)
    for path, t in per_file.items():
        flag = "  << under" if t.percent < args.threshold else ""
        print(
            f"  {path:<{width}}  {t.covered:>4}/{t.total:<4} {t.percent:>5.1f}%{flag}"
        )
        if t.uncovered_lines:
            print(f"  {'':<{width}}  uncovered: {t.uncovered_lines}")
        for n, c, tot in t.partial_branches:
            print(f"  {'':<{width}}  line {n}: only {c}/{tot} branches taken")

    print(
        f"\ndiff coverage vs {args.base}: {overall.percent:.1f}% "
        f"({overall.covered}/{overall.total} — {overall.lines_covered}/{overall.lines_total} lines, "
        f"{overall.branches_covered}/{overall.branches_total} branches), gate >= {args.threshold:.0f}%"
    )
    if overall.percent < args.threshold:
        print(
            "check-diff-coverage: FAILED — SonarCloud will block this PR.",
            file=sys.stderr,
        )
        return 1
    print("check-diff-coverage: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
