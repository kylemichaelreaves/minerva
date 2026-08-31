"""Splitter for the Objections & Réponses to Descartes' Meditations.

Source: ten fr.wikisource Parsoid-HTML pages (Clerselier's 1647 French
translation, Cousin 1824 edition) fetched by
``perseus/download_descartes_objections.py`` into
``data/descartes/raw_fr/objections_<code>.html``.

One chunk per paragraph, section = ``"<piece abbr>, ¶ <n>"``
(numbered continuously through each piece), book = the piece label —
so the Reader groups the ten pieces and a citation reads
``Objections et Réponses, Obj. III, ¶ 12``.

⚠ **Attribution** — the Objections are by other authors, not
Descartes (the misattribution trap the remediation plan flags).
Objector-voice paragraphs are emitted with ``block_type='objection'``
and the objector's name in ``speaker``; ``retrieve.format_locator``
cites those as "… — objection (Hobbes)", never as Descartes. Reply
paragraphs are Descartes's own and stay untyped.

Voice within a piece is tracked from the printed headings:

* ``OBJECTION …`` headings (Hobbes's set is interleaved
  objection/reply pairs) switch to the objector's voice;
* ``RÉPONSE …`` headings switch to Descartes;
* ``ADDITION DE DESCARTES`` (inside the Sixth Objections page) is
  Descartes; a later ``… À M. DESCARTES`` heading (the philosophers'
  and geometers' follow-up batch) switches back to the objectors;
* topic headings ("DE DIEU.", "DE LA NATURE DE L'ESPRIT HUMAIN.")
  leave the voice unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# filename code → (section abbr, book label, objector or None).
# objector None means the piece speaks as Descartes throughout
# (subject to heading-driven switches).
_PIECES: dict[str, tuple[str, str, str | None]] = {
    "obj1": ("Obj. I", "Premières objections (Caterus)", "Caterus"),
    "rep1": ("Rép. I", "Réponses aux premières objections", None),
    "obj2": ("Obj. II", "Secondes objections (Mersenne)", "Mersenne"),
    "rep2": ("Rép. II", "Réponses aux secondes objections", None),
    "obj3": ("Obj. III", "Troisièmes objections et réponses (Hobbes)", "Hobbes"),
    "obj4": ("Obj. IV", "Quatrièmes objections (Arnauld)", "Arnauld"),
    "rep4": ("Rép. IV", "Réponses aux quatrièmes objections", None),
    "obj5": ("Obj. V", "Cinquièmes objections (Gassendi)", "Gassendi"),
    "obj6": ("Obj. VI", "Sixièmes objections", "divers théologiens et philosophes"),
    "rep6": ("Rép. VI", "Réponses aux sixièmes objections", None),
}

_CODE_RE = re.compile(r"objections_(\w+)\.html?$")


def _piece_for_path(path: Path) -> tuple[str, str, str | None] | None:
    m = _CODE_RE.search(path.name)
    if not m:
        return None
    return _PIECES.get(m.group(1))


def _voice_after_heading(heading: str, current: str, objector: str | None) -> str:
    """New voice ('objector' | 'descartes') after one printed heading."""

    h = heading.upper()
    if h.startswith("RÉPONSE") or "ADDITION DE DESCARTES" in h:
        return "descartes"
    if objector is not None and (h.startswith("OBJECTION") or "À M. DESCARTES" in h):
        return "objector"
    return current


def split_descartes_objections(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    """Parse one fr.wikisource O&R page into paragraph Chunks."""

    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover - env-dependent
        from ..corpus_extract import IngestDepsMissing

        raise IngestDepsMissing(
            "descartes objections ingest needs beautifulsoup4 (pip install 'minerva[hegel]')"
        ) from e

    piece = _piece_for_path(path)
    if piece is None:
        return
    abbr, book_label, objector = piece

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    # Strip wikisource chrome: the header-template box, no-export nav,
    # footnote markers and their bodies (Cousin's editorial notes),
    # page-number anchors, styling and figures.
    for sel in (
        "table.headertemplate",
        "[class*=ws-noexport]",
        "sup.mw-ref",
        "ol.references",
        "[class*=ws-pagenum]",
        "style",
        "figure",
        "head",
    ):
        for el in soup.select(sel):
            el.decompose()

    voice = "objector" if objector is not None else "descartes"
    para_no = 0

    for el in soup.find_all(["h2", "h3", "h4", "div", "p"]):
        if el.name in ("h2", "h3", "h4"):
            heading = _norm_text(el.get_text(" "))
            if heading:
                voice = _voice_after_heading(heading, voice, objector)
            continue
        if el.name == "div":
            style = el.get("style") or ""
            if "text-align:center" not in style.replace(" ", ""):
                continue
            heading = _norm_text(el.get_text(" "))
            if heading:
                voice = _voice_after_heading(heading, voice, objector)
            continue

        text = _norm_text(el.get_text(" "))
        if not text:
            continue
        para_no += 1
        section = f"{abbr}, ¶ {para_no}"
        is_objection = voice == "objector"
        chunk_id = _make_chunk_id(
            path.name,
            work.title,
            work.lang,
            book_label,
            section,
            "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus=work.corpus,
            author=work.author,
            work=work.title,
            lang=work.lang,
            section=section,
            book=book_label,
            page=None,
            speaker=objector if is_objection else None,
            text=text,
            source_file=path.name,
            translator=work.translator,
            edition_year=work.edition_year,
            citation_system=work.citation_system,
            block_type="objection" if is_objection else None,
        )
