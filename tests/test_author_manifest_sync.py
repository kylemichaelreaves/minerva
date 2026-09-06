"""Manifest ↔ generated author artifacts stay in sync."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from minerva import author_ordering, corpus_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data" / "authors" / "manifest.yaml"

_spec = importlib.util.spec_from_file_location(
    "generate_author_artifacts", REPO_ROOT / "scripts" / "generate_author_artifacts.py"
)
assert _spec is not None
assert _spec.loader is not None
codegen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(codegen)

_ARTIFACTS = ("CORPUS_REGISTRY", "AUTHOR_ORDERING", "ATLAS_DATA", "DOMINANT_PHIL")


@pytest.fixture
def sandboxed_artifacts(tmp_path, monkeypatch):
    """Copy the four generated artifacts into tmp_path and point the
    codegen's path constants at the copies, so a write cannot touch the
    real tree."""

    copies = {}
    for name in _ARTIFACTS:
        real = getattr(codegen, name)
        dst = tmp_path / real.name
        shutil.copy(real, dst)
        monkeypatch.setattr(codegen, name, dst)
        copies[name] = dst
    return copies


def _stale_region(path: Path, begin: str, end: str, marker: str) -> None:
    """Replace a file's generated region with a marker, so that a write
    to that file is detectable even when the manifest is in sync."""

    text = path.read_text(encoding="utf-8")
    text, n = re.subn(
        re.escape(begin) + r".*?" + re.escape(end),
        lambda _m: f"{begin}\n{marker}\n{end}",
        text,
        count=1,
        flags=re.DOTALL,
    )
    assert n == 1
    path.write_text(text, encoding="utf-8")


def _load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_codegen_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_author_artifacts.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_manifest_corpora_match_registry() -> None:
    manifest = _load_manifest()
    manifest_ids = {c["id"] for c in manifest["corpora"]}
    registry_ids = {e.id for e in corpus_registry.CORPORA}
    assert manifest_ids == registry_ids


def test_manifest_authors_match_ordinal_keys() -> None:
    manifest = _load_manifest()
    manifest_names = {a["display_name"] for a in manifest["authors"]}
    assert manifest_names == set(author_ordering.AUTHOR_ORDINAL.keys())


def test_every_author_has_corpus_id_in_manifest() -> None:
    manifest = _load_manifest()
    corpus_ids = {c["id"] for c in manifest["corpora"]}
    for author in manifest["authors"]:
        assert author["corpus_id"] in corpus_ids, author["display_name"]


class TestCodegenWriteSafety:
    """#503. Two defects in `scripts/generate_author_artifacts.py`, both
    reachable only through `--write` — `check_sync` compares with
    `re.search` and a string equality, so `--check` (what CI runs) never
    sees either.
    """

    @pytest.mark.parametrize(
        "block",
        [
            r'RE = re.compile(r"\d+\s")',  # raises: bad escape \d
            r"A = '\\'",  # silently collapses to a single backslash
            r"B = '\g<0>'",  # substitutes the ENTIRE matched region back in
            r"C = '\1'",  # raises: invalid group reference
        ],
    )
    def test_replace_region_emits_the_block_verbatim(self, tmp_path, block) -> None:
        # Generated code is content, not an `re` replacement template.
        target = tmp_path / "target.py"
        target.write_text("head\n# BEGIN X\nold\n# END X\ntail\n", encoding="utf-8")
        out = codegen._replace_region(target, "# BEGIN X", "# END X", block)
        emitted = out.split("# BEGIN X\n", 1)[1].rsplit("\n# END X", 1)[0]
        assert emitted == block

    def test_apply_writes_is_all_or_nothing(self, sandboxed_artifacts) -> None:
        # The failure `_replace_region` exists to raise on — a missing or
        # duplicated sentinel — must not leave earlier files rewritten,
        # because those four files are what the sync gate compares.
        _stale_region(
            sandboxed_artifacts["CORPUS_REGISTRY"],
            codegen.BEGIN_CORPORA,
            codegen.END_CORPORA,
            "STALE_MARKER",
        )
        broken = sandboxed_artifacts["AUTHOR_ORDERING"]
        broken.write_text(
            broken.read_text(encoding="utf-8").replace(
                codegen.END_ORDINAL, "# END SOMETHING_ELSE"
            ),
            encoding="utf-8",
        )
        manifest = _load_manifest()

        with pytest.raises(RuntimeError, match="Markers"):
            codegen.apply_writes(manifest)

        assert "STALE_MARKER" in sandboxed_artifacts["CORPUS_REGISTRY"].read_text(
            encoding="utf-8"
        ), "the first file was rewritten before the second was validated"

    def test_apply_writes_still_writes_all_four_when_valid(
        self, sandboxed_artifacts
    ) -> None:
        for name, (begin, end) in {
            "CORPUS_REGISTRY": (codegen.BEGIN_CORPORA, codegen.END_CORPORA),
            "AUTHOR_ORDERING": (codegen.BEGIN_ORDINAL, codegen.END_ORDINAL),
            "ATLAS_DATA": (codegen.BEGIN_ATLAS, codegen.END_ATLAS),
            "DOMINANT_PHIL": (codegen.BEGIN_DOMINANT, codegen.END_DOMINANT),
        }.items():
            _stale_region(sandboxed_artifacts[name], begin, end, "STALE_MARKER")

        codegen.apply_writes(_load_manifest())

        for name in _ARTIFACTS:
            text = sandboxed_artifacts[name].read_text(encoding="utf-8")
            assert "STALE_MARKER" not in text, name
