#!/usr/bin/env python3
"""Download flagship works for Hobbes, Pascal, Hume, Locke, and Rousseau.

All sources are Project Gutenberg plain-text editions (public domain).
Each file lands under ``data/<author>/raw_<lang>/`` for ingestion via
the corresponding ``*_works.py`` table and the generic ``chapter``
splitter (``corpus/split_paragraphic.py``).

| Author   | Work                              | PG #  | Lang |
|----------|-----------------------------------|-------|------|
| Hobbes   | Leviathan                         | 3207  | eng  |
| Hobbes   | Philosophical Rudiments (De Cive) | 73906 | eng  |
| Hobbes   | Human Nature + De Corpore Politico (Vol 04 of English Works; split post-fetch) | 74236 | eng  |
| Pascal   | Pensées                           | 24499 | fra  |
| Hume     | An Enquiry Concerning Human Und.  | 9662  | eng  |
| Hume     | A Treatise of Human Nature        | 4705  | eng  |
| Locke    | An Essay Concerning Human Und.    | 10615 | eng  |
| Locke    | Second Treatise of Government     | 7370  | eng  |
| Rousseau | Du contrat social                 | 4636  | fra  |

Hobbes Vol 04 of the Molesworth English Works is a single PG file
containing TWO Hobbes works back-to-back: *Human Nature* (Part I of
*The Elements of Law*) and *De Corpore Politico* (Part II), with a
trailing *Of Liberty and Necessity*. We split it into
``human_nature.txt`` and ``de_corpore_politico.txt`` at download time
by locating the heading lines; the trailing *Liberty and Necessity*
piece is dropped (it's a separate short work, not in scope).

Latin Hobbes (Leviathan 1668, De Cive 1642) is NOT on Project
Gutenberg as clean plain text; it ships via ``download_hobbes_la.py``
which pulls Internet Archive OCR.

Run:

    uv run python perseus/download_early_modern.py
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from _gutenberg import fetch_pg_text

# (author_slug, lang_dir, filename, pg_id, language header)
_DOWNLOADS: tuple[tuple[str, str, str, int, str], ...] = (
    ("hobbes", "raw_eng", "leviathan.txt", 3207, "English"),
    ("hobbes", "raw_eng", "philosophical_rudiments.txt", 73906, "English"),
    # Vol 04 = Human Nature + De Corpore Politico. Downloaded as one
    # file and split into two by _post_process_hobbes_vol04 below; the
    # combined file is then removed.
    ("hobbes", "raw_eng", "elements_of_law_vol04.txt", 74236, "English"),
    # Pascal removed from PG path — PG 24499 is an English
    # translation, not the French original. Use
    # `perseus/download_pascal_fr.py` (Wikisource Brunschvicg 1925).
    ("hume", "raw_eng", "enquiry.txt", 9662, "English"),
    ("hume", "raw_eng", "treatise.txt", 4705, "English"),
    # PG splits the Essay into two volumes (Books I-II and III-IV);
    # _concat_locke_essay below joins them into one essay.txt after
    # both downloads complete.
    ("locke", "raw_eng", "essay_vol1.txt", 10615, "English"),
    ("locke", "raw_eng", "essay_vol2.txt", 10616, "English"),
    ("locke", "raw_eng", "second_treatise.txt", 7370, "English"),
    # Rousseau removed from PG path — PG 4636 is "A Tramp Through
    # the Bret Harte Country" (T. D. Beasley, English), not
    # Rousseau at all. Use `perseus/download_rousseau_fr.py`
    # (Wikisource 1762 edition, single-page texte entier).
)


# Heading patterns inside PG 74236 that mark the boundaries between
# the three Hobbes works in that volume. The Molesworth typography
# uses uppercased headings as the work titles; the OCR preserves them.
# These regexes match on a line basis; we split on whichever match
# fires first for each section.
_HN_HEAD_RE = re.compile(r"^HUMAN\s+NATURE", re.IGNORECASE)
_DCP_HEAD_RE = re.compile(r"^DE\s+CORPORE\s+POLITICO", re.IGNORECASE)
# PG 74236 uses "LIBERTY AND NECESSITY:" (without the "OF" prefix) for
# the work-start heading even though the title page lists it as "OF
# LIBERTY AND NECESSITY". Accept both.
_OLN_HEAD_RE = re.compile(r"^(?:OF\s+)?LIBERTY\s+AND\s+NECESSITY", re.IGNORECASE)


def _split_hobbes_vol04(combined: Path) -> tuple[Path, Path]:
    """Split the Vol 04 combined file into separate Human Nature and
    De Corpore Politico files. Drops the trailing Of Liberty and
    Necessity piece (out of scope for this round).

    Returns ``(human_nature_path, de_corpore_politico_path)``.
    """

    body = combined.read_text(encoding="utf-8")
    lines = body.splitlines(keepends=True)

    # Find every heading occurrence first, then pick the work-start
    # (not the title-page TOC entry that lists all three together).
    # PG 74236's title page lists all three headings within a ~20-line
    # window; the real work-starts are isolated by hundreds of lines
    # of body text. Heuristic: a real work-start has NO heading of
    # ANY of the three works within ±20 lines.
    def _find_all(pattern: re.Pattern[str]) -> list[int]:
        return [i for i, ln in enumerate(lines) if pattern.match(ln.strip())]

    hn_hits = _find_all(_HN_HEAD_RE)
    dcp_hits = _find_all(_DCP_HEAD_RE)
    oln_hits = _find_all(_OLN_HEAD_RE)
    all_hits = sorted(hn_hits + dcp_hits + oln_hits)

    def _pick_isolated(own_hits: list[int]) -> int | None:
        """First own_hit with no OTHER work-heading within ±20 lines."""

        for i in own_hits:
            neighbours = [j for j in all_hits if j != i and abs(j - i) <= 20]
            if not neighbours:
                return i
        return None

    hn_start = _pick_isolated(hn_hits)
    dcp_start = _pick_isolated(dcp_hits)
    oln_start = _pick_isolated(oln_hits)

    if hn_start is None or dcp_start is None:
        raise RuntimeError(
            f"Could not find HUMAN NATURE / DE CORPORE POLITICO "
            f"work-start headings in {combined}; OCR may have shifted. "
            f"(hn_hits={hn_hits[:5]}, dcp_hits={dcp_hits[:5]}, "
            f"hn_start={hn_start}, dcp_start={dcp_start})"
        )

    hn_body = "".join(lines[hn_start:dcp_start])
    # If we found Of Liberty and Necessity, cap De Corpore Politico
    # there; otherwise take everything to end of file.
    dcp_end = oln_start if oln_start is not None else len(lines)
    dcp_body = "".join(lines[dcp_start:dcp_end])

    hn_path = combined.parent / "human_nature.txt"
    dcp_path = combined.parent / "de_corpore_politico.txt"
    hn_path.write_text(hn_body, encoding="utf-8")
    dcp_path.write_text(dcp_body, encoding="utf-8")
    print(
        f"  ↳ split into {hn_path.name} ({len(hn_body):,} chars) + "
        f"{dcp_path.name} ({len(dcp_body):,} chars)"
    )
    # Remove the combined intermediate so the ingest dispatcher
    # doesn't pick it up as a third work (no hobbes_works entry
    # matches `elements_of_law_vol04.txt`).
    combined.unlink()
    return hn_path, dcp_path


def _concat_locke_essay(vol2_path: Path) -> Path:
    """Join Locke's Essay Vol 2 (PG 10616, Books III–IV) onto Vol 1
    (PG 10615, Books I–II) to produce a single ``essay.txt``. The
    Essay is conceptually one work; PG just split it across two
    ebook entries. We keep one CorpusWork row by gluing the two
    plain-text files together with a single blank-line separator
    and unlinking the Vol 2 intermediate so the ingest dispatcher
    sees only ``essay.txt``.
    """

    vol1_path = vol2_path.parent / "essay_vol1.txt"
    if not vol1_path.is_file():
        raise RuntimeError(
            f"Locke Essay Vol 1 not found at {vol1_path}; PG 10615 must download first."
        )
    vol1 = vol1_path.read_text(encoding="utf-8")
    vol2 = vol2_path.read_text(encoding="utf-8")
    combined = vol1.rstrip() + "\n\n" + vol2.lstrip()
    essay_path = vol2_path.parent / "essay.txt"
    essay_path.write_text(combined, encoding="utf-8")
    print(f"  ↳ joined vol1+vol2 into {essay_path.name} ({len(combined):,} chars)")
    # Drop the volume intermediates so locke_works.find_work sees
    # only "essay.txt" and ingest doesn't double-count.
    vol1_path.unlink()
    vol2_path.unlink()
    return essay_path


def _download_one(
    data_root: Path,
    author: str,
    lang_dir: str,
    filename: str,
    pg_id: int,
    language: str,
) -> Path:
    body = fetch_pg_text(pg_id, language=language)
    dest_dir = data_root / author / lang_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_text(body, encoding="utf-8")
    print(f"  → {dest} ({len(body):,} chars)")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/<author>/raw_*/.",
    )
    parser.add_argument(
        "--author",
        choices=sorted({a for a, *_ in _DOWNLOADS}),
        help="Download only one author (default: all).",
    )
    args = parser.parse_args()

    rows = _DOWNLOADS
    if args.author:
        rows = tuple(r for r in _DOWNLOADS if r[0] == args.author)

    for author, lang_dir, filename, pg_id, language in rows:
        print(f"\n{author}: {filename} (PG {pg_id})")
        dest = _download_one(args.data_root, author, lang_dir, filename, pg_id, language)
        # Post-process Hobbes Vol 04 split.
        if author == "hobbes" and filename == "elements_of_law_vol04.txt":
            _split_hobbes_vol04(dest)
        # Post-process Locke Essay: concat vol2 onto vol1 after both
        # land, then unlink the vol2 intermediate. Triggered on the
        # vol2 download so vol1 is guaranteed to exist already.
        if author == "locke" and filename == "essay_vol2.txt":
            _concat_locke_essay(dest)
        time.sleep(1.0)

    print("\nDone. Next: .venv/bin/minerva ingest && .venv/bin/minerva index")


if __name__ == "__main__":
    main()
