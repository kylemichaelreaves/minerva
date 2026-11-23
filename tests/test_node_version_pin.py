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

#760: and `.nvmrc` against every installed package's own `engines.node`.
Checking `engines` and vite alone left CI on 22.21.1 while jsdom@30 and
three of its dependencies required `^22.22.2`, so this also walks the
lockfile.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _engines_node() -> str:
    return json.loads((_ROOT / "web" / "package.json").read_text())["engines"]["node"]


def _nvmrc() -> tuple[int, int, int]:
    raw = (_ROOT / ".nvmrc").read_text().strip().lstrip("v")
    parts = [int(p) for p in raw.split(".")]
    assert len(parts) == 3, f".nvmrc must pin an exact version, got {raw!r}"
    return parts[0], parts[1], parts[2]


# One clause of an npm `engines.node` range: `*`, `>=X[.Y[.Z]]` (optional
# space and `v`), `^X[.Y[.Z]]` with X > 0, or a bare major `X`. These are
# every shape in web/package-lock.json (68 distinct ranges, #760), plus a
# trailing `.*`/`.x` wildcard, which is the same range with it dropped:
# get-caller-file@2 declares `6.* || 8.* || >= 10.*`, arriving with
# rollup-plugin-visualizer's yargs. npm also has `<`, `~`, hyphens and
# space-joined comparators; none occur, and an unknown shape raises rather
# than passing the gate.
_CLAUSE = re.compile(r"(?P<op>>=|\^)?\s*v?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?")


def _satisfies_clause(version: tuple[int, int, int], clause: str) -> bool:
    if clause == "*":
        return True
    m = _CLAUSE.fullmatch(re.sub(r"(?:\.[*xX])+$", "", clause))
    if m is None:
        raise ValueError(f"unhandled engines clause {clause!r}")
    floor = (int(m["major"]), int(m["minor"] or 0), int(m["patch"] or 0))
    if m["op"] == ">=":
        return version >= floor
    if m["op"] == "^" and floor[0] > 0:
        return version[0] == floor[0] and version >= floor
    if m["op"] is None and m["minor"] is None:
        return version[0] == floor[0]
    # `^0.y.z` caps at the minor in npm, and a bare `X.Y` means `X.Y.x`.
    # Neither occurs; refuse rather than guess.
    raise ValueError(f"unhandled engines clause {clause!r}")


def _satisfies(version: tuple[int, int, int], node_range: str) -> bool:
    """Whether *version* satisfies an npm `engines.node` range."""

    return any(_satisfies_clause(version, c.strip()) for c in node_range.split("||"))


def test_nvmrc_pins_an_exact_version():
    major, minor, patch = _nvmrc()
    assert (major, minor, patch) > (0, 0, 0)


def test_nvmrc_satisfies_the_declared_engines_range():
    version = _nvmrc()
    assert _satisfies(version, _engines_node()), (
        f".nvmrc pins {version}, which satisfies none of {_engines_node()!r}"
    )


def test_every_installed_package_accepts_the_pinned_node():
    """#760: the two tests above only compare `.nvmrc` with `engines` and
    `engines` with vite, so a transitive package can raise the floor past the
    pin unseen. jsdom@30 did — `^22.22.2 || ^24.15.0 || >=26.0.0` against a
    22.21.1 pin — and the only signal was an EBADENGINE warning in `npm ci`."""

    version = _nvmrc()
    lock = json.loads((_ROOT / "web" / "package-lock.json").read_text())
    refused = sorted(
        f"{path.removeprefix('node_modules/') or 'web'} ({node_range})"
        for path, meta in lock["packages"].items()
        if (node_range := meta.get("engines", {}).get("node"))
        and not _satisfies(version, node_range)
    )
    assert not refused, (
        f".nvmrc pins {'.'.join(map(str, version))}, which these installed "
        f"packages don't support: {refused}"
    )


def test_engines_is_at_least_as_strict_as_vite():
    """vite is the direct dependency that sets the floor. If it moves,
    `engines` must move with it, or the pin protects nothing."""

    lock = json.loads((_ROOT / "web" / "package-lock.json").read_text())
    vite = lock["packages"].get("node_modules/vite", {})
    assert vite.get("engines", {}).get("node") == _engines_node(), (
        "web/package.json engines must match vite's declared node range"
    )


@pytest.mark.parametrize(
    ("node_range", "version", "expected"),
    [
        (">=18", (18, 0, 0), True),
        (">=18", (17, 9, 9), False),
        (">= 12.0.0", (12, 0, 0), True),
        (">=v12.22.7", (12, 22, 7), True),
        (">=v12.22.7", (12, 22, 6), False),
        (">=14.17", (14, 17, 0), True),
        (">=14.17", (14, 16, 9), False),
        ("^10", (10, 9, 9), True),
        ("^10", (11, 0, 0), False),
        ("^13.7", (13, 7, 0), True),
        ("^13.7", (13, 6, 9), False),
        ("^13.7", (14, 0, 0), False),
        ("18 || 20 || >=22", (19, 0, 0), False),
        ("18 || 20 || >=22", (20, 5, 1), True),
        ("*", (0, 0, 1), True),
        ("16.x", (16, 4, 0), True),
        ("16.x", (17, 0, 0), False),
        # get-caller-file@2's range, the first wildcard in the lock.
        ("6.* || 8.* || >= 10.*", (8, 1, 0), True),
        ("6.* || 8.* || >= 10.*", (9, 0, 0), False),
        ("6.* || 8.* || >= 10.*", (22, 23, 2), True),
        # The range that #760 is about: jsdom@30's floor.
        ("^22.22.2 || ^24.15.0 || >=26.0.0", (22, 21, 1), False),
        ("^22.22.2 || ^24.15.0 || >=26.0.0", (22, 23, 2), True),
        ("^22.22.2 || ^24.15.0 || >=26.0.0", (23, 0, 0), False),
        ("^22.22.2 || ^24.15.0 || >=26.0.0", (26, 1, 0), True),
    ],
)
def test_satisfies_reads_npm_engine_ranges(node_range, version, expected):
    assert _satisfies(version, node_range) is expected


@pytest.mark.parametrize("node_range", ["<16", "~14.17.0", ">=12 <16", "^0.1.0", "16.2.x"])
def test_satisfies_refuses_a_range_shape_it_cannot_read(node_range):
    """A shape this parser doesn't know must fail the gate, not pass it."""

    with pytest.raises(ValueError, match="unhandled"):
        _satisfies((22, 0, 0), node_range)


def test_ci_reads_the_pin_rather_than_floating_a_major():
    """The drift this issue is about: CI said `node-version: "22"`, which
    is satisfied by 22.0.0 and violates the 22.12.0 floor."""

    workflow = (_ROOT / ".github" / "workflows" / "check.yml").read_text()
    assert "node-version-file: .nvmrc" in workflow
    assert not re.search(r'node-version:\s*"?\d', workflow), (
        "a floating major reintroduces the gap .nvmrc closes"
    )


# --- #605: npm is pinned too ------------------------------------------------
#
# The lock carries `libc` blocks that npm 11 writes and npm 10 strips. Node
# 22.23.2 ships npm 10.9.8, so every bare `npm install` on the pinned Node
# deleted 26 of them (78 lines) and staged that into whatever PR was open;
# Dependabot, on npm 11, put them back on its next bump. The Node pin does
# not pin npm, so npm gets its own: `packageManager` names it, `engines.npm`
# with `engine-strict` makes an older npm refuse to install rather than
# silently rewrite the lock, and CI installs the named version.


def _web_package() -> dict:
    return json.loads((_ROOT / "web" / "package.json").read_text())


def _pinned_npm() -> str:
    pm = _web_package().get("packageManager", "")
    m = re.fullmatch(r"npm@(\d+\.\d+\.\d+)", pm)
    assert m, f"web/package.json packageManager must pin an exact npm, got {pm!r}"
    return m[1]


def test_package_manager_pins_an_npm_that_writes_libc():
    """npm 10 is the one that strips them; 11.12.1 was measured keeping all 26."""

    assert int(_pinned_npm().split(".")[0]) >= 11


def test_engines_npm_floor_is_the_pinned_npm():
    assert _web_package()["engines"].get("npm") == f">={_pinned_npm()}"


def test_engines_are_enforced_not_advisory():
    """Without `engine-strict` an older npm prints EBADENGINE and rewrites
    the lock anyway — the silent failure this is here to stop."""

    npmrc = (_ROOT / "web" / ".npmrc").read_text().splitlines()
    assert "engine-strict=true" in npmrc


def test_ci_installs_the_pinned_npm_before_every_npm_ci():
    """setup-node installs the npm bundled with `.nvmrc`'s Node (10.9.8),
    which `engine-strict` now refuses."""

    workflow = (_ROOT / ".github" / "workflows" / "check.yml").read_text()
    jobs = re.split(r"\n  (?=[\w-]+:\n)", workflow)
    with_ci = [j for j in jobs if re.search(r"^\s*run: npm ci\s*$", j, re.MULTILINE)]
    assert with_ci
    for job in with_ci:
        install = job.find("npm install -g")
        assert 0 <= install < job.find("run: npm ci"), job.splitlines()[0]
        assert "packageManager" in job[install : job.find("\n", install)], (
            "read the version from package.json rather than restating it"
        )
