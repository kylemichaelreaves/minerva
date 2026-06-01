-- 0018_chunk_lemmas_fold.sql
-- ════════════════════════════════════════════════════════════════════
-- Add case-folded lemma column + index for KWIC lookups.
--
-- The concordance KWIC query is `WHERE LOWER(cl.lemma) = LOWER(?)` —
-- a classic SQLite anti-pattern that disables index use and forces
-- a full scan over chunk_lemmas (8M rows). EXPLAIN QUERY PLAN
-- reports SCAN c (340k chunks) + per-chunk lemma seek, totalling
-- ~2-3s per KWIC fetch.
--
-- The fix is a stored case-fold column with its own index. The
-- lemmatize CLI writes ``lemma_fold = LOWER(lemma)`` at insert
-- time; KWIC queries become ``WHERE cl.lemma_fold = ?`` and seek
-- the index in ms. Case-fold uses SQL ``LOWER()`` (not Python's
-- richer ``str.casefold()``) so the comparison happens at the same
-- byte level the index keys on.
--
-- Backfill is done inline here because the table is already large
-- (8M rows); doing it as a separate step would risk leaving rows
-- with NULL fold values that the KWIC seek would miss.
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE chunk_lemmas ADD COLUMN lemma_fold TEXT;

-- Backfill existing rows. Single UPDATE — SQLite holds a write lock
-- through it but the table is bounded (8M rows ≈ 30s).
UPDATE chunk_lemmas SET lemma_fold = LOWER(lemma);

-- KWIC lookup index. The query path is
--   ``WHERE cf.lang = ? AND cl.lemma_fold = ?``
-- so we lead with lemma_fold; the language filter comes from the
-- chunks_full join via chunk_id. A covering composite
-- ``(lemma_fold, chunk_id)`` would be even faster but doubles disk;
-- the simple index gets us into the same order of magnitude.
CREATE INDEX IF NOT EXISTS chunk_lemmas_by_fold
    ON chunk_lemmas(lemma_fold);
