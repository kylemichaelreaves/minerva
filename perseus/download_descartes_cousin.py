#!/usr/bin/env python3
"""Download Cousin's *Oeuvres de Descartes, Tome III* and slice out the
French Principes Parts II–IV.

Cousin's 1824 edition is the most-cited 19th-century French reprint
of Picot's 1647 translation. Tome III contains the Lettre-Préface and
all four Parts of the Principes. The first Part we already have, in
cleaner form, from Wikisource's Desrez transcription; this script
fills the Parts II / III / IV gap.

Source is archive.org's OCR of Gallica's BNF scan
(`bub_gal_ark_12148_bpt6k942606_djvu.txt`). The OCR is rough — mid-
2000s grade — so this script does a non-trivial cleanup pass before
emitting the canonical `[N.NNN] Title\\n\\nBody` shape that the
existing `split_descartes_articles` splitter consumes.

What we DO:

  • Fetch the djvu plain text.
  • Carve out the body of each of Parts II, III, IV.
  • Apply mechanical OCR fixes (BNF watermarks, hyphen-rejoin, common
    digit-for-letter and `I` -> `l` substitutions, broken ligatures).
  • Split each Partie body into chunks at paragraph breaks.
  • Number them sequentially within the Partie and emit `[N.NNN]`
    markers so the existing splitter sees them.

What we do NOT do:

  • Recover exact Picot article numbering. The OCR loses the marginal
    article markers from the original print; the sequential numbering
    here is an APPROXIMATE correspondence. The output is honest about
    this — section labels read 'Pars II, art. N' but the article
    count per Partie can differ from Picot's canonical numbering by
    ±10% due to OCR-induced paragraph splits/merges.
  • Re-ingest Pars I. Wikisource Desrez is cleaner.

Output:

    data/descartes/raw_fr/principes_pars2to4.txt

Run via:

    uv run python perseus/download_descartes_cousin.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _download import make_fetcher


_URL = (
    "https://archive.org/download/bub_gal_ark_12148_bpt6k942606/"
    "bub_gal_ark_12148_bpt6k942606_djvu.txt"
)


_fetch = make_fetcher()

def _apply_word_fixups(text: str) -> str:
    """Apply the curated `_OCR_FIXUPS` table token-by-token. Operates
    on alphabetic word matches only so punctuation surrounding the
    token is preserved. Cheap O(n) because the dict lookup is hashed.
    """

    def _sub(m: re.Match[str]) -> str:
        return _OCR_FIXUPS.get(m.group(0), m.group(0))

    return re.sub(r"[A-Za-zÀ-ÿ']+", _sub, text)


def _clean_ocr(text: str) -> str:
    """Apply the full OCR cleanup pipeline to a Partie body.

    The order here matters:

      1. Drop watermark lines (BNF / TABLE / page-number noise).
      2. Rejoin hyphenated line-breaks before any word-level fixup,
         so `pré-\\ncipites` becomes `précipites` and not two
         half-tokens.
      3. Apply mechanical regex substitutions (`I'` → `l'`, ligatures).
      4. Apply the curated word-level fixup dictionary.
      5. Normalize whitespace (one space between tokens, no leading
         or trailing).
    """

    # Step 1: drop watermarks.
    text = _WATERMARK_RE.sub("", text)
    # Step 2: rejoin hyphens.
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    # Step 3: mechanical substitutions.
    for pat, repl in _MECHANICAL:
        text = pat.sub(repl, text)
    # Step 4: curated dictionary.
    text = _apply_word_fixups(text)
    # Step 5: normalize spaces but PRESERVE paragraph breaks (one or
    # more blank lines). Collapse runs of >=2 newlines to exactly two,
    # so `\n\n\n` (page break gap) reads as a single paragraph break
    # rather than triggering double-splitting.
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


# Locate the start of each major section in Tome III. The OCR
# renders the banners as `PREMIERE PARTIE.`, etc., reliably enough
# that line-anchored regex works. We grab the banner closest to the
# expected line offset — Cousin Tome III has each banner appear
# twice (once in the TOC ~line 1000-2000, once at the body start
# ~lines 2580, 4784, 7221, 13070). The BODY banner is the second
# match for Parts I-IV.
_PART_BANNER = {
    1: re.compile(r"^\s*PREMIERE\s+PARTIE\.\s*$", re.MULTILINE),
    2: re.compile(r"^\s*SECONDE\s+PARTIE\.\s*$", re.MULTILINE),
    3: re.compile(r"^\s*TROISIEME\s+PARTIE\.\s*$", re.MULTILINE),
    4: re.compile(r"^\s*QUATRIEME\s+PARTIE\.\s*$", re.MULTILINE),
}

# End of the Principes body — the back-matter TABLE / final tables
# don't carry a uniformly-detectable header. We anchor on the
# uppercase-banner re-occurrence after the last Partie body, which
# in Tome III is the second appearance of `TABLE` (the first being
# the front TOC at line ~1067, the second the back-matter at
# ~line 20730). Since Partie IV is the longest, we expect the
# `^TABLE` line ~7-10k lines after Partie IV begins.
_BACK_TABLE_RE = re.compile(r"^\s*TABLE\s*$", re.MULTILINE)


def _carve_part_body(text: str, part_n: int) -> str:
    """Return the body of the named Partie. Returns text from the
    LAST occurrence of the Partie's banner (the body, not any TOC
    pre-mentions) up to the start of the next Partie or the back-
    matter TABLE.

    Tome III's TOC scatters Partie banners ahead of the body proper
    (e.g. `QUATRIEME PARTIE.` appears at line 1982 inside the TOC
    region, before any of the Pars II/III body content). The body
    is reliably the LAST occurrence: front-matter mentions come
    before line ~2500, and body banners appear strictly after.
    """

    banner_re = _PART_BANNER[part_n]
    matches = list(banner_re.finditer(text))
    if not matches:
        raise RuntimeError(
            f"Could not find body banner for Part {part_n}; "
            f"no matches of {banner_re.pattern!r}"
        )
    body_start = matches[-1].end()
    # End at the next Partie's body banner, or at the back-matter
    # TABLE if this is the last Partie.
    end_candidates: list[int] = []
    if part_n < 4:
        next_banner = _PART_BANNER[part_n + 1]
        next_matches = list(next_banner.finditer(text, pos=body_start))
        if next_matches:
            end_candidates.append(next_matches[0].start())
    table_matches = list(_BACK_TABLE_RE.finditer(text, pos=body_start))
    if table_matches:
        end_candidates.append(table_matches[0].start())
    if not end_candidates:
        end = len(text)
    else:
        end = min(end_candidates)
    return text[body_start:end]


# Marginal-annotation tokens — OCR scramblings of the article-title
# notes that the printed Cousin edition runs in the page margin.
# Strip them mid-prose so they don't befoul lemmatization. Each is
# a non-French short token containing one or more of:
#   - digit-and-letter mix (`piUB`, `nou.Mvoo.`)
#   - run of punctuation that French words never have (`*°'otipiU°`)
#   - all-caps short cluster surrounded by spaces (`Coissisbi`,
#     `inimgeu`) — these are marginal scribal artefacts where the OCR
#     mis-decoded a stylized title-cap into a meaningless letter run.
# The heuristic that catches all three: a whitespace-bounded token
# that contains a mid-token uppercase letter (not just initial cap)
# OR a digit mixed with letters OR ASCII punctuation-and-letter
# clusters like `nou.Mvoo.`. We strip these tokens but keep the
# surrounding prose intact.
_MARGINAL_TOKEN_RE = re.compile(
    r"\b(?:"
    r"(?=\S{2,30}\b)[A-Za-zÀ-ÿ]*[A-Z][a-z]*[A-Z][A-Za-zÀ-ÿ]*"  # mid-token cap
    r"|[A-Za-zÀ-ÿ]+[0-9]+[A-Za-zÀ-ÿ]*"  # letter-digit mix
    r"|[A-Za-zÀ-ÿ]+[*°][A-Za-zÀ-ÿ]*"  # letter + odd symbol mix
    r"|\S*°\S*"  # any token containing °
    r")(?=\s|$)"
)


def _strip_marginal(text: str) -> str:
    """Remove OCR-garbled marginal-annotation tokens from prose.
    Replaces each with a single space, then collapses runs of
    whitespace. Preserves paragraph boundaries (double newlines)."""

    paragraphs = re.split(r"\n\n+", text)
    out_paragraphs: list[str] = []
    for p in paragraphs:
        cleaned = _MARGINAL_TOKEN_RE.sub(" ", p)
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        if cleaned:
            out_paragraphs.append(cleaned)
    return "\n\n".join(out_paragraphs)


def _split_into_articles(body: str, part_n: int) -> list[tuple[str, str]]:
    """Split a cleaned Partie body into approximate articles by
    paragraph boundaries + capitalization-based merging. Returns a
    list of `(synthetic_title, body)` pairs in document order.

    The Picot edition prints one article per article-boundary; the
    Cousin reprint pages-break mid-article frequently, so a naive
    paragraph split (\\n\\n) produces ~2x too many chunks. We fix
    this by merging any paragraph that opens with a lowercase
    letter into its predecessor — the strong signal that a
    paragraph is a *continuation* of the prior article rather than
    a new one. Real Picot article openers are capitalized (the
    original print sets articles in a Title Case first phrase).
    """

    body = _strip_marginal(body)
    raw_paragraphs = re.split(r"\n\n+", body)
    paragraphs: list[str] = []
    for p in raw_paragraphs:
        p = re.sub(r"\s+", " ", p).strip()
        if not p:
            continue
        # Drop paragraphs that look like residual OCR garbage —
        # mostly-non-alphabetic content or ALL CAPS short bursts.
        alpha = sum(1 for ch in p if ch.isalpha())
        lower = sum(1 for ch in p if ch.islower())
        if alpha < 60 or (alpha and lower / alpha < 0.55):
            continue
        paragraphs.append(p)

    # Merge continuation paragraphs into a SHORT predecessor only.
    # The OCR introduces two kinds of paragraph breaks: real article
    # boundaries (consistent with Picot's article structure) and
    # spurious mid-article page breaks (where Cousin's print pages
    # split a long article across two physical pages). The two are
    # hard to tell apart by raw shape, but a useful proxy: spurious
    # breaks tend to leave a SHORT first paragraph (the upper page
    # tail) followed by a CONTINUATION paragraph; real article
    # breaks usually have both sides be substantial. We merge only
    # when the prior chunk is < 300 chars AND the next chunk starts
    # lowercase — biased toward keeping article boundaries.
    merged: list[str] = []
    for p in paragraphs:
        first_alpha = next((ch for ch in p if ch.isalpha()), "")
        is_continuation = first_alpha and first_alpha.islower()
        if merged and is_continuation and len(merged[-1]) < 300:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)

    out: list[tuple[str, str]] = []
    for p in merged:
        cut = re.search(r"^(.{20,120}?[.?!])(?:\s|$)", p)
        title = cut.group(1) if cut else p[:120]
        out.append((title, p))
    return out


def _render(by_part: dict[int, list[tuple[str, str]]]) -> str:
    """Serialise the (part → articles) map as one big `[N.NNN] Title
    \\n\\n Body \\n\\n …` blob matching the wikisource-output shape.
    Article numbers are 1-indexed and reset per Partie.
    """

    lines: list[str] = []
    for part_n in (2, 3, 4):
        articles = by_part.get(part_n, [])
        for i, (title, body) in enumerate(articles, start=1):
            if lines:
                lines.append("")  # blank line between articles
            lines.append(f"[{part_n}.{i:03d}] {title}")
            lines.append("")
            lines.append(body)
    return "\n".join(lines).strip() + "\n"


def fetch_cousin_principes(*, dest_root: Path, local_source: Path | None = None) -> Path:
    """Download + cleanup + chunk. Returns the output path.

    If `local_source` is provided, read the OCR text from there
    instead of fetching — used during development against a cached
    copy of the archive.org file.
    """

    if local_source is not None:
        raw = local_source.read_bytes()
        print(f"reading cached source {local_source}")
    else:
        print(f"GET {_URL}")
        raw = _fetch(_URL)
    text = raw.decode("utf-8", errors="replace")

    by_part: dict[int, list[tuple[str, str]]] = {}
    for part_n in (2, 3, 4):
        body = _carve_part_body(text, part_n)
        cleaned = _clean_ocr(body)
        articles = _split_into_articles(cleaned, part_n)
        by_part[part_n] = articles
        print(f"  Pars {part_n}: {len(articles)} chunks ({len(cleaned):,} chars cleaned)")

    rendered = _render(by_part)
    dest_dir = dest_root / "descartes" / "raw_fr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "principes_pars2to4.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars)")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; the file lands in <root>/descartes/raw_fr/.",
    )
    parser.add_argument(
        "--local-source",
        type=Path,
        default=None,
        help="Read the OCR text from this file instead of fetching. Useful "
        "during development against a cached archive.org dump.",
    )
    args = parser.parse_args()
    fetch_cousin_principes(dest_root=args.data_root, local_source=args.local_source)


if __name__ == "__main__":
    main()
