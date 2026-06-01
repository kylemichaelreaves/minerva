-- 0002_chunks_lang_to_iso_639_3.sql
-- Migrate `chunks.lang` from legacy two-letter codes to ISO 639-3.
--
-- Why a data migration rather than a column-type change: the column
-- type is already TEXT; SQLite doesn't enforce length. The schema is
-- unchanged. Only the stored values shift.
--
-- After this runs, all chunks.lang values are 639-3. The parsers
-- emit 639-3 going forward (see minerva.tei, minerva.corpus_works);
-- a future re-ingest produces the same shape without further fix-up.
--
-- Out of scope: the translate-cache database (data/translations.sqlite)
-- carries the same legacy codes in its target_lang column. Existing
-- cache rows become orphans (unreachable by 639-3 lookups) and the
-- cache heals on the next request. If this turns out to matter
-- somewhere, vacuum it by hand:
--   sqlite3 data/translations.sqlite "UPDATE translations SET
--     target_lang=CASE target_lang WHEN 'en' THEN 'eng' WHEN 'fr'
--     THEN 'fra' WHEN 'de' THEN 'deu' END WHERE target_lang IN
--     ('en','fr','de');"

UPDATE chunks SET lang = CASE lang
    WHEN 'gr' THEN 'grc'
    WHEN 'de' THEN 'deu'
    WHEN 'en' THEN 'eng'
    WHEN 'fr' THEN 'fra'
    ELSE lang
END
WHERE lang IN ('gr', 'de', 'en', 'fr');
