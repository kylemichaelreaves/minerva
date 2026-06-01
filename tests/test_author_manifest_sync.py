"""Manifest ↔ generated author artifacts stay in sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from minerva import author_ordering, corpus_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data" / "authors" / "manifest.yaml"


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
