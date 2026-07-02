"""Tests for the Kant Anmerkung typing post-pass in ``split_zeno``
(2026-07 block-structure remediation, item 6).

Kant sets his Anmerkungen apart with standalone head lines; the zeno
paragraph stream used to emit those heads as tiny untyped chunks and
leave the remark bodies indistinguishable from the main argument.
``_type_kant_remarks`` types head + body ``block_type='remark'`` until
the next structural head. Typing only — text and chunk_ids unchanged
(the whole point: embeddings survive the re-ingest).
"""

from __future__ import annotations

from minerva.corpus.split_zeno import _type_kant_remarks
from minerva.tei import Chunk


def _chunk(text: str, n: int) -> Chunk:
    return Chunk(
        chunk_id=f"c{n}",
        corpus="kant",
        author="Kant",
        work="Kritik der praktischen Vernunft",
        lang="deu",
        section=f"§ 3. Lehrsatz II, ¶{n}",
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file="kpv_de.html",
        translator="(Original)",
        edition_year="1788",
    )


def _types(texts: list[str]) -> list[str | None]:
    chunks = [_chunk(t, i + 1) for i, t in enumerate(texts)]
    return [c.block_type for c in _type_kant_remarks(chunks)]


def test_anmerkung_head_types_following_paragraphs() -> None:
    # The real § 3 Lehrsatz II shape: proposition → Folgerung →
    # Anmerkung I → Anmerkung II, remarks running to the page end.
    types = _types(
        [
            "§ 3. Lehrsatz II",
            "Alle materiale praktische Prinzipien sind insgesamt von einer Art.",
            "Folgerung",
            "Alle materiale praktische Regeln setzen den Bestimmungsgrund voraus.",
            "Anmerkung I",
            "Man muß sich wundern, wie sonst scharfsinnige Männer …",
            "Anmerkung II",
            "Glücklich zu sein, ist notwendig das Verlangen jedes Wesens.",
        ]
    )
    assert types == [None, None, None, None, "remark", "remark", "remark", "remark"]


def test_structural_head_closes_the_remark() -> None:
    types = _types(
        [
            "Anmerkung",
            "Der Begriff der Freiheit, sofern dessen Realität bewiesen ist.",
            "Beweis",
            "Die reine Vernunft ist für sich allein praktisch.",
        ]
    )
    assert types == ["remark", "remark", None, None]


def test_kasuistische_fragen_and_enumerated_heads_close() -> None:
    # Tugendlehre shape: remark → casuistical questions → enumerated
    # sub-head ("II. Vom Geize") both return to the main voice.
    types = _types(
        [
            "Anmerkung",
            "Eine Tugendpflicht läßt sich nicht erzwingen.",
            "Kasuistische Fragen",
            "Ist es erlaubt, sich der Not zu entziehen?",
        ]
    )
    assert types == ["remark", "remark", None, None]
    types = _types(
        [
            "Anmerkung",
            "Vom moralischen Eigennutz und seiner Grenze.",
            "II. Vom Geize",
            "Verschwendung und Kargheit sind beide verwerflich.",
        ]
    )
    assert types == ["remark", "remark", None, None]


def test_allgemeine_anmerkung_opens_a_remark() -> None:
    # MAN/KU/Religion long-form heads ("Allgemeine Anmerkung zur
    # Dynamik", the Religion parerga) are remark openers too.
    types = _types(
        [
            "Der Raum ist bloß die Form äußerer Anschauung.",
            "Allgemeine Anmerkung zur Dynamik",
            "Die allgemeine Aufgabe der Naturwissenschaft überhaupt.",
        ]
    )
    assert types == [None, "remark", "remark"]


def test_inline_anmerkung_mention_does_not_trigger() -> None:
    types = _types(
        [
            "Diese Anmerkung, welche bloß die Methode betrifft, ist von Wichtigkeit.",
            "Sie erklärt den veranlassenden Grund aller Verwirrungen.",
        ]
    )
    assert types == [None, None]


def test_typing_preserves_chunk_ids_and_text() -> None:
    chunks = [_chunk("Anmerkung", 1), _chunk("Der Text der Anmerkung.", 2)]
    out = list(_type_kant_remarks(chunks))
    assert [c.chunk_id for c in out] == ["c1", "c2"]
    assert [c.text for c in out] == ["Anmerkung", "Der Text der Anmerkung."]
