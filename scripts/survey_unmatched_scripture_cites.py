#!/usr/bin/env python3
"""Survey Aquinas + Augustine chunks for scripture-cite forms the
existing Latin :class:`ScriptureCiteRule` does NOT match.

Read-only against ``data/index.sqlite``. Output: a markdown summary
of the top unmatched cite-shaped forms by frequency, plus a coverage
ratio (matched vs. total cite-like spans) per author.

Use the output to draft new ``_LEXICON`` entries and regex variants
for :mod:`minerva.refs.rules.scripture_cite`. The goal is to lift
Aquinas's Vulgate cross-reference count from ~911 to closer to its
expected ~20,000+ (Summa Theologiae has well over 20k biblical
citations on a hand count).

Examples of forms the current rule misses:

* Spelled-out book names: ``ad Romanos`` instead of ``Rom.``.
* Colon separator: ``Mt 5:48`` instead of ``Matth. 5-48``.
* ``Phil.`` for Philippians (current rule only knows ``Phlp``).
* Ordinal-spelled ``prima Cor`` / ``secunda Cor`` instead of ``I Cor``.
* Macron-stripped variants (``Math.`` for ``Matth.``).

The script never writes to the index — purely read-and-print."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from minerva.refs.rules.scripture_cite import _CITE_RE, _LEXICON  # noqa: E402

# Loose "looks like a cite" pattern — captures more than the strict
# rule does, so the diff = what the rule misses. Permissive on the
# abbrev character class (allows AE / ae / oe / OE / lowercase
# variants), permissive on separator (- : . space), permissive on
# trailing context. Caps at 6 digits for chapter so we don't catch
# raw paragraph numbers.
_LOOSE_CITE_RE = re.compile(
    r"(?:\b(?P<prefix>I{1,4}|prim[ae]|secund[ae]|terti[ae]|quart[ae]|ad|de|in)\.?\s+)?"
    r"\b(?P<abbr>[A-Z][a-zæëœA-Z]{1,12})\.?"
    r"\s+"
    r"(?P<chap>\d{1,3})"
    r"\s*[-:.,\s]\s*"
    r"(?P<verse>\d{1,3})?"
)


def survey(index_path: Path, *, authors: tuple[str, ...], top_n: int) -> None:
    conn = sqlite3.connect(index_path)
    conn.row_factory = sqlite3.Row

    print("# Scripture-cite coverage survey")
    print("")
    print(f"Source: `{index_path}`")
    print("")

    placeholders = ",".join("?" * len(authors))
    rows = conn.execute(
        f"""SELECT author, COUNT(*) AS n
            FROM chunks_full
            WHERE author IN ({placeholders})
            GROUP BY author""",
        authors,
    ).fetchall()
    print("## Chunk counts")
    print("")
    print("| Author | Chunks |")
    print("|---|--:|")
    for r in rows:
        print(f"| {r['author']} | {r['n']:,} |")
    print("")

    for author in authors:
        print(f"## {author}")
        print("")
        cursor = conn.execute(
            "SELECT text FROM chunks_full WHERE author = ?",
            (author,),
        )
        matched_pairs: Counter[tuple[str | None, str]] = Counter()
        unmatched_pairs: Counter[tuple[str | None, str]] = Counter()
        unmatched_forms: Counter[str] = Counter()
        total_loose = 0
        total_strict = 0

        for row in cursor:
            text = row["text"] or ""
            for m in _LOOSE_CITE_RE.finditer(text):
                total_loose += 1
                prefix = m.group("prefix")
                abbr = m.group("abbr")
                key = (prefix, abbr)
                if key in _LEXICON:
                    matched_pairs[key] += 1
                else:
                    unmatched_pairs[key] += 1
                    unmatched_forms[m.group(0)[:60]] += 1
            for _ in _CITE_RE.finditer(text):
                total_strict += 1

        coverage = (total_strict / total_loose * 100) if total_loose else 0.0
        print(
            f"- Loose cite-like spans found: **{total_loose:,}**\n"
            f"- Strict rule matches: **{total_strict:,}** ({coverage:.1f}%)\n"
            f"- Unmatched ``(prefix, abbr)`` keys: **{len(unmatched_pairs):,}** distinct\n"
        )

        print("### Top unmatched `(prefix, abbr)` keys by frequency")
        print("")
        print("| prefix | abbr | hits | candidate fix |")
        print("|---|---|--:|---|")
        for (prefix, abbr), hits in unmatched_pairs.most_common(top_n):
            print(f"| `{prefix!r}` | `{abbr!r}` | {hits} | (verify and add to `_LEXICON`) |")
        print("")

        print("### Top unmatched surface forms (sampled)")
        print("")
        for form, hits in unmatched_forms.most_common(top_n):
            print(f"- `{form}` ({hits} hits)")
        print("")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--index",
        type=Path,
        default=REPO_ROOT / "data" / "index.sqlite",
        help="Path to the SQLite index.",
    )
    ap.add_argument(
        "--authors",
        nargs="+",
        default=("Aquinas", "Augustine"),
        help="Author column values to survey (default: Aquinas Augustine).",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=50,
        help="How many top unmatched entries to list per author (default: 50).",
    )
    args = ap.parse_args()

    if not args.index.is_file():
        sys.exit(f"index not found: {args.index}")

    survey(args.index, authors=tuple(args.authors), top_n=args.top)


if __name__ == "__main__":
    main()
