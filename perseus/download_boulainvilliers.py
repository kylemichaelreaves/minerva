#!/usr/bin/env python3
"""Download Boulainvilliers's *Memoires Historiques sur l'ancien
Gouvernement de la France* + *Lettres sur les anciens parlemens de
France* — the Frankish-conquest / two-race thesis that Nietzsche later
reformulates as master/slave morality, plus the political-historical
follow-on in epistolary form.

Sources:

* **Histoire**: archive.org ``etatdelafranceda01boul`` (1727 first
  edition of *Etat de la France* — bundles the historical essays as
  its preface). The OCR reads the long s as ``f`` throughout
  (``Hiftorïques``, ``fans``), which the cleaner's f→s pass repairs.
* **Lettres**: archive.org ``lettressurlesan00boulgoog`` (1753
  standalone first edition, Google Books scan). Rougher OCR, the same
  long-s misread, but with intact ``PREMIERE LETTRE.`` /
  ``SECONDE LETTRE.`` / ... section headings.

What this script ships:

* ``data/boulainvilliers/histoire_anc_gouv_fra.txt`` — the author's
  Préface and the *Mémoires historiques*. The full 3.1 MB archive.org
  file is the entire Etat de la France; the cut starts at the Préface's
  ``L'AUTEUR.'`` heading line, dropping the subscriber list, the
  publisher's Avertissement, the fold-out map's OCR and Louis XIV's 1697
  *Mémoire* to the intendants (not by Boulainvilliers), and ends on the
  Mémoires' last sentence, before ``Fin des Mémoires …`` and the
  intendant reports per province (#779).
* ``data/boulainvilliers/lettres_parlemens_fra.txt`` — the fourteen
  letters from the 1753 standalone edition, from ``PREMIERE LETTRE.``
  on (Google Books' usage notice and the title page are dropped). The
  all-caps ``PREMIERE LETTRE.`` / ``SECONDE LETTRE.`` headings hit the
  chapter-splitter's secondary branch
  (``[A-Z][A-Z \\-—:,'.]{6,80}``) and produce per-letter chunks.

Both files then go through ``scripts/clean-boulainvilliers-texts.py``.
``--raw-dir DIR`` reads ``DIR/<item>_djvu.txt`` instead of fetching, and
``--out-dir DIR`` writes somewhere other than ``data/boulainvilliers``.

What this script does NOT ship:

* *Essai sur la noblesse de France* — not on archive.org. It is
  extracted from a Gallica PDF by ``scripts/extract-essai-pdf.py``.
* *Lettres sur les anciens parlemens* — English Dryden 1739
  translation. The only PD English of any Boulainvilliers work, but
  the archive.org OCR is rough (raw long-s, mangled letter headings).
  Defer until cleanup investment is warranted or a re-keyed source
  appears.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "boulainvilliers"


def _archive_djvu(item: str) -> str:
    return f"https://archive.org/download/{item}/{item}_djvu.txt"


@dataclass(frozen=True)
class _Cut:
    """One archive.org item, sliced at fixed line numbers that are checked.

    archive.org regenerates OCR, and a regenerated file moves an absolute
    line cut with no error (#499). So each cut carries *fingerprints*: text
    that today's OCR has at known lines, compared whitespace-folded. If any
    is missing the OCR has changed, and the script raises rather than slice
    a file it was not written against.

    The fingerprints include the bounds themselves — the line at `start`
    and, when there is an `end`, the line at `end - 1` — so the first and
    last lines kept are content anchors, not offsets that happen to land
    near one (#779). `start`/`end` are 0-based slice indexes into
    ``raw.splitlines()``: `start=2089` keeps 1-based line 2090 onward.
    """

    item: str
    start: int
    end: int | None
    fingerprints: tuple[tuple[int, str], ...]


# The author's Préface and the Mémoires historiques. The Préface heading is
# printed `PREFACE` / `DE` / `L'AUTEUR.'` on three lines; the cleaner drops
# `PREFACE` as a running head, so a cut there would open the file on an
# orphaned `DE`. Before it: subscriber list, Avertissement, map OCR and
# Louis XIV's 1697 Mémoire. After the end: `Fin des Mémoires Hiftorïques…`
# and the intendant reports per province.
HISTOIRE = _Cut(
    item="etatdelafranceda01boul",
    start=2089,
    end=14312,
    fingerprints=(
        (2085, "PREFACE"),
        (2089, "L'AUTEUR.'"),
        (2092, "' A I ramafle avec foin les Mémoires de toutes les Généralitez"),
        (14311, "ici, fans autre intérêt que celui de leur gloire & du bien de l'Etat en général."),
        (14314, "Fin des Mémoires Hiftorïques fur l'ancien Gouvernement de France."),
    ),
)

# The 14 letters run across three volumes (TOME PREMIER, TOME SECOND and
# `TOME TROISIFME,` at raw line 18117, all joined in this djvu.txt);
# everything from the first letter's heading on is kept.
LETTRES = _Cut(
    item="lettressurlesan00boulgoog",
    start=166,
    end=None,
    fingerprints=(
        (165, "Par M. dt BotriAiNviLtiERs."),
        (166, "PREMIERE LETTRE."),
    ),
)


def _check_cut(lines: list[str], cut: _Cut) -> None:
    for index, text in cut.fingerprints:
        got = " ".join(lines[index].split()) if index < len(lines) else ""
        if text not in got:
            raise RuntimeError(
                f"{cut.item}: line {index + 1} no longer reads {text!r} "
                f"(got {got[:80]!r}). archive.org has regenerated the OCR; "
                f"re-probe the cut before re-running."
            )


def _fetch(url: str) -> str:
    """Pull the raw djvu.txt from archive.org with a User-Agent set
    (default urllib UA gets occasionally rate-limited)."""

    return fetch_with_retry(
        url,
        timeout=120,
        user_agent="minerva-ingest/1.0",
        encoding="utf-8",
    )


def _slice(lines: list[str], cut: _Cut) -> list[str]:
    """The cut's lines, after checking every fingerprint."""

    _check_cut(lines, cut)
    return lines[cut.start : cut.end]


def _clean(raw: str, cut: _Cut) -> str:
    """Trim to the cut's line range and drop the "Digitized by Google"
    page footers. Light text-level cleanup (collapse run-of-spaces and
    repeated blank lines) so the chapter splitter sees a usable
    paragraph structure."""

    text = "\n".join(_slice(raw.splitlines(), cut))
    # Drop recurring page footers that punctuate the OCR.
    text = re.sub(r"(?i)\bDigitized by Google\b", "", text)
    text = re.sub(r"(?i)\bdby Google\b", "", text)
    # Collapse runs of whitespace within lines (the OCR liberally
    # double-spaces for column alignment). Preserve paragraph blank
    # lines.
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    # Collapse 3+ consecutive blank lines to 2 (paragraph separator).
    return re.sub(r"\n{3,}", "\n\n", text)


def _read_raw(cut: _Cut, raw_dir: Path | None) -> str:
    if raw_dir is not None:
        path = raw_dir / f"{cut.item}_djvu.txt"
        print(f"Reading {path} ...", file=sys.stderr)
        return path.read_text(encoding="utf-8")
    url = _archive_djvu(cut.item)
    print(f"Fetching {url} ...", file=sys.stderr)
    return _fetch(url)


def _fetch_and_clean(cut: _Cut, out_path: Path, raw_dir: Path | None = None) -> None:
    raw = _read_raw(cut, raw_dir)
    print(f"  raw size: {len(raw):,} chars", file=sys.stderr)
    cleaned = _clean(raw, cut)
    print(f"  after cleanup: {len(cleaned):,} chars", file=sys.stderr)
    out_path.write_text(cleaned, encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--raw-dir", type=Path, help="read <item>_djvu.txt from here instead of archive.org"
    )
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    _fetch_and_clean(HISTOIRE, args.out_dir / "histoire_anc_gouv_fra.txt", args.raw_dir)
    _fetch_and_clean(LETTRES, args.out_dir / "lettres_parlemens_fra.txt", args.raw_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
