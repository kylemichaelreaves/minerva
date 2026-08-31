"""Chunk granularity in the verse-drama parser (#176, batch 4-op).

``tei_drama.py`` emits one chunk per **leaf** ``<div type="textpart">`` and its
docstring states the intent: "scene-or-ode granularity (typically 10-80
lines), which is the right size for retrieval". The leaf unit does not deliver
that. Measured on the live index, this parser owns **39 of the 44** ragged
``.xml`` work/lang pairs — max/median chunk size within a work >= 20x:

    Euripides Heracles    eng   85 chunks  median   135  max 11,404   (84x)
    Sophocles Trachiniae  grc   35 chunks  median   263  max 10,862   (41x)
    Euripides Cyclops     grc   18 chunks  median   206  max 10,510   (51x)

The giant chunks are single leaf textparts spanning 200+ lines —
``lyric 1204-1425``, ``choral 205-496``, ``episode 82-355`` — because the
source's textpart nesting is uneven: some leaves are one lyric line, others
are a whole episode. 87 tragedian chunks exceed 8,000 characters.

The fix splits an oversized leaf at ``<sp>`` speech boundaries, which is the
natural dramatic unit and one the parser already understands (it derives
``speaker`` from the first ``<sp>``). A leaf that is already within budget is
untouched, so its ``chunk_id`` does not churn.

This is the parser's first chunking test; it had none.
"""

from __future__ import annotations

from pathlib import Path

from minerva.sources import tei_drama

_TEI_NS = "http://www.tei-c.org/ns/1.0"


def _speech(speaker: str, first: int, count: int, line_text: str) -> str:
    lines = "\n".join(f'<l n="{first + i}">{line_text} {first + i}</l>' for i in range(count))
    return f"<sp><speaker>{speaker}</speaker>\n{lines}\n</sp>"


def _play(inner: str) -> str:
    return (
        f'<TEI xmlns="{_TEI_NS}">'
        "<teiHeader><fileDesc><titleStmt><editor>E. Ditor</editor></titleStmt>"
        "<sourceDesc><date>1913</date></sourceDesc></fileDesc></teiHeader>"
        f'<text><body><div type="edition">{inner}</div></body></text>'
        "</TEI>"
    )


def _write(tmp_path: Path, inner: str) -> Path:
    p = tmp_path / "grc.xml"
    p.write_text(_play(inner), encoding="utf-8")
    return p


def _parse(path: Path):
    return list(
        tei_drama.parse_file(
            path, corpus="euripides", author="Euripides", lang="grc", work="Heracles"
        )
    )


def test_a_leaf_within_budget_is_one_chunk(tmp_path: Path) -> None:
    """The common case, and the churn guard: a textpart that is already the
    right size keeps being exactly one chunk."""

    inner = (
        '<div type="textpart" subtype="episode" n="1">'
        + _speech("ΣΙΛΗΝΟΣ", 1, 6, "γραμμη")
        + "</div>"
    )
    chunks = _parse(_write(tmp_path, inner))

    assert len(chunks) == 1
    assert chunks[0].section == "episode 1-6"


def test_an_oversized_leaf_splits_at_speech_boundaries(tmp_path: Path) -> None:
    """The defect. One leaf holding several long speeches became one chunk of
    200+ lines; it now becomes one chunk per speech group, each addressable by
    its own line range."""

    long_line = "ΓΡΑΜΜΗ " * 60  # ~420 chars per line
    inner = (
        '<div type="textpart" subtype="episode" n="1">'
        + _speech("ΣΙΛΗΝΟΣ", 1, 12, long_line)
        + _speech("ΟΔΥΣΣΕΥΣ", 13, 12, long_line)
        + _speech("ΧΟΡΟΣ", 25, 12, long_line)
        + "</div>"
    )
    chunks = _parse(_write(tmp_path, inner))

    assert len(chunks) > 1, "oversized leaf was not split"
    assert all(len(c.text) <= tei_drama.MAX_CHUNK_CHARS for c in chunks), [
        len(c.text) for c in chunks
    ]
    # Every line stays addressable: the ranges tile the leaf without gaps.
    assert chunks[0].section is not None and chunks[0].section.startswith("episode 1-")
    assert chunks[-1].section is not None and chunks[-1].section.endswith("-36")


def test_split_chunks_carry_their_own_speaker(tmp_path: Path) -> None:
    """A split is only worth making if the pieces are correctly attributed —
    otherwise every piece inherits the leaf's first speaker and the speaker
    column becomes wrong for all but the first."""

    long_line = "ΓΡΑΜΜΗ " * 60
    inner = (
        '<div type="textpart" subtype="episode" n="1">'
        + _speech("ΣΙΛΗΝΟΣ", 1, 12, long_line)
        + _speech("ΟΔΥΣΣΕΥΣ", 13, 12, long_line)
        + "</div>"
    )
    chunks = _parse(_write(tmp_path, inner))

    speakers = [c.speaker for c in chunks]
    assert speakers[0] == "ΣΙΛΗΝΟΣ"
    assert "ΟΔΥΣΣΕΥΣ" in speakers


def test_an_oversized_leaf_without_speeches_still_splits(tmp_path: Path) -> None:
    """Choral odes are bare ``<l>`` runs with no ``<sp>`` wrapper, so a
    speech-boundary rule alone would leave them whole — which is exactly the
    ``choral 205-496`` case measured on Trachiniae."""

    long_line = "ΓΡΑΜΜΗ " * 60
    lines = "\n".join(f'<l n="{i}">{long_line} {i}</l>' for i in range(1, 40))
    inner = f'<div type="textpart" subtype="choral" n="1">{lines}</div>'
    chunks = _parse(_write(tmp_path, inner))

    assert len(chunks) > 1, "choral ode with no <sp> was not split"
    assert all(len(c.text) <= tei_drama.MAX_CHUNK_CHARS for c in chunks)


def test_every_line_survives_the_split(tmp_path: Path) -> None:
    """The invariant that matters most: splitting must not drop text. The
    concatenated pieces contain every line number the leaf held."""

    long_line = "ΓΡΑΜΜΗ " * 60
    inner = (
        '<div type="textpart" subtype="episode" n="1">'
        + _speech("ΣΙΛΗΝΟΣ", 1, 10, long_line)
        + _speech("ΟΔΥΣΣΕΥΣ", 11, 10, long_line)
        + _speech("ΧΟΡΟΣ", 21, 10, long_line)
        + "</div>"
    )
    chunks = _parse(_write(tmp_path, inner))

    joined = " ".join(c.text for c in chunks)
    for n in range(1, 31):
        assert f"ΓΡΑΜΜΗ {n}" in joined or f" {n}" in joined, f"line {n} lost"


def test_a_speechless_sp_does_not_invent_a_speaker(tmp_path: Path) -> None:
    """Not every ``<sp>`` carries a ``<speaker>`` — canonical-greekLit uses a
    bare ``<sp>`` for continuations and for choral interjections whose speaker
    is implied. Such a segment must contribute no speaker rather than raise or
    borrow the previous one, and the group falls back to the next segment that
    does name one."""

    long_line = "ΓΡΑΜΜΗ " * 60
    anon = "<sp>" + "\n".join(f'<l n="{i}">{long_line} {i}</l>' for i in range(1, 13)) + "</sp>"
    inner = (
        '<div type="textpart" subtype="episode" n="1">'
        + anon
        + _speech("ΧΟΡΟΣ", 13, 12, long_line)
        + "</div>"
    )
    chunks = _parse(_write(tmp_path, inner))

    assert len(chunks) > 1
    assert chunks[0].speaker is None
    assert "ΧΟΡΟΣ" in [c.speaker for c in chunks]
