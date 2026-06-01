"""Descartes splitter — paragraph-aware across named sections.

Three works share one shape: a sequence of named sections (Préface,
Abrégé, Med. I, Partie II, …) where each section's body is plain
paragraphs separated by blank lines. We walk the text linearly,
detect a section heading via per-CorpusWork regex tables, and emit one
:class:`Chunk` per paragraph within each section.

Section labels in the emitted chunks read like ``"Méd. III §5"`` /
``"Partie II §3"`` — major division plus a §-numbered paragraph
within. The `book` field carries the bare major division so the
Reader can group by it; the `section` field carries the full
combined label that goes into citations.

Per-section paragraph counters reset at each new section, so §
indices are stable across re-runs of the splitter against the same
source text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# Per-CorpusWork section ordering and matching. Each entry is a tuple of
# (display_label, regex). The regex matches the heading line as it
# appears in the per-work file. Order matters: we walk the headings
# in declared sequence and split the source on each successive
# match, so a misordered table will produce empty/mis-attributed
# sections. The "intro" front-matter (editor's bracket-italic note
# at the top of each downloaded file) is intentionally NOT given a
# heading entry — text before the first matched heading is dropped
# rather than chunked under a synthetic label.
_SECTIONS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "meditationes": [
        ("Praefatio", re.compile(r"^Praefatio ad lectorem\.\s*$", re.MULTILINE)),
        ("Synopsis", re.compile(r"^Synopsis sex sequentium meditationum\.\s*$", re.MULTILINE)),
        ("Med. I", re.compile(r"^Meditatio I\.\s*", re.MULTILINE)),
        ("Med. II", re.compile(r"^Meditatio II\.\s*", re.MULTILINE)),
        ("Med. III", re.compile(r"^Meditatio III\.\s*", re.MULTILINE)),
        ("Med. IV", re.compile(r"^Meditatio IV\.\s*", re.MULTILINE)),
        ("Med. V", re.compile(r"^Meditatio V\.\s*", re.MULTILINE)),
        ("Med. VI", re.compile(r"^Meditatio VI\.\s*", re.MULTILINE)),
    ],
    "discours": [
        ("Partie I", re.compile(r"^PREMIÈRE PARTIE\.\s*$", re.MULTILINE)),
        ("Partie II", re.compile(r"^SECONDE PARTIE\.\s*$", re.MULTILINE)),
        ("Partie III", re.compile(r"^TROISIÈME PARTIE\.\s*$", re.MULTILINE)),
        ("Partie IV", re.compile(r"^QUATRIÈME PARTIE\.\s*$", re.MULTILINE)),
        ("Partie V", re.compile(r"^CINQUIÈME PARTIE\.\s*$", re.MULTILINE)),
        ("Partie VI", re.compile(r"^SIXIÈME PARTIE\.\s*$", re.MULTILINE)),
    ],
    "meditations_fr": [
        # Cousin's Tome I prints the Méditation headings in slightly
        # inconsistent shape: the first (with accent) and the sixth
        # (without accent) drop a different vowel. The patterns
        # tolerate both spellings so we don't have to fix the source.
        ("Épître", re.compile(r"^\s*A MESSIEURS\s*$", re.MULTILINE)),
        ("Préface", re.compile(r"^\s*PRÉFACE\s*$", re.MULTILINE)),
        ("Abrégé", re.compile(r"^\s*ABRÉGÉ\s*$", re.MULTILINE)),
        ("Méd. I", re.compile(r"^PREMIÈRE MÉDITATION\.\s*$", re.MULTILINE)),
        ("Méd. II", re.compile(r"^MÉDITATION SECONDE\.\s*$", re.MULTILINE)),
        ("Méd. III", re.compile(r"^MÉDITATION TROISIÈME\.?\s*$", re.MULTILINE)),
        ("Méd. IV", re.compile(r"^MÉDITATION QUATRIÈME\.\s*$", re.MULTILINE)),
        ("Méd. V", re.compile(r"^MÉDITATION CINQUIÈME\.\s*$", re.MULTILINE)),
        ("Méd. VI", re.compile(r"^M[EÉ]DITATION SIXIÈME\.\s*$", re.MULTILINE)),
    ],
}


# Italic editorial intro paragraph at the top of each downloaded file
# starts with leading 4-space indent and an italicized opening line
# like "_Ce discours, écrit en français..._" — drop it by treating
# every leading blank/indented line up to the first section heading
# as not-a-paragraph (already handled: we don't emit pre-heading text
# at all).


# Splits a section body into paragraphs at runs of 2+ newlines. We
# join the lines within a paragraph with a single space afterwards;
# raw line breaks inside a paragraph are extraction artefacts from
# Gutenberg's hard-wrap, not the author's structure.
_BLANK_RE = re.compile(r"\n\s*\n+")


def _paragraphs(section_body: str) -> list[str]:
    parts = _BLANK_RE.split(section_body)
    out: list[str] = []
    for p in parts:
        cleaned = _norm_text(p)
        # Keep a minimum body length so heading echoes and chapter
        # numbers don't get emitted as one-token chunks. 40 chars is
        # short enough to keep terse marginal notes but long enough
        # to drop "I.", "II." etc.
        if len(cleaned) >= 40:
            out.append(cleaned)
    return out


def split_descartes(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Walk ``text`` for ``work``, yielding one Chunk per paragraph
    within each named section. Sections that don't match in the
    source (e.g. a partial download) are skipped silently — they
    just produce zero chunks for that division.
    """

    sections = _SECTIONS.get(work.code)
    if sections is None:
        raise ValueError(f"no Descartes section table for work code {work.code!r}")

    # Locate every section's heading position; sections that don't
    # match are dropped. Then slice the text between successive
    # matches (or to end-of-text for the last one).
    matches: list[tuple[str, int, int]] = []  # (label, heading_start, body_start)
    for label, pat in sections:
        m = pat.search(text)
        if m is None:
            continue
        matches.append((label, m.start(), m.end()))

    if not matches:
        return

    # Sort by appearance order in the file. Section tables above are
    # already declared in canonical order, but the search-and-skip
    # logic above may yield a sparser subset; sorting keeps slicing
    # honest regardless.
    matches.sort(key=lambda t: t[1])

    for i, (label, _hstart, body_start) in enumerate(matches):
        body_end = matches[i + 1][1] if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        paragraphs = _paragraphs(body)
        for n, para in enumerate(paragraphs, start=1):
            section_str = f"{label} §{n}"
            chunk_id = _make_chunk_id(
                path.name,
                work.title,
                work.lang,
                label,
                section_str,
                "",
                para[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus=work.corpus,
                author=work.author,
                work=work.title,
                lang=work.lang,
                section=section_str,
                book=label,
                page=None,
                speaker=None,
                text=para,
                source_file=path.name,
                translator=work.translator,
                edition_year=work.edition_year,
                citation_system=work.citation_system,
            )


# Article-marker regex for Principia / Principes-Pars-I sources:
# `[N.NNN]` at the very start of a line, followed by optional
# title prose on the same line. Produced verbatim by
# `perseus/download_descartes_wikisource.py` for both works.
_ARTICLE_MARKER_RE = re.compile(r"^\[(\d+)\.(\d{3})\](?:\s+(.*))?$", re.MULTILINE)

# Roman numerals for Descartes' four Pars. Hardcoded — we never
# need more than I-IV, so a lookup table is clearer than pulling
# in a general-purpose converter.
_ROMAN: dict[int, str] = {1: "I", 2: "II", 3: "III", 4: "IV"}


def split_descartes_articles(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Walk ``text`` for bracketed article markers (`[N.NNN]`) and
    emit one Chunk per article. Used for both the Latin Principia
    (all four Pars) and the French Principes Pars I — both share
    the marker format, courtesy of the Wikisource downloader.

    Section labels read ``"Pars I, art. 7"``; the bare major
    division (``"Pars I"``) lives on the chunk's ``book`` field
    so the Reader can group by it.

    The article body is everything between this marker and the
    next, with the title line (the same paragraph as the marker)
    preserved so retrieval over either prose or title hits.
    """

    matches = list(_ARTICLE_MARKER_RE.finditer(text))
    if not matches:
        return

    for i, m in enumerate(matches):
        pars_n = int(m.group(1))
        art_n = int(m.group(2))
        title = (m.group(3) or "").strip()
        body_start = m.start()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Re-norm the body: title on its own line, then any prose
        # below it, all whitespace-collapsed. Keeping the title in
        # the chunk text means BM25/embedding retrieval can match
        # against the topical heading too.
        raw_body = text[body_start:body_end]
        # Drop the marker prefix `[N.NNN]` from the text itself —
        # the section label already carries the locator; including
        # the bracket noise in the body would clutter retrieval.
        stripped = _ARTICLE_MARKER_RE.sub("", raw_body, count=1).strip()
        if title:
            chunk_text = f"{title}\n\n{stripped}".strip()
        else:
            chunk_text = stripped
        chunk_text = _norm_text(chunk_text)
        if not chunk_text:
            continue

        pars_label = f"Pars {_ROMAN.get(pars_n, str(pars_n))}"
        section_str = f"{pars_label}, art. {art_n}"

        chunk_id = _make_chunk_id(
            path.name,
            work.title,
            work.lang,
            pars_label,
            section_str,
            "",
            chunk_text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus=work.corpus,
            author=work.author,
            work=work.title,
            lang=work.lang,
            section=section_str,
            book=pars_label,
            page=None,
            speaker=None,
            text=chunk_text,
            source_file=path.name,
            translator=work.translator,
            edition_year=work.edition_year,
            citation_system=work.citation_system,
        )
