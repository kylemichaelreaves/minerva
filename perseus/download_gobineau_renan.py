#!/usr/bin/env python3
"""Download Gobineau's *Essai sur l'inégalité des races humaines*
and Renan's *Vie de Jésus*, *L'Antéchrist*, and *Histoire du peuple
d'Israël* from archive.org.

Source manifest:

  Gobineau Essai, tomes I-IV — the 1853-55 first edition (Paris,
  Firmin Didot; Hanover, Rumpler), one archive.org scan per tome,
  re-sourced 2026-10 (#742). The 1884 two-tome reset is a different
  setting and must not be mixed in. Each tome is identified by its
  title page, not by its archive.org id: the ``01``..``06`` in
  ``essaisurlingali0Ngobigoog`` are Google disambiguators, not volume
  numbers, and reading them as "vol. N" put Tome IV in the corpus twice
  and Tome III not at all. See ``GOBINEAU_TOMES``.

  Renan Vie de Jésus (1863) — University of Toronto scan. Clean OCR
  (no long-s preserved). Identifier: viedejsus00renauoft

  Renan L'Antéchrist (1877) — = vol 4 of Histoire des origines du
  christianisme. Identifier: histoiredesorigi04renauoft

  Renan Histoire du peuple d'Israël vols 1-5 — 1887/1889/1893 first
  editions. Identifiers: histoiredupeuple01rena .. histoiredupeuple05rena

Renan's cleanup applies the same minimal pass as the Boulainvilliers
fetcher: drop Google Books boilerplate at the head (a fixed 60 lines),
strip page footers, collapse run-of-spaces, normalize blank lines.
Gobineau's starts each tome at its half-title instead and checks the
title page first (`clean_tome`). The chapter splitter then catches
ALL-CAPS heading anchors that come through the OCR intact.

See ``add-gobineau-renan-plan`` memory for source manifest +
expected xref payoff.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent

# Per-author data directories. The corpus-label parser walks each
# of these and dispatches by filename via `find_work`.
GOBINEAU_DIR = REPO_ROOT / "data" / "gobineau"
RENAN_DIR = REPO_ROOT / "data" / "renan"

# Conservative header drop for Renan — Google Books scans typically
# prepend ~30-80 lines of licence boilerplate + the cover image text.
# The chunker then handles whatever residual front-matter slips
# through. Gobineau does not use it: one of its scans has no licence
# preamble at all, and 60 lines in is its first chapter (`clean_tome`).
HEADER_LINES = 60


def _archive_djvu(item: str) -> str:
    return f"https://archive.org/download/{item}/{item}_djvu.txt"


def _fetch(url: str) -> str:
    return fetch_with_retry(
        url,
        timeout=180,
        user_agent="minerva-ingest/1.0",
        encoding="utf-8",
    )


def _normalize(text: str) -> str:
    """Drop the Google page footers; collapse whitespace runs inside a
    line and blank-line runs to one paragraph break."""

    text = re.sub(r"(?i)\bDigitized by Google\b", "", text)
    text = re.sub(r"(?i)\bdby Google\b", "", text)
    # Collapse intra-line whitespace runs; preserve blank-line paragraphs.
    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        cleaned.append(re.sub(r"[ \t]+", " ", raw_line).strip())
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _clean(raw: str) -> str:
    """Boilerplate strip + light whitespace normalization (Renan).

    Same shape as the Boulainvilliers fetcher's `_clean`. Idempotent —
    rerunning produces identical output for identical input.
    """

    return _normalize("\n".join(raw.splitlines()[HEADER_LINES:]))


# ──────────────────────────────────────────────────────────────────
# Gobineau: one scan per tome, identified by its title page
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Tome:
    """One tome of the *Essai*, and the archive.org scan it comes from.

    ``title_page`` is text today's OCR prints on the half-title and title
    page, compared whitespace-folded: the tome line exactly as the OCR
    misreads it, plus a publisher or date line where one is legible. It
    does two jobs. It proves the scan is the tome it is filed as — the
    check that would have caught #742, where a Tome IV went in as
    "vol. 1" — and, like the Boulainvilliers `_Cut` fingerprints (#499),
    it fails loudly when archive.org regenerates the OCR rather than
    letting a different text through unseen.
    """

    number: int
    item: str
    title_page: tuple[str, ...]

    @property
    def out(self) -> str:
        return f"essai_inegalite_tome{self.number}_fra.txt"


GOBINEAU_TOMES: tuple[_Tome, ...] = (
    # Google scan, IA's OCR: 89.9% French vocabulary hit. Was "vol2".
    _Tome(1, "essaisurlingali02gobigoog", ("TOME PREMIER", "HANOVRE.— RUMPLKR")),
    # IA's own OCR of a Google scan with no licence preamble: 88.7%,
    # against 57.2% for the corrupt scan that was "vol4".
    _Tome(
        2,
        "bub_gb_kMd-BHlp-M8C",
        ("TOME SECOND.", "HANOVRE. — RUMPLER, LIBRAIRE-EDITEUR.", "1853."),
    ),
    # Was missing. 86.5%; the alternative, essaisurlingali06gobigoog,
    # binds Tomes III and IV together and its IA OCR reads 70.6% over
    # the Tome III half.
    _Tome(3, "bub_gb_Qk-jzgOI3KQC", ("TOME TROISIÈME.", "FRANCE A FRANCFORT", "1855 .")),
    # The better of two Tome IV scans: 88.7%, against 68.3% for
    # essaisurlingali03gobigoog, which was also ingested, as "vol3".
    _Tome(
        4,
        "essaisurlingali01gobigoog",
        ("TOME QUATRIÈAIE.", "TOME gUATUlKME.", "LIBRAIRIE J)K FÏRMIN DIDOT FRÈRES."),
    ),
)

#: Every tome opens on the half-title ``ESSAI`` (``SUR L'INÉGALITÉ DES
#: RACES HUMAINES``), after Google's usage notice when the scan has one.
_HALF_TITLE = "ESSAI"
#: The notices run to ~110 lines (English, then French on some scans).
_HALF_TITLE_WITHIN = 200
#: How far past the half-title the title-page text may sit.
_TITLE_PAGE_LINES = 80
#: A Google page footer is a line of its own, ``Digitized by Google``,
#: which the newer OCR misreads three dozen ways (``Oigitized``,
#: ``Digifaeâtiy``, ``J by Google``). No 1850s line says "Google", so any
#: short line that does is a footer...
_FOOTER_MAX_CHARS = 40
#: ...and any longer one left in the output is Google's usage notice,
#: which would be indexed as body text.
_GOOGLE = "Google"


def _fold(line: str) -> str:
    return " ".join(line.split())


def _half_title(lines: list[str], tome: _Tome) -> int:
    for index, line in enumerate(lines[:_HALF_TITLE_WITHIN]):
        if line.strip() == _HALF_TITLE:
            return index
    raise RuntimeError(
        f"{tome.item}: no half-title {_HALF_TITLE!r} in the first "
        f"{_HALF_TITLE_WITHIN} lines. archive.org has regenerated the OCR; "
        f"re-probe the scan before re-running."
    )


def _check_title_page(lines: list[str], tome: _Tome) -> None:
    page = "\n".join(_fold(line) for line in lines[:_TITLE_PAGE_LINES])
    for text in tome.title_page:
        if text not in page:
            raise RuntimeError(
                f"{tome.item}: the title page no longer reads {text!r}. Either "
                f"archive.org has regenerated the OCR or this scan is not "
                f"Tome {tome.number}; re-probe it before re-running."
            )


def _is_footer(line: str) -> bool:
    return _GOOGLE in line and len(line) <= _FOOTER_MAX_CHARS


def _check_no_notice(text: str, tome: _Tome) -> None:
    index = text.find(_GOOGLE)
    if index >= 0:
        raise RuntimeError(
            f"{tome.item}: Google's usage notice survived the cut and would be "
            f"indexed as body text: {text[max(0, index - 40) : index + 40]!r}"
        )


def clean_tome(raw: str, tome: _Tome) -> str:
    """One tome's text, from its half-title to the end of the scan.

    Content-anchored rather than a fixed line drop: the body starts at the
    half-title wherever it falls, and the title page after it must name the
    tome. Curly apostrophes are straightened — Tomes II and III come from a
    newer OCR that prints ’ (6,696 and 5,124 of them) where I and IV print
    ', and `split_by_chapter`'s capitals heading class takes only the
    straight one, so ``CIVILISATION ANTIQUE RAYONNANT DE L’ASIE CENTRALE``
    would not split.
    """

    lines = raw.splitlines()
    body = lines[_half_title(lines, tome) :]
    _check_title_page(body, tome)
    # Footers go line by line here, before `_normalize`: the newer OCR
    # double-spaces them (`Digitized  by  Google`, 311 in Tome II), which
    # its single-spaced pattern misses, and misreads 73 of them besides.
    folded = [_fold(line) for line in body]
    text = _normalize("\n".join(line for line in folded if not _is_footer(line)))
    text = text.replace("’", "'").replace("‘", "'")
    _check_no_notice(text, tome)
    return text


def _fetch_to(item: str, out_path: Path, clean: Callable[[str], str] = _clean) -> None:
    url = _archive_djvu(item)
    print(f"  Fetching {url}", file=sys.stderr)
    raw = _fetch(url)
    cleaned = clean(raw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(cleaned, encoding="utf-8")
    print(
        f"    raw {len(raw):>9,} → cleaned {len(cleaned):>9,} chars  →  {out_path}",
        file=sys.stderr,
    )


def fetch_gobineau() -> None:
    for tome in GOBINEAU_TOMES:
        _fetch_to(tome.item, GOBINEAU_DIR / tome.out, lambda raw, t=tome: clean_tome(raw, t))


# ──────────────────────────────────────────────────────────────────
# Renan: source → output mapping
# ──────────────────────────────────────────────────────────────────

RENAN_SOURCES: list[tuple[str, str]] = [
    ("viedejsus00renauoft", "vie_de_jesus_fra.txt"),
    ("histoiredesorigi04renauoft", "antechrist_fra.txt"),
    *[(f"histoiredupeuple0{v}rena", f"peuple_israel_vol{v}_fra.txt") for v in range(1, 6)],
]


def main() -> int:
    print("=== Gobineau ===", file=sys.stderr)
    fetch_gobineau()
    print("=== Renan ===", file=sys.stderr)
    for item, out in RENAN_SOURCES:
        _fetch_to(item, RENAN_DIR / out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
