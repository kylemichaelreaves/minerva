#!/usr/bin/env python3
"""Download Cicero's 15 philosophical + rhetorical works from
la.wikisource.org.

Each work has a top-level Latin page (e.g.
``https://la.wikisource.org/wiki/De_officiis``) which links to
per-book sub-pages (Liber Primus / Liber Secundus / etc.). We
BFS-walk each work's URL tree under its top-level slug, fetch
every reachable sub-page's HTML, and concatenate the text into
a single .txt file per work — same pattern as
``download_marx_zeno.py`` but targeting la.wikisource.

Output: ``data/cicero/raw_la/<work_code>.txt`` × 15. (Academica is
commented out of ``_WORKS`` below, which is why the count is 15 and not
16 — the header used to say 16 and the directory has never held that
many.)

Run: uv run python perseus/download_cicero_wikisource.py

FIDELITY CAVEAT — read before re-running over existing files.

``fetch_work`` was reconstructed in 2026-08 (issue #116); the original
never made it into the repo, so the files in ``data/cicero/raw_la/`` were
produced by an implementation we no longer have.

All 15 works were re-fetched to a scratch tree and diffed against the
committed files in 2026-08 (issue #151). After the marker filter below
was widened, ``topica`` is line-identical and the rest agree on prose;
the residual differences are paragraph-boundary blanks, not text.

Two things the diff established that are worth not re-learning:

* **Per-Liber page titles are produced correctly** wherever the source
  still carries them — ``de_legibus`` emits ``M. TVLLI CICERONIS De
  legibus - Liber I`` and ``- Liber II`` exactly as committed. #151
  described these as "absent from the reconstruction"; they are not. The
  only two missing are De natura deorum's Liber II and III, and those are
  **upstream deletions**: those sub-pages now contain no ``M. TVLLI``
  string at all. The committed file preserves titles la.wikisource has
  since removed, so this scraper cannot reproduce them without
  fabricating source text — and must not.
* ``de_re_publica`` intermittently fails with a non-retryable **HTTP
  301** on the REST endpoint during a full batch run, and succeeds on a
  ``--only`` retry moments later. A batch that loses a work this way
  still exits 0 (#300).

Byte-identity is not reachable anyway: la.wikisource has changed since
the May 2026 fetch (De fato has gained a ``FRAGMENTA`` heading). So
re-running this over the committed files WILL churn chunk_ids and cost
the affected works their embeddings / lemmas / cross-references. Use
``--only`` to fetch genuinely missing works rather than refreshing the
set wholesale.

Note the committed Latin files are **post-cleanup** artifacts:
``scripts/clean-cicero-chrome.py`` strips a Wikisource title/breadcrumb
header from them after the fetch. Diff against them accordingly.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote, unquote

from _download import ParagraphExtractor, make_fetcher

# (output filename, la.wikisource top-level page title)
_WORKS: tuple[tuple[str, str], ...] = (
    ("de_inventione_lat.txt", "De inventione"),
    ("de_oratore_lat.txt", "De oratore"),
    ("de_re_publica_lat.txt", "De re publica"),
    ("de_legibus_lat.txt", "De legibus"),
    ("brutus_lat.txt", "Brutus"),
    ("orator_lat.txt", "Orator"),
    # Academica intentionally omitted: la.wikisource has no full
    # transcription (it's fragmentary in the manuscript tradition).
    # English coverage still comes via PG 14970 + PG 29247.
    ("de_finibus_lat.txt", "De finibus bonorum et malorum"),
    ("de_natura_deorum_lat.txt", "De natura deorum"),
    ("tusculans_lat.txt", "Tusculanae disputationes"),
    ("de_officiis_lat.txt", "De officiis"),
    ("de_amicitia_lat.txt", "Laelius de Amicitia"),
    ("de_senectute_lat.txt", "Cato maior de senectute"),
    ("de_divinatione_lat.txt", "De divinatione"),
    ("de_fato_lat.txt", "De fato (Marcus Tullius Cicero)"),
    ("topica_lat.txt", "Topica (Marcus Tullius Cicero)"),
)


def _rest_url(title: str) -> str:
    """Parsoid HTML for ``title`` from la.wikisource's current REST API.

    Not ``/api/rest_v1/page/html/<title>``, which is the deprecated form
    and 301s here — a redirect ``urllib`` did not follow, so a full
    15-work run lost *De re publica* to it and still exited 0 (#300).
    Pointing at the target directly is the fix rather than retrying 3xx,
    since a retry that masks a genuine permanent redirect is worse than
    the skip. Verified byte-identical on 2026-08-09 (same sha1, same
    length) for De re publica, De officiis, Laelius de Amicitia, Topica
    and the ``De re publica/Liber I`` sub-page.

    ``safe=""`` keeps a sub-page's slash percent-encoded, so
    ``De officiis/Liber I`` cannot be read as a path segment against the
    ``/html`` suffix.
    """

    return (
        "https://la.wikisource.org/w/rest.php/v1/page/"
        + quote(title, safe="")
        + "/html"
    )


_fetch = make_fetcher()

# Wikisource apparatus classes / structural tags to drop. Same sets
# the other Wikisource scrapers use (see `download_pascal_fr.py`),
# plus `title` — the REST endpoint returns a full document, and its
# `<head><title>` would otherwise surface as a leading paragraph.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript", "title"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})
_SKIP_CLASS_TOKENS = frozenset(
    {"mw-references", "headertemplate", "ws-noexport", "navbox", "metadata"}
)

# Parsoid renders internal links as `href="./Page_title"`. Sub-pages of
# a work are exactly those whose title starts with `<work>/`.
_HREF_RE = re.compile(r'href="\./([^"#?]+)', re.IGNORECASE)

# la.wikisource opens each work page with a breadcrumb paragraph whose
# lines are prefixed `<` (`< Marcus Tullius Cicero / < Opera
# philosophica`). It carries no work text — drop it wherever it appears.
_BREADCRUMB_RE = re.compile(r"^<\s")

# Structural section markers that la.wikisource renders as standalone
# paragraphs. They duplicate the `[N]` numbering the body text already
# carries, and the committed files contain **zero** of any of these
# forms, so the lost original filtered them all.
#
# `_ROMAN_ONLY_RE` used to be `^[IVXLC]+$`, which caught only the bare
# form. Measured across a full re-fetch of all 15 works (#151): the
# dotted Roman form is by far the commonest at 381 paragraphs, against 18
# bare; Arabic markers add 104 bare and 40 dotted. So the old pattern
# filtered 18 of 543 markers — 3% — and every committed file would have
# gained hundreds of spurious one-token paragraphs on a re-fetch.
#
# `D` and `M` are added to the digit class; the old set stopped at `C`.
# The exposure that creates — a Latin word made only of Roman digits,
# e.g. `DIC` or `LVX` — is bounded by the anchors, since the marker must
# be the *entire* paragraph. None of the 259 distinct strings matched
# across the corpus was a word. `roman_to_int` in `_download.py` is not
# a safer gate: it sums rather than validating canonical form, so it
# accepts `DIC` (599) and `LVX` (55) just the same.
_ROMAN_ONLY_RE = re.compile(r"^[IVXLCDM]+\.?$")
_ARABIC_ONLY_RE = re.compile(r"^\d+\.?$")

# Lacuna sigil, all 46 of them in De re publica — the one work in the set
# whose transmission is substantially lost. The committed file drops
# them, and matching that convention is what keeps a re-fetch from
# churning chunk_ids; it is a fidelity choice, not a judgement that
# lacunae carry no information.
_LACUNA_RE = re.compile(r"^\(\*+\)$")


def _is_marker(paragraph: str) -> bool:
    return bool(
        _ROMAN_ONLY_RE.match(paragraph)
        or _ARABIC_ONLY_RE.match(paragraph)
        or _LACUNA_RE.match(paragraph)
    )


def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
    )
    p.feed(html.decode("utf-8"))
    p.close()
    return [q for q in p.paragraphs if not _BREADCRUMB_RE.match(q)]


def _subpage_titles(html: bytes, title: str) -> list[str]:
    """Return sub-page titles (`De officiis/Liber primus`, …) linked
    from a work's top-level page, in document order and de-duplicated.

    Titles are compared on the underscore form Parsoid emits and
    returned in that form — `_rest_url` re-quotes them, and
    Wikisource treats spaces and underscores as equivalent.
    """

    prefix = title.replace(" ", "_") + "/"
    out: list[str] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html.decode("utf-8")):
        sub = unquote(href)
        if not sub.startswith(prefix) or sub in seen:
            continue
        seen.add(sub)
        out.append(sub)
    return out


def fetch_work(title: str, *, dest: Path, delay: float = 1.5) -> Path | None:
    """Fetch one work from la.wikisource and write it as plain text.

    The on-disk shape — matched against the files this script already
    produced in `data/cicero/raw_la/` — is the top-level page's own
    paragraphs (the `M. TVLLI CICERONIS …` title and its table of
    contents) followed, for each `<work>/<subpage>` link, by that
    sub-page's title on its own line and then its body. Works whose
    whole text sits on the top-level page (e.g. De fato) simply have
    no sub-pages to append.

    Sub-page bodies are stripped of bare Roman-numeral section
    markers. They duplicate the `[N]` numbering the text already
    carries, and the committed files omit them — keeping them would
    churn every downstream chunk_id on the next ingest.

    Returns the written path, or None when nothing could be extracted
    (caller logs the skip; one dead work must not kill the batch).
    """

    root_html = _fetch(_rest_url(title))
    subpages = _subpage_titles(root_html, title)

    # The marker filter applies to the top-level page too. It used to be
    # sub-page-only, which is why 18 bare Roman markers still reached the
    # output on works whose text sits on the root page (#151).
    paragraphs: list[str] = [
        p for p in _extract_paragraphs(root_html) if not _is_marker(p)
    ]
    for sub in subpages:
        label = unquote(sub).replace("_", " ")
        print(f"  - {label}")
        try:
            body = _extract_paragraphs(_fetch(_rest_url(sub)))
        except Exception as e:  # one bad Liber shouldn't lose the work
            print(f"    [subpage skipped] {type(e).__name__}: {e}")
            continue
        paragraphs.append(label)
        paragraphs.extend(p for p in body if not _is_marker(p))
        time.sleep(delay)

    if not paragraphs:
        print("  no text extracted")
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n\n".join(paragraphs).strip() + "\n", encoding="utf-8")
    print(f"  → {dest} ({len(paragraphs)} paragraphs, {dest.stat().st_size:,} bytes)")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to sleep between requests (be polite to la.wikisource).",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Subset filename allowlist (e.g. --only de_officiis_lat.txt).",
    )
    args = ap.parse_args()
    out_dir = args.data_root / "cicero" / "raw_la"
    only = set(args.only) if args.only else None
    # Per-work `except` is right — one dead work must not lose the other
    # fourteen — but on its own it made a batch that dropped `De re
    # publica` to a transient HTTP 301 exit 0 with 14 of 15 files
    # written, and the only trace was one line in the middle of a long
    # log (#300). Collect the losses and report them where a summary is
    # read, then fail the run.
    skipped: list[str] = []
    for filename, title in _WORKS:
        if only and filename not in only:
            continue
        print(f"\n=== {filename}: {title} ===")
        try:
            fetch_work(title, dest=out_dir / filename, delay=args.delay)
        except urllib.error.HTTPError as e:
            print(f"  [WORK SKIPPED] {filename} ({title}): HTTP {e.code}")
            skipped.append(f"{filename} ({title}): HTTP {e.code}")
        except Exception as e:
            print(f"  [WORK SKIPPED] {filename}: {type(e).__name__}: {e}")
            skipped.append(f"{filename} ({title}): {type(e).__name__}: {e}")
        time.sleep(args.delay)

    if skipped:
        print(f"\n=== {len(skipped)} WORK(S) NOT WRITTEN ===")
        for line in skipped:
            print(f"  {line}")
        # Several of these are transient — the 301 that prompted this
        # succeeded on a plain `--only` retry minutes later — so the
        # retry is named rather than attempted automatically.
        print(f"  retry: --only {' '.join(s.split(' ')[0] for s in skipped)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
