#!/usr/bin/env python3
"""Download PD English translations of Cicero + Lucretius + Epictetus
from Project Gutenberg.

Marcus Aurelius English is handled by ``download_marcus_aurelius.py``
alongside its Greek source.

Cicero English coverage (PG IDs verified at execution-time):
  * PG 47001 — Walter Miller bilingual De Officiis (the ingest keeps the
               English and drops the Latin: `corpus/facing_text.py`).
  * PG 54161 — Featherstonhaugh, The Republic of Cicero (De Re Publica).
  * PG 14988 — Yonge, Tusculan Disputations standalone.
  * PG 29247 — Yonge, Academic Questions + De Finibus + Tusculans.
  * PG 2808  — Shuckburgh, Treatises on Friendship and Old Age
               (De Amicitia + De Senectute).
  * PG 9776  — E. Jones, Brutus + Orator.
  * PG 14970 — James S. Reid's edition of the Academica (1874): Latin
               text plus English commentary, NOT a translation (#675).

Lucretius English: PG 785 Leonard 1916 (alternate to Perseus
Munro — kept as redundant safety net).

Epictetus English: PG 10661 Long Discourses + Enchiridion (alternate
to Perseus 0237 — same translator).

Output lands in:
    data/cicero/raw_eng/<work_code>_en.txt
    data/lucretius/raw/dr_natura_en_pg.txt   (optional alternate)
    data/epictetus/raw/discourses_en_pg.txt   (optional alternate)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from _gutenberg import fetch, pg_txt_url, verify_language

# (target_dir_subpath, output filename, PG ID, the `Language:` header it
# must carry). The header is checked before anything is written (#783): a
# wrong id fetches a real, well-formed book in another language. Probed
# 2026-10-06, every id carries one on line 22; the two bilingual editions say
# so, and the check is an exact match.
_CICERO_PG: tuple[tuple[str, str, int, str], ...] = (
    ("cicero/raw_eng", "de_officiis_en.txt", 47001, "English, Latin"),
    ("cicero/raw_eng", "de_re_publica_en.txt", 54161, "English"),
    ("cicero/raw_eng", "tusculans_en.txt", 14988, "English"),
    ("cicero/raw_eng", "academic_finibus_tusculans_en.txt", 29247, "English"),
    ("cicero/raw_eng", "amicitia_senectute_en.txt", 2808, "English"),
    ("cicero/raw_eng", "brutus_orator_en.txt", 9776, "English"),
    ("cicero/raw_eng", "academica_en.txt", 14970, "English, Latin"),
)

# Alternates — only fetch if the Perseus equivalent failed; kept here
# for safety. Comment out the entries you don't want re-fetched.
_ALT_PG: tuple[tuple[str, str, int, str], ...] = (
    # ("lucretius/raw", "dr_natura_en_pg.txt", 785, "English"),
    # ("epictetus/raw", "discourses_en_pg.txt", 10661, "English"),
)


def _fetch(pg_id: int, language: str) -> str:
    body = fetch(pg_txt_url(pg_id)).decode("utf-8", errors="replace")
    verify_language(body, language)
    return body


def fetch_all(*, data_root: Path, delay: float = 1.0) -> list[Path]:
    written: list[Path] = []
    for sub, filename, pg_id, language in _CICERO_PG + _ALT_PG:
        dest_dir = data_root / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        print(f"\nGET PG {pg_id} → {dest}")
        body = _fetch(pg_id, language)
        dest.write_text(body, encoding="utf-8")
        print(f"  → {dest} ({len(body):,} chars)")
        written.append(dest)
        time.sleep(delay)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()
    fetch_all(data_root=args.data_root, delay=args.delay)


if __name__ == "__main__":
    main()
