#!/usr/bin/env python3
"""Strip the gutenberg.spiegel.de site chrome from Marx source files.

The Marx downloader pulls from gutenberg.spiegel.de — and for a
few files (``deutsche_ideologie.txt``, ``oek_phil_manuskripte_1844.txt``)
through the Wayback Machine. Both wrap every chapter in promotional
+ navigation + bibliographic chrome:

    <Title> – Karl Marx ← Zurück zur Startseite <Title>
    Kapitel 1. Titelseite 2. <ch1> 3. <ch2> ...             # flattened TOC
    Verlag: ... | Jahr: ... | Übersetzer: ...               # bibliographic banner
    Wenn Sie das Buch lieber in der Hand halten möchten...
    Bei [tredition] Bei Amazon Bei Thalia [Lokale Buchhandlung]
    ← Vorheriges Kapitel N / M Nächstes Kapitel →
    ...chapter body...
    Karl Marx-Friedrich Engels - <Title>                    # byline
    Projekt Gutenberg unterstützen
    Projekt Gutenberg lebt davon, dass Literatur frei zugänglich
        bleibt.Mit Ihrer Unterstützung helfen Sie, ...
    Nein. Ich möchte unterstützen!

The Wayback-scraped files additionally carry IA viewer chrome
interleaved between sections:

    The Wayback Machine - https://web.archive.org/web/.../...
    <N> captures <date1> - <date2>
    Collection: Wikipedia Outlinks March 2016
    Crawl of outlinks from wikipedia.org started March, 2016. ...
    The Internet Archive discovers and captures web pages ...
    The seed list contains a total of 431,055,452 URLs...
    MIA > Deutsch > Marxisten > Marx/Engels > ...

A book with N chapters ingests N copies of every chrome line.
The 2026-05-30 corpus quality audit flagged **3,140 duplicate
chunks** in Marx alone — every one of them was this boilerplate.

Strip with line-by-line regex matching against a curated allow-
list of the exact chrome phrases. Anything else (Marx's actual
prose) passes through untouched.

Idempotent: re-running on an already-cleaned file produces the
same output (the regexes don't match anything by then).

Role: oneoff
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARX_DIR = REPO_ROOT / "data" / "marx" / "raw_deu"

# Each pattern matches a complete line (after .strip()). Lines that
# match are dropped entirely. Empty-line collapse runs at the end.
_CHROME_LINE_PATTERNS = [
    # --- gutenberg.spiegel.de chrome ---
    # Title + back-button header. Example:
    #   "Der 18. Brumaire des Louis Bonaparte – Karl Marx ←
    #    Zurück zur Startseite Der 18. Brumaire des Louis Bonaparte"
    # The "Meistgelesen" suffix appears on some titles
    # (zur_kritik_pol_oekonomie.txt).
    re.compile(r"^.+– Karl Marx ← Zurück zur Startseite .+$"),
    # Flattened TOC summary line. Every gutenberg.spiegel.de
    # chapter page repeats the full book TOC inline like:
    #   "Kapitel 1. Titelseite 2. Vorrede 3. I. Kapitel ..."
    # Pinned by the literal prefix "Kapitel 1. Titelseite ".
    re.compile(r"^Kapitel 1\. Titelseite .+$"),
    # Bibliographic banner: "Verlag: ... | Jahr: ... [| Übersetzer: ...]".
    re.compile(r"^Verlag: .+\| Jahr: .+$"),
    # Print/buy CTA banner.
    re.compile(
        r"^Wenn Sie das Buch lieber in der Hand halten möchten, "
        r"können Sie es hier erwerben:$"
    ),
    # Vendor row — variants with/without "Bei tredition" prefix.
    # NB: the original regex doubled "Bei "; fixed here so the bare
    # "Bei Amazon Bei Thalia ..." form matches.
    re.compile(r"^(?:Bei tredition )?Bei Amazon Bei Thalia(?: Lokale Buchhandlung)?$"),
    # Chapter pager.
    re.compile(r"^← Vorheriges Kapitel \d+ / \d+ Nächstes Kapitel →$"),
    # Donation footer block.
    re.compile(r"^Projekt Gutenberg unterstützen$"),
    re.compile(
        r"^Projekt Gutenberg lebt davon, dass Literatur frei zugänglich "
        r"bleibt\.Mit Ihrer Unterstützung helfen Sie, diese Bibliothek zu "
        r"erhalten und weiter auszubauen\.$"
    ),
    re.compile(r"^Nein\. Ich möchte unterstützen!$"),
    # Secondary running header — "<Title> · Karl Marx" (U+00B7).
    re.compile(r"^.+ · Karl Marx$"),
    # Author/byline trailer at the end of a section:
    #   "Karl Marx-Friedrich Engels - Die deutsche Ideologie"
    re.compile(r"^Karl Marx-Friedrich Engels - .+$"),
    # --- Wayback Machine / Internet Archive viewer chrome ---
    # The Wayback page header lists the source URL.
    re.compile(r"^The Wayback Machine - https?://.+$"),
    # Capture-count line: "269 captures 20 Feb 2001 - 03 May 2026".
    re.compile(r"^\d+ captures \d+ [A-Za-zäöü]+ \d+ - \d+ [A-Za-zäöü]+ \d+$"),
    # IA collection banner.
    re.compile(r"^Collection: Wikipedia Outlinks March 2016$"),
    # IA crawl description paragraph (single long line).
    re.compile(r"^Crawl of outlinks from wikipedia\.org started .+$"),
    # IA Wayback Machine description.
    re.compile(r"^The Internet Archive discovers and captures web pages .+$"),
    # IA seed-list description.
    re.compile(r"^The seed list contains a total of .+$"),
    re.compile(r"^The modified seed list contains a total of .+$"),
    # MIA (Marxists Internet Archive) breadcrumb:
    #   "MIA > Deutsch > Marxisten > Marx/Engels > Öko.-phil. Manuskripte"
    re.compile(r"^MIA > .+$"),
]


# Minimum line length for the same-file dedup pass to consider a
# line as "substantive prose". Lines shorter than this stay even
# if they repeat — they're things like "Karl Marx" (chapter
# trailer), short headings, "1." numerals — repetition there is
# expected typography, not chrome.
_DEDUP_MIN_LEN = 60


def clean_text(raw: str) -> tuple[str, int, int]:
    """Strip chrome lines + same-file dup paragraphs.

    Returns ``(cleaned_text, chrome_dropped, dup_dropped)``. The
    dedup pass runs AFTER chrome strip: gutenberg.spiegel.de's
    per-chapter pages re-paste the prior chapter's trailing
    paragraph as a context recap, which the audit then flags as
    a duplicate chunk. Keeping the first occurrence of any
    ≥60-char line and dropping the rest in the same file is safe
    — Marx's actual prose doesn't repeat 100+ -char paragraphs
    verbatim within a single work (rhetorical repetition uses
    variations, not exact copies).
    """

    out_lines: list[str] = []
    chrome_dropped = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        if any(p.match(stripped) for p in _CHROME_LINE_PATTERNS):
            chrome_dropped += 1
            continue
        out_lines.append(line)

    # Same-file dedup pass.
    seen: set[str] = set()
    deduped: list[str] = []
    dup_dropped = 0
    for line in out_lines:
        stripped = line.strip()
        if len(stripped) >= _DEDUP_MIN_LEN:
            if stripped in seen:
                dup_dropped += 1
                continue
            seen.add(stripped)
        deduped.append(line)

    cleaned = "\n".join(deduped)
    # Collapse 3+ consecutive blank lines (left after chrome strip).
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, chrome_dropped, dup_dropped


def main() -> int:
    if not MARX_DIR.is_dir():
        print(f"Marx directory not found: {MARX_DIR}", file=sys.stderr)
        return 1
    total_chrome = 0
    total_dups = 0
    for path in sorted(MARX_DIR.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        cleaned, chrome, dups = clean_text(raw)
        if chrome or dups:
            path.write_text(cleaned, encoding="utf-8")
            total_chrome += chrome
            total_dups += dups
            print(
                f"  {path.name}: -{chrome} chrome, -{dups} dups "
                f"({len(raw):,} → {len(cleaned):,} chars)",
                file=sys.stderr,
            )
        else:
            print(f"  {path.name}: clean", file=sys.stderr)
    print(
        f"\nStripped {total_chrome} chrome lines + {total_dups} duplicate paragraphs.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
