"""Score the retriever on a small gold question set.

Each gold record names a question, the work(s) it should land in, and the
acceptable Stephanus/Bekker section locators. We measure:

* recall@k for the work (top hit is in any expected work)
* recall@k for the section (any expected section appears in top-k)
* MRR over correct-section hits

Optional book check is matched only when the gold record specifies one.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import retrieve


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _work_matches(work: str, expected: str) -> bool:
    # Whole-word match so e.g. expected "ion" does not match "constitution".
    if not work or not expected:
        return False
    if work == expected:
        return True
    return re.search(rf"(?:^|\W){re.escape(expected)}(?:\W|$)", work) is not None


def _hit_matches(
    hit: retrieve.Hit, expected_works: list[str], expected_sections: list[str]
) -> tuple[bool, bool]:
    work = _normalize(hit.meta.get("work"))
    work_ok = any(_work_matches(work, _normalize(w)) for w in expected_works)
    sec = _normalize(hit.meta.get("section"))
    sec_ok = sec in {_normalize(s) for s in expected_sections}
    return work_ok, sec_ok


def run(
    *,
    conn: sqlite3.Connection,
    gold_path: Path,
    top_k: int = 6,
    embedder=None,
    lang: str | None = "eng",
    corpus: str | None = "plato",
    section_recall_threshold: float = 0.6,
) -> dict:
    rows = _load_gold(gold_path)
    per_question: list[dict] = []
    work_hits = 0
    section_hits = 0
    mrr = 0.0
    for row in rows:
        hits = retrieve.search(
            conn,
            row["question"],
            top_k=top_k,
            lang=lang,
            corpus=corpus,
            embedder=embedder,
        )
        work_ok = False
        sec_ok = False
        rank = None
        for i, h in enumerate(hits, 1):
            wk, sk = _hit_matches(h, row["expected_works"], row["expected_sections"])
            work_ok = work_ok or wk
            if sk and rank is None:
                rank = i
                sec_ok = True
        if work_ok:
            work_hits += 1
        if sec_ok:
            section_hits += 1
            mrr += 1.0 / rank
        per_question.append(
            {
                "id": row["id"],
                "question": row["question"],
                "work_ok": work_ok,
                "section_ok": sec_ok,
                "rank": rank,
                "top_hit": (retrieve.format_locator(hits[0].meta) if hits else None),
                "expected_works": row["expected_works"],
                "expected_sections": row["expected_sections"],
            }
        )
    n = len(rows) or 1
    summary = {
        "n_questions": len(rows),
        "top_k": top_k,
        "work_recall_at_k": round(work_hits / n, 3),
        "section_recall_at_k": round(section_hits / n, 3),
        "section_mrr": round(mrr / n, 3),
        "pass": (section_hits / n) >= section_recall_threshold,
        "per_question": per_question,
    }
    return summary


_GOLD_REQUIRED_KEYS = ("id", "question", "expected_works", "expected_sections")


def _load_gold(path: Path) -> list[dict]:
    """Parse a gold JSONL file and validate each row's schema.

    Raises `ValueError` (rather than KeyError mid-iteration) on any
    row missing a required field, listing the offending line number,
    so the CLI surfaces a clear validation error instead of crashing
    inside `_hit_matches`.
    """

    rows: list[dict] = []
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
            rows.append(row)
    return rows
