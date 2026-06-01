#!/usr/bin/env python3
"""Scan ``data/index.sqlite`` for chunks that match heuristics for
known corpus-quality bugs and emit a per-author report.

Each heuristic is the encoded shape of an issue we've actually
shipped at some point and later fixed for a single author. Running
this script periodically against the full corpus catches whether
those issues have crept into a different author's ingest — instead
of waiting for a user to notice in the Reader.

Signals:

* ``long_s_codepoint`` — literal U+017F (``ſ``) anywhere. Pure OCR
  artifact. Should be 0 after the ``[[boulainvilliers]]``-era
  cleanup; if a non-zero count surfaces, that author's ingest
  bypassed the normalization pass.
* ``long_s_misread`` — words containing medial ``f`` in 18th-c
  long-s positions (``Hiftoire``, ``Affemblées``, ``confentement``).
  Detection is heuristic — we look for tokens that contain ``f``
  in a non-word-initial vowel-adjacent position AND are NOT in the
  French wordlist. Some false positives on archaic French
  spellings, but a high count flags an unprocessed source.
* ``glyph_soup`` — chunks where alphabetic chars are < 40 % of
  non-whitespace content. Pattern that bit us in the Boulainvilliers
  Essai EPUB front-matter and the Origen English HTML extraction.
* ``run_on_token`` — single tokens > 30 chars (excluding URLs). The
  Boulainvilliers PDF + EPUB extraction produced these
  (``DiffertationsurlaNobleffe``); also bites PDF extraction when
  spaces are dropped at glyph-cluster boundaries.
* ``replacement_char`` — U+FFFD (``�``) anywhere. Means decode
  failed and the bytes went lossy.
* ``mojibake`` — sequences like ``Ã©``, ``â€™`` indicating
  utf-8-misread-as-latin-1 in the source.
* ``tiny_chunk`` — chunk text shorter than 20 chars. Mostly
  page-marker noise.
* ``mostly_digits`` — chunk where >60 % of chars are digits/punct;
  page-number leakage.
* ``caret_artifact`` — ``^`` inside a word (``Mezt^ray``,
  ``Ckctrlema^ne``). OCR column-edge debris.
* ``duplicate_text`` — identical text under different chunk_ids.
  Symptom of the JSONL-merge regression where re-ingest left stale
  chunks alongside new ones.

Output: a Markdown table per author with counts for each signal,
ranked by total issue count. The top-N "worst offender" chunks are
appended per signal so the operator can spot-check.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB = REPO_ROOT / "data" / "index.sqlite"

# Pre-compile expensive regexes once; chunk loop hits them millions
# of times.
_LONG_S_CP = "ſ"  # ſ
_REPLACEMENT_CP = "�"
_RE_LONG_S_MISREAD = re.compile(
    # Vowel-f-Consonant or Vowel-ff-Vowel in NON-word-initial position.
    # Captures the dominant misread shapes (Hiftoire, Affemblées).
    r"\b\w*?[aàâeéèêëiîïoôuùûyAÀÂEÉÈÊËIÎÏOÔUÙÛY]"
    r"(?:f[ctpqmnh]|ff[aàâeéèêëiîïoôuùûyAÀÂEÉÈÊËIÎÏOÔUÙÛY])"
    r"\w*\b"
)
_RE_RUN_ON = re.compile(r"\b[A-Za-zÀ-ÿ]{30,}\b")
_RE_MOJIBAKE = re.compile(r"Ã[©®¨ª¯´·»¼½¾¿-¿]|â€[™˜œšž]")
_RE_CARET = re.compile(r"\b\w*\^\w+\b|\b\w+\^\w*\b")
_RE_DIGITS_DOMINANT = re.compile(r"[\d\s\.,:;\-—()]")


def _is_glyph_soup(text: str, lang: str | None = None) -> bool:
    """Heuristic for "OCR junk" chunks. Skipped for Hebrew/Arabic
    because their pointing/cantillation marks are non-letter
    combining characters and drag the alpha-ratio down on
    perfectly legitimate scripture verses (Hebrew Bible scored
    4,829 false positives before this guard)."""

    if lang in ("heb", "ara"):
        return False
    s = text.strip()
    if len(s) < 40:
        return False  # too short to confidently classify
    letters = sum(1 for c in s if c.isalpha())
    return letters < 0.40 * len(s)


def _is_mostly_digits(text: str) -> bool:
    s = text.strip()
    if len(s) < 10:
        return False
    digit_punct = sum(1 for c in s if _RE_DIGITS_DOMINANT.match(c))
    return digit_punct / len(s) > 0.60


_LONG_S_LANGS = {"eng", "fra", "deu"}

# Common modern English / French / German word stems that the
# vowel-f-consonant pattern matches but are NOT long-s misreads.
# Hegel's *Science of Logic* and *Phenomenology* fired 162 / 81
# false-positive chunks because the regex caught "different",
# "indifference", "indifferent" — Hegel's actual vocabulary.
# Similar story for "effect", "afford", "office", etc.
#
# We strip these from the match list before counting, leaving any
# residual matches to be flagged. A real OCR'd 18th-c text has 10+
# unique mangled words (Hiftoire, Affemblées, confentement, ...)
# so the threshold still trips on genuine long-s contamination.
_LONG_S_KNOWN_FP = frozenset(
    {
        # English everyday vocabulary the regex picks up.
        "different", "differently", "differential", "difference",
        "differences", "differed", "differing", "differs",
        "indifferent", "indifference", "indifferently",
        "effect", "effects", "effected", "affecting", "affected",
        "effective", "effectively", "effectiveness",
        "afford", "affords", "afforded", "affording", "affirmation",
        "affirmative", "affirmatively", "affirmed", "affirming",
        "affirms", "office", "offices", "officer", "officers",
        "official", "officially", "officials", "officially",
        "offer", "offered", "offering", "offers",
        "after", "afterward", "afterwards", "aftermath", "afterlife",
        "often", "oftentimes",
        "sufficient", "sufficiently", "sufficiency", "sufficiencies",
        "insufficient", "insufficiently", "insufficiency",
        "difficult", "difficulty", "difficulties", "difficultly",
        "effort", "efforts", "effortless", "effortlessly",
        "affection", "affections", "affectionate", "affectionately",
        "gift", "gifts", "gifted",
        "left", "deify", "deified", "deifies", "deifying",
        "shift", "shifts", "shifted", "shifting", "shifter",
        # German philosophical vocabulary.
        "auffassen", "auffassung", "auffassungen", "aufforderung",
        "offen", "offene", "offenen", "offener", "offenes",
        "offenbar", "offenbarte", "offenbart", "offenbarung",
        # French
        "effet", "effets", "effectif", "effective", "effectivement",
        "affirmation", "affirmative", "affirmé", "affirmer",
        "différent", "différente", "différents", "différentes",
        "différence", "différences", "différencier",
        "indifférent", "indifférence",
    }
)

# German morphology: certain suffixes (``-schaft``, ``-schrift``,
# ``-haft``) and the prefix ``Auf-`` produce vowel-f-consonant
# patterns by construction in legitimate modern German. Hegel's
# Wissenschaft/Eigenschaft/Bekanntschaft/Wirtschaft etc. all trip
# the regex but are not OCR misreads. We strip these morphological
# false positives in a second pass.
_GERMAN_FP_SUFFIX_RE = re.compile(
    r".+(?:schaft|schaften|schrift|schriften|haft|hafte|hafter|hafte[nrs]|"
    r"haftigkeit|haftig|nschaft|kraft|kräfte|kraefte|kräften|kraeften|"
    r"stoff|stoffe|stoffen|stoffes|stoffs|"
    r"heft|hefte|heften|heftes|"
    r"griff|griffe|griffen|griffes)$",
    re.IGNORECASE,
)
_GERMAN_FP_FFE_RE = re.compile(
    # Common -ffen, -ffer, -ffend, -ffene endings on German verbs/nouns:
    # schaffen, treffen, hoffen, öffnen, Schöpfer, etc.
    r"^.*ff(?:en|end|er|ne[nrs]?|ung|t|te[nrs]?|ig|el)?$",
    re.IGNORECASE,
)


def _is_german_morphological_fp(word: str) -> bool:
    if _GERMAN_FP_SUFFIX_RE.match(word):
        return True
    if _GERMAN_FP_FFE_RE.match(word) and len(word) >= 5:
        return True
    return False


def _is_long_s_misread(text: str, lang: str | None = None) -> bool:
    """Heuristic for the long-s OCR misread (``ſ`` rendered as ``f``).

    Only meaningful for 18th-c print sources in English / French /
    German — those are the languages where long-s was used and the
    OCR misread therefore manifests. Greek / Latin / Hebrew /
    Arabic are skipped because either the script doesn't use long-s
    (grc/heb/ara) or our Latin corpus comes from post-long-s
    print (Migne PG/PL, corpusthomisticum) where the heuristic
    over-fires on real Latin word patterns like ``effectus`` /
    ``officium`` / ``differentia`` (817 of 818 Aquinas hits were
    false positives before this guard).

    We strip matches that are common modern vocabulary stems (see
    ``_LONG_S_KNOWN_FP``) before counting. A real OCR'd 18th-c
    page has 10+ DIFFERENT mangled words; Hegel's prose may have
    "different" 6× but no other f-words, which after the strip
    yields 0 matches and avoids the false positive.

    Threshold: ≥5 surviving matches AND ≥3 unique word-forms.
    The unique-form gate prevents one frequent word repeated many
    times from tripping (Hume's "uniformity", e.g.).
    """

    if lang not in _LONG_S_LANGS:
        return False
    matches = _RE_LONG_S_MISREAD.findall(text)
    filtered = [m for m in matches if m.lower() not in _LONG_S_KNOWN_FP]
    if lang == "deu":
        filtered = [m for m in filtered if not _is_german_morphological_fp(m)]
    if len(filtered) < 5:
        return False
    return len({m.lower() for m in filtered}) >= 3


def audit(
    conn: sqlite3.Connection,
    *,
    sample_size: int = 5,
    min_total: int = 1,
) -> dict[str, dict]:
    """Return ``{author: {signal: (count, [(chunk_id, snippet), ...])}}``.

    ``sample_size`` is the number of worst-offender chunks to keep
    per (author, signal) for the report.
    """

    print("Scanning chunks_full ...", file=sys.stderr)
    cursor = conn.execute(
        "SELECT chunk_id, author, work, lang, text FROM chunks_full"
    )

    # author → signal → list of (chunk_id, snippet). Bounded by
    # ``sample_size`` so the report stays readable.
    findings: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # author → signal → unbounded count of hits across the corpus.
    # Always equals or exceeds ``len(findings[au][sig])``. Drives the
    # summary table so high-count signals stay visible even after the
    # sample list saturates.
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    # Track text → list of chunk_ids for duplicate detection
    seen_texts: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total_chunks = 0
    for cid, author, work, lang, text in cursor:
        total_chunks += 1
        if total_chunks % 50_000 == 0:
            print(f"  ... {total_chunks:,} chunks", file=sys.stderr)
        if author is None:
            continue
        # NFC-normalize once for codepoint checks.
        norm = unicodedata.normalize("NFC", text or "")

        def _record(signal: str, snippet_seed: str | None = None) -> None:
            totals[author][signal] += 1
            entries = findings[author][signal]
            if len(entries) < sample_size:
                snippet = (snippet_seed or norm)[:160].replace("\n", " ")
                entries.append((cid, snippet))

        # Cheap codepoint checks first.
        if _LONG_S_CP in norm:
            _record("long_s_codepoint")
        if _REPLACEMENT_CP in norm:
            _record("replacement_char")
        # Length-based gates.
        if len(norm.strip()) < 20:
            _record("tiny_chunk")
        # Predicate-based.
        if _is_glyph_soup(norm, lang):
            _record("glyph_soup")
        if _is_mostly_digits(norm):
            _record("mostly_digits")
        # Regex-based — more expensive, run last.
        if _RE_RUN_ON.search(norm):
            m = _RE_RUN_ON.search(norm)
            assert m is not None
            _record("run_on_token", m.group(0))
        if _is_long_s_misread(norm, lang):
            _record("long_s_misread")
        if _RE_MOJIBAKE.search(norm):
            _record("mojibake")
        if _RE_CARET.search(norm):
            _record("caret_artifact")
        # Duplicate tracking — store ALL chunks (sample-size cap applies
        # at report time so we can still tally accurately).
        if len(norm.strip()) >= 30:
            seen_texts[norm.strip()].append((cid, author))

    # Collapse duplicate findings post-scan. We tally the duplicate
    # *groups* per author (not per chunk) because the user cares
    # about how many distinct texts are duplicated, not the total
    # chunk-count across all duplicate groups.
    print(f"  scanned {total_chunks:,} chunks total", file=sys.stderr)
    print("Post-processing duplicates ...", file=sys.stderr)
    for text, chunks in seen_texts.items():
        if len(chunks) < 2:
            continue
        # Group by author; only flag intra-author repeats.
        by_author: dict[str, list[str]] = defaultdict(list)
        for cid, au in chunks:
            by_author[au].append(cid)
        for au, cids in by_author.items():
            if len(cids) >= 2:
                totals[au]["duplicate_text"] += 1
                entries = findings[au]["duplicate_text"]
                if len(entries) < sample_size:
                    entries.append(
                        (cids[0], f"({len(cids)} copies) {text[:140]}")
                    )

    # Materialize ``{signal: (total_count, sample_entries)}`` from
    # the two parallel structures.
    counts: dict[str, dict[str, tuple[int, list[tuple[str, str]]]]] = {}
    for au, sigs in findings.items():
        counts[au] = {}
        for sig, entries in sigs.items():
            counts[au][sig] = (totals[au][sig], entries)
    return counts


def render_report(
    findings: dict[str, dict[str, tuple[int, list[tuple[str, str]]]]],
    *,
    top_authors: int = 25,
) -> str:
    """Render a Markdown report. Authors ranked by total findings."""

    def _total(d: dict[str, tuple[int, list]]) -> int:
        return sum(n for n, _ in d.values())

    def _fmt(n: int) -> str:
        return f"{n:,}" if n else "·"

    ranked = sorted(findings.items(), key=lambda kv: _total(kv[1]), reverse=True)
    out: list[str] = ["# Corpus quality audit\n"]
    out.append(
        f"Total authors with findings: **{len(ranked)}**. "
        f"Showing top **{min(top_authors, len(ranked))}** by issue count.\n\n"
    )
    out.append("## Summary\n\n")
    # Discover the union of signals used (stable order via first occurrence).
    sig_order: list[str] = []
    seen_sigs: set[str] = set()
    for _, sigs in ranked:
        for s in sigs:
            if s not in seen_sigs:
                sig_order.append(s)
                seen_sigs.add(s)
    header_cells = ["Author", "Total"] + sig_order
    out.append("| " + " | ".join(header_cells) + " |")
    out.append("|" + "---|" * len(header_cells))
    for au, sigs in ranked[:top_authors]:
        cells = [au, _fmt(_total(sigs))]
        for s in sig_order:
            n = sigs.get(s, (0, []))[0]
            cells.append(_fmt(n))
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    out.append("## Triage\n")
    out.append(
        "Some signals fire on legitimate content — `long_s_misread` "
        "over-fires on English texts (real words like *affirmation*, "
        "*different*, *effective* hit the pattern), `tiny_chunk` "
        "includes structural front-matter (author names, section "
        "numbers like ``Vorwort``, ``1``). Use this section to "
        "prioritise verified-actionable findings; the per-author "
        "samples below let you spot-check before committing to a "
        "cleanup pass.\n"
    )
    out.append("**High-confidence flags worth investigating first:**\n")
    out.append("- `duplicate_text` with high counts → almost always real (re-ingest residue or Gutenberg/site-chrome bleed)")
    out.append("- `caret_artifact` → real OCR debris (column-edge ^ characters)")
    out.append("- `glyph_soup` (after Hebrew/Arabic skip) → real EPUB image-glyph leakage")
    out.append("- `mostly_digits` → real page-number leakage")
    out.append("- `long_s_codepoint` → real (literal ``ſ`` should be 0)\n")
    out.append("**Noisier signals — verify samples before acting:**\n")
    out.append("- `long_s_misread` on **eng** → mostly false positives on real `-ation`/`-ative`/`-iff-` words. Trustworthy on **fra** / **deu**.")
    out.append("- `tiny_chunk` → mix of real noise and legitimate short chunks (author/section names, numbered headings).")
    out.append("- `run_on_token` → catches real PDF-extraction issues but also legitimate long compound words (German *Bundesverfassungsgerichtsentscheidung*).\n")

    out.append("## Worst-offender samples per (author, signal)\n")
    for au, sigs in ranked[:top_authors]:
        out.append(f"### {au}\n")
        # Sort signals by count desc.
        signal_items = sorted(
            sigs.items(), key=lambda kv: kv[1][0], reverse=True
        )
        for sig, (n, entries) in signal_items:
            if n == 0:
                continue
            out.append(f"**{sig}** ({n}+ chunks):")
            for cid, snippet in entries:
                out.append(f"  - `{cid[:10]}` — {snippet!r}")
            out.append("")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DB))
    p.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Worst-offender chunks to retain per (author, signal).",
    )
    p.add_argument(
        "--top-authors",
        type=int,
        default=25,
        help="How many authors to include in the report.",
    )
    p.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "corpus-quality-audit.md"),
        help="Write the rendered report to this path (default: docs/).",
    )
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    findings = audit(conn, sample_size=args.sample_size)
    report = render_report(findings, top_authors=args.top_authors)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"Wrote report: {args.out}", file=sys.stderr)
    print(
        f"Authors with findings: {len(findings)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
