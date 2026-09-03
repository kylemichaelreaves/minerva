#!/usr/bin/env python3
"""Gate Prettier formatting against a pinned baseline (#483).

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
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WEB = _ROOT / "web"
_BASELINE = _WEB / ".prettier-baseline"

# The whole of `web/`, exclusions delegated to `.prettierignore` — the same
# call `npm run format` makes, and the same reasoning that turned
# `eslint src tests` into `eslint .` in #480: an enumerated scope is the
# defect, not the fix. Pinned to package.json by
# `test_format_scope_matches_package_json`.
_TARGETS = (".",)


def read_baseline(path: Path | None = None) -> set[str]:
    """Pinned paths, one per line; `#` comments and blank lines ignored."""
    # Read the module attribute at call time rather than binding it as a
    # default-argument value, which would freeze it at import and ignore a
    # test's monkeypatch entirely.
    target = _BASELINE if path is None else path
    if not target.exists():
        return set()
    out: set[str] = set()
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def unformatted_files() -> set[str]:
    """Paths Prettier would rewrite, relative to `web/`."""
    # `--list-different` exits 1 when it finds any, which is the normal
    # case here and not an error; a missing binary or a parse failure
    # exits 2, which is.
    proc = subprocess.run(
        ["npx", "prettier", "--list-different", *_TARGETS],
        cwd=_WEB,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"prettier --list-different failed ({proc.returncode}):\n{proc.stderr}"
        )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def compare(unformatted: set[str], baseline: set[str]) -> tuple[set[str], set[str]]:
    """`(drifted but unpinned, pinned but now clean)`."""
    return unformatted - baseline, baseline - unformatted


def main() -> int:
    added, stale = compare(unformatted_files(), read_baseline())

    if added:
        print(
            f"check-format-baseline: {len(added)} file(s) are not "
            f"Prettier-formatted and are not in the baseline:"
        )
        for path in sorted(added):
            print(f"  {path}")
        print("\n  Fix them:  cd web && npx prettier --write <path>")
        print("  Do NOT add them to web/.prettier-baseline — it only shrinks.")

    if stale:
        print(
            f"check-format-baseline: {len(stale)} baseline entry/entries are "
            f"now formatted and must be removed from web/.prettier-baseline:"
        )
        for path in sorted(stale):
            print(f"  {path}")
        print("\n  The baseline shrinks as files are fixed; a stale pin means")
        print("  the gate silently stopped covering a file that is now clean.")

    if added or stale:
        return 1

    print(
        f"check-format-baseline: ok "
        f"({len(read_baseline())} file(s) pinned, none drifted)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
