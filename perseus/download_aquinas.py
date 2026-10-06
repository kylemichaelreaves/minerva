#!/usr/bin/env python3
"""Download Aquinas's Summa Theologiae, Summa contra Gentiles, and
the four major Aristotle commentaries (Ethics, Metaphysics, Physics,
De anima) in Latin from Corpus Thomisticum.

Source: corpusthomisticum.org — the scholarly Latin edition of
Aquinas's Opera omnia maintained by Enrique Alarcón at the University
of Navarra. Each work is split across multiple HTML pages, each
covering a Question range (ST), a Chapter range (SCG), or a Book
range (commentaries). Every textual sub-section carries a structured
anchor of the form::

    <A NAME="NNNN"><SPAN CLASS="ref">[NNNN] <citation></SPAN>...body...

with `<citation>` in scholarly form, e.g. ``I&ordf; q. 3 a. 1 arg. 1``
(ST), ``Contra Gentiles, lib. 1 cap. 13 n. 7`` (SCG), or
``Sententia Ethic., lib. 1 l. 1 n. 1`` (commentary lectio). We harvest
those anchors, parse the citation, group sub-sections — keeping the
structural sub-labels inline as human-readable prefixes — then emit
one chunk per article (ST) / chapter (SCG) / lectio (commentaries).

Markers emitted to the raw .txt files:

    [ST.<p>.<q>.<a>]      ST Pars `p` (1=I, 2=I-II, 3=II-II, 4=III),
                          question `q`, article `a`. ``a=0`` means
                          the question's prooemium.
    [SCG.<lib>.<cap>]     SCG Liber `lib` (1–4), Caput `cap`.
    [SENT_<W>.<lib>.<l>]  Aristotle-commentary lectio. `W` ∈
                          {ETH, MET, PHY, AN}; `lib` is the Aristotle
                          book number; `l` is the lectio. ``lib=0
                          l=0`` is the commentary prooemium.

Output:

    data/aquinas/raw_la/summa_theologiae.txt        (all 4 Pars)
    data/aquinas/raw_la/contra_gentiles.txt         (all 4 Libri)
    data/aquinas/raw_la/sententia_ethicorum.txt     (10 Libri)
    data/aquinas/raw_la/sententia_metaphysicae.txt  (12 Libri + pr.)
    data/aquinas/raw_la/in_physicorum.txt           (8 Libri)
    data/aquinas/raw_la/sentencia_de_anima.txt      (3 Libri)

Run:

    uv run python perseus/download_aquinas.py
    uv run python perseus/download_aquinas.py --only st
    uv run python perseus/download_aquinas.py --only scg
    uv run python perseus/download_aquinas.py --only sent-eth --only sent-met

Deferred: the opuscula (De ente et essentia, Compendium theologiae,
…) and the remaining Aristotle commentaries with idiosyncratic
structure (Politicorum — Petrus de Alvernia continuation; Peri
Hermeneias — Cajetan continuation; De caelo, De gen. et corruptione,
De sensu, Posterior Analytics). The four commentaries shipped here
are the four targeted by ≥ 95% of the Summa's ``Philosophus`` citations,
so they unlock the structural `comments_on` cross-reference rule
without dragging in every minor opusculum.
"""

from __future__ import annotations

import argparse
import html
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple

from _download import make_fetcher
from _download import render_chunks as _render

_BASE = "https://www.corpusthomisticum.org"


# ----- page inventory (scraped once from iopera.html) -----
#
# Corpus Thomisticum groups multiple questions/chapters per page; the
# slug encodes (Pars, starting question) for ST and (Liber, starting
# chapter) for SCG. We hard-code the inventory rather than re-scraping
# the index each run — the works are stable (T. Aquinas died 1274),
# and a static list keeps the downloader deterministic.
#
# Pars encoding in the ST slug (`sth<P><NNN>`):
#   1 = Prima Pars (I)
#   2 = Prima Secundae (I-II)
#   3 = Secunda Secundae (II-II)
#   4 = Tertia Pars (III)
# The Supplementum is NOT carried by Corpus Thomisticum (it's a
# posthumous compilation from the Scriptum super Sententiis, not a
# work of Thomas himself).

_ST_PAGES: tuple[str, ...] = (
    "sth1001.html",
    "sth1002.html",
    "sth1003.html",
    "sth1015.html",
    "sth1028.html",
    "sth1044.html",
    "sth1050.html",
    "sth1065.html",
    "sth1075.html",
    "sth1077.html",
    "sth1084.html",
    "sth1090.html",
    "sth1103.html",
    "sth2000.html",
    "sth2001.html",
    "sth2006.html",
    "sth2022.html",
    "sth2026.html",
    "sth2040.html",
    "sth2049.html",
    "sth2055.html",
    "sth2071.html",
    "sth2072.html",
    "sth2073.html",
    "sth2074.html",
    "sth2075.html",
    "sth2085.html",
    "sth2090.html",
    "sth2093.html",
    "sth2094.html",
    "sth2095.html",
    "sth2098.html",
    "sth2106.html",
    "sth2109.html",
    "sth3000.html",
    "sth3001.html",
    "sth3017.html",
    "sth3023.html",
    "sth3025.html",
    "sth3027.html",
    "sth3034.html",
    "sth3044.html",
    "sth3045.html",
    "sth3047.html",
    "sth3057.html",
    "sth3061.html",
    "sth3079.html",
    "sth3080.html",
    "sth3081.html",
    "sth3082.html",
    "sth3092.html",
    "sth3101.html",
    "sth3102.html",
    "sth3106.html",
    "sth3109.html",
    "sth3121.html",
    "sth3122.html",
    "sth3123.html",
    "sth3141.html",
    "sth3143.html",
    "sth3144.html",
    "sth3146.html",
    "sth3155.html",
    "sth3170.html",
    "sth3171.html",
    "sth3179.html",
    "sth3183.html",
    "sth4000.html",
    "sth4001.html",
    "sth4002.html",
    "sth4016.html",
    "sth4027.html",
    "sth4040.html",
    "sth4046.html",
    "sth4053.html",
    "sth4060.html",
    "sth4066.html",
    "sth4072.html",
    "sth4073.html",
    "sth4074.html",
    "sth4078.html",
    "sth4079.html",
    "sth4080.html",
    "sth4082.html",
    "sth4083.html",
    "sth4084.html",
)

_SCG_PAGES: tuple[str, ...] = (
    "scg1001.html",
    "scg1010.html",
    "scg1014.html",
    "scg1029.html",
    "scg1037.html",
    "scg1044.html",
    "scg1072.html",
    "scg1097.html",
    "scg2001.html",
    "scg2006.html",
    "scg2039.html",
    "scg2046.html",
    "scg2056.html",
    "scg2091.html",
    "scg3001.html",
    "scg3064.html",
    "scg3111.html",
    "scg4001.html",
    "scg4027.html",
    "scg4079.html",
)


# Aristotle-commentary page inventories. Each commentary uses its own
# slug-numbering convention — there's no single suffix scheme. The
# lists below were extracted from iopera.html's link map; treat them
# as authoritative.
#
# Slug prefix per work:
#   cmp — Sententia libri Metaphysicae       (Aristotle: Metaphysics)
#   ctc — Sententia libri Ethicorum          (Aristotle: Nicomachean Ethics)
#   cpy — In libros Physicorum               (Aristotle: Physics)
#   can — Sentencia libri De anima           (Aristotle: De anima)

_SENT_MET_PAGES: tuple[str, ...] = (
    "cmp00.html",  # prooemium
    "cmp0101.html",  # lib. 1 lectiones 1-3
    "cmp0104.html",  # lib. 1 lectiones 4-17
    "cmp02.html",
    "cmp03.html",
    "cmp04.html",
    "cmp05.html",
    "cmp06.html",
    "cmp07.html",
    "cmp09.html",
    "cmp10.html",
    "cmp11.html",
    "cmp12.html",
)

_SENT_ETH_PAGES: tuple[str, ...] = (
    "ctc0101.html",
    "ctc0104.html",
    "ctc0119.html",
    "ctc02.html",
    "ctc0314.html",
    "ctc06.html",
    "ctc07.html",
    "ctc08.html",
    "ctc10.html",
)

_SENT_PHY_PAGES: tuple[str, ...] = (
    "cpy011.html",  # lib. 1 lectio 1
    "cpy012.html",  # lib. 1 lectio 2 — liber 2
    "cpy03.html",  # libri 3-4
    "cpy05.html",  # libri 5-6
    "cpy07.html",  # libri 7-8
)

_SENT_AN_PAGES: tuple[str, ...] = (
    "can1.html",
    "can2.html",
    "can3.html",
)


# Polite inter-request delay. Corpus Thomisticum is a small academic
# site; even at 1 req/s we're well under any rate limit, and the
# 87 ST + 20 SCG pages finish in ~2 minutes.
_INTER_REQUEST_DELAY = 1.0


# ----- fetch -----

_fetch = make_fetcher()


def _fetch_page(slug: str) -> str:
    url = f"{_BASE}/{slug}"
    print(f"GET {url}")
    data = _fetch(url)
    time.sleep(_INTER_REQUEST_DELAY)
    return data.decode("iso-8859-1")


# ----- HTML harvest -----

_P_BLOCK_RE = re.compile(
    r'<P\s+TITLE="(?P<title>[^"]*)"[^>]*>'
    r'<A\s+NAME="(?P<id>\d+)">'
    r'<SPAN\s+CLASS="ref">\[(?P=id)\]\s*(?P<cite>[^<]*)</SPAN></A>'
    r"(?P<body>.*?)</P>",
    re.IGNORECASE | re.DOTALL,
)


class _Block(NamedTuple):
    title: str
    anchor_id: str
    cite: str
    body: str


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(text)
    return " ".join(text.split())


def _iter_blocks(html_text: str) -> Iterator[_Block]:
    for m in _P_BLOCK_RE.finditer(html_text):
        yield _Block(
            title=m.group("title").strip(),
            anchor_id=m.group("id"),
            cite=m.group("cite").strip(),
            body=_strip_html(m.group("body")),
        )


# ----- ST citation parsing -----

_ST_PARS_LABEL: dict[str, int] = {
    "I": 1,
    "I-II": 2,
    "II-II": 3,
    "III": 4,
}

_ST_PARS_PRO_RE = re.compile(r"^(I|I-II|II-II|III) pr\.$")
_ST_Q_PRO_RE = re.compile(r"^(I|I-II|II-II|III) q\. (\d+) pr\.$")
_ST_ARTICLE_RE = re.compile(r"^(I|I-II|II-II|III) q\. (\d+) a\. (\d+) (?P<sub>.+)$")


def _cite_to_st_title(cite: str) -> str | None:
    """Map a span citation to the TITLE-shaped string ST parsers expect."""

    c = html.unescape(cite).strip()
    # Scholastic ordinals in span citations: I&ordf;/Iª, I&ordf;-IIae/Iª-IIae, …
    _ord = r"(?:&ordf;|[ªº])"
    c = re.sub(rf"^III{_ord}", "III", c)
    c = re.sub(rf"^II{_ord}-IIae\b", "II-II", c)
    c = re.sub(rf"^I{_ord}-IIae\b", "I-II", c)
    c = re.sub(rf"^I{_ord}", "I", c)
    return c.strip() or None


def _parse_st_locator(title: str) -> tuple[int, int, int, str | None] | None:
    """Return ``(pars, question, article, subsection)`` for one ST anchor."""

    m = _ST_PARS_PRO_RE.match(title)
    if m:
        return (_ST_PARS_LABEL[m.group(1)], 0, 0, None)

    m = _ST_Q_PRO_RE.match(title)
    if m:
        return (_ST_PARS_LABEL[m.group(1)], int(m.group(2)), 0, None)

    m = _ST_ARTICLE_RE.match(title)
    if m:
        return (
            _ST_PARS_LABEL[m.group(1)],
            int(m.group(2)),
            int(m.group(3)),
            m.group("sub").strip(),
        )

    return None


def _st_sub_label(sub: str | None) -> str | None:
    if not sub or sub == "pr.":
        return None
    return f"[{sub}]"


def _extract_st(pages: tuple[str, ...]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_key: tuple[int, int, int] | None = None
    current_parts: list[tuple[str | None, str]] = []

    def flush() -> None:
        nonlocal current_key, current_parts
        if current_key is None:
            return
        p, q, a = current_key
        marker = f"[ST.{p}.{q}.{a}]"
        body_parts: list[str] = []
        for label, text in current_parts:
            if label:
                body_parts.append(f"{label} {text}")
            else:
                body_parts.append(text)
        chunks.append((marker, "\n\n".join(body_parts)))
        current_key = None
        current_parts = []

    for slug in pages:
        html_text = _fetch_page(slug)
        for block in _iter_blocks(html_text):
            title = block.title
            loc = _parse_st_locator(title)
            if loc is None:
                alt = _cite_to_st_title(block.cite)
                if alt is not None:
                    loc = _parse_st_locator(alt)
            if loc is None:
                continue
            p, q, a, sub = loc
            key = (p, q, a)
            if key != current_key:
                flush()
                current_key = key
            current_parts.append((_st_sub_label(sub), block.body))

    flush()
    return chunks


# ----- SCG citation parsing -----

_SCG_RE = re.compile(
    r"Contra Gentiles, lib\. (\d+) cap\. (\d+) n\. (\d+)",
    re.IGNORECASE,
)


def _extract_scg(pages: tuple[str, ...]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_key: tuple[int, int] | None = None
    current_parts: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_key, current_parts
        if current_key is None:
            return
        lib, cap = current_key
        marker = f"[SCG.{lib}.{cap}]"
        body = "\n\n".join(f"[n. {n}] {text}" for n, text in current_parts)
        chunks.append((marker, body))
        current_key = None
        current_parts = []

    for slug in pages:
        html_text = _fetch_page(slug)
        for block in _iter_blocks(html_text):
            m = _SCG_RE.search(block.title) or _SCG_RE.search(block.cite)
            if not m:
                continue
            lib, cap, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
            key = (lib, cap)
            if key != current_key:
                flush()
                current_key = key
            current_parts.append((n, block.body))

    flush()
    return chunks


# ----- Aristotle-commentary citation parsing -----

_SENT_PRO_RE = re.compile(r"Sententia Metaphysicae, pr\.", re.IGNORECASE)

_SENT_LECT_RE = re.compile(
    r"(?:Sententia Ethic\.|Sententia Metaphysicae|In Physic\.|Sentencia De anima), "
    r"lib\. (\d+) l\. (\d+) n\. (\d+)",
    re.IGNORECASE,
)


def _extract_sententia(
    pages: tuple[str, ...],
    *,
    tag: str,
) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_key: tuple[int, int] | None = None
    current_parts: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_key, current_parts
        if current_key is None:
            return
        lib, lect = current_key
        marker = f"[SENT_{tag}.{lib}.{lect}]"
        if current_parts:
            body = "\n\n".join(f"[n. {n}] {text}" for n, text in current_parts)
        else:
            body = ""
        chunks.append((marker, body))
        current_key = None
        current_parts = []

    for slug in pages:
        html_text = _fetch_page(slug)
        for block in _iter_blocks(html_text):
            hay = f"{block.title} {block.cite}"
            if _SENT_PRO_RE.search(hay):
                flush()
                current_key = (0, 0)
                current_parts = [(0, block.body)]
                flush()
                continue

            m = _SENT_LECT_RE.search(block.title) or _SENT_LECT_RE.search(block.cite)
            if not m:
                continue
            lib, lect, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
            key = (lib, lect)
            if key != current_key:
                flush()
                current_key = key
            current_parts.append((n, block.body))

    flush()
    return chunks


def _write_work(
    *,
    dest_root: Path,
    filename: str,
    chunks: list[tuple[str, str]],
) -> Path:
    rendered = _render(chunks)
    dest_dir = dest_root / "aquinas" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(chunks)} chunks)")
    return dest


# ----- per-work fetch entry points -----


def fetch_summa_theologiae(*, dest_root: Path) -> Path:
    chunks = _extract_st(_ST_PAGES)
    return _write_work(
        dest_root=dest_root,
        filename="summa_theologiae.txt",
        chunks=chunks,
    )


def fetch_contra_gentiles(*, dest_root: Path) -> Path:
    chunks = _extract_scg(_SCG_PAGES)
    return _write_work(
        dest_root=dest_root,
        filename="contra_gentiles.txt",
        chunks=chunks,
    )


def fetch_sententia_ethicorum(*, dest_root: Path) -> Path:
    chunks = _extract_sententia(_SENT_ETH_PAGES, tag="ETH")
    return _write_work(
        dest_root=dest_root,
        filename="sententia_ethicorum.txt",
        chunks=chunks,
    )


def fetch_sententia_metaphysicae(*, dest_root: Path) -> Path:
    chunks = _extract_sententia(_SENT_MET_PAGES, tag="MET")
    return _write_work(
        dest_root=dest_root,
        filename="sententia_metaphysicae.txt",
        chunks=chunks,
    )


def fetch_in_physicorum(*, dest_root: Path) -> Path:
    chunks = _extract_sententia(_SENT_PHY_PAGES, tag="PHY")
    return _write_work(
        dest_root=dest_root,
        filename="in_physicorum.txt",
        chunks=chunks,
    )


def fetch_sentencia_de_anima(*, dest_root: Path) -> Path:
    chunks = _extract_sententia(_SENT_AN_PAGES, tag="AN")
    return _write_work(
        dest_root=dest_root,
        filename="sentencia_de_anima.txt",
        chunks=chunks,
    )


_WORKS: dict[str, Callable[..., Path]] = {
    "st": fetch_summa_theologiae,
    "scg": fetch_contra_gentiles,
    "sent-eth": fetch_sententia_ethicorum,
    "sent-met": fetch_sententia_metaphysicae,
    "sent-phy": fetch_in_physicorum,
    "sent-an": fetch_sentencia_de_anima,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/aquinas/raw_la/.",
    )
    parser.add_argument(
        "--only",
        choices=sorted(_WORKS),
        action="append",
        help=(
            "Fetch only this work (repeatable). Defaults to all. "
            "Useful for incremental testing without re-fetching every page."
        ),
    )
    args = parser.parse_args()
    targets = args.only or sorted(_WORKS)
    for name in targets:
        _WORKS[name](dest_root=args.data_root)


if __name__ == "__main__":
    main()
