#!/usr/bin/env python3
"""Download Nietzsche's German oeuvre + Nachlass from zeno.org.

25 works covering the full philosophical output:

  * 14 mature published works (Die Geburt der Tragödie 1872 →
    Nietzsche contra Wagner 1888, plus Dionysos-Dithyramben).
  * Aus dem Nachlaß der Achtzigerjahre — the canonical published
    1880s Nachlass selection (Naumann-edition), 32 sub-pages.
  * 8 early essays / lectures (Über Wahrheit und Lüge, Philosophie
    im tragischen Zeitalter, Über die Zukunft unserer Bildungs-
    Anstalten, etc.) — often classified as "early Nachlass."
  * Briefe (correspondence, 29 sub-pages).

Each work gets BFS-walked on zeno's URL tree; sub-pages are
concatenated with `<!-- ZENO_PAGE: ... -->` markers per the same
convention `download_hegel_de.py` uses. The downstream
`corpus/pipeline.py::split_zeno_pages` chunks at those boundaries.

Output: `data/nietzsche/raw_deu/<work_code>.html`

Run:
    uv run python perseus/download_nietzsche_de.py

zeno's source charset is ISO-8859-1; we decode accordingly and
write UTF-8 on disk (matches `download_hegel_de.py:70` behavior).
Be polite to zeno.org — default delay 1.5s between fetches; the
total scrape is ~300 sub-page fetches across all 25 works = ~8 min.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from pathlib import Path

from _download import fetch_with_retry

ROOT = "http://www.zeno.org"

# (output filename, zeno root URL path)
WORKS: list[tuple[str, str]] = [
    # ─── Mature published works (14) ───────────────────────────
    (
        "geburt_tragodie.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+Geburt+der+Trag%C3%B6die",
    ),
    (
        "unzeitgemaesse_betrachtungen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Unzeitgem%C3%A4%C3%9Fe+Betrachtungen",
    ),
    (
        "menschliches_allzumenschliches.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Menschliches,+Allzumenschliches",
    ),
    (
        "morgenroete.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Morgenr%C3%B6te",
    ),
    (
        "froehliche_wissenschaft.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+fr%C3%B6hliche+Wissenschaft",
    ),
    (
        "zarathustra.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Also+sprach+Zarathustra",
    ),
    (
        "jenseits_gut_boese.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Jenseits+von+Gut+und+B%C3%B6se",
    ),
    (
        "genealogie_moral.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Zur+Genealogie+der+Moral",
    ),
    (
        "fall_wagner.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Der+Fall+Wagner",
    ),
    (
        "goetzen_daemmerung.html",
        "/Philosophie/M/Nietzsche,+Friedrich/G%C3%B6tzen-D%C3%A4mmerung",
    ),
    (
        "antichrist.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Der+Antichrist",
    ),
    (
        "ecce_homo.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Ecce+Homo",
    ),
    (
        "nietzsche_contra_wagner.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Nietzsche+contra+Wagner",
    ),
    (
        "dionysos_dithyramben.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Dionysos-Dithyramben",
    ),

    # ─── Nachlass (1) ──────────────────────────────────────────
    (
        "nachlass_achtzigerjahre.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Aus+dem+Nachla%C3%9F+der+Achtzigerjahre",
    ),

    # ─── Early essays / lectures (8) ───────────────────────────
    (
        "wahrheit_luege.html",
        "/Philosophie/M/Nietzsche,+Friedrich/%C3%9Cber+Wahrheit+und+L%C3%BCge+im+au%C3%9Fermoralischen+Sinn",
    ),
    (
        "philosophie_tragisches_zeitalter.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Die+Philosophie+im+tragischen+Zeitalter+der+Griechen",
    ),
    (
        "zukunft_bildung.html",
        "/Philosophie/M/Nietzsche,+Friedrich/%C3%9Cber+die+Zukunft+unserer+Bildungs-Anstalten",
    ),
    (
        "fuenf_vorreden.html",
        "/Philosophie/M/Nietzsche,+Friedrich/F%C3%BCnf+Vorreden+zu+f%C3%BCnf+ungeschriebenen+B%C3%BCchern",
    ),
    (
        "homer_philologie.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Homer+und+die+klassische+Philologie",
    ),
    (
        "mahnruf_deutschen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Mahnruf+an+die+Deutschen",
    ),
    (
        "wir_philologen.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Wir+Philologen",
    ),
    (
        "wissenschaft_weisheit.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Wissenschaft+und+Weisheit+im+Kampfe",
    ),

    # ─── Correspondence (1) ────────────────────────────────────
    (
        "briefe.html",
        "/Philosophie/M/Nietzsche,+Friedrich/Briefe",
    ),
]

USER_AGENT = "minerva-research/1.0 (local research; one-shot bulk fetch with delays)"

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def fetch(url: str, *, timeout: float = 30, retries: int = 8) -> str:
    """GET with exponential backoff. zeno.org serves ISO-8859-1."""

    return fetch_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        encoding="iso-8859-1",
    )


def extract_links(html: str, root_path: str) -> list[str]:
    """Return paths under `root_path` linked from the given HTML.
    Fragment / query strings are stripped; only true sub-pages."""

    out: list[str] = []
    seen: set[str] = set()
    for raw in _HREF_RE.findall(html):
        if raw.startswith(ROOT):
            raw = raw[len(ROOT):]
        if not raw.startswith("/"):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if not path.startswith(root_path):
            continue
        if path == root_path:
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def crawl_work(
    root_path: str, *, delay: float = 1.5, max_pages: int = 2000
) -> list[tuple[str, str]]:
    """BFS-walk one work's subtree on zeno. Cap at max_pages for safety.

    Default cap is 2000 (higher than the Hegel scraper's 600) because
    Nietzsche's aphoristic works on zeno each get a separate sub-page
    per numbered aphorism. Menschliches, Allzumenschliches alone has
    ~1300 aphorism leaves; with the smaller 600 cap, MA would
    truncate at roughly aphorism #580. The 2000 cap covers all
    Nietzsche works comfortably.
    """

    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    pages: list[tuple[str, str]] = []
    while queue and len(pages) < max_pages:
        path = queue.pop(0)
        url = ROOT + path
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  [skip] {path}: {e}")
            continue
        pages.append((path, html))
        decoded = urllib.parse.unquote(path)
        print(f"  [{len(pages):>3}] {decoded[-80:]:<80}  {len(html):>7,} bytes")
        for child in extract_links(html, root_path):
            if child in seen:
                continue
            seen.add(child)
            queue.append(child)
        time.sleep(delay)
    if len(pages) >= max_pages:
        print(f"  (hit max_pages={max_pages}; stopping)")
    return pages


def download_work(
    filename: str, root_path: str, out_dir: Path, *, delay: float
) -> Path | None:
    print(f"\n=== {filename}: {urllib.parse.unquote(root_path)} ===")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = crawl_work(root_path, delay=delay)
    if not pages:
        print("  no content fetched")
        return None
    parts = [
        f"<!-- ZENO_PAGE: {urllib.parse.unquote(p)} -->\n{html}"
        for p, html in pages
    ]
    out_path = out_dir / filename
    out_path.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"  → {out_path} ({len(pages)} pages, {out_path.stat().st_size:,} bytes)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/nietzsche/raw_deu/.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between requests (be polite to zeno.org).",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Optional filename allowlist (e.g., `--only zarathustra.html`).",
    )
    args = parser.parse_args()
    out_dir = args.data_root / "nietzsche" / "raw_deu"
    only = set(args.only) if args.only else None
    for filename, root_path in WORKS:
        if only and filename not in only:
            continue
        download_work(filename, root_path, out_dir, delay=args.delay)


if __name__ == "__main__":
    main()
