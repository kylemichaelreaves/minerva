-- 0019_lemma_counts.sql
-- ════════════════════════════════════════════════════════════════════
-- Materialized aggregate table for the concordance leaderboard.
--
-- The corpus-wide concordance query
--   SELECT lemma, pos, COUNT(*), COUNT(DISTINCT work) FROM chunk_lemmas
--   JOIN chunks_full ON ... WHERE lang = ? GROUP BY lemma, pos
-- scans all 8M chunk_lemmas rows + a 4-way chunks_full join + 3 TEMP
-- B-trees, taking 16-36s on the current corpus. With the redesigned
-- filter bar (freq-range slider, POS dropdown, lemma search), every
-- knob the user touches re-issues this query — interactive use is
-- impossible.
--
-- This table pre-computes the GROUP BY at ``minerva index`` time so
-- read queries become single-table seeks. Filter dimensions on the
-- leaderboard (letter, POS, q-search, freq-range) are all expressible
-- against this denormalised shape; sort modes (freq, alpha, pos) hit
-- the secondary indexes.
--
-- Sizing
-- ------
-- With ~120k distinct lemmas per language × 7 languages × 3 scope
-- levels (corpus, per-author, per-work) the table sits around 6-8M
-- rows — same order as chunk_lemmas but each row carries a count
-- instead of a token, so the read path is ~100× fewer SQL rows.
--
-- Population
-- ----------
-- The table is built by ``minerva.concordance.aggregate.build()``,
-- called from ``minerva index`` after chunks land + lemmatize finishes.
-- Manual rebuild: ``minerva terms aggregate-lemmas``. This migration
-- only declares the schema — the build happens out-of-band so the
-- migration runs in <1s on a fresh DB.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS lemma_counts (
    -- Scope identity. scope_kind is one of 'corpus' | 'author' | 'work'.
    -- For 'corpus' rows scope_value is NULL (one row per lang/lemma/pos);
    -- for 'author'/'work' scope_value carries the author display name or
    -- the canonical work title (matches what ``chunks_full.work`` holds).
    lang             TEXT NOT NULL,
    scope_kind       TEXT NOT NULL,
    scope_value      TEXT,
    -- Lemma key. We store the variant exactly as it appears in
    -- chunk_lemmas (no pre-case-merge here — the read path can fold
    -- on a per-page slice, which is fast and lets ``merge_case=0``
    -- callers see the raw variants). ``pos`` is the UD tag the
    -- lemmatizer assigned.
    lemma            TEXT NOT NULL,
    pos              TEXT NOT NULL,
    -- Aggregate counts.
    count            INTEGER NOT NULL,
    distinct_works   INTEGER NOT NULL,
    -- JSON payload: ``[{"work": "...", "n": NN}, ...]`` capped at top-8
    -- per the existing sparkline contract. Built once during aggregate;
    -- the API just passes it through.
    per_work_json    TEXT,
    PRIMARY KEY (lang, scope_kind, scope_value, lemma, pos)
);

-- Frequency-sorted leaderboard — the default sort on the index page.
-- Composite (lang, scope) prefix lets a single scope read range-scan
-- in count-desc order without a temp B-tree.
CREATE INDEX IF NOT EXISTS lemma_counts_by_freq
    ON lemma_counts(lang, scope_kind, scope_value, count DESC, lemma COLLATE NOCASE);

-- Alphabetical sort — leading letter filter (``WHERE lemma LIKE 'A%'``)
-- + alpha order in one path.
CREATE INDEX IF NOT EXISTS lemma_counts_by_alpha
    ON lemma_counts(lang, scope_kind, scope_value, lemma COLLATE NOCASE);

-- POS-grouped sort — list all NOUN, then all VERB, etc. Inside each
-- POS the count-desc ordering is fed by the freq index's secondary
-- key; SQLite handles the join transparently.
CREATE INDEX IF NOT EXISTS lemma_counts_by_pos
    ON lemma_counts(lang, scope_kind, scope_value, pos, count DESC);
