"""The model wheels stay out of the resolution graph, and stay pinned (#282).

`uv sync --locked` verifies the lock against `pyproject.toml`, and for a
`direct+https` source that verification re-derives the package's metadata by
fetching the wheel — for *every* URL dependency in the graph, whatever extra
is being installed. So a model wheel declared in the `lemma` extra made
`uv sync --locked --extra dev` reach github.com and huggingface.co on every
CI job, and a 429 from either failed the PR, docs-only diffs included.

Measured, cold cache, no network:

    uv sync --locked --extra dev --dry-run --offline   # before: fails on the first URL wheel
    uv sync --locked --extra dev --dry-run --offline   # after:  resolves in 2ms

The fix moved the five wheels to `lemma-models.txt`. That buys the network
independence and costs `uv.lock`'s hash verification, so the integrity
guarantees #122 established have to be carried by that file instead. These
tests hold both ends: nothing may put a URL dependency back into the graph,
and every entry in the requirements file stays hash-pinned.

Pure file reads — no network, no uv invocation.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
MODELS = ROOT / "lemma-models.txt"

# Hosts that rate-limit and are not a package index. A `direct+https` entry
# pointing at one of these is the #282 defect by construction.
MODEL_HOST_PATTERNS = ("huggingface.co", "spacy-models/releases")

EXPECTED_MODELS = {
    "de_core_news_sm",
    "en_core_web_sm",
    "fr_core_news_sm",
    "grc_dep_web_sm",
    "la_core_web_sm",
}


def _requirement_lines() -> list[str]:
    return [
        line.strip()
        for line in MODELS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class TestResolutionGraphHasNoUrlDependencies:
    def test_no_extra_declares_a_url_requirement(self):
        """A URL requirement in *any* extra reintroduces the fetch, so this
        is deliberately broader than the five model wheels."""

        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        offenders = [
            (extra, req)
            for extra, reqs in data["project"]
            .get("optional-dependencies", {})
            .items()
            for req in reqs
            if "@ http" in req
        ]
        assert offenders == [], (
            "URL requirements are back in an extra; `uv sync --locked` will "
            f"fetch them on every CI job (#282): {offenders}"
        )

    def test_core_dependencies_declare_no_url_requirement(self):
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        offenders = [r for r in data["project"].get("dependencies", []) if "@ http" in r]
        assert offenders == [], f"URL requirements in core dependencies: {offenders}"

    @pytest.mark.parametrize("pattern", MODEL_HOST_PATTERNS)
    def test_uv_lock_is_free_of_model_hosts(self, pattern):
        """The lock is the thing `--locked` walks. If a model host is in it,
        the fetch is back regardless of what `pyproject.toml` says."""

        text = UV_LOCK.read_text(encoding="utf-8")
        assert pattern not in text, (
            f"`{pattern}` is back in uv.lock — `uv sync --locked` will fetch "
            "from it during the lock check on every CI job (#282). Run "
            "`uv lock` after removing the URL dependency."
        )


class TestModelWheelsStayPinned:
    """What leaving the lock costs, and what `lemma-models.txt` owes in
    exchange (#122)."""

    def test_every_expected_model_is_present(self):
        names = {line.split("@")[0].strip() for line in _requirement_lines()}
        assert names == EXPECTED_MODELS, (
            "lemma-models.txt no longer matches the models `lemmatize.py` "
            f"loads. Present: {sorted(names)}"
        )

    @pytest.mark.parametrize("line", _requirement_lines(), ids=lambda s: s.split("@")[0].strip())
    def test_requirement_carries_a_sha256_fragment(self, line):
        """Without the fragment there is no integrity check anywhere: the
        lock is gone and a model wheel executes its own code on install."""

        assert re.search(r"#sha256=[0-9a-f]{64}$", line), (
            f"missing or malformed `#sha256=` fragment: {line[:90]}"
        )

    @pytest.mark.parametrize("line", _requirement_lines(), ids=lambda s: s.split("@")[0].strip())
    def test_huggingface_urls_are_commit_pinned(self, line):
        """`resolve/main` is a mutable branch — the bytes behind such a URL
        can be replaced in place, and `la_core_web_sm-3.9.4` was pinned that
        way and has since been deleted outright."""

        if "huggingface.co" not in line:
            pytest.skip("not a HuggingFace URL")
        assert "/resolve/main/" not in line, f"mutable `resolve/main` pin: {line[:90]}"
        assert re.search(r"/resolve/[0-9a-f]{40}/", line), (
            f"HuggingFace URL is not pinned to a 40-char commit SHA: {line[:90]}"
        )

    def test_no_requirement_is_unversioned(self):
        """Each URL names its version in the wheel filename; a bare package
        name here would silently resolve from PyPI instead."""

        for line in _requirement_lines():
            assert "@ https://" in line, f"not a pinned URL requirement: {line[:90]}"
