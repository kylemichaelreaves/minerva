"""Parse Perseus TEI.2 XML into normalized chunks keyed by section milestones.

The Perseus Plato/Aristotle corpus uses TEI.2 with milestones for `book`, `section`,
and `page`. Section milestones carry the canonical locator (e.g. Stephanus `327a`
for Plato, Bekker analogs for Aristotle). We treat each section milestone as a
chunk boundary; speaker, book, and page are recorded as metadata.

**A body carrying no boundary milestone at all chunks at its
``type="chapter"`` divisions instead** (#176). Perseus's English Epictetus
is that whole case here — 4 of the 6 works in the two Epictetus files,
against 0 of the 22 Aristotle and Homer works — and without the fallback
the only boundary left was ``<div1 type="book">``: the *Discourses* ran to
a 151,427-char chunk against a 125-char median. A body whose milestones
fire never consults its chapters, so no existing ``chunk_id`` moves.

Files come in three shapes:

* Single work: ``text > body > div1 ...`` (e.g. Republic, Laws).
* Group of works: ``text > group > text n="..." > body ...`` (e.g. Euthyphro,
  Apology, Crito, Phaedo packaged together).
* Per-letter divs: ``text > body > div1 type="Letter" n="N" ...`` (Letters).

Notes (footnotes) are excluded from running text and emitted as separate
``block_type="note"`` chunks. Beta-code Greek is transliterated to polytonic
Unicode here, *after* the ``chunk_id`` is computed so ids stay stable — this
paragraph used to say it was "preserved verbatim" for downstream consumers to
convert, which stopped being true when `_flush` gained that hook.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

from .authors import plato_titles
from .transliterate import (
    betacode_to_unicode as _betacode_to_unicode,
)
from .transliterate import (
    looks_like_betacode as _looks_like_betacode,
)
from .xml_safe import parse as _parse_xml

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
    # Subordinate per-edition/translation display title, when the
    # canonical ``work`` title differs from what this edition calls it —
    # e.g. canonical Plato work "Politeia" whose English translation is
    # locally titled "Republic". Written to editions/translations
    # .title_local by the store; NOT part of the chunk_id hash (display
    # metadata only). See authors/plato_titles.py.
    title_local: str | None = None

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


# Back matter that a TEI file ships as a sibling ``<text>`` alongside the
# real works, and which must not become a work of its own. Perseus's
# English Epictetus does exactly this: after the Discourses, Enchiridion
# and Fragments comes ``<text lang="en" n="index"><head>Index.</head>``,
# 8,495 characters of "Academics, deny the evidence of the senses, i.
# 193." — page-number apparatus, ingested and retrievable as though
# Epictetus wrote it (#177).
#
# A dense list of proper names and topic words is a magnet for BM25: it
# contains *every* topic term in the volume by construction, with no
# prose to dilute it. That is #165's failure mode in its purest form.
#
# Matched on the ``n`` attribute and on the head, because neither is
# reliably present — the Epictetus index carries both, but a file with
# only one still needs catching.
_APPARATUS_TEXT_IDS = frozenset(
    {"index", "indices", "contents", "toc", "errata", "corrigenda", "addenda"}
)
_APPARATUS_TITLES = frozenset(
    {
        "index", "indices", "general index", "index of names",
        "index of passages", "contents", "table of contents",
        "errata", "corrigenda", "addenda",
    }
)


def _is_apparatus_text(sub: ET.Element, title: str) -> bool:
    """True when a ``<group>`` sub-text is back matter rather than a work."""

    if (sub.get("n") or "").strip().lower() in _APPARATUS_TEXT_IDS:
        return True
    # "Index." — the trailing period is typographic, not part of the name.
    return title.strip().rstrip(".").lower() in _APPARATUS_TITLES


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
            if _is_apparatus_text(sub, title):
                # Loud, because the alternative is what happened for
                # months: apparatus sitting in the corpus as a work, found
                # only by auditing single-token work titles.
                print(
                    f"tei: skipping back matter {title!r} "
                    f"(<text n={sub.get('n')!r}>) — not a work.",
                    file=sys.stderr,
                )
                continue
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


# Milestone units that name their own citation series rather than a
# position in a shared one: the Greek *Fragmenta*'s `unit="Fragment"`
# (Schenkl's *Fr.* 1-36) and `unit="Sententia"` (the two Stobaeus
# gnomologia). Unlike `section`/`card`, the number alone does not
# identify the passage — `Fragment 9` and `Sententia 9` are different
# texts — so the series name goes into `section` with it (#395).
_NAMED_SERIES_UNITS = frozenset({"fragment", "sententia"})


def _detect_chunk_boundary_units(body: ET.Element) -> frozenset[str]:
    """Decide which milestone units fire as chunk boundaries for this
    body. Three policies coexist:

    * The Plato/Aristotle pattern: `unit="section"` (Stephanus letters)
      and `unit="bekker page"` (Bekker pagination) BOTH count as
      boundaries. Several Aristotle works (NE, Rhetoric, Virtues
      and Vices) carry both and rely on both for proper granularity.
    * The Homer pattern: `unit="card"` is the only chunk boundary.
      Used only when no section/bekker-page markers appear at all —
      otherwise stray cards in a section-chunked work (Aristotle
      Economics has 5) would re-split the work spuriously.
    * The Epictetus *Fragmenta* pattern: a named series
      (`_NAMED_SERIES_UNITS`). Last, and for the same reason `card` is
      not first — a stray `Fragment` inside a section-chunked body must
      not re-split it.

    Note the units are read but filtered, so "no boundary unit" never
    means "no milestones". #395 read `frozenset()` here as the latter and
    reported the *Fragmenta*'s 111 well-formed milestones as unit-less.
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
    return frozenset(seen & _NAMED_SERIES_UNITS)


# `<div1>`/`<div2>`/`<div3>` — TEI.2 numbers its division levels rather
# than nesting one `<div>`, so the chapter level sits at a different depth
# per work (Epictetus's *Discourses* at `div2`, its *Enchiridion* at
# `div1`).
_DIV_TAGS = frozenset({"div1", "div2", "div3"})


def _has_chapter_divisions(body: ET.Element) -> bool:
    """Whether this body carries `type="chapter"` divisions with numbers.

    Only consulted for bodies where `_detect_chunk_boundary_units` found
    nothing — see `_ChunkBuilder.walk`.
    """

    for tag in _DIV_TAGS:
        for el in body.iter(tag):
            if (el.get("type") or "").lower() == "chapter" and el.get("n"):
                return True
    return False


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
        title_local: str | None = None,
    ) -> None:
        self.meta_common = {
            "corpus": corpus,
            "author": author,
            "work": work,
            "lang": lang,
            "source_file": source_file,
            "translator": translator,
            "edition_year": edition_year,
            # Subordinate display title (spread into every Chunk; excluded
            # from _make_chunk_id, so it never churns ids).
            "title_local": title_local,
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
        # bodies with no chunk-boundary milestones — Perseus's English
        # Epictetus is the whole of that case in the corpora this parser
        # reads (4 of 6 works in the two Epictetus files; 0 of 22 across
        # Aristotle and Homer). Those bodies fall back to their chapter
        # divisions; see _chapter_fallback below.
        self._chunk_boundary_units: frozenset[str] = frozenset()
        # Chunk at `type="chapter"` divisions instead. Set by walk() only
        # when no boundary milestone fired for this body, so a work whose
        # milestones work keeps its existing chunk_ids.
        self._chapter_fallback = False

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
        # Without milestones the only boundary left is `<div1 type="book">`,
        # which made whole books single chunks: the English *Discourses*
        # ran to 151,427 characters against a 125-char median. Chapters are
        # the citable unit on that side anyway (*Disc.* II.18 = book 2,
        # chapter 18), and the Greek is already finer than this.
        self._chapter_fallback = not self._chunk_boundary_units and _has_chapter_divisions(body)
        self._walk(body)
        self._flush()

    def _walk(self, el: ET.Element) -> None:
        tag = el.tag

        if self._chapter_fallback and tag in _DIV_TAGS:
            n = el.get("n")
            if (el.get("type") or "").lower() == "chapter" and n:
                # Flush before the section moves, exactly as a milestone
                # does — the buffered tail belongs to the chapter that has
                # just ended. Falls through to the tag handlers below,
                # which still walk the children and stamp `book`.
                self._flush()
                self._cur_section = n

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
            elif unit in _NAMED_SERIES_UNITS and n and unit in self._chunk_boundary_units:
                # The series name is part of the citation, so it is kept —
                # from the source's own spelling of the unit, not a
                # synthesised abbreviation. See _NAMED_SERIES_UNITS.
                self._flush()
                self._cur_section = f"{el.get('unit')} {n}"
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
                # Flush BEFORE reassigning, or the still-buffered tail of
                # the previous book gets stamped with this one's number
                # (#207). Chunking is driven by section/card milestones,
                # not by `div1`, so at a boundary the previous book's last
                # milestone-chunk is sitting in `_buf` waiting for the
                # next milestone to flush it — by which time `_cur_book`
                # has already moved on. `section` was unaffected because
                # it is captured at the milestone itself.
                #
                # Usually the next milestone's `_flush()` then finds an
                # empty buffer and emits nothing, so only the `book` value
                # changes — 293 chunks across the five tei.py corpora, one
                # per boundary where the tail spilled. In 7 places the
                # buffer holds text that no later milestone would have
                # flushed separately, so a chunk that used to be merged
                # into the *next* book is now emitted under its own: 3 in
                # Aristotle (Metaphysics/grc, NE/grc) and 4 in Epictetus
                # (Discourses/eng). That is the correct division — the text
                # belongs to the book it was written in — but it does mean
                # this is not a pure re-stamp.
                #
                # Either way `book` is an input to `_make_chunk_id`, so
                # every corrected chunk gets a new id and loses its
                # embedding / lemma / cross-reference rows on the next
                # ingest. 293 of 35,241 (0.83%).
                if n != self._cur_book:
                    self._flush()
                self._cur_book = n
            elif self._chunk_boundary_units & _NAMED_SERIES_UNITS:
                # A named series numbers each division from 1, so `book`
                # is what keeps two runs of it apart — and in the
                # *Fragmenta* the two gnomologia divisions carry no `n`,
                # leaving both stamped with the first division's "0" and
                # citing identically. Their `<head>` is the only thing in
                # the source that tells them apart, so it stands in for
                # the missing number. Confined to bodies chunked by a
                # named series: `head` is prose, and promoting it to a
                # locator anywhere else is how Babrius ended up with 409
                # chunks labelled with an OCR'd apparatus line (#398).
                head = el.find("head")
                label = _norm_text("".join(head.itertext())) if head is not None else ""
                if label and label != self._cur_book:
                    self._flush()
                    self._cur_book = label
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

    tree = _parse_xml(path)
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
        print(
            f"tei: {path.name!r}: no addressable works found "
            f"(missing <text> or <body> root elements?)",
            file=sys.stderr,
        )
        return

    for work in works:
        if work.title:
            work_title = work.title
        else:
            work_title = re.sub(r"\.\s*Machine readable text\s*$", "", bundle_title).strip()
            work_title = re.sub(r"\s*\(.*?\)\s*$", "", work_title).strip()
            if not work_title:
                work_title = path.stem

        # Canonicalize Plato work titles to their Latinized-Greek names so
        # the Greek original, English translation, and German translation
        # of a dialogue resolve to ONE works row. The raw title (beta-code
        # for grc, anglicized for eng) is kept as the subordinate
        # title_local so each edition can still show its own title.
        title_local: str | None = None
        if corpus == "plato":
            canonical = plato_titles.canonical_for(work_title)
            if canonical is not None:
                title_local = plato_titles.local_title(canonical, lang)
                work_title = canonical

        builder = _ChunkBuilder(
            corpus=corpus,
            author=author,
            work=work_title,
            lang=lang,
            source_file=path.name,
            translator=translator,
            edition_year=edition_year,
            title_local=title_local,
        )
        builder.walk(work.body)
        yield from builder.chunks


def guarded_parse_file(
    label: str, path: Path, produce: Callable[[], Iterable[Chunk]]
) -> Iterator[Chunk]:
    """Yield chunks from ``produce()``, but convert any per-file parse
    error into a recorded ``record_parse_failure`` and skip that file.

    This is the isolation contract every dir-walker must use: one
    malformed/truncated XML file must never abort a whole (potentially
    multi-corpus) ingest. The older ``tei_*``/``osis``/``hebrew_mt``
    walkers called ``parse_file`` unguarded and would hard-abort the
    entire run on a single bad file (issue #45); route them through
    here so they degrade to a partial ingest like ``parse_dir`` does.
    """
    from .corpus.pipeline import record_parse_failure

    try:
        yield from produce()
    except Exception as exc:
        record_parse_failure(f"{label}: failed to parse {path.name!r}: {exc}")


def parse_dir(directory: Path, *, corpus: str, author: str) -> Iterable[Chunk]:
    for xml_path in sorted(directory.glob("*.xml")):
        yield from guarded_parse_file(
            corpus, xml_path, lambda p=xml_path: parse_file(p, corpus=corpus, author=author)
        )
