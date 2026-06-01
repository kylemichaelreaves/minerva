-- 0005_occurrence_renderings_shadow.sql
-- Translation-side shadow address on `occurrence_renderings`,
-- symmetric to the source-side shadow already on `term_occurrences`.
--
-- Why: when a translation gets re-ingested (a parser fix on a
-- translated PDF, fresh OCR pass, etc.), `chunks.chunk_id` values for
-- that translation regenerate from content hashes. Any
-- `occurrence_renderings.translation_chunk_id` becomes a dangling FK
-- and the CASCADE on chunk delete would wipe curated renderings.
-- This shadow lets the relink path recover those rows from the
-- (translation, source-side locator, rendered phrase, nth-instance)
-- tuple — the same recipe used on the source side.
--
-- Columns added (both nullable for now — existing rows would need
-- backfill from the parent occurrence; we have zero existing rows in
-- practice so NULLs only happen if the curator inserts directly via
-- SQL, which they shouldn't). Going forward, the helper
-- `terms.insert_occurrence_rendering` populates them.
--
--   source_locator_sort_key
--      Denormalized from `term_occurrences.location_sort_key` (the
--      sort key of the SOURCE-side occurrence). Lets the relink path
--      find the matching translation chunk in one indexed read,
--      assuming translations carry the source's locator (which they
--      do for every translation in the corpus today — Stephanus
--      numbers in a translated Republic, §-paragraph numbers in a
--      translated PR).
--
--   rendered_form_snapshot
--      Strict snapshot of the literal characters at curation time.
--      Equal to `rendered_text` at insert time but recorded
--      separately so that a curator-led correction to
--      `rendered_text` (typo fix, normalization) doesn't break the
--      relink address. The shadow stays canonical.
--
--   instance_index
--      1-based count of the nth match of `rendered_form_snapshot`
--      within the translation chunk identified by
--      `source_locator_sort_key`. Disambiguates the case where the
--      same word appears multiple times at the same locator —
--      Shorey writing "reason" three times in a paragraph that
--      contains three λόγος occurrences each tagged separately.

ALTER TABLE occurrence_renderings ADD COLUMN source_locator_sort_key TEXT;
ALTER TABLE occurrence_renderings ADD COLUMN rendered_form_snapshot   TEXT;
ALTER TABLE occurrence_renderings ADD COLUMN instance_index           INTEGER;

-- The shadow address. Logically: ``(translation_id,
-- source_locator_sort_key, rendered_form_snapshot, instance_index)``
-- is unique. We index it explicitly for the relink scan; the
-- existing ``UNIQUE (occurrence_id, translation_id)`` constraint
-- still enforces "one rendering override per (occurrence,
-- translation)" — that one's not redundant with the shadow.
CREATE INDEX IF NOT EXISTS occ_render_by_shadow
    ON occurrence_renderings(
        translation_id,
        source_locator_sort_key,
        rendered_form_snapshot,
        instance_index
    );
