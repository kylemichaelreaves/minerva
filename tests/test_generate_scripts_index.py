"""#505: `docs/SCRIPTS.md` named 4 of 43 scripts and read as complete.

It is now generated from each script's own module docstring (Python) or
leading comment block (shell), and each script declares a `Role:` of
`workflow` or `oneoff`. These tests pin the parsing and the `--check`
path that fails `make check` when the index is stale or a script is
undocumented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_scripts_index as gsi  # noqa: E402

PY_WORKFLOW = '''#!/usr/bin/env python3
"""Do the recurring thing, wrapped
across two lines.

Longer explanation that is not the summary.

Role: workflow
"""

print("hi")
'''

PY_ONEOFF = '''"""Repair a | pipe-bearing corpus once.

Role: oneoff
"""
'''

SH_WORKFLOW = """#!/usr/bin/env bash
# Snapshot the thing before you break it.
#
# Usage:
#   scripts/thing.sh <reason>
#
# Role: workflow

set -e
echo hi
"""

INDEX_SKELETON = f"""# Operator scripts

Hand-written preamble that the generator must keep.

{gsi.BEGIN}
{gsi.END}

Hand-written epilogue, also kept.
"""


def _tree(tmp_path: Path, files: dict[str, str], index: str | None = INDEX_SKELETON) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    for name, body in files.items():
        (tmp_path / "scripts" / name).write_text(body)
    if index is not None:
        (tmp_path / "docs" / "SCRIPTS.md").write_text(index)
    return tmp_path


# --- parsing ---------------------------------------------------------------


def test_python_summary_is_the_first_paragraph_on_one_line(tmp_path: Path):
    path = tmp_path / "a.py"
    path.write_text(PY_WORKFLOW)

    entry = gsi.parse_script(path)

    assert entry.name == "a.py"
    assert entry.summary == "Do the recurring thing, wrapped across two lines."
    assert entry.role == "workflow"


def test_shell_header_is_parsed_like_a_docstring(tmp_path: Path):
    path = tmp_path / "thing.sh"
    path.write_text(SH_WORKFLOW)

    entry = gsi.parse_script(path)

    assert entry.summary == "Snapshot the thing before you break it."
    assert entry.role == "workflow"


def test_shell_header_stops_at_the_first_code_line(tmp_path: Path):
    path = tmp_path / "late.sh"
    path.write_text("#!/bin/sh\n# Summary.\nset -e\n# Role: oneoff\n")

    with pytest.raises(gsi.ScriptDocError, match="no `Role:` line"):
        gsi.parse_script(path)


def test_missing_docstring_is_an_error(tmp_path: Path):
    path = tmp_path / "bare.py"
    path.write_text("print('no docstring')\n")

    with pytest.raises(gsi.ScriptDocError, match="no module docstring"):
        gsi.parse_script(path)


def test_missing_role_is_an_error(tmp_path: Path):
    path = tmp_path / "norole.py"
    path.write_text('"""Has a summary but no role."""\n')

    with pytest.raises(gsi.ScriptDocError, match="no `Role:` line"):
        gsi.parse_script(path)


def test_unknown_role_is_an_error(tmp_path: Path):
    path = tmp_path / "odd.py"
    path.write_text('"""Summary.\n\nRole: sometimes\n"""\n')

    with pytest.raises(gsi.ScriptDocError, match="sometimes"):
        gsi.parse_script(path)


def test_two_role_lines_is_an_error(tmp_path: Path):
    path = tmp_path / "twice.py"
    path.write_text('"""Summary.\n\nRole: workflow\nRole: oneoff\n"""\n')

    with pytest.raises(gsi.ScriptDocError, match="more than one"):
        gsi.parse_script(path)


# --- rendering ---------------------------------------------------------------


def test_render_keeps_the_hand_written_text_and_splits_by_role(tmp_path: Path):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW, "b.py": PY_ONEOFF, "thing.sh": SH_WORKFLOW})

    entries, errors = gsi.collect(root / "scripts")
    assert errors == []
    text = gsi.render((root / "docs" / "SCRIPTS.md").read_text(), entries)

    assert text.startswith("# Operator scripts\n\nHand-written preamble")
    assert text.rstrip().endswith("Hand-written epilogue, also kept.")
    workflow, oneoff = text.split("### One-off")
    assert "[`a.py`](../scripts/a.py)" in workflow
    assert "[`thing.sh`](../scripts/thing.sh)" in workflow
    assert "b.py" not in workflow
    assert "[`b.py`](../scripts/b.py)" in oneoff
    # A pipe in a summary would split the table cell.
    assert r"Repair a \| pipe-bearing corpus once." in oneoff


def test_angle_brackets_outside_code_spans_are_escaped(tmp_path: Path):
    """`minerva.<author>_works` in a summary would render as an unknown
    HTML tag, and the word would vanish from the page."""

    path = tmp_path / "x.py"
    path.write_text('"""Fail on minerva.<author>_works, not `<code>`.\n\nRole: oneoff\n"""\n')

    text = gsi.render(INDEX_SKELETON, [gsi.parse_script(path)])

    assert "minerva.&lt;author>_works, not `<code>`." in text


def test_render_is_idempotent(tmp_path: Path):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW})
    entries, _ = gsi.collect(root / "scripts")

    once = gsi.render(INDEX_SKELETON, entries)

    assert gsi.render(once, entries) == once


def test_render_without_markers_is_an_error():
    with pytest.raises(gsi.ScriptDocError, match="markers"):
        gsi.render("# no markers here\n", [])


def test_only_top_level_py_and_sh_are_indexed(tmp_path: Path):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW, "notes.txt": "x"})
    (root / "scripts" / "githooks").mkdir()
    (root / "scripts" / "githooks" / "pre-commit").write_text("#!/bin/sh\n")

    entries, _ = gsi.collect(root / "scripts")

    assert [e.name for e in entries] == ["a.py"]


# --- --write / --check ---------------------------------------------------------


def test_write_then_check_passes(tmp_path: Path, capsys):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW, "b.py": PY_ONEOFF})

    assert gsi.main(["--write", "--root", str(root)]) == 0
    assert gsi.main(["--check", "--root", str(root)]) == 0
    assert "up to date" in capsys.readouterr().out


def test_check_fails_when_the_index_is_stale(tmp_path: Path, capsys):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW})
    assert gsi.main(["--write", "--root", str(root)]) == 0

    # A new script lands without anyone regenerating the index.
    (root / "scripts" / "b.py").write_text(PY_ONEOFF)

    assert gsi.main(["--check", "--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "stale" in err
    assert "make generate-scripts-index" in err


def test_check_fails_when_a_summary_changes(tmp_path: Path):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW})
    assert gsi.main(["--write", "--root", str(root)]) == 0

    (root / "scripts" / "a.py").write_text(PY_WORKFLOW.replace("recurring", "weekly"))

    assert gsi.main(["--check", "--root", str(root)]) == 1


def test_check_fails_and_names_an_undocumented_script(tmp_path: Path, capsys):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW})
    assert gsi.main(["--write", "--root", str(root)]) == 0
    (root / "scripts" / "bare.py").write_text("print(1)\n")

    assert gsi.main(["--check", "--root", str(root)]) == 1
    assert "bare.py: no module docstring" in capsys.readouterr().err


def test_write_refuses_while_a_script_is_undocumented(tmp_path: Path):
    root = _tree(tmp_path, {"bare.py": "print(1)\n"})
    before = (root / "docs" / "SCRIPTS.md").read_text()

    assert gsi.main(["--write", "--root", str(root)]) == 1
    assert (root / "docs" / "SCRIPTS.md").read_text() == before


def test_check_fails_when_the_index_is_missing(tmp_path: Path, capsys):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW}, index=None)

    assert gsi.main(["--check", "--root", str(root)]) == 1
    assert "SCRIPTS.md" in capsys.readouterr().err


def test_no_mode_prints_usage(tmp_path: Path):
    root = _tree(tmp_path, {"a.py": PY_WORKFLOW})

    with pytest.raises(SystemExit):
        gsi.main(["--root", str(root)])


# --- the real tree -------------------------------------------------------------


def test_the_committed_index_is_current():
    """The same assertion `make check-scripts-index` makes, so a stale
    index also fails the pytest run CI already does."""

    assert gsi.main(["--check"]) == 0
