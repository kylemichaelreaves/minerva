-- 0025_work_aliases.sql
-- ════════════════════════════════════════════════════════════════════
-- Extra names a work answers to, for work/corpus detection only.
--
-- `works.title` is one string, and for some works it is not a name any
-- reader uses: Hegel's Phenomenology carries its translator's surname
-- ("Phenomenology of Spirit (Pinkard)"), and Marx's Kapital is split by
-- volume ("Das Kapital, Band I"). Both were unreachable by the name a
-- reader would type — the two failures left after #194 (#195).
--
-- Why not `title_local` (migration 0023): that column holds ONE value
-- per (work, language) and it is what the reader DISPLAYS. Using it as
-- an alias slot forces a display change to buy a detection fix, and it
-- still cannot express the cross-language pairs, where an English work
-- must answer to its German name while keeping its English one. This
-- table is detection-only; nothing in the reader reads it.
--
-- DERIVED, NOT CURATED. Rows are re-materialized from
-- `authors/work_aliases.py` on every `minerva index`, keyed on the
-- natural `(author, works.title)` pair. `works.id` is a surrogate
-- reassigned by insertion order and reshuffled by `--reset` (#193), so
-- nothing here is hand-maintained and there is nothing to preserve
-- across a re-ingest — hence no entry in the preserved-state snapshot
-- path, unlike the term glossary (#192).
--
-- ON DELETE CASCADE for the same reason: if a work goes away, its
-- aliases are meaningless, and the next index run rebuilds whatever
-- should still exist.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS work_aliases (
    work_id  INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    alias    TEXT NOT NULL,
    PRIMARY KEY (work_id, alias)
);

-- Detection scans aliases by name across an author or the whole index.
CREATE INDEX IF NOT EXISTS work_aliases_by_alias ON work_aliases(alias);
