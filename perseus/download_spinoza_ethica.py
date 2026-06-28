#!/usr/bin/env python3
"""Download Spinoza's *Ethica* (Latin, 1677) from thelatinlibrary.com.

The Ethics is Spinoza's geometric-order masterwork — five Parts of
definitions, axioms, propositions, demonstrations, scholia, corollaries
and appendices. The minerva corpus previously carried it as a single
flat ``ethica.txt`` (one merged chunk per proposition: statement +
demonstration + scholium fused), which lost the apparatus structure and,
crucially, made the **Scholia** — where Spinoza's philosophy actually
lives — unretrievable on their own.

**Source:** ``thelatinlibrary.com`` ships the Ethica one Part per page
with the geometric apparatus labelled inline (``PROPOSITIO``,
``DEMONSTRATIO``, ``SCHOLIUM``, ``COROLLARIUM``, ``DEFINITIO``, …). The
downstream structure-aware splitter
:mod:`minerva.corpus.split_spinoza_ethica` reads that markup directly, so
this downloader's only job is to fetch the five raw HTML pages verbatim.

Quirks the splitter handles (don't "fix" them here — keep the bytes raw):
  * Parts II–V never close their ``<p>`` tags (the splitter parses with
    ``lxml`` so a ``<p>`` auto-closes at the next ``<p>``).
  * Part I omits the ``DEFINITIONES`` / ``AXIOMATA`` section headers — its
    definitions then axioms start straight in as ``I .`` items.
  * Part IV's single axiom is written ``AXIOMA: <content>`` (singular);
    Part II's physical-digression axioms restart numbering ``AXIOMA I/II``.
  * latin-1 encoding with HTML entities (``&aelig;`` etc.).

Output: ``data/spinoza/raw_la/ethica_ll_<N>.html`` for N in 1..5, the
filenames :mod:`minerva.authors.spinoza_works` points the Ethica work at.
"""

from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

_BASE = "https://www.thelatinlibrary.com/spinoza.ethica{n}.html"
_OUT = Path(__file__).resolve().parent.parent / "data" / "spinoza" / "raw_la"
_UA = "Mozilla/5.0 (minerva corpus downloader; +https://github.com/)"


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        url = _BASE.format(n=n)
        dest = _OUT / f"ethica_ll_{n}.html"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        dest.write_bytes(data)
        print(f"  {url} -> {dest.relative_to(_OUT.parent.parent)} ({len(data):,} bytes)")
        time.sleep(1)  # be polite to the host
    print("Done. Re-ingest with `make reingest-only ONLY=spinoza`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
