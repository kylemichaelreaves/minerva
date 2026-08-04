#!/usr/bin/env python3
"""Derive the common-word work-title tokens that `detect_work` distrusts.

Over half the work names in the corpus (479 of 911) have exactly one
significant token, so a single-token title cannot simply be refused —
that would take *Republic*, *Apology* and every biblical book name with
it. But some of those tokens are ordinary words (`laws`, `lovers`,
`soul`), and matching them against running prose silently narrows
retrieval to one dialogue (#168).

Corpus frequency does not tell the two apart: `lovers` occurs in 170
chunks and `republic` in 371, because the corpus talks about Plato's
subjects as often as his titles. Part of speech does. The lemmatizer
already tags every token, so a title token's PROPN share over the whole
corpus separates names from words with no overlap near the line:

    statesman 1.4%  laws 5.6%  politics 28.7% | metaphysics 31.1%  republic 55.8%

Run this after an ingest that adds works, and paste the output over
`_COMMON_TITLE_TOKENS` in `src/minerva/agent/detect.py`. A token this
script does not list is trusted, so a stale list fails open — it
over-scopes as before rather than refusing a real title.

    $ uv run python scripts/derive_common_title_tokens.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from minerva.agent.detect import _TITLE_STOPWORDS, _WORD_RE  # noqa: E402

DEFAULT_DB = REPO_ROOT / "data" / "index.sqlite"

# Every name a work answers to, the same three sources detect_work reads.
_NAMES_SQL = """
    SELECT w.author, w.title FROM works w
    UNION
    SELECT w.author, t.title_local FROM works w JOIN translations t ON t.work_id = w.id
     WHERE t.title_local IS NOT NULL
    UNION
    SELECT w.author, e.title_local FROM works w JOIN editions e ON e.work_id = w.id
     WHERE e.title_local IS NOT NULL
"""


def single_token_names(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Map each one-significant-token work name to the works using it."""

    out: dict[str, set[str]] = {}
    for author, name in conn.execute(_NAMES_SQL):
        sig = [t for t in _WORD_RE.findall((name or "").lower()) if t not in _TITLE_STOPWORDS]
        if len(sig) == 1:
            out.setdefault(sig[0], set()).add(f"{author}: {name}")
    return out


def propn_ratio(conn: sqlite3.Connection, tokens: list[str]) -> dict[str, tuple[float, int]]:
    """PROPN share and total tagged occurrences, per surface form.

    Keyed on `surface_form`, not `lemma` — the title token is a surface
    form ("laws"), and its lemma ("law") is what the query would have to
    be lemmatized to reach, which detect_work cannot do at query time.
    """

    placeholders = ",".join("?" * len(tokens))
    rows = conn.execute(
        f"SELECT LOWER(surface_form), pos, count(*) FROM chunk_lemmas "
        f"WHERE LOWER(surface_form) IN ({placeholders}) GROUP BY 1, 2",
        tokens,
    )
    agg: dict[str, dict[str, int]] = {}
    for surface, pos, n in rows:
        agg.setdefault(surface, {})[pos] = n
    return {
        tok: (poss.get("PROPN", 0) / sum(poss.values()), sum(poss.values()))
        for tok, poss in agg.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="PROPN share below which a token is treated as a common word",
    )
    ap.add_argument(
        "--min-occurrences",
        type=int,
        default=30,
        help="tokens rarer than this are left out — too little evidence to distrust",
    )
    ap.add_argument("--show-all", action="store_true", help="print every token and its ratio")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"no index at {args.db}", file=sys.stderr)
        return 1

    # Plain path, not a `file:...?mode=ro` URI — interpolating a CLI
    # argument into a connection string lets a crafted path append URI
    # parameters and reopen the index writable. `query_only` gets the
    # read-only guarantee without building a string to attack.
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA query_only = ON")
    names = single_token_names(conn)
    ratios = propn_ratio(conn, sorted(names))

    common = sorted(
        tok
        for tok, (ratio, n) in ratios.items()
        if n >= args.min_occurrences and ratio < args.threshold
    )

    if args.show_all:
        for tok, (ratio, n) in sorted(ratios.items(), key=lambda kv: kv[1][0]):
            mark = "COMMON" if tok in common else "name  "
            print(f"{mark} {tok:20} {ratio * 100:5.1f}%  n={n:7,}  {sorted(names[tok])[:2]}")
        print(file=sys.stderr)

    print(
        f"# Derived by scripts/derive_common_title_tokens.py: work-title tokens\n"
        f"# whose corpus-wide PROPN share is under {args.threshold:.0%} over at least\n"
        f"# {args.min_occurrences} tagged occurrences — ordinary words that happen to\n"
        f"# name a work. {len(common)} of {len(ratios)} single-token names, from an\n"
        f"# index of {conn.execute('SELECT count(*) FROM chunks').fetchone()[0]:,} chunks."
    )
    print("_COMMON_TITLE_TOKENS = frozenset(")
    print("    {")
    line = "        "
    for tok in common:
        piece = f'"{tok}", '
        if len(line) + len(piece) > 92:
            print(line.rstrip())
            line = "        "
        line += piece
    if line.strip():
        print(line.rstrip().rstrip(","))
    print("    }")
    print(")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
