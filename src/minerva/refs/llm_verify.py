"""Phase 4 — LLM verification of auto-detected cross-references.

For each ``curator_status='auto'`` row that survives the rules + embed
passes, this stage sends a structured (source, target) pair to the
configured LLM backend and asks: "Does the source passage reference
the target? If so, what kind of reference?"

The LLM response is JSON-only:

    [{
       "id": <int>,
       "references": true|false,
       "type": "cites" | "quotes" | "paraphrases" | "alludes" |
               "comments_on" | "translates" | "disputes" | "corrects",
       "confidence": 0.0-1.0,
       "notes": "<one short sentence>"
    }, ...]

`references=false`  → ``curator_status='rejected'``,
                      ``source_method='rule+embed+llm'``
`references=true`   → bump confidence to max(prev, llm_conf),
                      adopt the LLM's reference_type, set
                      ``source_method='rule+embed+llm'``,
                      keep ``curator_status='auto'`` (curator still
                      promotes to 'approved' via the review walker).

Rows are batched (default 10 per call) to amortize the system-prompt
overhead. The LLM returns one JSON array per call; we match each
verdict back to its source row by ``id``. Out-of-order or missing
verdicts are tolerated — a missing id leaves the row untouched.

Cost guard: ``max_llm_calls`` caps total API calls. Once the budget
is exhausted the verifier stops; remaining rows stay at their prior
state and a subsequent run will pick up where this one left off (the
filter excludes ``source_method LIKE '%llm%'``).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Any

from .. import llm as llm_mod

# Reference-type vocabulary the LLM is allowed to return. Mirrors the
# CHECK constraint on cross_references.reference_type. Anything outside
# this set is coerced to the row's existing type to keep the schema
# happy.
_ALLOWED_TYPES = frozenset(
    {
        "cites",
        "quotes",
        "paraphrases",
        "alludes",
        "comments_on",
        "translates",
        "disputes",
        "corrects",
    }
)


# Progress bar — minimal, dependency-free, tty-aware.
#
# On a tty, prints `\r`-overwritten progress so the bar updates in
# place without scrolling. When stdout is piped or redirected (the
# normal case when running long jobs under `tee` or in a CI/log
# capture), falls back to a newline-per-update layout every N calls
# so the output remains useful but doesn't drown the log.
#
# `flush=True` on every print is what made the difference between
# "log file shows nothing for 40 minutes" and "progress visible in
# real time" — Python block-buffers stdout when not connected to a
# tty, and `tee` propagates whatever line buffering the parent has.


def _format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


class _ProgressBar:
    """Minimal progress renderer. Emit `update()` per LLM call; the
    bar handles bar-rendering, throughput estimation, and tty
    detection internally."""

    def __init__(self, total: int, *, label: str = "verify") -> None:
        self.total = total
        self.label = label
        self.start = time.time()
        self.n = 0
        # Status counters the caller bumps via `set_stats()`.
        self.n_promoted = 0
        self.n_rejected = 0
        self.n_errors = 0
        # Detect tty once. `sys.stdout.isatty()` returns False when
        # piped to `tee` or a log file — the common long-run case.
        self.is_tty = sys.stdout.isatty()
        # When piped, only re-emit every Nth call to keep log noise
        # bounded. Tty mode re-emits on every update.
        self.piped_every = max(1, total // 50) if total else 1

    def set_stats(self, *, promoted: int, rejected: int, errors: int) -> None:
        self.n_promoted = promoted
        self.n_rejected = rejected
        self.n_errors = errors

    def update(self, n: int = 1) -> None:
        self.n += n
        # Throttle output on piped streams; render every step on tty.
        if not self.is_tty and self.n % self.piped_every != 0 and self.n < self.total:
            return
        self._render()

    def close(self, *, final_note: str | None = None) -> None:
        # Force a final render so the line ends in a complete state
        # (especially important on tty where the `\r` would otherwise
        # leave the cursor mid-line).
        self._render(final=True)
        if final_note:
            print(f"  {final_note}", flush=True)

    def _render(self, *, final: bool = False) -> None:
        frac = (self.n / self.total) if self.total else 0.0
        bar_width = 24
        filled = int(bar_width * frac)
        bar = "█" * filled + "·" * (bar_width - filled)
        elapsed = time.time() - self.start
        rate = self.n / elapsed if elapsed > 0 else 0.0
        eta = (self.total - self.n) / rate if rate > 0 and self.n < self.total else 0.0
        line = (
            f"  {self.label} [{bar}] "
            f"{self.n:>5d}/{self.total} ({frac*100:5.1f}%)  "
            f"+{self.n_promoted} −{self.n_rejected} err={self.n_errors}  "
            f"{rate*60:.1f}/min  ETA {_format_eta(eta)}"
        )
        # On tty: overwrite the same line via \r; no newline.
        # On piped: write a complete line with a newline so log files
        # show a stable history.
        if self.is_tty and not final:
            print("\r" + line, end="", flush=True)
        else:
            # For the final render on tty, terminate with a newline so
            # the next print() lands on a fresh line.
            print(line, flush=True)


@dataclass(frozen=True)
class LLMVerifyStats:
    examined: int = 0
    promoted: int = 0
    rejected: int = 0
    unchanged: int = 0
    llm_calls: int = 0
    parse_errors: int = 0
    missing_verdicts: int = 0


_SYSTEM_PROMPT = """You verify cross-references between texts in a corpus of \
canonical Western philosophy (Plato, Aristotle, Augustine, Aquinas, Hegel, \
Kant, Descartes, Spinoza, and the canonical out-of-corpus authors they \
cite — Cicero, Plotinus, Vergil, Boethius, Avicenna, Maimonides, Porphyry, \
etc.).

You will receive a JSON array of candidate references. For each one:

- Decide whether the SOURCE passage actually references the TARGET. The
  target may be (a) a specific in-corpus chunk text, (b) a work-level
  reference where the target text isn't available, or (c) an
  out-of-corpus author whose text we don't have.
- When you can't see the target text, judge based on whether the
  source passage genuinely engages the named author/work — name
  mention alone is enough for cites/alludes; quote/paraphrase/comments_on
  require textual evidence of the engagement.
- Pick the most-specific reference_type from this vocabulary:
    cites        — named attribution
    quotes       — literal phrase reuse
    paraphrases  — content reuse without literal wording
    alludes      — recognizable echo without naming
    comments_on  — sustained structural engagement (Aquinas's De anima commentaries)
    translates   — Latin rendering of a Greek source (rare; commentary work)
    disputes     — explicit disagreement
    corrects     — adopting + amending the source's position
- confidence: your judgment, 0.0 to 1.0. Default ~0.85 when you're sure;
  ~0.6 when you'd want a curator to confirm.

Respond with a single JSON array, no prose:

[{"id": <int>, "references": true|false, "type": "<type>", "confidence": <0..1>, "notes": "<one short sentence>"}, ...]

One object per input row. Use the same `id` values you saw in the input. \
Omit a verdict only if the row was malformed."""


def _build_user_message(rows: list[dict[str, Any]]) -> str:
    """Render a batch into the user-message JSON the LLM consumes.
    Keep target_text short (under ~300 chars) — the verifier is a
    binary "real reference?" judgment, not a full reading."""

    payload = []
    for r in rows:
        item: dict[str, Any] = {
            "id": r["id"],
            "source_author": r["source_author"],
            "source_work": r["source_work"],
            "source_section": r["source_section"],
            "source_text": _truncate(r["source_text"], 400),
            "source_form": r.get("source_form_snapshot"),
            "target_author": r["target_author"],
            "target_work": r["target_work"],
            "target_locator": r["target_locator"],
            "current_reference_type": r["reference_type"],
            "current_method": r["source_method"],
            "current_confidence": r["confidence"],
        }
        if r.get("target_text"):
            item["target_text"] = _truncate(r["target_text"], 300)
            item["target_in_corpus"] = True
        else:
            item["target_in_corpus"] = False
        if r.get("quoted_phrase"):
            item["quoted_phrase"] = r["quoted_phrase"]
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False)


def _truncate(text: str | None, n: int) -> str:
    if text is None:
        return ""
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "…"


# Match the LLM's JSON response. We expect a JSON array but a model
# occasionally wraps it in ```json ... ``` fences or prepends prose.
# This regex extracts the outermost JSON array even when wrapped.
_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def _parse_verdicts(raw: str) -> list[dict[str, Any]] | None:
    """Parse the LLM response into a list of verdict dicts. Returns
    None on unrecoverable parse failure; the caller skips the batch.

    Handles the two common deviations from spec: fenced JSON
    (```json ... ```) and prose-prefixed JSON. Anything more
    pathological we just count as a parse_error."""

    text = raw.strip()
    # Strip a leading ```json or ``` fence + the matching close.
    if text.startswith("```"):
        # Drop the opening fence line and the closing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Direct parse first.
    try:
        out = json.loads(text)
        if isinstance(out, list):
            return out
    except json.JSONDecodeError:
        pass

    # Salvage: pull out the outermost [{...}] match.
    m = _JSON_ARRAY_RE.search(text)
    if m:
        try:
            out = json.loads(m.group(0))
            if isinstance(out, list):
                return out
        except json.JSONDecodeError:
            return None
    return None


def _eligible_rows_sql(
    *,
    skip_short_chunks: bool = True,
    skip_strong: bool = True,
    min_confidence: float | None = None,
    source_author: str | None = None,
    source_work: str | None = None,
    target_author: str | None = None,
    resume_from_id: int | None = None,
) -> tuple[str, list[Any]]:
    """Build the SELECT that pulls Phase-4-eligible rows. The default
    matches the user-confirmed scope: skip the boilerplate-tied
    embed_only rows (chunks under 80 chars on either side) and skip
    rule_strong rows (already 0.92+ from a definitional convention).

    ``resume_from_id`` shifts the lower bound on ``xr.id`` for the
    Phase 6b ``--resume`` checkpoint: skip every row already
    processed by a prior interrupted run.
    """

    clauses = [
        "xr.curator_status = 'auto'",
        "xr.source_method NOT LIKE '%llm%'",
    ]
    params: list[Any] = []
    if skip_strong:
        clauses.append("xr.source_method != 'rule_strong'")
    if skip_short_chunks:
        # Filter rows whose source OR target chunk is too short (the
        # section-banner pattern that produces cosine=1 noise).
        clauses.append("length(c.text) >= 80")
        clauses.append("(xr.target_chunk_id IS NULL OR length(tc.text) >= 80)")
    if min_confidence is not None:
        clauses.append("xr.confidence >= ?")
        params.append(min_confidence)
    if source_author is not None:
        clauses.append("src_work.author = ?")
        params.append(source_author)
    if source_work is not None:
        clauses.append("src_work.title = ?")
        params.append(source_work)
    if target_author is not None:
        clauses.append("rt.canonical_author = ?")
        params.append(target_author)
    if resume_from_id is not None:
        clauses.append("xr.id > ?")
        params.append(resume_from_id)

    where = " AND ".join(clauses)
    sql = (
        "SELECT xr.id, xr.source_chunk_id, xr.source_form_snapshot, "
        "       xr.quoted_phrase, xr.reference_type, xr.confidence, "
        "       xr.source_method, "
        "       c.text AS source_text, "
        "       c.section AS source_section, "
        "       src_work.author AS source_author, "
        "       src_work.title AS source_work, "
        "       rt.canonical_author AS target_author, "
        "       rt.canonical_work AS target_work, "
        "       xr.target_locator, xr.target_chunk_id, "
        "       tc.text AS target_text "
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN chunks tc ON tc.chunk_id = xr.target_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"WHERE {where} "
        "ORDER BY xr.id"
    )
    return sql, params


_LLM_VERIFY_CHECKPOINT_KEY = "refs.llm_verify.last_row_id"


def _read_checkpoint(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (_LLM_VERIFY_CHECKPOINT_KEY,)
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _write_checkpoint(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (_LLM_VERIFY_CHECKPOINT_KEY, str(row_id)),
    )


def verify_rows_with_llm(
    conn: sqlite3.Connection,
    backend: llm_mod.LLMBackend,
    *,
    batch_size: int = 10,
    max_llm_calls: int = 100,
    skip_short_chunks: bool = True,
    skip_strong: bool = True,
    min_confidence: float | None = None,
    source_author: str | None = None,
    source_work: str | None = None,
    target_author: str | None = None,
    verbose: bool = False,
    sleep_between_calls: float = 0.0,
    resume: bool = False,
) -> LLMVerifyStats:
    """Drive the Phase 4 verifier. Batches eligible rows, calls the
    backend per batch, parses verdicts, updates the database. Returns
    summary stats.

    ``max_llm_calls`` is the cost guard — once reached, the function
    stops and remaining rows stay at their prior state. Re-running
    the verifier picks up where this one left off (the filter
    excludes already-LLM-verified rows).

    ``resume=True`` (Phase 6b) reads ``meta.refs.llm_verify.last_row_id``
    and skips rows ``<=`` that id, so a budget-exhausted run can
    pick up the tail efficiently instead of re-issuing the
    already-llm-verified-filtered SQL over the whole table. The
    checkpoint is updated after every batch so an interrupted run
    only re-does at most one batch's worth of rows.
    """

    conn.row_factory = sqlite3.Row

    resume_from_id: int | None = None
    if resume:
        resume_from_id = _read_checkpoint(conn)
        if verbose:
            print(
                "  [resume] starting from xr.id > "
                f"{resume_from_id if resume_from_id is not None else 'none (no checkpoint)'}",
                flush=True,
            )

    sql, params = _eligible_rows_sql(
        skip_short_chunks=skip_short_chunks,
        skip_strong=skip_strong,
        min_confidence=min_confidence,
        source_author=source_author,
        source_work=source_work,
        target_author=target_author,
        resume_from_id=resume_from_id,
    )
    rows = list(conn.execute(sql, params))

    if not rows:
        return LLMVerifyStats()

    if verbose:
        print(
            f"  eligible rows: {len(rows)} "
            f"(budget: {max_llm_calls} calls × {batch_size} rows = "
            f"{max_llm_calls * batch_size} max rows)",
            flush=True,
        )

    n_examined = 0
    n_promoted = 0
    n_rejected = 0
    n_unchanged = 0
    n_calls = 0
    n_parse_errors = 0
    n_missing = 0

    # Materialize rows into a list-of-dicts so we can slice into
    # batches without holding the sqlite cursor open across calls.
    row_dicts = [dict(r) for r in rows]

    # Total calls we'll actually run is bounded by both the budget
    # and the available rows. Pre-compute for the progress bar.
    n_batches_total = (len(row_dicts) + batch_size - 1) // batch_size
    n_calls_target = min(max_llm_calls, n_batches_total)
    progress = _ProgressBar(total=n_calls_target, label="llm-verify")

    for batch_start in range(0, len(row_dicts), batch_size):
        if n_calls >= max_llm_calls:
            progress.close(
                final_note=(
                    f"[budget] reached --max-llm-calls={max_llm_calls}; "
                    f"{len(row_dicts) - batch_start} rows unprocessed "
                    f"(re-run will resume from id > last_seen)"
                )
            )
            break

        batch = row_dicts[batch_start : batch_start + batch_size]
        user_payload = _build_user_message(batch)

        try:
            response = backend.complete(
                [
                    llm_mod.Message(role="system", content=_SYSTEM_PROMPT),
                    llm_mod.Message(role="user", content=user_payload),
                ],
                temperature=0.1,
            )
        except llm_mod.LLMError as exc:
            if verbose:
                # Print on its own line so the in-place progress bar
                # isn't clobbered. `print` to a tty after a `\r` write
                # would overlap; emit a newline first.
                print(f"\n  [error] batch {batch_start//batch_size}: {exc}", flush=True)
            n_calls += 1
            n_parse_errors += 1
            progress.set_stats(promoted=n_promoted, rejected=n_rejected, errors=n_parse_errors)
            progress.update()
            if sleep_between_calls:
                time.sleep(sleep_between_calls)
            continue

        n_calls += 1
        verdicts = _parse_verdicts(response)
        if verdicts is None:
            if verbose:
                print(
                    f"\n  [parse_error] batch {batch_start//batch_size}: "
                    f"could not extract JSON array; first 200 chars: "
                    f"{response[:200]!r}",
                    flush=True,
                )
            n_parse_errors += 1
            progress.set_stats(promoted=n_promoted, rejected=n_rejected, errors=n_parse_errors)
            progress.update()
            if sleep_between_calls:
                time.sleep(sleep_between_calls)
            continue

        # Match each input row to its verdict by id; apply.
        verdict_by_id = {v.get("id"): v for v in verdicts if isinstance(v, dict)}
        for row in batch:
            n_examined += 1
            v = verdict_by_id.get(row["id"])
            if v is None:
                n_missing += 1
                continue

            references = bool(v.get("references"))
            llm_type = str(v.get("type", row["reference_type"]))
            if llm_type not in _ALLOWED_TYPES:
                llm_type = row["reference_type"]
            llm_conf = v.get("confidence")
            try:
                llm_conf_f = float(llm_conf) if llm_conf is not None else None
            except (TypeError, ValueError):
                llm_conf_f = None
            if llm_conf_f is not None:
                llm_conf_f = max(0.0, min(1.0, llm_conf_f))
            llm_notes = str(v.get("notes", "")).strip() or None

            # The LLM observation is per-row and genuinely informative
            # (e.g. "Aquinas attributes the gloss on 1 Tim. 2 to Augustine
            # by name"). Curator_note used to be the rule's template
            # string with this observation appended — that produced
            # thousands of duplicate boilerplate prefixes. Now we replace
            # rather than append: the LLM observation IS the row's note.
            # Manual rows (curator-written notes from YAML specs) are
            # filtered out of the verifier upstream so we never overwrite
            # those.
            if not references:
                conn.execute(
                    "UPDATE cross_references "
                    "SET curator_status = 'rejected', "
                    "    source_method = 'rule+embed+llm', "
                    "    curator_note = ? "
                    "WHERE id = ?",
                    (llm_notes, row["id"]),
                )
                n_rejected += 1
                continue

            # Promote: keep curator_status='auto' (so the curator still
            # signs off via the review walker), but mark provenance + bump
            # confidence + adopt the LLM's type if it differs.
            new_conf = max(row["confidence"], llm_conf_f or row["confidence"])
            conn.execute(
                "UPDATE cross_references "
                "SET confidence = ?, "
                "    reference_type = ?, "
                "    source_method = 'rule+embed+llm', "
                "    curator_note = ? "
                "WHERE id = ?",
                (new_conf, llm_type, llm_notes, row["id"]),
            )
            n_promoted += 1

        # Persist the last processed xr.id so a follow-up `--resume`
        # picks up at exactly the next row. Cheap (single meta upsert)
        # and bounded — one write per batch, not per row.
        _write_checkpoint(conn, batch[-1]["id"])
        conn.commit()

        # Tick the progress bar once per successful call.
        progress.set_stats(promoted=n_promoted, rejected=n_rejected, errors=n_parse_errors)
        progress.update()

        if verbose and n_calls % 50 == 0 and not progress.is_tty:
            # Inline detailed-stats snapshot every 50 calls on piped
            # output. On tty, the bar's per-call render already shows
            # this. Skipped silently otherwise.
            print(
                f"  ... {n_calls}/{max_llm_calls} calls, "
                f"{n_examined} examined, {n_promoted} promoted, "
                f"{n_rejected} rejected",
                flush=True,
            )

        if sleep_between_calls:
            time.sleep(sleep_between_calls)
    else:
        # The `else` clause on `for` runs when the loop exits without
        # `break` — i.e. we processed every batch within budget. Close
        # the bar with no special note.
        progress.close()

    n_unchanged = n_examined - n_promoted - n_rejected

    return LLMVerifyStats(
        examined=n_examined,
        promoted=n_promoted,
        rejected=n_rejected,
        unchanged=n_unchanged,
        llm_calls=n_calls,
        parse_errors=n_parse_errors,
        missing_verdicts=n_missing,
    )


__all__ = [
    "LLMVerifyStats",
    "verify_rows_with_llm",
]
