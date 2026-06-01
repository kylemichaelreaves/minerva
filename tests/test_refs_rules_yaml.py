"""YAML-backed author mention rules."""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo, apply_rules_to_chunk
from minerva.refs.rules.loader import load_author_rules_from_yaml, spec_path_for_author


def test_gobineau_yaml_spec_loads() -> None:
    path = spec_path_for_author("Gobineau")
    rules = load_author_rules_from_yaml(path, prefix="gobineau")
    names = {r.name for r in rules if hasattr(r, "name")}
    assert "gobineau_boulainvilliers" in names
    assert "gobineau_hegel" in names


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
