-- 0008_chunk_lemmas_morph.sql
-- ════════════════════════════════════════════════════════════════════
-- Add Universal Dependencies POS + morph-features columns to
-- chunk_lemmas. Lets the Reader's word-info drawer surface "noun ·
-- masc. · sing." (and any other UD-tagged morphology) without
-- re-running the lemmatizer at lookup time.
--
-- Stanza produces these natively (word.upos, word.feats); spaCy's
-- token.pos_ + token.morph cover the German path. Both already use
-- the UD tagset, so the column contents are the same vocabulary
-- regardless of backend.
--
-- Backfill: ALTER TABLE leaves existing rows with NULL pos/feats.
-- The next `minerva terms lemmatize --all` re-pass overwrites them
-- because the lemmatize CLI's INSERT switched from `OR IGNORE` to
-- `OR REPLACE` in the same change set. Until that pass runs, the
-- word-info drawer just hides the morph chip (the backend returns
-- the fields as null and the frontend skips rendering).
-- ════════════════════════════════════════════════════════════════════

-- UPOS code: NOUN, VERB, ADJ, ADV, PRON, DET, ADP, CCONJ, SCONJ,
-- PART, INTJ, NUM, PROPN, AUX, SYM, X. Nullable to keep the
-- pre-backfill state queryable.
ALTER TABLE chunk_lemmas ADD COLUMN pos TEXT;

-- Raw UD morph features in the canonical `Key=Value|Key=Value`
-- shape (e.g., "Case=Acc|Gender=Fem|Number=Sing"). Parsed
-- server-side by handlers/reader.py:_parse_morph_feats to pull out
-- the fields the UI renders; the column itself stays unparsed so
-- adding a new chip later doesn't need a migration.
ALTER TABLE chunk_lemmas ADD COLUMN feats TEXT;
