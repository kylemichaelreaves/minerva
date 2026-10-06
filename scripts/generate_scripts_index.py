#!/usr/bin/env python3
"""Generate the script index in `docs/SCRIPTS.md` from the scripts themselves (#505).

The hand-written index named 4 of 43 scripts and read as complete, which
is worse than no list. The index is now built from each script's own
documentation, so a script cannot land without appearing in it:

* a Python script's **module docstring**;
* a shell script's **leading comment block** — the `#` lines straight
  after the shebang, up to the first line that is not a comment.

The summary is the first paragraph of that text, folded onto one line.
Somewhere in the text a line must read exactly `Role: workflow` or
`Role: oneoff`:

* `workflow` — a step something else runs or tells you to run: the
  Makefile, CI, a Claude Code hook, `CONTRIBUTING.md` / `INGESTION.md` /
  `MEMORY.md`, another script, or a recurring operator procedure.
* `oneoff` — written for a migration or remediation that has landed.
  Kept for the record and for a re-source that needs the same repair,
  not because anything runs it.

Only the region between the two `GENERATED` markers in `docs/SCRIPTS.md`
is rewritten; everything outside them is hand-written and preserved.

    ./.venv/bin/python scripts/generate_scripts_index.py --write   # make generate-scripts-index
    ./.venv/bin/python scripts/generate_scripts_index.py --check   # make check-scripts-index

`--check` exits 1 when a script has no docstring, no `Role:` line or an
unknown role, or when the committed index differs from what `--write`
would produce. It runs in `make check`.

Role: workflow
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INDEX = Path("docs") / "SCRIPTS.md"

BEGIN = "<!-- BEGIN GENERATED: scripts/generate_scripts_index.py — edit the scripts' docstrings, not this table -->"
END = "<!-- END GENERATED -->"

ROLES = ("workflow", "oneoff")
_ROLE_LINE = re.compile(r"^Role:\s*(\S+)\s*$")
_HEADINGS = {"workflow": "### Workflow", "oneoff": "### One-off"}
_BLURBS = {
    "workflow": "Run by the Makefile, CI, a hook, another script, or a documented procedure.",
    "oneoff": "Written for a migration or remediation that has landed. Nothing runs these.",
}


class ScriptDocError(Exception):
    """A script's documentation cannot be indexed."""


@dataclass(frozen=True)
class Entry:
    name: str
    summary: str
    role: str


def _python_doc(path: Path) -> str | None:
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))


def _shell_doc(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    doc: list[str] = []
    for line in lines:
        if not line.startswith("#"):
            break
        doc.append(line[1:].removeprefix(" "))
    return "\n".join(doc).strip() or None


def parse_script(path: Path) -> Entry:
    """Read one script's summary and role, or raise `ScriptDocError`."""

    doc = _shell_doc(path) if path.suffix == ".sh" else _python_doc(path)
    if not doc:
        kind = "leading comment block" if path.suffix == ".sh" else "module docstring"
        raise ScriptDocError(f"{path.name}: no {kind}")

    roles = [m.group(1) for line in doc.splitlines() if (m := _ROLE_LINE.match(line.strip()))]
    if not roles:
        raise ScriptDocError(f"{path.name}: no `Role:` line (one of: {', '.join(ROLES)})")
    if len(roles) > 1:
        raise ScriptDocError(f"{path.name}: more than one `Role:` line")
    if roles[0] not in ROLES:
        raise ScriptDocError(f"{path.name}: unknown role {roles[0]!r} (one of: {', '.join(ROLES)})")

    first_paragraph = doc.strip().split("\n\n", 1)[0]
    summary = " ".join(first_paragraph.split())
    return Entry(name=path.name, summary=summary, role=roles[0])


def collect(scripts_dir: Path) -> tuple[list[Entry], list[str]]:
    """Every top-level `*.py` / `*.sh` under `scripts_dir`, plus the errors."""

    entries: list[Entry] = []
    errors: list[str] = []
    paths = sorted(p for p in scripts_dir.iterdir() if p.is_file() and p.suffix in (".py", ".sh"))
    for path in paths:
        try:
            entries.append(parse_script(path))
        except ScriptDocError as exc:
            errors.append(str(exc))
    return entries, errors


def _cell(summary: str) -> str:
    """`summary` made safe for a Markdown table cell.

    A `|` would split the cell, and a `<` outside a code span would open an
    HTML tag and hide the word after it. Code spans are the odd-numbered
    pieces of a split on backticks."""

    pieces = summary.replace("|", r"\|").split("`")
    return "`".join(p if i % 2 else p.replace("<", "&lt;") for i, p in enumerate(pieces))


def _table(entries: list[Entry], role: str) -> list[str]:
    rows = [e for e in entries if e.role == role]
    out = [_HEADINGS[role], "", _BLURBS[role], "", "| Script | Summary |", "|--------|---------|"]
    for e in rows:
        out.append(f"| [`{e.name}`](../scripts/{e.name}) | {_cell(e.summary)} |")
    return out


def render(current: str, entries: list[Entry]) -> str:
    """`current` with the generated region replaced from `entries`."""

    if current.count(BEGIN) != 1 or current.count(END) != 1:
        raise ScriptDocError(
            f"{INDEX}: the BEGIN/END GENERATED markers must each appear exactly once"
        )
    head, rest = current.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    counts = {role: sum(e.role == role for e in entries) for role in ROLES}
    body = [
        f"{len(entries)} scripts: {counts['workflow']} workflow, {counts['oneoff']} one-off.",
        "",
        *_table(entries, "workflow"),
        "",
        *_table(entries, "oneoff"),
    ]
    return f"{head}{BEGIN}\n{chr(10).join(body)}\n{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help=f"regenerate {INDEX}")
    mode.add_argument("--check", action="store_true", help=f"exit 1 if {INDEX} is stale")
    parser.add_argument("--root", type=Path, default=REPO, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    index = args.root / INDEX
    entries, errors = collect(args.root / "scripts")
    if not index.is_file():
        errors.append(f"{INDEX}: missing")
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    current = index.read_text(encoding="utf-8")
    try:
        expected = render(current, entries)
    except ScriptDocError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.write:
        index.write_text(expected, encoding="utf-8")
        print(f"wrote {INDEX} ({len(entries)} scripts)")
        return 0
    if current != expected:
        print(
            f"{INDEX} is stale — run `make generate-scripts-index` and commit the result",
            file=sys.stderr,
        )
        return 1
    print(f"{INDEX} up to date ({len(entries)} scripts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
