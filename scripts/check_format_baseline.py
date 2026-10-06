#!/usr/bin/env python3
"""Gate Prettier and ruff formatting against pinned baselines (#483, #136).

`make check` ran `lint`, `typecheck` and the suites but never Prettier, so
formatting drift accumulated unseen: **152 of the 352 files** Prettier
considers were unformatted when this landed. `eslint-config-prettier` sits
last in the ESLint chain and *disables* the formatting rules on the
assumption that Prettier owns them — with nothing running Prettier, that
assumption held for nothing outside a developer's editor-on-save.

Reformatting all 152 is not available. It churns 98 files under `web/src`
and scores **74.4% (314/422) against the 80% changed-line gate**, because
re-wrapped lines count as changed lines and the sweep takes untested files
along with well-covered ones. That is #324's lesson again: a mechanical,
behaviour-free change constrained entirely by the coverage gate.

So this is baseline-pinned, the same shape as `granularity.known_coarse`
in `data/authors/manifest.yaml`. `web/.prettier-baseline` is **policy** —
hand-edited, never regenerated, which is what stops the gate blessing its
own violations. The measurement is generated fresh on every run.

Both directions are enforced, and the second is the one that makes it a
baseline rather than a permanent amnesty:

- a file that drifts **without** being pinned fails, which is the point;
- a pinned file that has since been formatted fails too, demanding its
  line be deleted. A list that only ever grows would let the gate quietly
  stop covering the tree.

Note the baseline deliberately does **not** live in `.prettierignore`.
`npm run format` honours that file, so a pinned entry there could never be
fixed by the formatter and the baseline could never shrink.
`.prettierignore` carries only genuine exclusions: generated output, and
the two codegen-owned files whose reformatting breaks `make check` (#486).

#136 put ruff behind the same gate, over `src tests scripts perseus`, with
`.ruff-format-baseline` at the repo root as its policy file. Nothing gated
`ruff format` before that, and a comment on #136 read *this* script as the
Python gate; the residue grew from 90 files to 143 while it was believed
covered. Run with no arguments for both, or name one (`prettier`, `ruff`) —
CI runs each in the job that installs its formatter.

Role: workflow
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Formatter:
    name: str
    #: Where the command runs; baseline paths are relative to it.
    cwd: Path
    baseline: Path
    #: What the formatter's own write command covers. Pinned to
    #: package.json / the Makefile by tests, so the gate polices exactly
    #: what the formatter would fix.
    targets: tuple[str, ...]
    #: The report-only invocation; `targets` is appended.
    command: tuple[str, ...]
    fix: str

    def parse(self, stdout: str) -> set[str]:
        """Paths in the formatter's report. Prettier's `--list-different`
        prints one per line; ruff's concise `--check` prints
        `path:line:col: unformatted: ...` plus a summary line."""
        lines = (line.strip() for line in stdout.splitlines())
        if self.name == "ruff":
            return {line.split(":", 1)[0] for line in lines if ": unformatted:" in line}
        return {line for line in lines if line}


# The whole of `web/`, exclusions delegated to `.prettierignore` — the same
# call `npm run format` makes, and the same reasoning that turned
# `eslint src tests` into `eslint .` in #480: an enumerated scope is the
# defect, not the fix.
PRETTIER = Formatter(
    name="prettier",
    cwd=_ROOT / "web",
    baseline=_ROOT / "web" / ".prettier-baseline",
    targets=(".",),
    command=("npx", "prettier", "--list-different"),
    fix="cd web && npx prettier --write <path>",
)

# `python -m ruff`, not a bare `ruff`: the interpreter running this is the
# venv's, so the formatter is the version uv.lock pins rather than whichever
# one is on PATH. The codegen-owned files are excluded in pyproject.toml.
RUFF = Formatter(
    name="ruff",
    cwd=_ROOT,
    baseline=_ROOT / ".ruff-format-baseline",
    targets=("src", "tests", "scripts", "perseus"),
    command=(sys.executable, "-m", "ruff", "format", "--check", "--output-format", "concise"),
    fix=".venv/bin/ruff format <path>",
)

FORMATTERS = {f.name: f for f in (PRETTIER, RUFF)}


def read_baseline(path: Path) -> set[str]:
    """Pinned paths, one per line; `#` comments and blank lines ignored."""
    if not path.exists():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def unformatted_files(fmt: Formatter) -> set[str]:
    """Paths the formatter would rewrite, relative to `fmt.cwd`."""
    # Both exit 1 when they find any, which is the normal case here and not
    # an error; a missing binary or a parse failure exits 2, which is.
    proc = subprocess.run(
        [*fmt.command, *fmt.targets], cwd=fmt.cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"{fmt.name} check failed ({proc.returncode}):\n{proc.stderr}")
    return fmt.parse(proc.stdout)


def compare(unformatted: set[str], baseline: set[str]) -> tuple[set[str], set[str]]:
    """`(drifted but unpinned, pinned but now clean)`."""
    return unformatted - baseline, baseline - unformatted


def _report(fmt: Formatter, added: set[str], stale: set[str]) -> None:
    where = fmt.baseline.relative_to(_ROOT)
    if added:
        print(
            f"check-format-baseline: {len(added)} file(s) are not "
            f"{fmt.name}-formatted and are not in the baseline:"
        )
        for path in sorted(added):
            print(f"  {path}")
        print(f"\n  Fix them:  {fmt.fix}")
        print(f"  Do NOT add them to {where} — it only shrinks.")
    if stale:
        print(
            f"check-format-baseline: {len(stale)} baseline entry/entries are "
            f"now formatted and must be removed from {where}:"
        )
        for path in sorted(stale):
            print(f"  {path}")
        print("\n  The baseline shrinks as files are fixed; a stale pin means")
        print("  the gate silently stopped covering a file that is now clean.")


def check(fmt: Formatter) -> bool:
    baseline = read_baseline(fmt.baseline)
    added, stale = compare(unformatted_files(fmt), baseline)
    _report(fmt, added, stale)
    if not (added or stale):
        print(
            f"check-format-baseline: {fmt.name} ok ({len(baseline)} file(s) pinned, none drifted)"
        )
    return not (added or stale)


def main(argv: list[str] | None = None) -> int:
    names = sys.argv[1:] if argv is None else argv
    selected = [FORMATTERS[n] for n in names] if names else list(FORMATTERS.values())
    results = [check(fmt) for fmt in selected]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
