#!/usr/bin/env python3
"""Download Hobbes's Latin works from Molesworth's 1839 *Opera Latina*.

Unlike Spinoza / Augustine / Aquinas — whose Latin works exist as
hand-transcribed clean text on la.wikisource.org — Hobbes's Latin
corpus has no keyed digital edition anywhere. Probed 2026-09-12 and
all negative: la.wikisource (no Hobbes at all), thelatinlibrary
(404), Corpus Corporum (mlat.uzh.ch), IntraText. EEBO-TCP, which
*does* key early-modern Latin, covers books printed in England or in
English abroad — and both Latin Hobbes texts were printed on the
continent (Paris 1642, Amsterdam 1668). So this is OCR, and the only
question is whose.

**Which edition matters far more than which OCR engine.** Until
2026-09 we pulled Internet Archive scans of the *original 17th-century
printings* (``leviathansivedem00hobb``, the 1668 Blaeu Leviathan;
``gri_elementaphilos00ho``, a 1704 reprint of De Cive). Those are set
in a long-s typeface, and no OCR engine reads long-s as ``s``: the
result was ``Cbrifti`` for *Christi*, ``$eniet`` for *veniet*,
``Damel`` for *Daniel*, ``triwmphum`` for *triumphum* — see #535.

William Molesworth's *Thomae Hobbes Malmesburiensis Opera philosophica
quae latine scripsit omnia* (London: Bohn, 1839) reprints the same
texts in ordinary 19th-century roman type. The long-s problem does not
exist there, because the long-s is not on the page.

Measured over the sliced bodies, scoring each token of 4+ letters
against ``data/latin_vocab.json`` (50,141 words drawn from the corpus's
clean Aquinas / Augustine / Spinoza Latin):

    work         old (17th-c scan)   new (Molesworth 1839)
    De Cive           55.3%                 81.4%
    Leviathan         71.0%                 82.3%

For calibration on the same scorer: Aquinas and Spinoza — whose own
text built the vocabulary — read 96–99%, and clean Latin from *outside*
the vocabulary's sources reads 78–88% (Lucretius 77.6%, Cicero's *De
oratore* 83.6%, *De finibus* 88.3%). Both re-sourced files land inside
that band; neither old file came close to it.

Two other defect classes clear at the same time, counted on the raw
files rather than the parsed chunks:

    long-s signature tokens   6,853  →  11
    run-together tokens (24+)   116  →   3   (#561's Hobbes share)

Sources — note both are *volumes*, not works. Each carries more than
the one text we want, so each is sliced (see ``_SLICES``):

  * Latin Leviathan — IA ``thomhobbesmalme02hobbgoog`` = Opera Latina
    vol. III. Contains Leviathan (Caput I–XLVII) followed by the
    *Appendix ad Leviathan* and an index. We take the Leviathan only
    from this scan, because the scan has **no leaves for pp. 510–512**
    (``_page_numbers.json`` runs leaf 475 = p. 509, leaf 476 = p. 513):
    they hold the last page of the Leviathan's *Conclusio*, the
    appendix's title and the opening of its Caput I. The slice used to
    end mid-sentence there ("Itaque atramentum"). Changing the whole
    work's source would re-mint every Leviathan ``chunk_id``, so only the
    missing p. 510 is taken from the UofT scan below and appended
    (``LEVIATHAN_TAIL``, #733).
  * Appendix ad Leviathan (#575) — IA ``operaphilosophic03hobbuoft``,
    the University of Toronto scan of the same vol. III, which has
    pp. 510–512. Hobbes's own 1668 addition, ingested as its own work.
    Vocabulary hit over the parsed chunks, same scorer as above: 84.2%,
    against 87.0% for the Leviathan from the Google scan — but 83.2% for
    the Leviathan read from *this* scan, so the gap is the scan, not the
    text. Its OCR mangles running heads (``APPENDIX AD LEVIATHAN. 5a3``),
    which ``sources/hobbes_la.py`` handles by shape (and, since #734,
    for the other two works as well).
  * De Cive Latin — IA ``thomhobbesmalmes0002hobb`` = Opera Latina
    vol. II. Contains *De Homine* (Caput I–XV) and then *De Cive*
    (Caput I–XVIII). Slicing is not optional here: De Homine's chapter
    numbers would otherwise be parsed as De Cive's.

All three are the ``_djvu.txt`` derivative, not ``_hocr_searchtext.txt.gz``
as before. That is what the numbers above were measured on; the two
derivatives are different OCR passes and are not interchangeable.

Output:

    data/hobbes/raw_lat/leviathan_lat.txt
    data/hobbes/raw_lat/leviathan_appendix_lat.txt
    data/hobbes/raw_lat/de_cive_lat.txt

Run:

    uv run python perseus/download_hobbes_la.py

Then, in order:

    uv run python scripts/clean-hobbes-latin.py
    .venv/bin/minerva ingest --only hobbes ...
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _download import fetch_bytes_with_retry


class SliceError(RuntimeError):
    """A volume did not contain the boundaries we slice it on.

    Raised rather than silently writing a wrong-sized file: a marker
    that stops matching means the IA item changed or the wrong item id
    was used, and either way the downstream parser would produce
    plausible-looking chunks of the wrong work.
    """


# ──────────────────────────────────────────────────────────────────
# Volume slicing
# ──────────────────────────────────────────────────────────────────


class VolumeSlice:
    """Where one work starts and ends inside a scanned volume.

    ``start`` and ``end`` are regexes matched against whole lines.
    ``expected_lines`` is the slice length observed when this was
    built (2026-09-12); we allow ±15% and fail outside it. Archive.org
    items are immutable once derived, so a drift here means the item id
    is wrong, not that the scan was revised.
    """

    def __init__(
        self,
        *,
        start: str,
        end: str,
        expected_lines: int,
        start_occurrence: int = 1,
    ) -> None:
        self.start = re.compile(start, re.IGNORECASE)
        self.end = re.compile(end, re.IGNORECASE)
        self.expected_lines = expected_lines
        # Which match of `start` opens the work. Both volumes repeat
        # their work titles in the front-matter index ("INDEX CAPITUM
        # LIBRI DE CIVE"), so the first match is not always the body.
        self.start_occurrence = start_occurrence

    def apply(self, text: str, *, label: str) -> str:
        lines = text.split("\n")
        starts = [i for i, ln in enumerate(lines) if self.start.match(ln)]
        if len(starts) < self.start_occurrence:
            raise SliceError(
                f"{label}: start marker {self.start.pattern!r} matched "
                f"{len(starts)} time(s), needed at least "
                f"{self.start_occurrence}"
            )
        first = starts[self.start_occurrence - 1]
        ends = [i for i, ln in enumerate(lines) if i > first and self.end.match(ln)]
        if not ends:
            raise SliceError(
                f"{label}: end marker {self.end.pattern!r} never matched after line {first + 1}"
            )
        out = lines[first : ends[0]]
        low = int(self.expected_lines * 0.85)
        high = int(self.expected_lines * 1.15)
        if not low <= len(out) <= high:
            raise SliceError(
                f"{label}: sliced {len(out)} lines, expected "
                f"~{self.expected_lines} (accepting {low}–{high}). "
                f"Start line {first + 1}, end line {ends[0] + 1}."
            )
        return "\n".join(out)


_SLICES: dict[str, VolumeSlice] = {
    # Vol. III: Leviathan runs from its own CAPUT I to the first page
    # carrying the APPENDIX AD LEVIATHAN running head. The volume's
    # front matter has an "INDEX CAPITUM" whose entries are not
    # line-initial CAPUT headings, so occurrence 1 is already the body.
    "leviathan_lat.txt": VolumeSlice(
        start=r"\s*CAPUT\s+I\s*[.,]?\s*$",
        end=r"\s*APPENDIX\s+AD\s+LEVIATHAN",
        expected_lines=19878,
    ),
    # Vol. III again, from the UofT scan (see the module docstring for
    # why not the Google one): from the appendix's title page to the end
    # of the volume, before its index. The anchored pattern needs the bare
    # title — every running head after it carries a page number, or a
    # mangled one ("53/", "5a3"), and none precedes it.
    "leviathan_appendix_lat.txt": VolumeSlice(
        start=r"\s*APPENDIX\s+AD\s+LEVIATHAN\s*[.,]?\s*$",
        end=r"\s*[.,]?\s*FINIS\s+VOLUMINIS",
        expected_lines=2633,
    ),
    # Vol. II: De Cive opens with a half-title page reading "DE CIVE."
    # after De Homine ends, and closes at "FINIS VOLUMINIS SECUNDI".
    # Occurrence 1 of the half-title is the front-matter index line
    # "INDEX CAPITUM LIBRI DE CIVE." — which this anchored pattern does
    # not match — so the body title is occurrence 1 here too.
    "de_cive_lat.txt": VolumeSlice(
        start=r"\s*DE\s+CIVE\s*[.,]?\s*$",
        end=r"\s*[.,]?\s*FINIS\s+VOLUMINIS\s+SECUNDI",
        expected_lines=14121,
    ),
}


# ──────────────────────────────────────────────────────────────────
# Tail patch (#733)
# ──────────────────────────────────────────────────────────────────


class TailPatch:
    """Lines one scan lacks at a work's end, taken from another scan.

    ``after`` matches the last line both scans share, which must be the
    slice's last non-blank line; the patch is every donor line after it,
    up to the line matching ``until``. Each check fails loudly rather than
    appending the wrong page, or the right page twice.
    """

    def __init__(self, *, donor_ia: str, after: str, until: str, max_lines: int) -> None:
        self.donor_ia = donor_ia
        self.after = re.compile(after, re.IGNORECASE)
        self.until = re.compile(until, re.IGNORECASE)
        self.max_lines = max_lines


# The Google scan of vol. III has no leaves for pp. 510–512, so the
# Leviathan slice stops mid-sentence at "Itaque atramentum" with the last
# eight lines of Caput XLVII on p. 510 missing. The UofT scan has them.
LEVIATHAN_TAIL = TailPatch(
    donor_ia="operaphilosophic03hobbuoft",
    after=r".*\bItaque\s+atramentum\s*$",
    until=r"\s*APPENDIX\s+AD\s+LEVIATHAN\s*[.,]?\s*$",
    max_lines=60,
)

_TAILS: dict[str, TailPatch] = {"leviathan_lat.txt": LEVIATHAN_TAIL}


def patch_tail(body: str, donor: str, patch: TailPatch, *, label: str) -> str:
    """Append the donor lines ``patch`` names to ``body``."""

    last = next((ln for ln in reversed(body.split("\n")) if ln.strip()), "")
    if not patch.after.match(last):
        raise SliceError(
            f"{label}: slice does not end at {patch.after.pattern!r} (ends {last!r}); "
            "the gap this patch fills may be gone"
        )
    lines = donor.split("\n")
    anchors = [i for i, ln in enumerate(lines) if patch.after.match(ln)]
    if len(anchors) != 1:
        raise SliceError(
            f"{label}: anchor {patch.after.pattern!r} matched {len(anchors)} time(s) "
            f"in {patch.donor_ia}, needed exactly 1"
        )
    ends = [i for i in range(anchors[0] + 1, len(lines)) if patch.until.match(lines[i])]
    if not ends:
        raise SliceError(
            f"{label}: end marker {patch.until.pattern!r} not found in {patch.donor_ia}"
        )
    tail = lines[anchors[0] + 1 : ends[0]]
    if len(tail) > patch.max_lines:
        raise SliceError(
            f"{label}: patch from {patch.donor_ia} is {len(tail)} lines, over {patch.max_lines}"
        )
    return body.rstrip("\n") + "\n" + "\n".join(tail).rstrip() + "\n"


# (work_label, ia_item_id, output_filename)
_DOWNLOADS: tuple[tuple[str, str, str], ...] = (
    (
        "Latin Leviathan (Molesworth 1839, Opera Latina vol. III)",
        "thomhobbesmalme02hobbgoog",
        "leviathan_lat.txt",
    ),
    (
        "Appendix ad Leviathan (Molesworth 1839, Opera Latina vol. III, UofT scan)",
        "operaphilosophic03hobbuoft",
        "leviathan_appendix_lat.txt",
    ),
    (
        "De Cive (Molesworth 1839, Opera Latina vol. II)",
        "thomhobbesmalmes0002hobb",
        "de_cive_lat.txt",
    ),
)


def _fetch_ia_text(ia_id: str) -> str:
    """Pull the plain-text OCR derivative from an Internet Archive item."""

    url = f"https://archive.org/download/{ia_id}/{ia_id}_djvu.txt"
    raw = fetch_bytes_with_retry(
        url,
        timeout=120,
        user_agent="minerva-corpus-fetch/0.1 (research)",
    )
    return raw.decode("utf-8", errors="replace")


def _volume(ia_id: str, volumes: dict[str, str]) -> str:
    """Fetch an item's text once per run; the UofT scan serves two files."""

    if ia_id not in volumes:
        volumes[ia_id] = _fetch_ia_text(ia_id)
    return volumes[ia_id]


def _download_one(
    data_root: Path,
    label: str,
    ia_id: str,
    filename: str,
    volumes: dict[str, str],
) -> Path:
    volume = _volume(ia_id, volumes)
    body = _SLICES[filename].apply(volume, label=label)
    tail = _TAILS.get(filename)
    if tail is not None:
        body = patch_tail(body, _volume(tail.donor_ia, volumes), tail, label=label)
    dest_dir = data_root / "hobbes" / "raw_lat"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_text(body, encoding="utf-8")
    print(
        f"  → {dest} ({len(body):,} chars, {body.count(chr(10)) + 1:,} lines, "
        f"sliced from {len(volume):,} chars of volume)"
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/hobbes/raw_lat/.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    volumes: dict[str, str] = {}
    for label, ia_id, filename in _DOWNLOADS:
        print(f"\n{label}: {filename} (IA {ia_id})")
        try:
            _download_one(args.data_root, label, ia_id, filename, volumes)
        except SliceError as exc:
            print(f"  ✗ {exc}", file=sys.stderr)
            failures.append(filename)

    if failures:
        print(f"\nFAILED: {', '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)

    print(
        "\nDone. Next: uv run python scripts/clean-hobbes-latin.py, "
        "then .venv/bin/minerva ingest --only hobbes"
    )


if __name__ == "__main__":
    main()
