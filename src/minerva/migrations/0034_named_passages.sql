-- 0034_named_passages.sql
-- ════════════════════════════════════════════════════════════════════
-- Labels scholarship gave a passage that the passage's own text never
-- uses — "the divided line" (Politeia 509d–511e), "the slave boy"
-- (Menon 82b–85b), "the Copernican revolution" (Kant's B-preface) — so a
-- reader who asks about the label rather than naming the work finds
-- nothing (#182).
--
-- NOT `terms` (migration for the term glossary). That table is a
-- lemma-keyed lexical glossary: an occurrence is a character-offset
-- span (`source_start`/`source_end`) anchoring a word the text actually
-- contains. "The divided line" has no lemma, no `source_form` in any
-- source language, and no span to anchor to — it names a passage, not a
-- word. Conflating the two was the original, corrected suggestion on
-- #182.
--
-- FOLLOWS `work_aliases` (migration 0025). Same reasoning applies twice
-- over: the data lives in code (`authors/named_passages.py`) keyed on
-- the natural key `(author, works.title)`, because `works.id` is a
-- surrogate reassigned by insertion order and reshuffled by `--reset`
-- (#193) — so nothing here is hand-curated into the DB, and there is
-- nothing to preserve across a re-ingest, unlike the term glossary
-- (#192). Re-materialized on every `minerva index`; ON DELETE CASCADE
-- for the same reason `work_aliases` has it.
--
-- `section_start`/`section_end` are TEXT, not offsets: they hold a
-- locator in whatever scheme the work's own tradition uses (Stephanus
-- for Plato, Bekker for Aristotle), not a byte or character position,
-- and are nullable because not every label has one yet (a label can be
-- seeded for work-resolution before a section range has been measured
-- against the corpus's own chunking — see #182's own "Unmeasured" note
-- on Hegel's "master and slave"). Deliberately NOT consulted by the
-- retrieval filter (#182 Phase 0's measurement): resolving the WORK is
-- necessary and sufficient for the two verified instances, and the
-- range is for citation and display once something consumes it.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS named_passages (
    work_id        INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    label          TEXT NOT NULL,
    section_start  TEXT,
    section_end    TEXT,
    tradition      TEXT NOT NULL,
    PRIMARY KEY (work_id, label)
);

-- Detection scans labels by name across an author or the whole index,
-- same access pattern as `work_aliases_by_alias`.
CREATE INDEX IF NOT EXISTS named_passages_by_label ON named_passages(label);
