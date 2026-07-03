"""Parse Perseus TEI.2 XML into normalized chunks keyed by section milestones.

The Perseus Plato/Aristotle corpus uses TEI.2 with milestones for `book`, `section`,
and `page`. Section milestones carry the canonical locator (e.g. Stephanus `327a`
for Plato, Bekker analogs for Aristotle). We treat each section milestone as a
chunk boundary; speaker, book, and page are recorded as metadata.

Files come in three shapes:

* Single work: ``text > body > div1 ...`` (e.g. Republic, Laws).
* Group of works: ``text > group > text n="..." > body ...`` (e.g. Euthyphro,
  Apology, Crito, Phaedo packaged together).
* Per-letter divs: ``text > body > div1 type="Letter" n="N" ...`` (Letters).

Notes (footnotes) are excluded from running text. Beta-code Greek is preserved
verbatim; downstream consumers may transliterate to polytonic Unicode if desired.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

from .transliterate import (
    betacode_to_unicode as _betacode_to_unicode,
)
from .transliterate import (
    looks_like_betacode as _looks_like_betacode,
)

WHITESPACE_RE = re.compile(r"\s+")


@dataclasses.dataclass
class TeiWork:
    """A single addressable work inside a TEI bundle."""

    title: str
    container_type: str
    body: ET.Element


@dataclasses.dataclass
class Chunk:
    """One retrieval unit, keyed to a section locator."""

    chunk_id: str
    corpus: str
    author: str
    work: str
    lang: str
    section: str | None
    book: str | None
    page: str | None
    speaker: str | None
    text: str
    source_file: str
    translator: str | None
    edition_year: str | None
    # Optional citation-system override carried through ingest. When
    # set, ``store._resolve_work_refs`` writes it into the works row
    # the first time this Work is materialized. Most chunks leave
    # this ``None`` and inherit the corpus default — set explicitly
    # only when a single Work uses a different system from its
    # corpus, e.g. KrV (kant_ab) vs. the rest of Kant (paragraph).
    citation_system: str | None = None
    # Structural role of this chunk within its work. ``None`` (≡ "body")
    # is ordinary section/paragraph prose; structure-aware extractors set
    # "remark" (Hegel Anmerkung / Spinoza Scholium), "addition" (Hegel
    # Zusatz), "note" (footnote), or "blockquote". See
    # docs/block-structure-remediation-plan.md.
    block_type: str | None = None

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def _norm_text(s: str) -> str:
    return WHITESPACE_RE.sub(" ", s).strip()


def _header_text(root: ET.Element, xpath: str) -> str | None:
    el = root.find(xpath)
    if el is None:
        return None
    text = " ".join(el.itertext())
    text = _norm_text(text)
    return text or None


def _detect_lang(file_stem: str, root: ET.Element) -> str:
    # ISO 639-3 codes. The Perseus filenames still end in `_gr` / `_en`
    # (legacy two-letter) — that's a filename convention, not a stored
    # value. The returned code is what chunks.lang carries.
    if file_stem.endswith(("_gr", "_grc")):
        return "grc"
    if file_stem.endswith(("_en", "_eng")):
        return "eng"
    if file_stem.endswith(("_lat", "_la")):
        return "lat"
    title = _header_text(root, ".//teiHeader//titleStmt/title") or ""
    if "Greek" in title:
        return "grc"
    if "English" in title:
        return "eng"
    if "Latin" in title:
        return "lat"
    return "eng"


def _make_chunk_id(*parts: str) -> str:
    blob = "|".join(p or "" for p in parts).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=10).hexdigest()


def _dominant_speaker(buf: list[tuple[str, str | None]]) -> str | None:
    """First non-None speaker associated with non-whitespace text in `buf`."""

    for fragment, speaker in buf:
        if speaker and fragment.strip():
            return speaker
    return None


def _text_excluding_notes(el: ET.Element) -> str:
    """Concatenated text of ``el``, skipping ``<note>`` subtrees. Used for
    work titles so a glossing footnote inside a ``<head>`` (e.g. Plato's
    Epinomis, Epictetus' Fragments) doesn't get swallowed into the title."""
    return text_excluding(el, frozenset({"note"}))


def text_excluding(el: ET.Element, skip_tags: frozenset[str]) -> str:
    """Concatenated text of ``el``, skipping entire subtrees whose tag is
    in ``skip_tags``.

    Walks direct children only (not ``iter()``), so skipped elements'
    descendants are omitted and each child's ``tail`` (text after the
    closing tag, before the next sibling) is still collected. This is
    the shared implementation behind every "text excluding ``<note>``"
    parser — TEI.2 ``note``, namespaced TEI P5 ``{tei}note``, drama
    ``speaker``/``stage``, OSIS apparatus, etc.
    """

    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag not in skip_tags:
            parts.append(text_excluding(child, skip_tags))
        if child.tail:
            parts.append(child.tail)
    return " ".join(p for p in parts if p)


def _identify_works(root: ET.Element) -> list[TeiWork]:
    """Find each addressable work in the file."""

    text_el = root.find("text")
    if text_el is None:
        return []

    group = text_el.find("group")
    if group is not None:
        works: list[TeiWork] = []
        for sub in group.findall("text"):
            body = sub.find("body")
            if body is None:
                continue
            head = body.find("head")
            head_text = _norm_text(_text_excluding_notes(head)) if head is not None else None
            title = head_text or sub.get("n") or "untitled"
            works.append(TeiWork(title=title, container_type="dialogue", body=body))
        if works:
            return works

    body = text_el.find("body")
    if body is None:
        return []

    div1s = body.findall("div1")
    if div1s and all((d.get("type") or "").lower() == "letter" for d in div1s):
        out: list[TeiWork] = []
        for d in div1s:
            n = d.get("n") or "?"
            out.append(TeiWork(title=f"Letter {n}", container_type="letter", body=d))
        return out

    return [TeiWork(title="", container_type="single", body=body)]


def _detect_chunk_boundary_units(body: ET.Element) -> frozenset[str]:
    """Decide which milestone units fire as chunk boundaries for this
    body. Two policies coexist:

    * The Plato/Aristotle pattern: `unit="section"` (Stephanus letters)
      and `unit="bekker page"` (Bekker pagination) BOTH count as
      boundaries. Several Aristotle works (NE, Rhetoric, Virtues
      and Vices) carry both and rely on both for proper granularity.
    * The Homer pattern: `unit="card"` is the only chunk boundary.
      Used only when no section/bekker-page markers appear at all —
      otherwise stray cards in a section-chunked work (Aristotle
      Economics has 5) would re-split the work spuriously.
    """

    seen: set[str] = set()
    for ms in body.iter("milestone"):
        u = (ms.get("unit") or "").lower()
        if u:
            seen.add(u)
    section_family = seen & {"section", "bekker page"}
    if section_family:
        return frozenset(section_family)
    if "card" in seen:
        return frozenset({"card"})
    return frozenset()


class _ChunkBuilder:
    """Streaming chunker: walks a body element in document order."""

    def __init__(
        self,
        *,
        corpus: str,
        author: str,
        work: str,
        lang: str,
        source_file: str,
        translator: str | None,
        edition_year: str | None,
    ) -> None:
        self.meta_common = {
            "corpus": corpus,
            "author": author,
            "work": work,
            "lang": lang,
            "source_file": source_file,
            "translator": translator,
            "edition_year": edition_year,
        }
        # Buffered fragments paired with the speaker active at the time the
        # fragment was emitted. The speaker is captured here (not at flush
        # time) because <sp> push/pop happens around walk() but the flush
        # is anchored to section milestones, which can fire after the
        # original <sp> has already been popped.
        self._buf: list[tuple[str, str | None]] = []
        self._cur_section: str | None = None
        self._cur_book: str | None = None
        self._cur_page: str | None = None
        self._cur_speaker: str | None = None
        self._note_depth = 0
        self._cast_depth = 0
        # Set-apart text. Footnotes (<note>) and dramatis-personae lists
        # (<castList>) used to be DROPPED entirely; now their text is
        # collected here and emitted as block_type 'note'/'cast' chunks at
        # the next section flush — distinct from the running body text, which
        # is untouched, so main chunk_ids stay stable across the re-ingest.
        self._note_buf: list[str] = []
        self._cast_buf: list[str] = []
        self._pending_notes: list[str] = []
        self._pending_casts: list[str] = []
        self._aux_seq = 0  # monotonic per work → stable note/cast chunk_ids
        self._chunks: list[Chunk] = []
        # Set by walk() before _walk() recurses. Empty frozenset for
        # bodies with no chunk-boundary milestones (rare; the body
        # produces a single chunk).
        self._chunk_boundary_units: frozenset[str] = frozenset()

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    def _flush(self) -> None:
        text = _norm_text(" ".join(t for t, _ in self._buf))
        speaker = _dominant_speaker(self._buf)
        self._buf.clear()
        if text:
            meta = self.meta_common
            chunk_id = _make_chunk_id(
                meta["source_file"],
                meta["work"],
                meta["lang"],
                self._cur_book or "",
                self._cur_section or "",
                self._cur_page or "",
                text[:120],
            )
            # Transliterate Perseus beta-code Greek to polytonic Unicode
            # AFTER computing chunk_id, so re-ingests keep stable ids.
            # Migration 0006 already converted the existing in-DB chunks
            # in-place but didn't touch ingest, so without this hook a
            # new Greek author (Homer here, the LXX/NT later) would land
            # beta-code text and rely on the runtime display shim. Doing
            # it server-side at ingest matches what the UI expects and
            # lets term-occurrence byte-offsets land against the
            # displayable form.
            if meta["lang"] == "grc" and _looks_like_betacode(text):
                text = _betacode_to_unicode(text)
            self._chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    section=self._cur_section,
                    book=self._cur_book,
                    page=self._cur_page,
                    speaker=speaker,
                    text=text,
                    **meta,
                )
            )
        # Footnotes / cast lists captured during this section, emitted AFTER
        # the main chunk so reading order stays body-then-notes. The main
        # chunk's id is computed without block_type/seq (above), exactly as
        # before, so existing main chunk_ids — and their embeddings — survive
        # the re-ingest unchanged; only these aux chunks are new.
        self._emit_aux(self._pending_notes, "note")
        self._emit_aux(self._pending_casts, "cast")

    def _emit_aux(self, pending: list[str], block_type: str) -> None:
        meta = self.meta_common
        for text in pending:
            chunk_id = _make_chunk_id(
                meta["source_file"],
                meta["work"],
                meta["lang"],
                self._cur_book or "",
                self._cur_section or "",
                self._cur_page or "",
                block_type,
                str(self._aux_seq),
                text[:120],
            )
            self._aux_seq += 1
            if meta["lang"] == "grc" and _looks_like_betacode(text):
                text = _betacode_to_unicode(text)
            self._chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    section=self._cur_section,
                    book=self._cur_book,
                    page=self._cur_page,
                    speaker=None,
                    text=text,
                    block_type=block_type,
                    **meta,
                )
            )
        pending.clear()

    def _add_text(self, text: str | None) -> None:
        if not text:
            return
        if self._note_depth:
            self._note_buf.append(text)
        elif self._cast_depth:
            self._cast_buf.append(text)
        else:
            self._buf.append((text, self._cur_speaker))

    def walk(self, body: ET.Element) -> None:
        # Pre-scan to pick the milestone units that drive chunking for
        # this body. See _detect_chunk_boundary_units for the policy.
        self._chunk_boundary_units = _detect_chunk_boundary_units(body)
        self._walk(body)
        self._flush()

    def _walk(self, el: ET.Element) -> None:
        tag = el.tag

        if tag == "milestone":
            unit = (el.get("unit") or "").lower()
            n = el.get("n")
            # Section-boundary triggers vary by corpus:
            #   * Plato uses ``unit="section"`` for Stephanus letters
            #     (327a, 327b, …) — one chunk per Stephanus letter.
            #   * Aristotle uses ``unit="bekker page"`` for Bekker
            #     pagination (1094a, 1094b, 1095a, …) — one chunk per
            #     Bekker page. Without this, Aristotle TEI files
            #     collapse into one chunk per work because no
            #     `unit="section"` milestone ever fires.
            #   * Homer uses ``unit="card"`` for the traditional
            #     Perseus card-numbered chunks (~30–50 lines each;
            #     e.g. Il. 1.1 = book 1, card starting at line 1).
            #     The card's `n` is the starting line; combining with
            #     the surrounding `<div1 type="Book">` gives a clean
            #     `<book>.<line>` locator like "1.33".
            # Gate chunk-boundary milestones on the work's detected
            # set (see _detect_chunk_boundary_units). Without this, a
            # stray `unit="card"` in an otherwise section-chunked work
            # (Aristotle Economics has 5 cards inside a 28-section
            # body) would re-split the work.
            if unit in ("section", "bekker page") and n and unit in self._chunk_boundary_units:
                self._flush()
                self._cur_section = n
            elif unit == "card" and n and "card" in self._chunk_boundary_units:
                self._flush()
                self._cur_section = f"{self._cur_book}.{n}" if self._cur_book else n
            elif unit == "page" and n:
                self._cur_page = n
            elif unit == "bekker line" and n:
                # Line numbers aren't the chunk-boundary; they're a
                # secondary locator. Stash on `_cur_page` (the existing
                # secondary slot) so they get recorded but don't
                # split chunks.
                self._cur_page = n
            elif unit == "para":
                self._add_text(" ")
            return

        if tag == "div1":
            type_attr = (el.get("type") or "").lower()
            n = el.get("n")
            if (type_attr in {"book"} and n) or (
                type_attr in {"section"} and n and self._cur_book is None
            ):
                self._cur_book = n
            self._add_text(el.text)
            for child in el:
                self._walk(child)
                self._add_text(child.tail)
            return

        if tag == "head":
            return

        if tag == "castList":
            self._cast_depth += 1
            try:
                self._add_text(el.text)
                for child in el:
                    self._walk(child)
                    self._add_text(child.tail)
            finally:
                self._cast_depth -= 1
                if self._cast_depth == 0:
                    cast = _norm_text(" ".join(self._cast_buf))
                    self._cast_buf.clear()
                    if cast:
                        self._pending_casts.append(cast)
            return

        if tag == "note":
            self._note_depth += 1
            try:
                # Capture the note's own text + child tails (the original
                # handler walked children but never added this text, so even
                # before the drop-guard the note body was lost).
                self._add_text(el.text)
                for child in el:
                    self._walk(child)
                    self._add_text(child.tail)
            finally:
                self._note_depth -= 1
                if self._note_depth == 0:
                    note = _norm_text(" ".join(self._note_buf))
                    self._note_buf.clear()
                    if note:
                        self._pending_notes.append(note)
            return

        if tag == "sp":
            speaker_el = el.find("speaker")
            speaker = None
            if speaker_el is not None:
                speaker = _norm_text(" ".join(speaker_el.itertext())) or None
            previous = self._cur_speaker
            self._cur_speaker = speaker or previous
            try:
                self._add_text(el.text)
                for child in el:
                    if child.tag == "speaker":
                        self._add_text(child.tail)
                        continue
                    self._walk(child)
                    self._add_text(child.tail)
            finally:
                self._cur_speaker = previous
            return

        self._add_text(el.text)
        for child in el:
            self._walk(child)
            self._add_text(child.tail)


def parse_file(path: Path, *, corpus: str, author: str) -> Iterator[Chunk]:
    """Yield chunks for every section in every work of the TEI file."""

    tree = ET.parse(path)
    root = tree.getroot()
    lang = _detect_lang(path.stem, root)

    bundle_title = _header_text(root, ".//teiHeader//titleStmt/title") or ""
    # Two source-bibliography shapes appear in Perseus's TEI.2 for
    # different works:
    #   * `<sourceDesc><biblStruct><monogr><title>X</title>...</monogr></biblStruct>`
    #     — the modern shape used for most Plato and most Aristotle.
    #   * `<sourceDesc><bibl><title>X</title>...</bibl>` — the older flat
    #     shape used by Aristotle Constitution of Athens, Nicomachean
    #     Ethics, Virtues and Vices. Without this fallback the parser
    #     records `translator=None` for those three works, and the
    #     ingest layer's `_resolve_work_refs` mislabels them as
    #     "(Original)" since the translator field is missing.
    translator = _header_text(root, ".//sourceDesc//monogr/title") or _header_text(
        root, ".//sourceDesc/bibl/title"
    )
    edition_year = _header_text(root, ".//sourceDesc//monogr/imprint/date") or _header_text(
        root, ".//sourceDesc/bibl/date"
    )

    works = _identify_works(root)
    if not works:
        return

    for work in works:
        if work.title:
            work_title = work.title
        else:
            work_title = re.sub(r"\.\s*Machine readable text\s*$", "", bundle_title).strip()
            work_title = re.sub(r"\s*\(.*?\)\s*$", "", work_title).strip()
            if not work_title:
                work_title = path.stem

        builder = _ChunkBuilder(
            corpus=corpus,
            author=author,
            work=work_title,
            lang=lang,
            source_file=path.name,
            translator=translator,
            edition_year=edition_year,
        )
        builder.walk(work.body)
        yield from builder.chunks


def parse_dir(directory: Path, *, corpus: str, author: str) -> Iterable[Chunk]:
    for xml_path in sorted(directory.glob("*.xml")):
        yield from parse_file(xml_path, corpus=corpus, author=author)
