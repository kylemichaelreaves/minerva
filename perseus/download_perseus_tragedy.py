#!/usr/bin/env python3
"""
Download Greek tragedies from PerseusDL/canonical-greekLit on GitHub.

Source: https://github.com/PerseusDL/canonical-greekLit
License: CC-BY-SA-4.0 (per the ``<licence>`` element in each TEI file).

Three tragedians, each with their Loeb-paired Greek + English TEI P5
files served from raw.githubusercontent.com:

  * Aeschylus  (tlg0085) — 7 surviving plays
  * Sophocles  (tlg0011) — 7 surviving plays (skips tlg008 Ichneutae,
                          a fragmentary satyr play)
  * Euripides  (tlg0006) — 19 surviving plays (Rhesus included
                          despite disputed authorship — traditional
                          corpus member)

Output layout
-------------
``perseus/raw_xml_<author>/<canonical_title>/{grc,eng}.xml``

One directory per play, named with the canonical title (e.g.
``oedipus_tyrannus``). The TEI parser keys on the directory name to
look up the canonical title in the ingest registry.

Why not Perseus dltext?
-----------------------
The other authors (Plato, Aristotle, Homer) fetch from the legacy
``hopper/dltext`` endpoint using ``Perseus:text:1999.01.NNNN`` document
IDs. Those IDs aren't documented in any catalog we can hit
programmatically — they were transcribed by hand from Perseus's web
TOC. For tragedy the canonical-greekLit GitHub repo IS the catalog
(every play sits at a predictable URN path), so the download is
deterministic and the script doesn't need a hand-maintained ID table.
"""

from __future__ import annotations

import argparse
import time
import urllib.error
from pathlib import Path

from _download import FailureAccumulator, fetch_bytes_with_retry

USER_AGENT = (
    "minerva-corpus-fetch/1.0 (+personal research; "
    "respects canonical-greekLit CC-BY-SA-4.0 license)"
)

RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "PerseusDL/canonical-greekLit/master/data"
)

# (work_urn_suffix, canonical_title, slug_for_directory)
# Canonical titles match the Loeb / OCT editions; slugs are
# lowercase-snake-case for filesystem friendliness.
AESCHYLUS_PLAYS: list[tuple[str, str, str]] = [
    ("tlg001", "Suppliants",            "suppliants"),
    ("tlg002", "Persians",              "persians"),
    ("tlg003", "Prometheus Bound",      "prometheus_bound"),
    ("tlg004", "Seven Against Thebes",  "seven_against_thebes"),
    ("tlg005", "Agamemnon",             "agamemnon"),
    ("tlg006", "Libation Bearers",      "libation_bearers"),
    ("tlg007", "Eumenides",             "eumenides"),
]
SOPHOCLES_PLAYS: list[tuple[str, str, str]] = [
    ("tlg001", "Trachiniae",            "trachiniae"),
    ("tlg002", "Antigone",              "antigone"),
    ("tlg003", "Ajax",                  "ajax"),
    ("tlg004", "Oedipus Tyrannus",      "oedipus_tyrannus"),
    ("tlg005", "Electra",               "electra"),
    ("tlg006", "Philoctetes",           "philoctetes"),
    ("tlg007", "Oedipus at Colonus",    "oedipus_at_colonus"),
    # tlg008 (Ichneutae / Tracking Satyrs) is a fragmentary satyr
    # play from Oxyrhynchus papyri — explicitly excluded per the
    # "surviving plays only" scope.
]
EURIPIDES_PLAYS: list[tuple[str, str, str]] = [
    ("tlg001", "Cyclops",                  "cyclops"),
    ("tlg002", "Alcestis",                 "alcestis"),
    ("tlg003", "Medea",                    "medea"),
    ("tlg004", "Heraclidae",               "heraclidae"),
    ("tlg005", "Hippolytus",               "hippolytus"),
    ("tlg006", "Andromache",               "andromache"),
    ("tlg007", "Hecuba",                   "hecuba"),
    ("tlg008", "Suppliants",               "suppliants"),
    ("tlg009", "Heracles",                 "heracles"),
    ("tlg010", "Ion",                      "ion"),
    ("tlg011", "Trojan Women",             "trojan_women"),
    ("tlg012", "Electra",                  "electra"),
    ("tlg013", "Iphigenia in Tauris",      "iphigenia_in_tauris"),
    ("tlg014", "Helen",                    "helen"),
    ("tlg015", "Phoenician Women",         "phoenician_women"),
    ("tlg016", "Orestes",                  "orestes"),
    ("tlg017", "Bacchae",                  "bacchae"),
    ("tlg018", "Iphigenia in Aulis",       "iphigenia_in_aulis"),
    ("tlg019", "Rhesus",                   "rhesus"),
]

# (author_urn, raw_dir_name, plays)
AUTHORS: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("tlg0085", "raw_xml_aeschylus", AESCHYLUS_PLAYS),
    ("tlg0011", "raw_xml_sophocles", SOPHOCLES_PLAYS),
    ("tlg0006", "raw_xml_euripides", EURIPIDES_PLAYS),
]

# Language → candidate TEI file suffixes on canonical-greekLit, in
# preference order. Most plays carry the ``-grc2`` / ``-eng2`` edition
# matching the Loeb pairing, but a handful (e.g. Aeschylus Agamemnon)
# only have ``-eng3`` / ``-eng4`` — typically because the original
# ``-eng2`` was reassigned to a different translator. We probe each
# variant in turn.
LANG_SUFFIX_CANDIDATES: dict[str, list[str]] = {
    "grc": ["perseus-grc2", "perseus-grc1", "perseus-grc3"],
    "eng": ["perseus-eng2", "perseus-eng3", "perseus-eng1", "perseus-eng4"],
}


def _fetch(url: str, *, retries: int = 8, timeout: float = 90.0) -> bytes:
    """HTTP GET with backoff for transient failures. raw.githubusercontent.com
    is reliable but rate-limits aggressively when hammered."""

    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers={
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
        backoff_initial=5.0,
        backoff_max=60.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Greek tragedy TEI from PerseusDL/canonical-greekLit.",
    )
    ap.add_argument(
        "--lang",
        choices=("grc", "eng", "both"),
        default="both",
        help="Which language editions to download (default: both).",
    )
    ap.add_argument(
        "--author",
        choices=("aeschylus", "sophocles", "euripides", "all"),
        default="all",
        help="Restrict to one tragedian (default: all three).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent,
        help=(
            "Parent directory for raw_xml_<author>/. "
            "Default: perseus/ (i.e. alongside the existing raw_xml/)."
        ),
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Seconds between requests (default: 0.4 — GitHub-friendly).",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip download if destination file already exists and is non-empty.",
    )
    args = ap.parse_args()

    if args.author == "all":
        authors = AUTHORS
    else:
        author_map = {
            "aeschylus": AUTHORS[0],
            "sophocles": AUTHORS[1],
            "euripides": AUTHORS[2],
        }
        authors = [author_map[args.author]]

    langs = ("grc", "eng") if args.lang == "both" else (args.lang,)

    total = sum(len(plays) * len(langs) for _, _, plays in authors)
    n = 0
    failures = FailureAccumulator()
    for author_urn, raw_dir_name, plays in authors:
        print(f"=== {raw_dir_name} ({len(plays)} plays × {len(langs)} langs) ===")
        out_root = args.out / raw_dir_name
        out_root.mkdir(parents=True, exist_ok=True)

        for work_urn, title, slug in plays:
            play_dir = out_root / slug
            play_dir.mkdir(parents=True, exist_ok=True)

            for lang in langs:
                n += 1
                dest = play_dir / f"{lang}.xml"
                rel = dest.relative_to(args.out)
                print(f"[{n}/{total}] {title} ({lang}) -> {rel}")
                if (
                    args.skip_existing
                    and dest.is_file()
                    and dest.stat().st_size > 0
                ):
                    print("  skip (already exists)")
                    if n < total:
                        time.sleep(args.delay)
                    continue

                data: bytes | None = None
                tried: list[str] = []
                failure: str | None = None
                for file_suffix in LANG_SUFFIX_CANDIDATES[lang]:
                    url = (
                        f"{RAW_BASE}/{author_urn}/{work_urn}/"
                        f"{author_urn}.{work_urn}.{file_suffix}.xml"
                    )
                    tried.append(file_suffix)
                    try:
                        data = _fetch(url)
                        break
                    except urllib.error.HTTPError as e:
                        if e.code == 404:
                            continue  # try next candidate edition
                        failure = f"HTTP {e.code}: {e.reason}"
                        break
                    except urllib.error.URLError as e:
                        failure = f"URL error: {e.reason}"
                        break

                if failure is not None:
                    failures.record(str(rel), failure)
                    if n < total:
                        time.sleep(args.delay)
                    continue

                if data is None:
                    # No edition variant matched — likely canonical-
                    # greekLit doesn't carry this play in this language
                    # (a real situation for some satyr/fragmentary
                    # plays). Skip rather than abort.
                    print(f"  ✗ 404 — tried {tried}, no edition available")
                    if n < total:
                        time.sleep(args.delay)
                    continue

                dest.write_bytes(data)
                size_kb = len(data) // 1024
                used = tried[-1]
                print(f"  ✓ {size_kb} KB ({used})")
                if n < total:
                    time.sleep(args.delay)
        print()

    print(f"Done. {total} attempted; output under {args.out.resolve()}")
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
