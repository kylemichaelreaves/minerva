"""Fetch the Gans/Werke OCR of Hegel's *Grundlinien der Philosophie des
Rechts* and extract its Zusätze (Additions) appendix.

The zeno.org German source we ingest (``pr_de.html``) carries the main
text and the Anmerkungen but **omits the Zusätze** — Gans compiled those
for the 1833 Werke edition from lecture notes. The only freely available
German source with them is the Google-digitized Gans edition on
archive.org, whose OCR is clean (Antiqua, not Fraktur). The Additions sit
in a back-of-volume appendix headed ``Zusätze.``, each item introduced by
``N. Zusatz zu § <num>. (<topic>.)``.

This writes the appendix verbatim to ``data/hegel/pr_de_zusaetze.txt``;
``corpus/split_hegel_pr_de.py`` parses it (split on "Zusatz zu § N",
de-hyphenate, strip Google watermarks / running headers) and splices each
Addition into the German work as an ``addition``-typed chunk under its §.

Usage:  python perseus/download_hegel_zusaetze.py
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

_ARCHIVE_ID = "grundlinienderp00gansgoog"
_URL = f"https://archive.org/download/{_ARCHIVE_ID}/{_ARCHIVE_ID}_djvu.txt"
_OUT = Path(__file__).resolve().parent.parent / "data" / "hegel" / "pr_de_zusaetze.txt"


def main() -> int:
    req = urllib.request.Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "replace")
    m = re.search(r"\bZus[äa]tze\.", text)
    if m is None:
        print("could not locate the 'Zusätze.' appendix header", file=sys.stderr)
        return 1
    appendix = text[m.start() :]
    n = len(re.findall(r"Zusatz\s+zu\s+§", appendix))
    _OUT.write_text(appendix, encoding="utf-8")
    print(f"wrote {_OUT} ({len(appendix)} chars, {n} Zusatz headers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
