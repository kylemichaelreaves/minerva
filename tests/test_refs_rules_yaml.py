"""YAML-backed author mention rules."""

from __future__ import annotations

import pytest

from minerva.refs.rules import ChunkInfo, apply_rules_to_chunk
from minerva.refs.rules.loader import load_author_rules_from_yaml, spec_path_for_author


def test_gobineau_yaml_spec_loads() -> None:
    path = spec_path_for_author("Gobineau")
    rules = load_author_rules_from_yaml(path, prefix="gobineau")
    names = {r.name for r in rules if hasattr(r, "name")}
    assert "gobineau_boulainvilliers" in names
    assert "gobineau_hegel" in names


def test_hegel_rules_come_from_module_not_yaml() -> None:
    """Regression: a proof-of-concept specs/hegel.yaml (4 rules) used to
    silently shadow rules/hegel.py (31 rules) because the loader
    preferred YAML. The YAML is gone; the module must win."""
    from minerva.refs import rules as refs_rules

    refs_rules._AUTHOR_RULES_CACHE.pop("Hegel", None)
    rules = refs_rules._rules_for_author("Hegel")
    names = {r.name for r in rules if hasattr(r, "name")}
    assert "hegel_kant" in names
    assert "hegel_spinoza" in names
    assert len(rules) > 10


def test_author_with_both_yaml_and_module_raises(monkeypatch, tmp_path) -> None:
    from minerva.refs import rules as refs_rules
    from minerva.refs.rules import loader

    shadow = tmp_path / "hume.yaml"
    shadow.write_text("author: Hume\nmentions: []\n", encoding="utf-8")
    monkeypatch.setattr(loader, "spec_path_for_author", lambda author: shadow)
    refs_rules._AUTHOR_RULES_CACHE.pop("Hume", None)
    try:
        with pytest.raises(RuntimeError, match="defined twice"):
            refs_rules._rules_for_author("Hume")
    finally:
        refs_rules._AUTHOR_RULES_CACHE.pop("Hume", None)


def test_gobineau_yaml_rule_scans_chunk() -> None:
    chunk = ChunkInfo(
        chunk_id="g1",
        author="Gobineau",
        work="Essai",
        lang="fra",
        section="I",
        text="Comme l'a montré Boulainvilliers, la conquête franque divise deux races.",
    )
    cands = apply_rules_to_chunk(chunk)
    authors = {c.target_author for c in cands}
    assert "Boulainvilliers" in authors
