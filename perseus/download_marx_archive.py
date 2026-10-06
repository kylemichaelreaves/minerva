#!/usr/bin/env python3
"""Download Marx works from three OCR/HTML sources.

Three pipelines:

  1. **Internet Archive OCR** — Kapital Bd 1 (`daskapitalkritik67marx`,
     1867 Fraktur first edition), Bd 2 (`ldpd_13046079_002`), Bd 3
     (`ldpd_13046079_003`). Each item exposes a `_djvu.txt` plain
     OCR file; we fetch it directly. Output lands in
     `data/marx/raw_deu_ocr/` so the ingest dispatcher routes it
     through the German state-machine parser at `marx_de.py`.

  2. **marxists.org native HTML** — Ökonomisch-philosophische
     Manuskripte 1844, served as 11 sub-pages of
     `marxists.org/deutsch/archiv/marx-engels/1844/oek-phil/`.
     Concatenate sub-pages → `data/marx/raw_deu/oek_phil_manuskripte_1844.txt`.

  3. **web.archive.org snapshot of mlwerke.de** — Die deutsche
     Ideologie, lives at multiple `me03_NNN.htm` pages of an
     archived mlwerke.de Werke Bd 3. Concatenate sub-pages →
     `data/marx/raw_deu/deutsche_ideologie.txt`. The wayback wrapper
     adds a toolbar we strip via the extractor — by **`id`**, not by
     class: see `_SKIP_ID_TOKENS` below and issue #152.

Gap: Grundrisse der Kritik der politischen Ökonomie. No clean
plain-text German source found on archive.org or marxists.org;
deferred to a future round.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
from pathlib import Path

from _download import ParagraphExtractor, make_fetcher

# ─────────────────────────────────────────────────────────────────
# Internet Archive: Kapital Bd 1/2/3 djvu.txt
# ─────────────────────────────────────────────────────────────────

_IA_WORKS: tuple[tuple[str, str], ...] = (
    # (output filename, IA identifier)
    ("kapital_bd1.txt", "daskapitalkritik67marx"),  # 1867 Fraktur
    ("kapital_bd2.txt", "ldpd_13046079_002"),  # Bd 2
    ("kapital_bd3.txt", "ldpd_13046079_003"),  # Bd 3
)


def _ia_url(ident: str) -> str:
    return f"https://archive.org/download/{ident}/{ident}_djvu.txt"


# ─────────────────────────────────────────────────────────────────
# marxists.org: 1844 Manuscripts (11 sub-pages)
# ─────────────────────────────────────────────────────────────────

_MARXISTS_BASE = "https://www.marxists.org/deutsch/archiv/marx-engels/1844/oek-phil/"
_MARXISTS_1844_SUBPAGES: tuple[tuple[str, str], ...] = (
    # (heading inserted into output, sub-page filename)
    ("VORREDE", "vorrede.htm"),
    ("ARBEITSLOHN", "1-1_arbl.htm"),
    ("PROFIT DES KAPITALS", "1-2_prof.htm"),
    ("GRUNDRENTE", "1-3_grun.htm"),
    ("DIE ENTFREMDETE ARBEIT", "1-4_frem.htm"),
    ("DAS VERHÄLTNIS DES PRIVATEIGENTUMS", "2_prveig.htm"),
    ("PRIVATEIGENTUM UND ARBEIT", "3-1_prar.htm"),
    ("PRIVATEIGENTUM UND KOMMUNISMUS", "3-2_prkm.htm"),
    ("BEDÜRFNIS PRODUKTION UND ARBEITSTEILUNG", "3-3_prod.htm"),
    ("GELD", "3-4_geld.htm"),
    ("KRITIK DER HEGELSCHEN DIALEKTIK", "3-5_hegl.htm"),
)


# ─────────────────────────────────────────────────────────────────
# web.archive.org snapshot of mlwerke.de: Deutsche Ideologie
# ─────────────────────────────────────────────────────────────────
#
# The TOC page links to sub-pages me03_011.htm, me03_017.htm, etc.
# We extract those at runtime from the TOC; the TOC URL itself is
# fixed:

_WAYBACK_DI_TOC = (
    "https://web.archive.org/web/20160303184231/http://www.mlwerke.de/me/me03/me03_009.htm"
)
_WAYBACK_DI_BASE = "https://web.archive.org/web/20160303184231/http://www.mlwerke.de/me/me03/"


# ─────────────────────────────────────────────────────────────────
# Shared: retry-with-backoff fetch
# ─────────────────────────────────────────────────────────────────


_fetch = make_fetcher()

# Tag sets are the canonical pair shared with the other HTML scrapers.
#
# The skip sets below are measured against the live pages, not inferred
# from this docstring — issue #152, which was filed because the previous
# values were the inference. All seven of those class tokens
# (`wm-ipp`, `wm-ipp-base`, `wm-ipp-print`,
# `wb-autocomplete-suggestions`, `donato`, `footer`, `navbar`) matched
# **zero elements** on every one of this module's three sources, so the
# guard was inert and the wayback chrome came through: `269 captures 20
# Feb 2001 - 28 Jul 2026`, `Collection: Wikipedia Outlinks March 2016`,
# `The Wayback Machine - https://…` and a 606-character crawl blurb all
# cleared the caller's `len >= 30` filter.
#
# The wayback toolbar carries **no distinguishing class** — it is keyed
# on `id`, which is why a class-only set could never see it. marxists.org
# names its own chrome with classes, but different ones than assumed:
# `p.toplink` is the `MIA > Deutsch > …` breadcrumb and `p.link` the
# "Anfang der Seite / Zuletzt aktualisiert am …" footer. `p.fst` (body)
# and `p.note` (Marx's own manuscript notes) are content and stay.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})
_SKIP_CLASS_TOKENS = frozenset({"toplink", "link", "updat"})
_SKIP_ID_TOKENS = frozenset(
    {
        "wm-ipp",
        "wm-ipp-base",
        "wm-ipp-print",
        "donato",
        "donato-base",
        "donato-if",
    }
)


# web.archive.org delimits its injected toolbar with these two literal
# comments. Excising the region between them is the only reliable way to
# drop it: attribute-based subtree skipping cannot, because the toolbar's
# own markup is tag-unbalanced. Measured on `me03_017.htm` — with
# `wm-ipp-base` correctly matched by id and skipping active, a stray
# `</form>` drove ParagraphExtractor's depth counter from 1 to 0 partway
# through the toolbar, and `269 captures 20 Feb 2001 - 28 Jul 2026`,
# `Collection: Wikipedia Outlinks March 2016` and a 606-character crawl
# blurb leaked out (#152). This is issue #297.
_WAYBACK_INSERT_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?"
    r"<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.IGNORECASE | re.DOTALL,
)


def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
        skip_id_tokens=_SKIP_ID_TOKENS,
    )
    # Some pages (mlwerke.de via web.archive.org) are ISO-8859-1.
    try:
        decoded = html.decode("utf-8")
    except UnicodeDecodeError:
        decoded = html.decode("iso-8859-1")
    # Primary defence. `_SKIP_ID_TOKENS` stays as a second line for
    # snapshots served without the boundary comments; on its own it
    # removed 3 of the 6 leaking chrome paragraphs.
    decoded = _WAYBACK_INSERT_RE.sub("", decoded)
    p.feed(decoded)
    p.close()
    return p.paragraphs


# ─────────────────────────────────────────────────────────────────
# Pipeline 1: IA OCR
# ─────────────────────────────────────────────────────────────────


def fetch_ia_ocr(*, dest_root: Path) -> list[Path]:
    """Fetch each Kapital Bd's djvu.txt and write verbatim to
    `data/marx/raw_deu_ocr/`. No paragraph extraction — the OCR
    text comes through as-is for the state-machine parser to
    chunk."""

    dest_dir = dest_root / "marx" / "raw_deu_ocr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, ident in _IA_WORKS:
        url = _ia_url(ident)
        print(f"\n{filename} ← IA {ident}")
        print(f"  GET {url}")
        raw = _fetch(url)
        body = raw.decode("utf-8", errors="replace")
        dest = dest_dir / filename
        dest.write_text(body, encoding="utf-8")
        print(f"  ↳ {dest} ({len(body):,} chars)")
        written.append(dest)
        time.sleep(1.0)
    return written


# ─────────────────────────────────────────────────────────────────
# Pipeline 2: marxists.org 1844 Manuscripts
# ─────────────────────────────────────────────────────────────────


def fetch_1844_manuscripts(*, dest_root: Path) -> Path:
    print("\noek_phil_manuskripte_1844.txt ← marxists.org /1844/oek-phil/")
    out: list[str] = []
    for heading, sub_path in _MARXISTS_1844_SUBPAGES:
        url = _MARXISTS_BASE + sub_path
        print(f"  GET {url}")
        raw = _fetch(url)
        paragraphs = _extract_paragraphs(raw)
        body = [p for p in paragraphs if len(p) >= 30]
        if not body:
            print(f"    WARNING: 0 paragraphs from {sub_path}; skipping")
            continue
        print(f"    {len(body)} paragraphs")
        out.append("")
        out.append(heading)
        out.append("")
        out.extend(body)
        time.sleep(1.0)
    rendered = "\n\n".join(out).strip() + "\n"
    dest_dir = dest_root / "marx" / "raw_deu"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "oek_phil_manuskripte_1844.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  ↳ {dest} ({len(rendered):,} chars)")
    return dest


# ─────────────────────────────────────────────────────────────────
# Pipeline 3: web.archive.org/mlwerke.de Deutsche Ideologie
# ─────────────────────────────────────────────────────────────────


_DI_SUBPAGE_RE = re.compile(r'href="(me03_\d+\.htm)(?:#[^"]*)?"')

# mlwerke.de's own chrome, which carries no class or id to skip on: a
# per-page running head, the "back to index" nav link, and the MEW
# edition note. All three are absent from the committed
# `deutsche_ideologie.txt`, so the lost original filtered them; they are
# re-filtered here rather than left to bleed into corpus chunks. The same
# edition note *did* leak from a sibling scraper — 18 chunks under
# `Das Kapital, Band III` and `Lohnarbeit und Kapital` carry it today
# (#298).
_MLWERKE_CHROME_RES = (
    re.compile(r"^Karl Marx\s*[-–]\s*Friedrich Engels\s*[-–]\s*.{0,60}$"),
    re.compile(r"^Zurück zum Gesamtverzeichnis\b"),
    re.compile(r"^Seitenzahlen verweisen auf:"),
)


def _drop_mlwerke_chrome(paragraphs: list[str]) -> list[str]:
    return [p for p in paragraphs if not any(rx.match(p) for rx in _MLWERKE_CHROME_RES)]


def fetch_deutsche_ideologie(*, dest_root: Path) -> Path:
    """Walk the TOC for me03_NNN.htm sub-pages, fetch each
    (deduplicated), concatenate with no synthetic headers (the
    body content includes Roman-numeral chapter headers naturally
    that the splitter recognizes)."""

    print("\ndeutsche_ideologie.txt ← web.archive.org snapshot of mlwerke.de")
    print(f"  GET {_WAYBACK_DI_TOC} (TOC)")
    toc_raw = _fetch(_WAYBACK_DI_TOC)
    try:
        toc_text = toc_raw.decode("utf-8")
    except UnicodeDecodeError:
        toc_text = toc_raw.decode("iso-8859-1")
    sub_pages: list[str] = []
    for m in _DI_SUBPAGE_RE.finditer(toc_text):
        page = m.group(1)
        if page not in sub_pages and page != "me03_009.htm":  # exclude TOC itself
            sub_pages.append(page)
    print(f"  found {len(sub_pages)} sub-pages")

    out: list[str] = []
    for page in sub_pages:
        url = _WAYBACK_DI_BASE + page
        print(f"  GET {url}")
        try:
            raw = _fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"    404 on {page}; skipping")
                continue
            raise
        paragraphs = _drop_mlwerke_chrome(_extract_paragraphs(raw))
        body = [p for p in paragraphs if len(p) >= 30]
        if not body:
            print(f"    0 paragraphs from {page}; skipping")
            continue
        print(f"    {len(body)} paragraphs")
        out.extend(body)
        out.append("")
        time.sleep(1.0)

    rendered = "\n\n".join(out).strip() + "\n"
    dest_dir = dest_root / "marx" / "raw_deu"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "deutsche_ideologie.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  ↳ {dest} ({len(rendered):,} chars)")
    return dest


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree.",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        choices=["ia", "1844", "ideologie"],
        default=(),
        help="Pipelines to skip (default: run all three).",
    )
    args = parser.parse_args()

    skip = set(args.skip)

    if "ia" not in skip:
        fetch_ia_ocr(dest_root=args.data_root)
    if "1844" not in skip:
        fetch_1844_manuscripts(dest_root=args.data_root)
    if "ideologie" not in skip:
        fetch_deutsche_ideologie(dest_root=args.data_root)

    print("\nGap: Grundrisse der Kritik der politischen Ökonomie deferred — no clean source found.")


if __name__ == "__main__":
    main()
