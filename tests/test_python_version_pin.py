"""#758: CI floated `python-version: "3.13"` and ran `uv sync -p 3.13`, so
it tested whichever 3.13.x the runner image carried (3.13.15 on 2026-10-06)
while `.python-version` pinned 3.13.12. Every `uv run --no-sync` step then
warned that the environment did not satisfy the pin.

Same shape as the Node pin (#528, `tests/test_node_version_pin.py`): the pin
file is the single source of truth and CI reads it rather than restating a
version.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "check.yml"


def test_python_version_pins_an_exact_version():
    raw = (_ROOT / ".python-version").read_text().strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", raw), f".python-version must be exact, got {raw!r}"


def test_every_setup_python_step_reads_the_pin():
    workflow = _WORKFLOW.read_text()
    steps = workflow.count("uses: actions/setup-python@")
    assert steps > 0
    assert workflow.count("python-version-file: .python-version") == steps
    assert not re.search(r'^\s*python-version:\s*"?\d', workflow, re.MULTILINE), (
        "a floating minor installs whatever patch release the runner carries"
    )


def test_uv_sync_does_not_override_the_pin():
    """`-p 3.13` outranks `.python-version` for the sync, so the venv can be
    built on a different patch release from the one `uv run` then asks for."""

    syncs = re.findall(r"uv sync[^\n]*", _WORKFLOW.read_text())
    assert syncs
    assert not [s for s in syncs if re.search(r"\s(-p|--python)\b", s)], syncs
