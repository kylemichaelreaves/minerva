#!/usr/bin/env python3
"""Check whole-corpus invariants against the live index (#320).

Three defects — #307, #311, #314 — were found by one query written from
scratch each time and thrown away with the scratch directory. This is
that query, committed, with room for the others beside it.

Run it after any pass that writes derived tables: an ingest, a
``terms lemmatize``, a re-chunk::

    ./.venv/bin/python scripts/audit_invariants.py
    ./.venv/bin/python scripts/audit_invariants.py --format json

Two properties are deliberate, and both come from a way the throwaway
versions went wrong.

**It reads every row; there is no sampling flag.** Both wrong numbers in
this repo's history came from a sample that looked representative. The
batch 2-ter operator record put ``grc`` at 99.67% from 400 chunks drawn
in ``ord`` order; over all 2,942,344 grc rows the figure was 93.09%, and
#311 was scoped from the sampled number and understated its own
population by 109×. A ``--sample`` option would get used, so there
isn't one. Measured cost: **40 seconds** for all 26,005,053 rows against
the 8.2 GB index, paid by an operator who has just spent an hour on a
re-ingest.

**It reports; it does not gate.** ``ara`` violates the lemma-surface
invariant legitimately — Stanza's multi-word-token expansion gives a
clitic sub-word its parent's span on purpose. A red/green check would
have to be silenced for it, and a silenced check is not run. So a
violation exits 0: it is the output, not a failure. Exit is non-zero only
when the audit could not look at all, which is a different thing and must
not be confused with a clean result.

This is an operator script, not a CI gate: it needs `data/index.sqlite`,
which is gitignored and absent in CI. ``scripts/**`` is coverage-excluded.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "index.sqlite"


def resolve_db_path() -> Path:
    """The index to audit: ``$MINERVA_DB`` if set, else the repo default.

    Deliberately an environment variable rather than a ``--db`` flag,
    matching ``corpus-quality-audit.py`` and
    ``clean-hegel-lectures-glossary.py``. SonarCloud's
    ``pythonsecurity:S8706`` fails a PR when a CLI argument reaches
    ``sqlite3.connect``; this script's first PR was failed by exactly
    that, on this line.

    Fixed in code rather than marked Accepted in SonarCloud because
    Accepted status does not survive a line move — which is how #167 went
    red on a diff that only shifted one — see #179.

    Point it at a snapshot with::

        MINERVA_DB=data/snapshots/20260809T204241Z-.../index.sqlite \\
            ./.venv/bin/python scripts/audit_invariants.py
    """

    override = os.environ.get("MINERVA_DB")
    return Path(override) if override else _DEFAULT_DB

# How many offending rows to keep per invariant. A count alone sends the
# next reader back to write the query again by hand, which is the whole
# thing this script exists to stop; a full dump is unreadable.
_MAX_EXAMPLES = 6


@dataclass(frozen=True)
class Violation:
    group: str
    chunk_id: str
    detail: str


@dataclass
class Result:
    name: str
    rows_checked: int = 0
    violations: int = 0
    # group -> (rows checked, rows violating)
    per_group: dict[str, tuple[int, int]] = field(default_factory=dict)
    examples: list[Violation] = field(default_factory=list)

    def record(self, group: str, *, bad: bool) -> None:
        checked, violated = self.per_group.get(group, (0, 0))
        self.per_group[group] = (checked + 1, violated + int(bad))
        self.rows_checked += 1
        self.violations += int(bad)


@dataclass(frozen=True)
class Invariant:
    name: str
    statement: str
    run: Callable[[sqlite3.Connection], Result]
    # Printed beside the number. Nonzero is not automatically wrong, and
    # the explanation is what stops the next operator re-investigating a
    # known one — `ara` cost two sessions before it was written down.
    known_exceptions: str | None = None


def audit_lemma_surface_offsets(conn: sqlite3.Connection) -> Result:
    """``chunks.text[surface_start:surface_end] == surface_form``, for
    every row of ``chunk_lemmas``, grouped by language.

    One pass. The chunk texts are held in a dict — 161 MB of text across
    428k chunks, so a few hundred MB resident on a machine that already
    runs spaCy models against an 8.2 GB database — and the 26 million
    lemma rows stream past it. Joining the text back onto the lemma rows
    in SQL would re-send each chunk's text once per token, which is the
    same data several hundred times over.
    """

    result = Result(name="lemma_surface_offsets")
    chunks = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT chunk_id, lang, text FROM chunks_full WHERE lang IS NOT NULL"
        )
    }
    rows = conn.execute(
        "SELECT chunk_id, surface_form, surface_start, surface_end FROM chunk_lemmas"
    )
    for chunk_id, surface_form, start, end in rows:
        found = chunks.get(chunk_id)
        if found is None:
            # An orphaned lemma row — a different invariant's business,
            # and counting it here would understate the language totals.
            continue
        lang, text = found
        actual = text[start:end]
        bad = actual != surface_form
        result.record(lang, bad=bad)
        if bad and len(result.examples) < _MAX_EXAMPLES:
            result.examples.append(
                Violation(
                    group=lang,
                    chunk_id=chunk_id,
                    detail=(
                        f"[{start}:{end}] stored {surface_form!r} "
                        f"but text holds {actual!r}"
                    ),
                )
            )
    return result


def audit_chunk_work_id(conn: sqlite3.Connection) -> Result:
    """``chunks.work_id == COALESCE(editions.work_id, translations.work_id)``,
    for every row of ``chunks``, grouped by language.

    Why this one is worth a pass of its own: since migration 0030 (#339)
    ``chunks_full`` reaches ``works`` through ``JOIN works w ON w.id =
    c.work_id`` — an INNER join on a NULLABLE column. A chunk whose
    ``work_id`` is unset therefore does not surface with a missing title,
    it does not surface at all: it disappears from the reader, from
    search, from refs and from every count taken through the view, and
    nothing raises. `NOT NULL` is not declarable without rebuilding a
    428,606-row table whose rowids the FTS content tables depend on, so
    the constraint lives here instead.

    Read directly off ``chunks`` rather than through the view, because the
    view is precisely what hides the violation.
    """

    result = Result(name="chunk_work_id")
    rows = conn.execute(
        "SELECT c.chunk_id, c.lang, c.work_id, "
        "       COALESCE(e.work_id, t.work_id) AS expected "
        "FROM chunks c "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id"
    )
    for chunk_id, lang, work_id, expected in rows:
        bad = work_id is None or work_id != expected
        result.record(lang or "(null)", bad=bad)
        if bad and len(result.examples) < _MAX_EXAMPLES:
            result.examples.append(
                Violation(
                    group=lang or "(null)",
                    chunk_id=chunk_id,
                    detail=(
                        f"work_id={work_id!r} but edition/translation "
                        f"resolves to {expected!r} — row is invisible in chunks_full"
                        if work_id is None
                        else f"work_id={work_id!r} disagrees with {expected!r}"
                    ),
                )
            )
    return result


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        name="lemma_surface_offsets",
        statement="chunks.text[surface_start:surface_end] == surface_form",
        run=audit_lemma_surface_offsets,
        known_exceptions=(
            "ara is legitimately nonzero: Stanza's multi-word-token expansion "
            "gives a clitic sub-word its parent's span deliberately "
            "(_tokens_from_stanza_doc). Of its mismatches, the share that is "
            "NOT that case is #314."
        ),
    ),
    Invariant(
        name="chunk_work_id",
        statement="chunks.work_id == COALESCE(editions.work_id, translations.work_id)",
        run=audit_chunk_work_id,
        known_exceptions=(
            "Expected to be exactly zero. Any nonzero count means those chunks "
            "are missing from chunks_full entirely — the view inner-joins works "
            "on this column — so they are absent from the reader, search and "
            "refs with no error raised anywhere."
        ),
    ),
)


def _format_text(results: list[tuple[Invariant, Result]]) -> str:
    out: list[str] = []
    for inv, res in results:
        out.append(f"\n=== {inv.name}")
        out.append(f"    {inv.statement}")
        out.append("")
        out.append(f"    {'group':8} {'rows':>12} {'violations':>12} {'holds':>9}")
        for group in sorted(res.per_group):
            checked, bad = res.per_group[group]
            pct = 100.0 * (checked - bad) / checked if checked else 100.0
            out.append(f"    {group:8} {checked:12,} {bad:12,} {pct:8.2f}%")
        pct = (
            100.0 * (res.rows_checked - res.violations) / res.rows_checked
            if res.rows_checked
            else 100.0
        )
        out.append(
            f"    {'ALL':8} {res.rows_checked:12,} {res.violations:12,} {pct:8.2f}%"
        )
        if inv.known_exceptions:
            out.append(f"\n    note: {inv.known_exceptions}")
        if res.examples:
            out.append("\n    examples:")
            for ex in res.examples:
                out.append(f"      {ex.group} {ex.chunk_id} {ex.detail}")
    return "\n".join(out) + "\n"


def _format_json(results: list[tuple[Invariant, Result]]) -> str:
    return json.dumps(
        {
            "invariants": [
                {
                    "name": inv.name,
                    "statement": inv.statement,
                    "rows_checked": res.rows_checked,
                    "violations": res.violations,
                    "per_group": {
                        g: {"checked": c, "violations": v}
                        for g, (c, v) in sorted(res.per_group.items())
                    },
                    "known_exceptions": inv.known_exceptions,
                    "examples": [
                        {"group": e.group, "chunk_id": e.chunk_id, "detail": e.detail}
                        for e in res.examples
                    ],
                }
                for inv, res in results
            ]
        },
        indent=2,
        ensure_ascii=False,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument(
        "--only",
        action="append",
        help="Run only the named invariant (repeatable).",
    )
    args = ap.parse_args(argv)

    db = resolve_db_path()
    if not db.exists():
        # Distinct from "found violations", which is exit 0. Being unable
        # to look must never read as a clean bill of health — a previous
        # verification reported "0 chrome, 0 markers" from a grep over a
        # directory that did not exist (batch 5).
        print(f"audit: no database at {db}", file=sys.stderr)
        return 2

    selected = [i for i in INVARIANTS if not args.only or i.name in args.only]
    if not selected:
        print(f"audit: no invariant matches {args.only}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db)
    # Strictly a reader. The target is an 8.2 GB production index and the
    # cost of a stray write is a snapshot restore, so say so to SQLite
    # rather than relying on the queries staying read-only.
    conn.execute("PRAGMA query_only = ON")
    try:
        results = [(inv, inv.run(conn)) for inv in selected]
    finally:
        conn.close()

    render = _format_json if args.format == "json" else _format_text
    print(render(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
