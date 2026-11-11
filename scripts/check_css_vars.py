#!/usr/bin/env python3
"""Fail when `web/src` reads a CSS custom property that nothing defines (#877).

A `var(--x)` with no fallback that names an undefined property is invalid
at computed-value time, so the whole declaration falls back to its initial
or inherited value, and nothing reports it. Measured on #877:
`--paper-deep` was never defined, so all twelve of its uses were dropped.
`border: 1px solid var(--paper-deep)` computed to `border-style: none`,
and the Refs review cards rendered with no borders and no backgrounds.
Six such names had been in the tree since the initial commit. A fallback
does not make the use correct either: `var(--r-paper-soft, transparent)`
was always `transparent`, and `var(--muted, #888)` never followed the dark
theme.

A property counts as *defined* if any file under `web/src` (or
`web/index.html`) declares it, either as a CSS declaration `--x:` or as a
quoted `"--x"` string in TS/TSX, which covers `style={{ "--x": v }}` and
`el.style.setProperty("--x", v)`. This is a whole-tree check, not a
cascade check. It cannot tell that a property defined only under
`.reader` is read outside it. That would take a browser; this catches the
class #877 found, names that are defined nowhere.

Exempt prefixes are properties *read* through a name built at runtime,
`` `var(--atlas-${t})` `` (Atlas.tsx) and `` `var(--net-step-${k})` ``
(MatrixPanel.tsx). Statically, the use is only the prefix, so there is
nothing to look up. A new runtime-built prefix fails this check until it
is added here, which is deliberate: it makes the next one a decision.

Role: workflow
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

#: Prefixes read through a runtime-built name; see the module docstring.
EXEMPT_PREFIXES = ("--atlas-", "--net-step-")

_SUFFIXES = (".css", ".ts", ".tsx")
_NAME = r"--[A-Za-z0-9_-]+"
_USE = re.compile(rf"var\(\s*({_NAME})")
_CSS_DEF = re.compile(rf"({_NAME})\s*:")
_TS_DEF = re.compile(rf"""["'`]({_NAME})["'`]""")


def _sources(root: Path) -> list[Path]:
    src = root / "web" / "src"
    files = sorted(p for p in src.rglob("*") if p.suffix in _SUFFIXES and p.is_file())
    index = root / "web" / "index.html"
    return [*files, index] if index.is_file() else files


def scan(root: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Return (defined names, {used name: ["path:line", ...]})."""

    defined: set[str] = set()
    used: dict[str, list[str]] = {}
    for path in _sources(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        defs = _CSS_DEF if path.suffix in (".css", ".html") else _TS_DEF
        defined.update(defs.findall(text))
        if path.suffix != ".css":
            # `"--x": v` in a TSX style object is a CSS-shaped definition too.
            defined.update(_CSS_DEF.findall(text))
        for lineno, line in enumerate(text.splitlines(), 1):
            for name in _USE.findall(line):
                used.setdefault(name, []).append(f"{rel}:{lineno}")
    return defined, used


def undefined_uses(root: Path) -> dict[str, list[str]]:
    defined, used = scan(root)
    return {
        name: sites
        for name, sites in sorted(used.items())
        if name not in defined and not name.startswith(EXEMPT_PREFIXES)
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else _ROOT

    missing = undefined_uses(root)
    if not missing:
        print("check-css-vars: ok (every var(--x) under web/src has a definition)")
        return 0

    print("check-css-vars: var() reads a custom property that nothing defines", file=sys.stderr)
    for name, sites in missing.items():
        print(f"  {name}  ({len(sites)} use{'s' if len(sites) != 1 else ''})", file=sys.stderr)
        for site in sites:
            print(f"    {site}", file=sys.stderr)
    print(
        "\nAn undefined var() is invalid at computed-value time: the declaration is\n"
        "dropped to its initial value (a border becomes `none`) or to its fallback\n"
        "forever. Map it to an existing token, or define it deliberately.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
