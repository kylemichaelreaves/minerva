"""Tests for `minerva.sources.tei_p5`'s flat single-work directory layout.

Fixture markup is invented, but mirrors the EpiDoc shape First1KGreek
actually ships: `<div type="edition">` wrapping numbered
`<div type="textpart">` levels.
"""

from __future__ import annotations

from pathlib import Path

from minerva.sources import tei_p5

_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt>
  <title xml:lang="lat">Fabulae Aesopeae</title><author>Babrius</author>
</titleStmt></fileDesc></teiHeader>
<text><body>
<div type="edition" xml:lang="grc" n="urn:cts:greekLit:tlg0614.tlg001.1st1K-grc1">
 <div type="textpart" subtype="book" n="1">
  <div type="textpart" subtype="section" n="1">
   <p>A fable of some length, standing in for one of Babrius's choliambs.</p>
  </div>
 </div>
</div>
</body></text></TEI>
"""


def _write(dirpath: Path, name: str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    p.write_text(_TEI)
    return p


def test_flat_layout_derives_the_work_title_from_the_file_stem(tmp_path: Path):
    """The existing rule, pinned because the override below must not
    change it: `phaedrus_lat.xml` has been ingested as `Phaedrus` since
    2026-05-29 and retitling it would move all of its chunk_ids."""

    _write(tmp_path / "aesop", "phaedrus_lat.xml")
    chunks = list(tei_p5.parse_dir(tmp_path / "aesop"))
    assert chunks
    assert {c.work for c in chunks} == {"Phaedrus"}
    assert {c.author for c in chunks} == {"Aesop"}


def test_a_work_title_override_applies_to_the_named_file_only(tmp_path: Path):
    """Babrius's Greek is one half of a work whose English half is
    `Fables (Babrius)`; the stem would title it `Babrius` and split the
    pair in two. The override is keyed by filename so it cannot reach
    Phaedrus, which sits in the same directory (#398)."""

    d = tmp_path / "aesop"
    _write(d, "babrius_grc.xml")
    _write(d, "phaedrus_lat.xml")
    chunks = list(tei_p5.parse_dir(d, work_titles={"babrius_grc.xml": "Fables (Babrius)"}))
    by_file = {c.source_file: c.work for c in chunks}
    assert by_file == {"babrius_grc.xml": "Fables (Babrius)", "phaedrus_lat.xml": "Phaedrus"}


def test_an_override_for_a_file_that_is_not_there_changes_nothing(tmp_path: Path):
    """A stale entry must not suppress or rename the files that are."""

    _write(tmp_path / "aesop", "phaedrus_lat.xml")
    chunks = list(tei_p5.parse_dir(tmp_path / "aesop", work_titles={"gone_grc.xml": "Ghost"}))
    assert {c.work for c in chunks} == {"Phaedrus"}


def test_the_aesop_ingest_source_carries_the_title_overrides(tmp_path: Path):
    """The wiring, not the mechanism. `parse_dir` takes the overrides as
    an argument, so a registry entry that reverts to the bare
    `_module_parse_dir("sources.tei_p5")` would title Babrius's Greek
    from its file stem again and silently split the pair in two — with
    every grc `chunk_id` moving on the next ingest (#398)."""

    from minerva.ingest.registry import INGEST_SOURCES

    d = tmp_path / "aesop"
    _write(d, "babrius_grc.xml")
    _write(d, "phaedrus_lat.xml")
    (source,) = [s for s in INGEST_SOURCES if s.id == "aesop"]
    by_file = {c.source_file: c.work for c in source.parse(d)}
    assert by_file == {"babrius_grc.xml": "Fables (Babrius)", "phaedrus_lat.xml": "Phaedrus"}
