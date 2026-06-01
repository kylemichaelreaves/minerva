#!/usr/bin/env python3
"""Download Descartes' major works in Latin and French.

Two sources today:

  Project Gutenberg #23306 — Meditationes de prima philosophia (Latin).
    Carries Buchenau's 1907 Insel-Verlag edition, with a German
    editor's preface up front and German footnotes (`Fussnoten`)
    at the back. We slice out the Latin body (Praefatio → Synopsis
    → Meditatio I–VI) and discard the bracketing German.

  Project Gutenberg #13846 — Victor Cousin's *Oeuvres de Descartes,
    Tome Premier* (1824). A single file containing **three** works:

      • Discours de la méthode (six Parties)
      • Méditations métaphysiques (Luynes 1647 translation, six
        Méditations + Épître + Préface + Abrégé)
      • Objections et Réponses (not ingested in this pass)

    We split it on the section banners and write Discours and
    Méditations as separate plain-text files.

Outputs land under `data/descartes/`:

    raw_la/meditationes.txt
    raw_fr/discours.txt
    raw_fr/meditations.txt

Three additional Descartes texts (Latin Principia philosophiae,
French Principes, Latin Regulae) live on Wikisource and need a
separate scraper — not in this pass.

Run via:

    uv run python perseus/download_descartes.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _download import fetch_bytes_with_retry

USER_AGENT = "minerva-research/1.0 (local research; bulk fetch with delays)"


_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers=_HTML_HEADERS,
        backoff_initial=5.0,
        backoff_max=120.0,
    )

def _strip_pg_boilerplate(raw: str) -> str:
    start = _PG_START.search(raw)
    end = _PG_END.search(raw)
    if not start or not end or end.start() <= start.end():
        print("  WARN: PG START/END markers not both found; returning raw text.")
        return raw
    return raw[start.end() : end.start()].strip() + "\n"


def _verify_language(raw: str, expected: str) -> None:
    """Raise if Gutenberg's `Language:` header doesn't match expected.

    We bail loudly so a typoed ID can't overwrite a correct file
    with a wrong-language transcription.
    """

    m = re.search(r"^Language:\s*(.+)$", raw[:4000], re.MULTILINE)
    if m and m.group(1).strip().lower() != expected.lower():
        raise RuntimeError(
            f"Gutenberg header says Language: {m.group(1).strip()!r}; "
            f"expected {expected!r}. Wrong PG ID?"
        )


def _slice_between(text: str, start_pat: str, end_pat: str | None) -> str:
    """Return the substring of ``text`` from the first match of
    ``start_pat`` up to (but not including) the first match of
    ``end_pat`` that follows it. If ``end_pat`` is None or doesn't
    match after the start, slice to end-of-text. Both patterns are
    matched line-anchored (`re.MULTILINE`).

    Used to carve specific works out of the Cousin omnibus and to
    drop the German preface/footnotes from the Latin Meditationes.
    """

    sm = re.search(start_pat, text, re.MULTILINE)
    if not sm:
        raise RuntimeError(f"start marker not found: {start_pat!r}")
    body_start = sm.start()
    if end_pat is None:
        return text[body_start:].strip() + "\n"
    em = re.search(end_pat, text[body_start:], re.MULTILINE)
    if not em:
        return text[body_start:].strip() + "\n"
    return text[body_start : body_start + em.start()].strip() + "\n"


def fetch_latin_meditationes(*, dest_root: Path) -> Path:
    """PG #23306 — Buchenau 1907. Latin body sits between the
    `Praefatio ad lectorem.` heading and the editor's `Fussnoten`
    block. Everything outside that range is German apparatus.
    """

    url = "https://www.gutenberg.org/cache/epub/23306/pg23306.txt"
    print(f"GET {url}")
    raw = _fetch(url).decode("utf-8")
    _verify_language(raw, "Latin")
    body = _strip_pg_boilerplate(raw)
    latin = _slice_between(body, r"^Praefatio ad lectorem\.", r"^Fussnoten")
    dest_dir = dest_root / "descartes" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "meditationes.txt"
    dest.write_text(latin, encoding="utf-8")
    print(f"  → {dest} ({len(latin):,} chars)")
    return dest


def fetch_french_cousin(*, dest_root: Path) -> tuple[Path, Path]:
    """PG #13846 — Cousin's Oeuvres I. Slices the file into two
    separate plain-text files: Discours and Méditations. The
    Objections-et-Réponses tail of the omnibus is not split out;
    re-add a third call here if it ever needs to be ingested.
    """

    url = "https://www.gutenberg.org/cache/epub/13846/pg13846.txt"
    print(f"GET {url}")
    raw = _fetch(url).decode("utf-8")
    _verify_language(raw, "French")
    body = _strip_pg_boilerplate(raw)

    discours = _slice_between(
        body,
        r"^DISCOURS DE LA MÉTHODE\.\s*$",
        r"^MÉDITATIONS MÉTAPHYSIQUES\.\s*$",
    )
    meditations = _slice_between(
        body,
        r"^MÉDITATIONS MÉTAPHYSIQUES\.\s*$",
        r"^OBJECTIONS AUX MÉDITATIONS\.\s*$",
    )

    dest_dir = dest_root / "descartes" / "raw_fr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    disc_path = dest_dir / "discours.txt"
    med_path = dest_dir / "meditations.txt"
    disc_path.write_text(discours, encoding="utf-8")
    med_path.write_text(meditations, encoding="utf-8")
    print(f"  → {disc_path} ({len(discours):,} chars)")
    print(f"  → {med_path} ({len(meditations):,} chars)")
    return disc_path, med_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/descartes/raw_*/.",
    )
    args = parser.parse_args()

    fetch_latin_meditationes(dest_root=args.data_root)
    fetch_french_cousin(dest_root=args.data_root)

    print()
    print("Two further Descartes works (Latin Principia, French")
    print("Principes) live on Wikisource and need a separate scraper")
    print("— not in this pass.")


if __name__ == "__main__":
    main()
