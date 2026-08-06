"""Score the retriever on a small gold question set.

Each gold record names a question, the work(s) it should land in, and the
acceptable Stephanus/Bekker section locators. We measure:

* recall@k for the work (top hit is in any expected work)
* recall@k for the section (any expected section appears in top-k)
* MRR over correct-section hits

Gold records also carry `expected_book` and `type`, which nothing reads:
this docstring claimed a book check that has never existed (#187).

A gold record's ``expected_works`` names a *work*, not a spelling of one:
each name is resolved to the work it belongs to and then compared against
every name that work answers to. So a gold set written when the Republic
was called `Republic` keeps scoring after #78 renamed it `Politeia` — a
rename that quietly held `work_recall_at_k` at 0.1 for months, because
nothing resolved and nothing gated on it (#183).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import retrieve
from .agent.detect import work_titles


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _work_alias_index(
    conn: sqlite3.Connection, corpus: str | None
) -> tuple[dict[str, set[int]], dict[int, set[str]]]:
    """Two directions of the same name↔work mapping for *corpus*.

    ``by_name`` maps a normalized name to the works answering to it (a
    name can be shared: `Ion` is Plato's dialogue and, elsewhere, a
    tragedy). ``by_id`` maps a work to all of its names. Together they
    turn one gold name into the full alias set of the work it names.
    """

    by_name: dict[str, set[int]] = defaultdict(set)
    by_id: dict[int, set[str]] = defaultdict(set)
    for work_id, title in work_titles(conn, corpus):
        name = _normalize(title)
        by_name[name].add(work_id)
        by_id[work_id].add(name)
    return by_name, by_id


def _expand_expected_works(
    expected: list[str],
    by_name: dict[str, set[int]],
    by_id: dict[int, set[str]],
) -> tuple[list[str], list[str]]:
    """Every name the expected works answer to, plus the unresolvable ones.

    An expected name that no work answers to is returned separately
    rather than dropped: it can only ever score 0, so the caller raises
    instead of reporting a number that means "the gold set is stale".
    """

    names: set[str] = set()
    unresolved: list[str] = []
    for raw in expected:
        ids = by_name.get(_normalize(raw))
        if not ids:
            unresolved.append(raw)
            continue
        for work_id in ids:
            names.update(by_id[work_id])
    return sorted(names), unresolved


def _hit_matches(
    hit: retrieve.Hit,
    expected_works: list[str],
    expected_sections: list[str],
    expected_book: str | None = None,
) -> tuple[bool, bool, bool | None]:
    """``(work_ok, sec_ok, book_ok)`` for one hit.

    Work matching is exact on the normalized name, not a whole-word
    substring. Both sides are verbatim DB values — ``hit.meta["work"]``
    is ``chunks_full.work``, i.e. ``w.title``, and the expected list is
    the alias set built from ``works.title`` / ``title_local`` — and a
    work's canonical title is always in its own alias set. So exact
    match decides every true case, and the looser form could only add
    false positives: with #195's proposed `Das Kapital` alias it would
    have scored Band I as a hit for gold expecting Band II (#189).

    ``book_ok`` is ``None`` when the gold row names no book, so a row
    without one is not scored on it in either direction.
    """

    work = _normalize(hit.meta.get("work"))
    work_ok = work in {_normalize(w) for w in expected_works}
    sec = _normalize(hit.meta.get("section"))
    sec_ok = sec in {_normalize(s) for s in expected_sections}
    book_ok: bool | None = None
    if expected_book is not None:
        book_ok = _normalize(hit.meta.get("book")) == _normalize(expected_book)
    return work_ok, sec_ok, book_ok


def run(
    *,
    conn: sqlite3.Connection,
    gold_path: Path,
    top_k: int = 6,
    embedder=None,
    lang: str | None = "eng",
    corpus: str | None = "plato",
    section_recall_threshold: float = 0.6,
    work_recall_threshold: float = 0.6,
    book_recall_threshold: float = 0.6,
) -> dict:
    rows = _load_gold(gold_path)
    # Positional, not keyed by `row["id"]`: ids are not validated unique,
    # and a collision there would score one row against another's works.
    aliases = _resolve_gold_works(conn, rows, corpus, gold_path)
    per_question: list[dict] = []
    work_hits = 0
    section_hits = 0
    book_hits = 0
    book_questions = 0
    mrr = 0.0
    for idx, row in enumerate(rows):
        hits = retrieve.search(
            conn,
            row["question"],
            top_k=top_k,
            lang=lang,
            corpus=corpus,
            embedder=embedder,
        )
        expected_book = row.get("expected_book")
        work_ok = False
        sec_ok = False
        book_ok: bool | None = None if expected_book is None else False
        rank = None
        for i, h in enumerate(hits, 1):
            wk, sk, bk = _hit_matches(h, aliases[idx], row["expected_sections"], expected_book)
            work_ok = work_ok or wk
            if bk:
                book_ok = True
            if sk and rank is None:
                rank = i
                sec_ok = True
        if work_ok:
            work_hits += 1
        if expected_book is not None:
            book_questions += 1
            if book_ok:
                book_hits += 1
        if sec_ok:
            section_hits += 1
            mrr += 1.0 / rank
        per_question.append(
            {
                "id": row["id"],
                "question": row["question"],
                "work_ok": work_ok,
                "section_ok": sec_ok,
                "book_ok": book_ok,
                "rank": rank,
                "top_hit": (retrieve.format_locator(hits[0].meta) if hits else None),
                "expected_works": row["expected_works"],
                # Every name the expected works answer to. Printed so a
                # `work_ok: false` can be read without guessing which
                # spelling the index is using today.
                "expected_work_aliases": aliases[idx],
                "expected_sections": row["expected_sections"],
                "expected_book": expected_book,
            }
        )
    n = len(rows) or 1
    work_recall = work_hits / n
    section_recall = section_hits / n
    # Denominator is the rows that name a book, not every row — a gold
    # record without `expected_book` is not evidence either way.
    book_recall = book_hits / book_questions if book_questions else 1.0
    summary = {
        "n_questions": len(rows),
        "top_k": top_k,
        "work_recall_at_k": round(work_recall, 3),
        "section_recall_at_k": round(section_recall, 3),
        "section_mrr": round(mrr / n, 3),
        "book_recall_at_k": round(book_recall, 3),
        "n_questions_with_book": book_questions,
        # Both metrics gate. Work recall is the easier of the two — a hit
        # on the right section is a hit in the right work — so a run
        # where it falls below section recall is structurally broken, and
        # used to pass anyway (#183).
        "pass": (
            section_recall >= section_recall_threshold
            and work_recall >= work_recall_threshold
            and book_recall >= book_recall_threshold
        ),
        "per_question": per_question,
    }
    return summary


def _resolve_gold_works(
    conn: sqlite3.Connection,
    rows: list[dict],
    corpus: str | None,
    gold_path: Path,
) -> list[list[str]]:
    """Alias set of each gold row's expected works, in row order.

    Raises ``ValueError`` naming every gold row whose ``expected_works``
    no work in the index answers to. Such a row scores 0 by construction,
    so failing here is the difference between "retrieval regressed" and
    "the gold set is out of date" — a distinction the pre-#183 runner
    could not make, and reported as the former for months.
    """

    by_name, by_id = _work_alias_index(conn, corpus)
    aliases: list[list[str]] = []
    problems: list[str] = []
    for row in rows:
        names, unresolved = _expand_expected_works(row["expected_works"], by_name, by_id)
        aliases.append(names)
        if unresolved:
            problems.append(f"  {row['id']}: {unresolved}")
    if problems:
        scope = corpus or "any"
        raise ValueError(
            f"{gold_path}: expected_works naming no work in corpus {scope!r}:\n"
            + "\n".join(problems)
            + "\nEither the work is not ingested, or it was renamed and the gold "
            "set needs the new name (or the work needs a title_local alias)."
        )
    return aliases


_GOLD_REQUIRED_KEYS = ("id", "question", "expected_works", "expected_sections")


def _load_gold(path: Path) -> list[dict]:
    """Parse a gold JSONL file and validate each row's schema.

    Raises `ValueError` (rather than KeyError mid-iteration) on any
    row missing a required field, listing the offending line number,
    so the CLI surfaces a clear validation error instead of crashing
    inside `_hit_matches`.
    """

    rows: list[dict] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected object, got {type(row).__name__}")
            missing = [k for k in _GOLD_REQUIRED_KEYS if k not in row]
            if missing:
                raise ValueError(f"{path}:{line_no}: missing required keys: {missing}")
            if not isinstance(row["expected_works"], list) or not isinstance(
                row["expected_sections"], list
            ):
                raise ValueError(
                    f"{path}:{line_no}: 'expected_works' and 'expected_sections' must be lists"
                )
            # `id` is what a reader — and any future code — keys a row
            # by; a collision silently scores one row against another's
            # expectations. #183's first draft did exactly that (#190).
            row_id = str(row["id"])
            if row_id in seen_ids:
                raise ValueError(f"{path}:{line_no}: duplicate id {row_id!r}")
            seen_ids.add(row_id)
            rows.append(row)
    return rows
