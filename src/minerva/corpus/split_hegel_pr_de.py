"""Structure-aware parser for Hegel's *Grundlinien der Philosophie des
Rechts* (German, zeno.org Werke text) — typed §-chunks.

zeno.org's HTML carries § headings (in h4/h5/h6) that the generic
``chapter`` splitter ignores, but it flattens every paragraph to
``<p class="zenoPLm4n0">`` with no cue for where a numbered § proposition
ends and its *Anmerkung* (Remark) begins, injects "Buchempfehlung" ad
cruft (``class="empf"``), and **omits the Zusätze (Additions) entirely**.

The §§ are NOT in monotonic document order: each § appears multiple times
across the heading hierarchy (a TOC-style listing plus the body), but only
one occurrence is content-bearing. So we accumulate prose paragraphs *by §
number* and emit in numeric order:

* Per §, the first prose paragraph is the **main** proposition and the
  rest is the **Remark**. Validated heuristic: 97% agreement with the
  Cambridge English edition's explicit markup, *zero false negatives*; the
  ~3% error is a multi-paragraph main whose tail is over-typed as Remark.
* The **Additions** are spliced from the Gans/Werke OCR appendix
  (``data/hegel/pr_de_zusaetze.txt``, see ``download_hegel_zusaetze.py``),
  attached by their explicit "Zusatz zu § N" header.
* Hegel's **Vorrede** (Owl-of-Minerva passage) is captured as front matter
  so the §-only pass doesn't drop it.

German-native section locators ("§N Anmerkung" / "§N Zusatz"); the
``block_type`` machine value stays the canonical ``remark`` / ``addition``.
See ``docs/block-structure-remediation-plan.md`` (Phase 2).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# NB: `bs4` is imported lazily inside split_hegel_pr_de (see there). It's an
# `[hegel]`-extra dependency; a module-top import would make `minerva serve`
# (which imports the whole corpus pipeline) crash anywhere the extra isn't
# installed, e.g. the CI base venv.

_SECTION_RE = re.compile(r"§\s*(\d{1,3})")
_PAGE_MARKER_RE = re.compile(r"\[\d+\]")
# Optional leading sequence number ("4. ") is consumed so it isn't left
# dangling on the *previous* Addition's body when we slice between headers.
_ZUSATZ_HDR_RE = re.compile(r"(?:\d{1,3}\.\s*)?Zusatz\s+zu\s+§\s*(\d{1,3})\s*\.?", re.I)
_ZUSAETZE_FILE = "pr_de_zusaetze.txt"


def _is_prose(el) -> bool:
    css = " ".join(el.get("class", []))
    if "empf" in css:  # zeno.org "Buchempfehlung" affiliate cruft
        return False
    return "zenopl" in css.lower()


def _clean_ocr(s: str) -> str:
    s = re.sub(r"Digitized\s+by\s+Googl?e?k?", " ", s, flags=re.I)  # watermark
    s = re.sub(r"\bZu\s+§\s*[\d.\- ]+", " ", s)  # running page headers ("Zu § 1-4.")
    s = re.sub(r"-\s+", "", s)  # de-hyphenate line breaks
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _load_zusaetze(path: Path) -> dict[int, str]:
    """Map § number → cleaned Addition text from the Gans OCR appendix."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = list(_ZUSATZ_HDR_RE.finditer(text))
    out: dict[int, str] = {}
    for i, m in enumerate(hits):
        sec = int(m.group(1))
        if sec in out:  # first occurrence wins
            continue
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = _clean_ocr(text[m.end() : end])
        if body:
            out[sec] = body
    return out


def _chunk(
    work: CorpusWork,
    path: Path,
    *,
    section: str,
    book: str | None,
    block_type: str | None,
    paragraphs: list[str],
) -> Chunk | None:
    text = "\n\n".join(p for p in (_norm_text(t) for t in paragraphs) if p)
    if not text:
        return None
    chunk_id = _make_chunk_id(
        path.name, work.title, work.lang, book or "", section, "", text[:120]
    )
    return Chunk(
        chunk_id=chunk_id,
        corpus=work.corpus,
        author=work.author,
        work=work.title,
        lang=work.lang,
        section=section,
        book=book,
        page=None,
        speaker=None,
        text=text,
        source_file=path.name,
        translator=work.translator,
        edition_year=work.edition_year,
        citation_system=work.citation_system,
        block_type=block_type,
    )


def split_hegel_pr_de(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        from ..corpus_extract import IngestDepsMissing

        raise IngestDepsMissing(
            "HTML ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    additions = _load_zusaetze(path.parent / _ZUSAETZE_FILE)
    front_headings = {h.lower() for h in work.front_matter_headings}
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")

    by_section: dict[int, list[str]] = defaultdict(list)
    cur: int | None = None
    cur_front: str | None = None
    front_idx = 0

    # Pass 1: accumulate prose by § number (handles the duplicate, out-of-
    # order TOC headings — only one occurrence per § carries prose). Front
    # matter (Vorrede) is yielded as encountered, ahead of the §§.
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        txt = el.get_text(" ", strip=True)
        if el.name != "p":
            m = _SECTION_RE.search(txt)
            if m and txt.strip().startswith("§"):
                cur = int(m.group(1))
            elif cur is None and txt.lower() in front_headings:
                cur_front = txt
                front_idx = 0
            elif cur is None:
                cur_front = None
            continue
        if not _is_prose(el):
            continue
        body = _PAGE_MARKER_RE.sub("", txt).strip()
        if not body:
            continue
        if cur is not None:
            by_section[cur].append(body)
        elif cur_front is not None:
            front_idx += 1
            chunk = _chunk(
                work, path, section=f"{cur_front}, ¶{front_idx}",
                book=cur_front, block_type=None, paragraphs=[body],
            )
            if chunk is not None:
                yield chunk

    # Pass 2: emit §§ in numeric order — main, Remark, then Addition.
    for n in sorted(set(by_section) | set(additions)):
        paras = by_section.get(n, [])
        if paras:
            main = _chunk(work, path, section=f"§{n}", book=None, block_type=None, paragraphs=paras[:1])
            if main is not None:
                yield main
            if len(paras) > 1:
                rem = _chunk(
                    work, path, section=f"§{n} Anmerkung", book=None,
                    block_type="remark", paragraphs=paras[1:],
                )
                if rem is not None:
                    yield rem
        if n in additions:
            add = _chunk(
                work, path, section=f"§{n} Zusatz", book=None,
                block_type="addition", paragraphs=[additions[n]],
            )
            if add is not None:
                yield add
