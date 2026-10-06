#!/usr/bin/env python3
"""Download Nietzsche's German oeuvre + Nachlass from zeno.org.

24 works covering the full philosophical output:

  * 14 mature published works (Die Geburt der Tragödie 1872 →
    Nietzsche contra Wagner 1888, plus Dionysos-Dithyramben).
  * Aus dem Nachlaß der Achtzigerjahre — the canonical published
    1880s Nachlass selection (Naumann-edition), 33 pages.
  * 8 early essays / lectures (Über Wahrheit und Lüge, Philosophie
    im tragischen Zeitalter, Über die Zukunft unserer Bildungs-
    Anstalten, etc.) — often classified as "early Nachlass."
  * Briefe (correspondence, 308 pages).

Each work gets BFS-walked on zeno's URL tree; sub-pages are
concatenated with `<!-- ZENO_PAGE: ... -->` markers per the same
convention `download_hegel_de.py` uses. The downstream
`corpus/split_zeno.py::split_zeno_pages` chunks at those boundaries.

Output: `data/nietzsche/raw_deu/<work_code>.html`

Run:
    uv run python perseus/download_nietzsche_de.py

zeno's source charset is ISO-8859-1; we decode accordingly and
write UTF-8 on disk (`_zeno.ZENO_ENCODING`, shared by all five zeno crawlers).
Be polite to zeno.org — default delay 1.5s between fetches; the
total scrape is ~3,100 page fetches across the 24 works = ~80 min
(3,116 ``ZENO_PAGE`` markers in the dumps on disk, 2026-10-06;
Menschliches, Allzumenschliches alone is 1,413).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _zeno import ZenoWork, add_crawl_args, main_for

# Higher than Hegel's 600: Nietzsche's aphoristic works get one zeno
# sub-page per numbered aphorism, and Menschliches, Allzumenschliches
# alone has ~1300 leaves — a 600 cap would cut it near aphorism #580.
MAX_PAGES = 2000

# (output filename, zeno root URL path)
WORKS: list[ZenoWork] = [
    # ─── Mature published works (14) ───────────────────────────
    ZenoWork(
        "geburt_tragodie.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+Geburt+der+Trag%C3%B6die",
    ),
    ZenoWork(
        "unzeitgemaesse_betrachtungen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Unzeitgem%C3%A4%C3%9Fe+Betrachtungen",
    ),
    ZenoWork(
        "menschliches_allzumenschliches.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Menschliches,+Allzumenschliches",
    ),
    ZenoWork(
        "morgenroete.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Morgenr%C3%B6te",
    ),
    ZenoWork(
        "froehliche_wissenschaft.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+fr%C3%B6hliche+Wissenschaft",
    ),
    ZenoWork(
        "zarathustra.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Also+sprach+Zarathustra",
    ),
    ZenoWork(
        "jenseits_gut_boese.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Jenseits+von+Gut+und+B%C3%B6se",
    ),
    ZenoWork(
        "genealogie_moral.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Zur+Genealogie+der+Moral",
    ),
    ZenoWork(
        "fall_wagner.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Der+Fall+Wagner",
    ),
    ZenoWork(
        "goetzen_daemmerung.html",
        "/Philosophie/M/Nietzsche,+Friedrich/G%C3%B6tzen-D%C3%A4mmerung",
    ),
    ZenoWork(
        "antichrist.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Der+Antichrist",
    ),
    ZenoWork(
        "ecce_homo.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Ecce+Homo",
    ),
    ZenoWork(
        "nietzsche_contra_wagner.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Nietzsche+contra+Wagner",
    ),
    ZenoWork(
        "dionysos_dithyramben.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Dionysos-Dithyramben",
    ),
    # ─── Nachlass (1) ──────────────────────────────────────────
    ZenoWork(
        "nachlass_achtzigerjahre.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Aus+dem+Nachla%C3%9F+der+Achtzigerjahre",
    ),
    # ─── Early essays / lectures (8) ───────────────────────────
    ZenoWork(
        "wahrheit_luege.html",
        "/Philosophie/M/Nietzsche,+Friedrich/%C3%9Cber+Wahrheit+und+L%C3%BCge+im+au%C3%9Fermoralischen+Sinn",
    ),
    ZenoWork(
        "philosophie_tragisches_zeitalter.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+Philosophie+im+tragischen+Zeitalter+der+Griechen",
    ),
    ZenoWork(
        "zukunft_bildung.html",
        "/Philosophie/M/Nietzsche,+Friedrich/%C3%9Cber+die+Zukunft+unserer+Bildungs-Anstalten",
    ),
    ZenoWork(
        "fuenf_vorreden.html",
        "/Philosophie/M/Nietzsche,+Friedrich/F%C3%BCnf+Vorreden+zu+f%C3%BCnf+ungeschriebenen+B%C3%BCchern",
    ),
    ZenoWork(
        "homer_philologie.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Homer+und+die+klassische+Philologie",
    ),
    ZenoWork(
        "mahnruf_deutschen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Mahnruf+an+die+Deutschen",
    ),
    ZenoWork(
        "wir_philologen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Wir+Philologen",
    ),
    ZenoWork(
        "wissenschaft_weisheit.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Wissenschaft+und+Weisheit+im+Kampfe",
    ),
    # ─── Correspondence (1) ────────────────────────────────────
    ZenoWork(
        "briefe.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Briefe",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/nietzsche/raw_deu/.",
    )
    add_crawl_args(parser)
    args = parser.parse_args()
    return main_for(WORKS, args.data_root / "nietzsche" / "raw_deu", args, max_pages=MAX_PAGES)


if __name__ == "__main__":
    raise SystemExit(main())
