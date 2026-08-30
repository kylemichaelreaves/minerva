"""`minerva terms lemmatize` — populate the chunk_lemmas cache.

One row per (chunk, token) for every grc/deu chunk; downstream the
glossary importer joins this against `terms.lemma` to find term
occurrences. Designed to be run once after a fresh ingest and then
left alone — re-runs skip chunks already present unless ``--all`` is
passed.

The expensive step is loading the spaCy model (~1-2 s for
``de_core_news_sm``) and running it over thousands of chunks (~10 k
tokens/sec). We batch by chunk and commit every N inserts so a Ctrl-C
mid-run doesn't lose all progress.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from ...lemmatize import (
    SUPPORTED_LANGUAGES as _SUPPORTED,
)
from ...lemmatize import (
    Lemmatizer,
    Token,
    UnsupportedLanguageError,
    find_alt_script_runs,
    fix_grc_ascii_prefix_confusables,
    is_supported,
    is_valid_lemma,
    mask_runs,
)
from ...sqlite_util import register_text_hash, text_hash
from ._io import _open

# Commit every N chunk-batches. Bigger = fewer fsyncs; smaller = less
# work lost on interrupt. At 2000 chunks an interrupt costs ~30s of
# work in the worst case — acceptable for the SQLite-throughput
# headroom we get back. See lemmatize-perf-plan memory.
_COMMIT_BATCH = 2000


def cmd_terms_lemmatize(args: argparse.Namespace) -> int:
    """Driver. Builds the list of chunks to process, instantiates the
    lemmatizer once, streams tokens into ``chunk_lemmas`` in batches."""

    lang = args.lang
    if not is_supported(lang):
        # argparse `choices` already rejects unknown codes at parse time;
        # this guards programmatic callers. An unsupported language is an
        # ERROR, not a silent success — a pipeline must not mistake a
        # no-op for a completed lemmatize pass (issue #67).
        print(
            f"lemmatize: language {lang!r} is not supported "
            f"(known: {', '.join(sorted(_SUPPORTED))}).",
            file=sys.stderr,
        )
        return 2

    conn = _open(args)
    try:
        # Build the candidate-chunk query. `chunks_full` includes
        # work_id / edition_id / corpus, so filtering by edition or
        # by language stays a clean WHERE clause.
        where: list[str] = ["cf.lang = ?"]
        params: list[object] = [lang]
        if args.edition_id is not None:
            where.append("cf.edition_id = ?")
            params.append(args.edition_id)
        if not args.all:
            # Skip chunks already ATTEMPTED at their current text —
            # not merely chunks that produced output. Keying this on
            # chunk_lemmas (as it was until #263) meant a chunk yielding
            # no valid lemma wrote no row, was never recorded, and came
            # back as a candidate on every subsequent pass forever: 859
            # of them across eng/fra/deu/grc. The hash comparison is
            # what catches a chunk whose text changed under a stable
            # chunk_id — see `sqlite_util.text_hash`.
            register_text_hash(conn)
            where.append(
                "NOT EXISTS (SELECT 1 FROM chunk_lemma_state s "
                " WHERE s.chunk_id = cf.chunk_id "
                "   AND s.text_hash = text_hash(cf.text))"
            )
        where_clause = " AND ".join(where)
        count_sql = "SELECT COUNT(*) FROM chunks_full cf WHERE " + where_clause
        select_sql = (
            "SELECT cf.chunk_id, cf.text FROM chunks_full cf "
            "WHERE " + where_clause + " ORDER BY cf.ord"
        )
        total = conn.execute(count_sql, params).fetchone()[0]
        print(f"lemmatize: {total} chunks to process for lang={lang}")
        if total == 0:
            return 0

        if args.dry_run:
            # Tokenise the first few chunks just to confirm the model
            # is loadable and produces plausible output — useful when
            # the curator wants to sanity-check before committing to a
            # full pass.
            try:
                lm = Lemmatizer(lang)
            except UnsupportedLanguageError as exc:
                print(f"lemmatize: {exc}")
                return 1
            print(
                f"lemmatize: backend={getattr(lm, 'backend', '?')} "
                f"model={getattr(lm, 'model', '?')} (dry-run)"
            )
            sample = conn.execute(select_sql + " LIMIT 3", params).fetchall()
            for ch in sample:
                tokens = list(lm.tokens(ch["text"]))
                preview = ", ".join(
                    f"{t.surface}→{t.lemma}" for t in tokens[:8]
                )
                print(f"  {ch['chunk_id']}: {len(tokens)} tokens · {preview}")
            return 0

        try:
            lm = Lemmatizer(lang)
        except UnsupportedLanguageError as exc:
            print(f"lemmatize: {exc}")
            return 1
        print(
            f"lemmatize: backend={getattr(lm, 'backend', '?')} "
            f"model={getattr(lm, 'model', '?')}"
        )

        # Stream the candidate chunks through `Lemmatizer.batch_pipe`
        # instead of materializing them all up front. On the full
        # deu pass that's ~104 k rows × ~1-2 KB of text per row =
        # ~200 MB held in RAM just to feed the generator. The
        # streaming form starts processing chunk 1 immediately and
        # never holds more than the current spaCy pipe batch in
        # memory. SQLite cursors survive commits issued on the same
        # connection — each Cursor owns its own prepared statement
        # handle and resumes from its row position after the writer
        # finishes. (A second connection would deadlock here because
        # the read cursor's SHARED lock blocks the writer's EXCLUSIVE
        # lock acquisition at commit time.)
        # Tuple shape matches the INSERT in ``_flush`` — the lemma_fold
        # slot was added with migration 0018 so KWIC lookups can seek
        # ``chunk_lemmas_by_fold`` instead of forcing a scan via
        # ``LOWER(lemma) = LOWER(?)``. ``lang`` (migration 0032) is NULL
        # for an ordinary same-script token — meaning "this row's
        # language is its chunk's language", still true for every row
        # this pass writes under ``lang`` itself — and is only ever the
        # OTHER language for a cross-script run (#430).
        inserts: list[
            tuple[str, int, str, int, int, str, str, str | None, str | None, str | None]
        ] = []
        # One row per chunk the lemmatizer was run over, written in the
        # same transaction as that chunk's lemmas so an interrupt can
        # never record an attempt whose output was rolled back (#263).
        attempts: list[tuple[str, str, int]] = []
        tokens_total = 0
        chunks_done = 0
        chunks_productive = 0
        progress = _progress_bar(total=total, lang=lang)
        cursor = conn.execute(select_sql, params)
        # Hashed on the way in and popped on the way out, so this holds
        # only the chunks currently inside the spaCy pipe — keeping the
        # text itself would restore the ~200 MB the streaming cursor was
        # introduced to avoid. ``pending_alt_runs`` is the same shape but
        # holds only the (small) substrings of chunks that actually carry
        # a cross-script run — the vast majority of chunks never appear
        # in it at all.
        pending_hash: dict[str, str] = {}
        pending_alt_runs: dict[str, list[tuple[str, int, int, str]]] = {}
        # Lazily constructed — a model load per language, paid only if a
        # cross-script run is actually found, and only once for the
        # whole pass, not once per chunk.
        secondary_lemmatizers: dict[str, Lemmatizer] = {}

        def _items():
            for row in cursor:
                raw = row["text"]
                pending_hash[row["chunk_id"]] = text_hash(raw)
                # #446: repair a glued ASCII prefix (numeral marker or
                # misencoded initial letter) before #430's alt-script
                # detection runs — the words this fixes contain a Greek
                # letter, so they classify as 'greek' and would reach
                # the primary model untouched otherwise.
                if lang == "grc":
                    raw = fix_grc_ascii_prefix_confusables(raw)
                # #430: find spans whose script doesn't match `lang`
                # BEFORE this chunk's text reaches the primary model —
                # blanking them out is what stops e.g. embedded Latin
                # prose from being tokenized (and mislemmatized) as Greek
                # in the first place, rather than merely fixing up the
                # rows afterward.
                alt_runs = find_alt_script_runs(raw, lang)
                if alt_runs:
                    pending_alt_runs[row["chunk_id"]] = [
                        (alt_lang, start, end, raw[start:end])
                        for alt_lang, start, end in alt_runs
                    ]
                    text = mask_runs(raw, alt_runs)
                else:
                    text = raw
                # The stored text, verbatim (modulo the masking above).
                # This used to yield `unicodedata.normalize("NFC", ...)`,
                # and the offsets that came back indexed *that* string
                # while every consumer slices `chunks.text` — 1,866 rows
                # wrong across 16,032 non-NFC chunks (#311). The
                # normalization is still done, and still has to be, but
                # it belongs to `Lemmatizer`, which maps the offsets
                # back; see `lemmatize._pipeline_text`.
                yield text, row["chunk_id"]

        def _secondary_tokens(chunk_id: str) -> list[tuple[Token, str]]:
            """Cross-script runs for `chunk_id`, each lemmatized under
            its own alternate-language model and shifted back to the
            chunk's own offsets. Empty for the overwhelming majority of
            chunks, which never entered `pending_alt_runs` at all."""

            out: list[tuple[Token, str]] = []
            for alt_lang, start, _end, substring in pending_alt_runs.pop(chunk_id, []):
                secondary = secondary_lemmatizers.get(alt_lang)
                if secondary is None:
                    try:
                        secondary = Lemmatizer(alt_lang)
                    except UnsupportedLanguageError:
                        # No lemmatizer registered for the alternate
                        # language — leave the run unlemmatized rather
                        # than fail the whole pass over it.
                        continue
                    secondary_lemmatizers[alt_lang] = secondary
                for tok in secondary.tokens(substring):
                    out.append(
                        (
                            Token(
                                surface=tok.surface,
                                start=tok.start + start,
                                end=tok.end + start,
                                lemma=tok.lemma,
                                pos=tok.pos,
                                feats=tok.feats,
                            ),
                            alt_lang,
                        )
                    )
            return out

        for tokens, chunk_id in lm.batch_pipe(
            _items(), batch_size=args.batch_size, n_process=args.n_process
        ):
            # Primary tokens carry no explicit lang (NULL — "this
            # chunk's own language"); secondary tokens carry the
            # alternate language they were actually lemmatized under.
            # Merged and sorted by surface offset so token_index still
            # reflects left-to-right reading order across both passes.
            combined = [(tok, None) for tok in tokens] + _secondary_tokens(chunk_id)
            combined.sort(key=lambda pair: pair[0].start)

            # token_index is 0-based within the chunk and survives
            # filtering — we increment only on valid lemmas so the
            # stored indices stay dense. Original positions in the
            # source text still recover via (surface_start, surface_end).
            kept = 0
            for tok, tok_lang in combined:
                if not is_valid_lemma(tok.lemma):
                    continue
                inserts.append(
                    (
                        chunk_id, kept,
                        tok.surface, tok.start, tok.end,
                        tok.lemma, tok.lemma.lower(),
                        tok.pos, tok.feats, tok_lang,
                    )
                )
                kept += 1
                tokens_total += 1
            attempts.append((chunk_id, pending_hash.pop(chunk_id), kept))
            chunks_done += 1
            chunks_productive += bool(kept)
            progress.update(1)
            progress.set_postfix_str(f"{tokens_total} tokens", refresh=False)
            if chunks_done % _COMMIT_BATCH == 0:
                _flush(conn, inserts, attempts)
                inserts.clear()
                attempts.clear()
        _flush(conn, inserts, attempts)
        progress.close()
        # Attempted and productive reported separately: "done · 679
        # chunks" read as 679 chunks lemmatized when it meant 679 tried,
        # 260 of which produced anything (#263).
        print(
            f"lemmatize: done · {chunks_done} chunks "
            f"({chunks_productive} productive) · {tokens_total} tokens"
        )

        # Rebuild the concordance aggregate table — the only consumer
        # of chunk_lemmas at read time. Skipping this would leave the
        # leaderboard stale until the next manual ``aggregate-lemmas``
        # run. Cost: ~30s on the current corpus, dwarfed by the
        # lemmatize pass itself.
        if not getattr(args, "skip_aggregate", False):
            from ...concordance import aggregate
            summary = aggregate.build(conn, verbose=True)
            print(
                f"aggregate-lemmas: {summary['total']:,} rows in "
                f"{summary['elapsed_seconds']:.1f}s"
            )
        return 0
    finally:
        conn.close()


def _progress_bar(*, total: int, lang: str):
    """Return a tqdm-compatible progress handle, gracefully degrading
    to a no-op when stdout isn't a TTY (CI logs, piped output) or when
    tqdm isn't importable. tqdm is a transitive dep via Stanza so
    `import tqdm` succeeds on any install with `[lemma]`; the
    fallback keeps the CLI usable on a no-extras install too."""

    if not sys.stdout.isatty():
        return _NoOpProgress(total=total)
    try:
        from tqdm import tqdm
    except ImportError:
        return _NoOpProgress(total=total)
    return tqdm(
        total=total,
        desc=f"lemmatize {lang}",
        unit="chunk",
        # ASCII-only so the bar renders cleanly in any terminal,
        # including the basic line-buffered ones used by CI.
        ascii=True,
        # Sub-second refresh would burn CPU on a fast pass; once per
        # chunk-batch is plenty of feedback for a multi-minute run.
        mininterval=0.5,
    )


class _NoOpProgress:
    """Drop-in for tqdm when no TTY is available. Keeps the call sites
    identical and prevents `--report json` consumers from seeing
    bar fragments in their stdout."""

    def __init__(self, *, total: int) -> None:
        self._total = total
        self._done = 0
        # Periodically write a plain `N/total` line so a non-TTY run
        # (`make lemmatize | tee log`) still records progress.
        self._next_milestone = max(total // 20, 1)

    def update(self, n: int = 1) -> None:
        self._done += n
        if self._done >= self._next_milestone:
            print(f"  {self._done}/{self._total} chunks")
            self._next_milestone += max(self._total // 20, 1)

    def set_postfix_str(self, _s: str, refresh: bool = True) -> None:
        del refresh

    def close(self) -> None:
        pass


def _flush(
    conn: sqlite3.Connection,
    rows: list[
        tuple[str, int, str, int, int, str, str, str | None, str | None, str | None]
    ],
    attempts: list[tuple[str, str, int]],
) -> None:
    """Delete each attempted chunk's prior lemmas, then bulk-insert the
    accumulated rows — one transaction for both.

    THE DELETE IS NOT OPTIONAL (#284). `INSERT OR REPLACE` is keyed on
    (chunk_id, token_index), so overwriting alone leaves indices
    ``N..M-1`` behind whenever a re-pass yields FEWER tokens than the
    pass before it — rows carrying the *previous* tokenization's
    surface offsets, indistinguishable from current output. Their
    ``surface_start``/``surface_end`` address text that has moved, so
    the concordance and the Reader's KWIC view highlight the wrong span
    and ``lemma_counts`` over-counts. The docstring here used to call
    this a trade-off ("a partial earlier run isn't preserved across a
    re-pass") and had it exactly backwards: the earlier run's surplus
    rows were the thing that survived.

    A shrinking re-pass is not hypothetical — a tokenizer upgrade (the
    LatinCy migration was one), a tightening of ``is_valid_lemma``
    (every past edit to it rejected more), or an edited chunk that kept
    its ``chunk_id`` all produce it.

    Keyed on ``attempts``, not on ``rows``. A chunk that yielded nothing
    this pass contributes no insert at all, and it is precisely the
    chunk whose entire previous output is now stale — deleting by the
    rows about to be written would skip it. Issued per flush batch and
    in the same transaction as the insert, rather than once up front:
    an up-front delete would lose every lemma in the corpus if the run
    were interrupted.

    ``OR REPLACE`` stays on the insert even though the delete makes it
    redundant for the case it was added for (overwriting legacy rows
    that predate migration 0008's pos/feats columns). It is now only a
    backstop against the same chunk appearing twice in one batch, which
    nothing produces today.

    Each tuple carries ``lemma_fold`` (added in migration 0018) after
    ``lemma`` so the KWIC index can seek by case-folded value instead
    of a runtime ``LOWER(lemma)`` that disables the index. ``lang``
    (migration 0032) is the last column — NULL for an ordinary token,
    the alternate language for a cross-script run (#430).

    ``attempts`` carries the ``chunk_lemma_state`` markers for the same
    chunks and is written in the SAME transaction. A chunk recorded as
    attempted whose lemmas were rolled back by an interrupt would be
    skipped forever, which is the bug in the other direction.
    """

    if not rows and not attempts:
        return
    # No `if rows:` / `if attempts:` guards — `executemany` over an empty
    # sequence is already a no-op, and a wholly barren commit batch
    # (markers, no lemma rows) is the normal case for an OCR-damaged
    # corpus rather than an exception to branch on.
    conn.executemany(
        "DELETE FROM chunk_lemmas WHERE chunk_id = ?",
        [(chunk_id,) for chunk_id, _text_hash, _count in attempts],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, "
        " surface_end, lemma, lemma_fold, pos, feats, lang) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.executemany(
        "INSERT INTO chunk_lemma_state (chunk_id, text_hash, token_count) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(chunk_id) DO UPDATE SET "
        "  text_hash = excluded.text_hash, "
        "  token_count = excluded.token_count, "
        "  lemmatized_at = CURRENT_TIMESTAMP",
        attempts,
    )
    conn.commit()
