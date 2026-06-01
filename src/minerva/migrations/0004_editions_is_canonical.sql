-- 0004_editions_is_canonical.sql
-- Cross-edition reconciliation, level 1 (per 0001's DEFERRED note):
-- add an `is_canonical` flag on editions and enforce exactly one
-- canonical edition per (work_id, language).
--
-- Why now: term-glossary queries that ask "every λόγος in Republic"
-- need a tie-breaker when a Work has multiple source-language
-- editions. Without is_canonical, Q2 must either filter by an
-- arbitrary edition_id or return rows from each edition (duplicate
-- presentation). With is_canonical, the default is "the canonical
-- edition's occurrences"; the others remain available behind an
-- explicit edition selector in the curator UI.
--
-- Out of scope for this migration (still deferred):
--   * `edition_alignments` table for noting where two editions
--     disagree at the same locator.
--   * UI behaviour. The schema change is forward-additive; readers
--     that don't care about is_canonical continue to work.
--
-- Existing data: every editions row gets is_canonical=1 because the
-- corpus today has at most one edition per (work, lang) — a fresh
-- start state for the constraint to land in.

ALTER TABLE editions ADD COLUMN is_canonical INTEGER NOT NULL DEFAULT 1
    CHECK (is_canonical IN (0, 1));

-- Partial unique index: at most one canonical edition per
-- (work_id, language). A non-canonical edition can coexist freely.
CREATE UNIQUE INDEX IF NOT EXISTS editions_canonical_unique
    ON editions(work_id, language) WHERE is_canonical = 1;

-- Backfill: every existing editions row is canonical by default
-- (handled by DEFAULT 1 above; this no-op statement documents the
-- intent so future maintainers don't wonder why the DEFAULT is set
-- to 1 instead of 0).
UPDATE editions SET is_canonical = 1 WHERE is_canonical IS NULL;
