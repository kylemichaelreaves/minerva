"""#528: nothing pinned a Node version. CI floated `node-version: "22"`,
which resolves to the latest 22.x, so a local checkout could sit below a
dependency's floor while CI stayed green.

The floor is real and set by a direct dependency: `vite` declares
`^20.19.0 || >=22.12.0`, and 49 packages in the lockfile carry that
constraint or `>=20.19.0`. Node 22.0-22.11 satisfies `"22"` and violates
it.

`.nvmrc` is the single source of truth — CI reads it via
`node-version-file`, so those two cannot drift. What can still drift is
`.nvmrc` against the `engines` range, which is what this pins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _engines_node() -> str:
    return json.loads((_ROOT / "web" / "package.json").read_text())["engines"]["node"]


def _nvmrc() -> tuple[int, int, int]:
    raw = (_ROOT / ".nvmrc").read_text().strip().lstrip("v")
    parts = [int(p) for p in raw.split(".")]
    assert len(parts) == 3, f".nvmrc must pin an exact version, got {raw!r}"
    return parts[0], parts[1], parts[2]


def _satisfies(version: tuple[int, int, int], clause: str) -> bool:
    """Enough semver for the two clause shapes this repo uses."""

    clause = clause.strip()
    if m := re.fullmatch(r"\^(\d+)\.(\d+)\.(\d+)", clause):
        want = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return version[0] == want[0] and version >= want
    if m := re.fullmatch(r">=(\d+)\.(\d+)\.(\d+)", clause):
        return version >= (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise AssertionError(f"unhandled engines clause {clause!r}")


def test_nvmrc_pins_an_exact_version():
    major, minor, patch = _nvmrc()
    assert (major, minor, patch) > (0, 0, 0)


def test_nvmrc_satisfies_the_declared_engines_range():
    version = _nvmrc()
    clauses = _engines_node().split("||")
    assert any(_satisfies(version, c) for c in clauses), (
        f".nvmrc pins {version}, which satisfies none of {_engines_node()!r}"
    )


def test_engines_is_at_least_as_strict_as_vite():
    """vite is the direct dependency that sets the floor. If it moves,
    `engines` must move with it, or the pin protects nothing."""

    lock = json.loads((_ROOT / "web" / "package-lock.json").read_text())
    vite = lock["packages"].get("node_modules/vite", {})
    assert vite.get("engines", {}).get("node") == _engines_node(), (
        "web/package.json engines must match vite's declared node range"
    )


def test_ci_reads_the_pin_rather_than_floating_a_major():
    """The drift this issue is about: CI said `node-version: "22"`, which
    is satisfied by 22.0.0 and violates the 22.12.0 floor."""

    workflow = (_ROOT / ".github" / "workflows" / "check.yml").read_text()
    assert "node-version-file: .nvmrc" in workflow
    assert not re.search(r'node-version:\s*"?\d', workflow), (
        "a floating major reintroduces the gap .nvmrc closes"
    )
