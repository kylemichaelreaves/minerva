"""Parser for verse-drama TEI P5 files from PerseusDL/canonical-greekLit.

The Greek tragedians (Aeschylus / Sophocles / Euripides) and the
English Loeb translations of their plays are encoded as TEI P5 with
EpiDoc. The body structure differs from prose treatises (which
``tei_p5.py`` handles) in three concrete ways:

1. **Text content is `<l n="N">` line elements**, not `<p>` paragraphs.
   Each line is numbered with the standard scholarly line count, so
   a citation reads "Soph. OT 873" not "Soph. OT, ¶12".
2. **`<sp>` blocks carry speaker attribution** via a `<speaker>`
   element. Tragedies and dialogues both use `<sp>`, but tragedy lines
   are tagged individually; in Plato they sit inside `<p>` paragraphs.
3. **Choral material lives in nested `<lg>` line groups** (strophe /
   antistrophe / epode). The line-numbering convention treats these
   as continuous with the spoken dialogue, so we ignore the `<lg>`
   wrapper and just gather every `<l>` in document order.

Chunking
--------
One chunk per **leaf** ``<div type="textpart">``. Inner divs (e.g.
``<textpart subtype="lyric">`` inside ``<textpart subtype="episode">``)
are walked recursively; only the innermost ones emit chunks. This
keeps chunks at scene-or-ode granularity (typically 10–80 lines),
which is the right size for retrieval — a whole choral ode is one
unit of meaning, a single line is not.

The chunk's ``section`` is ``"{subtype} {first}-{last}"`` (e.g.
``"lyric 217-247"``). When the subtype is missing or ``unknown``,
we fall back to just the line range. The dominant speaker (first
attested in the chunk) is captured in ``speaker``.

Hard-coded author/corpus/lang as parameters
-------------------------------------------
Unlike ``tei_p5.py`` (which hard-codes Aristotle), this parser takes
``corpus`` / ``author`` / ``lang`` from the caller so the same code
serves all three tragedians + their English translations.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from minerva.sources.tragedians import find_play
from minerva.tei import (
    Chunk,
    _make_chunk_id,
    _norm_text,
    guarded_parse_file,
    text_excluding,
)

from ..xml_safe import parse as _parse_xml

_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


_SPEAKER_TAG = "{http://www.tei-c.org/ns/1.0}speaker"
_STAGE_TAG = "{http://www.tei-c.org/ns/1.0}stage"


def _text_of(elem: ET.Element) -> str:
    """All text content beneath ``elem``, whitespace-normalised.

    Excludes ``<speaker>`` (the character name belongs in the chunk's
    ``speaker`` column, not its body) and ``<stage>`` (editorial stage
    directions aren't part of the line-numbered text). Uses the shared
    child-walk extractor so inline stage directions don't drop the prose
    that follows them."""

    return _norm_text(text_excluding(elem, frozenset({_SPEAKER_TAG, _STAGE_TAG})))


def _has_inner_textpart(elem: ET.Element) -> bool:
    """True when at least one direct ``<div type="textpart">`` child
    exists. Used by the walker to decide whether to recurse or emit."""

    return any(child.get("type") == "textpart" for child in elem.findall("tei:div", _NS))


def _gather_lines(elem: ET.Element) -> list[ET.Element]:
    """All ``<l>`` elements at any depth below ``elem``, in document
    order. We don't need to preserve the ``<sp>`` / ``<lg>`` wrappers
    in the chunk text — the line numbers carry the addressable
    citation, and the speaker is derived separately."""

    return list(elem.iter("{http://www.tei-c.org/ns/1.0}l"))


def _first_speaker(elem: ET.Element) -> str | None:
    """First ``<speaker>`` text found in document order beneath
    ``elem``. Tragedy speakers can change inside a single textpart
    (an episode has multiple ``<sp>`` turns), but the first speaker
    is the most useful single label for the chunk."""

    sp = elem.find(".//tei:sp/tei:speaker", _NS)
    if sp is None:
        return None
    text = _norm_text(" ".join(sp.itertext()))
    return text or None


def _line_range(lines: list[ET.Element]) -> tuple[str | None, str | None]:
    """Return ``(first_n, last_n)`` for the line range covered by
    these elements. Lines without a numeric ``@n`` are skipped — they
    occur for editorial stage directions and choral lacunae."""

    numbered = [ln.get("n", "").strip() for ln in lines if (ln.get("n") or "").strip()]
    if not numbered:
        return None, None
    return numbered[0], numbered[-1]


def _walk_textparts(
    elem: ET.Element,
    breadcrumb: list[tuple[str | None, str | None]],
) -> Iterator[tuple[list[tuple[str | None, str | None]], ET.Element]]:
    """Yield ``(breadcrumb, leaf_element)`` for every leaf textpart.

    Leaf = a textpart with no inner textparts. ``breadcrumb`` is the
    outer-to-inner subtype trail (kept for richer locator strings in
    the future, though we currently only consume the leaf's own
    subtype + line range)."""

    if not _has_inner_textpart(elem):
        yield breadcrumb, elem
        return
    for child in elem.findall("tei:div", _NS):
        if child.get("type") != "textpart":
            continue
        sub = child.get("subtype")
        n = child.get("n")
        yield from _walk_textparts(child, [*breadcrumb, (sub, n)])


def _format_section(
    subtype: str | None,
    first_line: str | None,
    last_line: str | None,
) -> str | None:
    """Locator like ``"episode 217-247"``. Single-line chunks (rare —
    fragments / stage directions) collapse to ``"episode 217"``. When
    no subtype is set we fall back to the raw line range so the
    citation is still useful."""

    label = (subtype or "").strip() or None
    if first_line and last_line:
        rng = first_line if first_line == last_line else f"{first_line}-{last_line}"
        return f"{label} {rng}" if label else rng
    return label


def parse_file(
    path: Path,
    *,
    corpus: str,
    author: str,
    lang: str,
    work: str,
    citation_system: str | None = None,
) -> Iterator[Chunk]:
    """Parse one canonical-greekLit verse-drama TEI P5 file into Chunks.

    ``work`` is the canonical play title (e.g. ``"Oedipus Tyrannus"``).
    ``citation_system`` overrides the corpus default when present —
    most callers can leave this ``None`` and let the corpus map decide.
    """

    tree = _parse_xml(path)
    root = tree.getroot()
    edition = root.find("tei:text/tei:body/tei:div", _NS)
    if edition is None:
        print(
            f"tei_drama: {path.name!r}: no edition root at text/body/div — skipping file",
            file=sys.stderr,
        )
        return

    # Editor / translator metadata. For Greek originals the editor name
    # gets recorded; for English, the translator is the named
    # contributor. Both come from ``<titleStmt><editor>`` in canonical-
    # greekLit's encoding convention.
    editor_el = root.find(
        "tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:editor",
        _NS,
    )
    editor_name = editor_el.text.strip() if editor_el is not None and editor_el.text else None
    date_el = root.find(
        "tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:date",
        _NS,
    )
    year = date_el.text.strip() if date_el is not None and date_el.text else None

    for _breadcrumb, leaf in _walk_textparts(edition, []):
        lines = _gather_lines(leaf)
        if not lines:
            continue
        first_line, last_line = _line_range(lines)
        subtype = leaf.get("subtype")
        section = _format_section(subtype, first_line, last_line)
        speaker = _first_speaker(leaf)
        text = _text_of(leaf)
        if not text:
            continue

        chunk_id = _make_chunk_id(
            path.name,
            work,
            lang,
            "",
            section or "",
            speaker or "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus=corpus,
            author=author,
            work=work,
            lang=lang,
            section=section,
            book=None,
            page=None,
            speaker=speaker,
            text=text,
            source_file=path.name,
            translator=editor_name,
            edition_year=year,
            citation_system=citation_system,
        )


# ── Directory-level driver ───────────────────────────────────────


# Filename → ISO 639-3 language code. The downloader writes
# ``{lang}.xml`` per the LANG_SUFFIX_CANDIDATES table, so the mapping
# is just file-stem → code.
_LANG_BY_FILENAME: dict[str, str] = {
    "grc.xml": "grc",
    "eng.xml": "eng",
}


def parse_dir(path: Path, *, corpus: str, author: str) -> Iterator[Chunk]:
    """Walk ``raw_xml_<corpus>/<play_slug>/{grc,eng}.xml`` and emit
    chunks for every play file found.

    ``corpus`` is the lower-case author slug (``"aeschylus"`` etc.) —
    matches the ``Chunk.corpus`` column and the directory name under
    ``perseus/``. ``author`` is the display name (``"Aeschylus"``).

    Unknown subdirectories (e.g. stray scratch files) are skipped
    with a warning rather than raising — the ingest CLI runs in batch
    over many corpora and one orphaned dir shouldn't abort the run."""

    if not path.is_dir():
        return

    for play_dir in sorted(path.iterdir()):
        if not play_dir.is_dir():
            continue
        play = find_play(corpus, play_dir.name)
        if play is None:
            # The slug isn't in the canonical catalogue. Most likely an
            # editorial mistake (typo, half-applied rename). Skip with
            # a print so it surfaces in the ingest log but doesn't
            # block the rest.
            print(f"  ⚠ skipping {play_dir.name}: not in tragedians.TRAGEDIANS[{corpus!r}]")
            continue
        for xml_file in sorted(play_dir.iterdir()):
            lang = _LANG_BY_FILENAME.get(xml_file.name)
            if lang is None:
                continue
            yield from guarded_parse_file(
                corpus,
                xml_file,
                lambda f=xml_file, ln=lang, w=play.title: parse_file(
                    f, corpus=corpus, author=author, lang=ln, work=w
                ),
            )
