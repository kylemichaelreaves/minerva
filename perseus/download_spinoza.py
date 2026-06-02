#!/usr/bin/env python3
"""Download Spinoza's three major Latin works from Wikisource.

Spinoza wrote in Latin; his canon ships posthumously in the 1677
*Opera Posthuma*. Wikisource Latin carries clean transcriptions of:

  • Ethica (Ordine Geometrico Demonstrata) — 5 Pars, each a separate
    Wikisource subpage. Geometric structure: DEFINITIONES + AXIOMATA
    + (POSTULATA in Pars II/III) + PROPOSITIO I–N, each Prop carrying
    its DEMONSTRATIO / COROLLARIUM / SCHOLIUM / EXPLICATIO / ALITER.
    Pars I–V each end with an APPENDIX.
  • Tractatus de Intellectus Emendatione (TIE) — single page, ~110
    numbered paragraphs (Bruder / Gebhardt convention).
  • Tractatus Politicus (TP) — single page, 11 chapters (CAPUT I–XI),
    each with Roman-numeral-numbered articles.

This script fetches each via the Wikisource REST API
(`/api/rest_v1/page/html/<title>`), parses with the same stdlib
HTMLParser-based extractor we use for Descartes, and emits the
canonical `[N.NNN]`-style marker shape that the corpus splitter
(`split_spinoza`) consumes. Marker conventions:

    [E.<p>.D.<n>]      Ethica Pars `p`, Definition `n`
    [E.<p>.A.<n>]      Ethica Pars `p`, Axiom `n`
    [E.<p>.Post.<n>]   Ethica Pars `p`, Postulate `n`
    [E.<p>.P.<n>]      Ethica Pars `p`, Proposition `n` (includes its
                       Demonstratio + Corollaria + Scholia inline)
    [E.<p>.App]        Ethica Pars `p`, Appendix
    [TIE.<nnn>]        TIE, paragraph `nnn` (1–110)
    [TP.<c>.<nnn>]     TP, Caput `c`, article `nnn`

Output:

    data/spinoza/raw_la/ethica.txt
    data/spinoza/raw_la/tie.txt
    data/spinoza/raw_la/tp.txt

Run:

    uv run python perseus/download_spinoza.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _download import (
    ParagraphExtractor,
    make_fetcher,
    render_chunks as _render,
    roman_to_int as _roman_to_int,
)


_REST = "https://la.wikisource.org/api/rest_v1/page/html"

_ETHICA_SUBPAGES = [
    (1, "Ethica%2FPars_prima_-_De_Deo"),
    (2, "Ethica%2FPars_secunda_-_De_natura_et_origine_mentis"),
    (3, "Ethica%2FPars_tertia_-_De_origine_et_natura_affectuum"),
    (4, "Ethica%2FPars_quarta_-_De_servitute_humana_seu_de_affectuum_viribus"),
    (5, "Ethica%2FPars_quinta_-_De_potentia_intellectus_seu_de_libertate_humana"),
]
_TIE_TITLE = (
    "Tractatus_de_intellectus_emendatione,_et_de_via_qua_optime_"
    "in_veram_rerum_cognitionem_dirigitur"
)
_TP_TITLE = "Tractatus_Politicus"


_fetch = make_fetcher()

_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})


def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS, break_end_tags=_BREAK_END_TAGS
    )
    p.feed(html.decode("utf-8"))
    p.close()
    return p.paragraphs


# ----- Ethica per-Pars walker -----

# Section-banner phrases that mark a top-level state transition in
# Ethica. Compared as full-string (paragraph == phrase) since the
# extractor produces them as their own paragraph.
_ETHICA_DEFINITIONES = re.compile(r"^DEFINITIONES?\s*$")
_ETHICA_AXIOMATA = re.compile(r"^AXIOMATA\s*$")
_ETHICA_POSTULATA = re.compile(r"^POSTULATA\s*$")
_ETHICA_PROPOSITIO = re.compile(r"^PROPOSITIO\s+([IVXLC]+)\s*$")
_ETHICA_APPENDIX = re.compile(r"^APPENDIX\s*$")
_ETHICA_FINIS = re.compile(r"^FINIS PARTIS\b")

# Within a Definitiones / Axiomata / Postulata block, each numbered
# entry opens with `<roman-or-digit>. <body>`. We accept either
# Roman numerals (the Wikisource Ethica uses these) or Arabic digits
# (some printings use them) — and fall back to a sequential counter
# if neither matches a known shape.
_NUMBERED_ITEM = re.compile(r"^([IVXLC]+|\d{1,3})\.\s+(.*)$", re.DOTALL)

# Internal Prop sub-headings — DEMONSTRATIO / COROLLARIUM / SCHOLIUM
# etc. They DON'T close the current proposition chunk; they just
# label a sub-section inside it. We keep them as inline labels so
# the chunk body reads like the original.
_PROP_SUBHEADING = re.compile(
    r"^("
    r"DEMONSTRATIO|ALITER|"
    r"COROLLARIUM(?:\s+[IVXLC]+)?|"
    r"SCHOLIUM(?:\s+[IVXLC]+)?|"
    r"EXPLICATIO|LEMMA(?:\s+[IVXLC]+)?|"
    r"AFFECTUUM DEFINITIONES"
    r")\.?\s*$"
)


def _extract_ethica_pars(html: bytes, pars_n: int) -> list[tuple[str, str]]:
    """Walk a single Ethica Pars's paragraph stream, yielding one
    `(marker, body)` pair per chunk. Markers are the canonical
    `[E.<p>.<TYPE>.<n>]` shape (see module docstring).

    State machine: track which top-level block we're in (DEFS / AXS /
    POSTS / PROP_N / APPENDIX / OUT). Transitions happen when we see
    one of the section-banner phrases as a standalone paragraph.
    """

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []

    state: str | None = None  # "D" | "A" | "Post" | "P" | "App" | None
    prop_n: int | None = None
    item_seq: dict[str, int] = {"D": 0, "A": 0, "Post": 0}
    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue

        # End-of-Pars marker.
        if _ETHICA_FINIS.match(p):
            flush()
            state = None
            continue

        # Top-level state transitions.
        if _ETHICA_DEFINITIONES.match(p):
            flush()
            state = "D"
            continue
        if _ETHICA_AXIOMATA.match(p):
            flush()
            state = "A"
            continue
        if _ETHICA_POSTULATA.match(p):
            flush()
            state = "Post"
            continue
        if _ETHICA_APPENDIX.match(p):
            flush()
            state = "App"
            current_marker = f"[E.{pars_n}.App]"
            current_body = []
            continue
        m = _ETHICA_PROPOSITIO.match(p)
        if m:
            flush()
            state = "P"
            prop_n = _roman_to_int(m.group(1)) or 0
            current_marker = f"[E.{pars_n}.P.{prop_n}]"
            current_body = []
            continue

        # Skip Prop-internal subheadings — they're decorative labels
        # for sections that we keep inside the same chunk.
        if _PROP_SUBHEADING.match(p):
            # We could inject e.g. "Demonstratio:" into the body so
            # the reader sees the sub-structure, but it tends to
            # over-clutter the rail's snippet view; leave it out.
            continue

        # In Def / Ax / Post state: each numbered item starts a new
        # chunk; non-numbered prose is appended to the prior chunk.
        if state in ("D", "A", "Post"):
            mi = _NUMBERED_ITEM.match(p)
            if mi:
                flush()
                n_raw, rest = mi.group(1), mi.group(2)
                n = _roman_to_int(n_raw) if n_raw.isalpha() else int(n_raw)
                if not n:
                    # Couldn't parse — fall back to sequence counter.
                    item_seq[state] += 1
                    n = item_seq[state]
                else:
                    item_seq[state] = max(item_seq[state], n)
                current_marker = f"[E.{pars_n}.{state}.{n}]"
                current_body = [rest]
                continue
            # Continuation of the previous item.
            if current_marker is not None:
                current_body.append(p)
            continue

        # In a Prop or Appendix — append all prose to current chunk.
        if state in ("P", "App"):
            current_body.append(p)
            continue

        # OUT of any tracked state — drop (front-matter / nav / page
        # numbers / editorial apparatus).

    flush()
    return out


# ----- TIE walker (numbered paragraphs §1–§110) -----

# TIE paragraphs in Wikisource render with a leading `N.` or `[N]`
# label. We accept both shapes; the digit is the section index.
_TIE_PARA = re.compile(r"^(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+(.*)$", re.DOTALL)


def _extract_tie(html: bytes) -> list[tuple[str, str]]:
    """TIE has a flat structure: front-matter, then §1 through §110
    of numbered prose. Each numbered paragraph is one chunk."""

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []
    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue
        m = _TIE_PARA.match(p)
        if m:
            n = int(m.group(1) or m.group(2))
            # Allow only the first 200 — defensive against false
            # positives where a body sentence happens to open with
            # a digit-and-dot (rare in Bruder Latin, but cheap).
            if 1 <= n <= 200:
                flush()
                current_marker = f"[TIE.{n:03d}]"
                current_body = [m.group(3)]
                continue
        if current_marker is not None:
            current_body.append(p)

    flush()
    return out


# ----- TP walker (11 chapters × Roman-numeral articles) -----

_TP_CAPUT = re.compile(r"^CAPUT\s+([IVXLC]+)\.?\s*$")
# Articles inside a chapter open paragraphs with `I.` `II.` etc.
_TP_ARTICLE = re.compile(r"^([IVXLC]+)\.\s+(.*)$", re.DOTALL)


def _extract_tp(html: bytes) -> list[tuple[str, str]]:
    """TP has 11 Caputs; each Caput's articles open with a Roman-
    numeral prefix on the paragraph (`I. In nostro tractatu…`)."""

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []
    current_caput: int | None = None
    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue

        # Chapter banner.
        m = _TP_CAPUT.match(p)
        if m:
            flush()
            current_caput = _roman_to_int(m.group(1))
            continue

        if current_caput is None:
            # Front-matter — skip.
            continue

        # Article opener.
        ma = _TP_ARTICLE.match(p)
        if ma:
            n_raw, rest = ma.group(1), ma.group(2)
            n = _roman_to_int(n_raw)
            if n and 1 <= n <= 200:
                flush()
                current_marker = f"[TP.{current_caput}.{n:03d}]"
                current_body = [rest]
                continue

        # Continuation of the current article.
        if current_marker is not None:
            current_body.append(p)

    flush()
    return out


# ----- per-work fetch entry points -----

def fetch_ethica(*, dest_root: Path) -> Path:
    all_chunks: list[tuple[str, str]] = []
    for pars_n, slug in _ETHICA_SUBPAGES:
        url = f"{_REST}/{slug}"
        print(f"GET {url}")
        html = _fetch(url)
        chunks = _extract_ethica_pars(html, pars_n)
        print(f"  Pars {pars_n}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    rendered = _render(all_chunks)
    dest_dir = dest_root / "spinoza" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "ethica.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(all_chunks)} chunks)")
    return dest


def fetch_tie(*, dest_root: Path) -> Path:
    url = f"{_REST}/{_TIE_TITLE}"
    print(f"GET {url}")
    html = _fetch(url)
    chunks = _extract_tie(html)
    rendered = _render(chunks)
    dest_dir = dest_root / "spinoza" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "tie.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(chunks)} chunks)")
    return dest


def fetch_tp(*, dest_root: Path) -> Path:
    url = f"{_REST}/{_TP_TITLE}"
    print(f"GET {url}")
    html = _fetch(url)
    chunks = _extract_tp(html)
    rendered = _render(chunks)
    dest_dir = dest_root / "spinoza" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "tp.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(chunks)} chunks)")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/spinoza/raw_la/.",
    )
    args = parser.parse_args()
    fetch_ethica(dest_root=args.data_root)
    fetch_tie(dest_root=args.data_root)
    fetch_tp(dest_root=args.data_root)


if __name__ == "__main__":
    main()
