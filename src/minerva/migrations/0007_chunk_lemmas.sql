-- 0007_chunk_lemmas.sql
-- ════════════════════════════════════════════════════════════════════
-- Lemma cache for the term-glossary importer. One row per token of
-- every grc/deu chunk, materialised once via `minerva terms
-- lemmatize` (CLTK for grc, spaCy for deu). The glossary importer
-- joins this table against `terms.lemma` to find term occurrences
-- mechanically, so the curator can specify a lemma instead of
-- hand-listing every inflected surface form.
--
-- Why a separate table and not a chunks column
-- --------------------------------------------
-- Tokens are 1-to-many with chunks: one chunk has tens to hundreds of
-- tokens. Stacking them as a JSON column on `chunks` would defeat
-- the join we want (`WHERE chunk_lemmas.lemma = ?`). A dedicated
-- table with a (chunk_id, lemma) index makes the lookup an O(log n)
-- index hit instead of a full table scan.
--
-- The FK on chunk_id cascades on delete, so re-ingest paths that
-- drop a chunk automatically clear its lemmas. Re-running the
-- lemmatizer is the cheap recovery (skips rows already present).
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS chunk_lemmas (
    chunk_id      TEXT    NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    -- 0-based position within the chunk's token stream. Stable for a
    -- given (chunk_id, lemmatizer-version) pair; if we ever swap
    -- lemmatizers, the lemmatize CLI's `--all` flag forces a
    -- full re-pass and re-numbers from scratch.
    token_index   INTEGER NOT NULL,
    -- The exact substring from chunks.text that this token covers.
    -- Lets the glossary importer fill `source_form_snapshot` without
    -- re-slicing the chunk on the import-side.
    surface_form  TEXT    NOT NULL,
    -- Character offsets into chunks.text. Match the same convention
    -- used by term_occurrences.source_start/source_end so the
    -- importer can copy them straight through.
    surface_start INTEGER NOT NULL,
    surface_end   INTEGER NOT NULL,
    -- The lemma the lemmatizer assigned. NFC-normalised by the
    -- writer so equality comparisons against terms.lemma are exact.
    lemma         TEXT    NOT NULL,
    PRIMARY KEY (chunk_id, token_index),
    CHECK (surface_end > surface_start)
);

-- Glossary-import lookup: "every chunk where the lemma appears."
CREATE INDEX IF NOT EXISTS chunk_lemmas_by_lemma
    ON chunk_lemmas(lemma);

-- Per-chunk scan filtered by lemma — used when the importer wants
-- every occurrence in one specific chunk (e.g. surfacing all sites of
-- a term within a small Reader window without a wide scan).
CREATE INDEX IF NOT EXISTS chunk_lemmas_by_chunk_and_lemma
    ON chunk_lemmas(chunk_id, lemma);
