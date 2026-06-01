-- 0001_term_glossary.sql
-- ════════════════════════════════════════════════════════════════════
-- Term-glossary schema: works · editions · translations · terms ·
-- term_relations · term_renderings · term_occurrences ·
-- occurrence_renderings.
--
-- Anchors `term_occurrences.source_chunk_id` and
-- `occurrence_renderings.translation_chunk_id` into the existing
-- `chunks` table by chunk_id (a content hash). Shadow-address columns
-- on `term_occurrences` make rows recoverable across re-ingests that
-- change chunk_ids.
--
-- FK enforcement: store.open_db sets `PRAGMA foreign_keys = ON` per
-- connection. With it off the REFERENCES clauses below are
-- documentation only; tests assert the pragma is active.
--
-- ════════════════════════════════════════════════════════════════════
-- DEFERRED: cross-edition reconciliation
-- ════════════════════════════════════════════════════════════════════
-- Today, term_occurrences anchors to a single edition_id. Curating
-- λόγος in Burnet's OCT and λόγος in Slings's OCT produces two rows
-- per scholarly site, one per edition. Q2 ("every occurrence in this
-- work") is filtered to the term's source_language; when a work has
-- exactly one edition in that language (the current state), Q2 is
-- unambiguous. When a work eventually has multiple source-language
-- editions, we need a tie-breaker. The deferred work, in order of
-- escalating cost:
--
--   1. Add an `editions.is_canonical BOOLEAN DEFAULT FALSE` column,
--      enforce one canonical edition per (work_id, language), and
--      have Q2 default to the canonical edition with an explicit
--      opt-in for the others. Trivial migration; covers the typical
--      "we prefer Burnet, can fall back to Slings" workflow.
--
--   2. When editions actually disagree on text at a shared locator
--      (Stephanus 514a says λόγος in Burnet, λόγου in Slings),
--      record disagreements in an `edition_alignments` table keyed
--      on (work_id, location_sort_key, edition_a_id, edition_b_id)
--      with a `divergence_kind` enum. UI surfaces the divergence
--      where the rendering pane currently shows a single rendering.
--
--   3. When an occurrence in edition A has no counterpart in edition
--      B (e.g., one edition deletes a passage Burnet keeps), the
--      alignment table carries NULLs in the appropriate side and the
--      UI grays out that translator's column for that row.
--
-- None of (1)–(3) require a destructive change to the schema below.
-- They are forward-additive migrations. Hold them for when there's
-- actually a second source-language edition of a work in the corpus.
-- ════════════════════════════════════════════════════════════════════


-- ════════════════════════════════════════════════════════════════════
-- Works · editions · translations
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS works (
    id                  INTEGER PRIMARY KEY,
    author              TEXT NOT NULL,
    title               TEXT NOT NULL,
    -- ISO 639-3. Legacy chunks.lang uses 2-letter codes; the boundary
    -- adapter in minerva.language_codes converts on the way in.
    original_language   TEXT NOT NULL CHECK (original_language IN
        ('grc', 'fra', 'deu', 'eng')),
    citation_system     TEXT NOT NULL CHECK (citation_system IN
        ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph')),
    UNIQUE (author, title)
);

CREATE TABLE IF NOT EXISTS editions (
    id        INTEGER PRIMARY KEY,
    work_id   INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    language  TEXT NOT NULL CHECK (language IN ('grc', 'fra', 'deu', 'eng')),
    year      INTEGER,
    notes     TEXT,
    UNIQUE (work_id, name, year)
);

CREATE TABLE IF NOT EXISTS translations (
    id                    INTEGER PRIMARY KEY,
    work_id               INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    based_on_edition_id   INTEGER REFERENCES editions(id) ON DELETE SET NULL,
    translator_name       TEXT NOT NULL,
    year                  INTEGER,
    language              TEXT NOT NULL CHECK (language IN ('grc', 'fra', 'deu', 'eng')),
    edition_notes         TEXT,
    UNIQUE (work_id, translator_name, year, language)
);

-- ════════════════════════════════════════════════════════════════════
-- Terms · relations · per-translator default renderings
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS terms (
    id                INTEGER PRIMARY KEY,
    source_form       TEXT NOT NULL,
    source_language   TEXT NOT NULL CHECK (source_language IN
        ('grc', 'fra', 'deu', 'eng')),
    transliteration   TEXT,
    lemma             TEXT,
    short_gloss       TEXT NOT NULL,
    long_description  TEXT NOT NULL,
    UNIQUE (source_form, source_language)
);

CREATE TABLE IF NOT EXISTS term_relations (
    term_id          INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    related_term_id  INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    relation_kind    TEXT,
    notes            TEXT,
    PRIMARY KEY (term_id, related_term_id),
    CHECK (term_id <> related_term_id)
);

CREATE TABLE IF NOT EXISTS term_renderings (
    id                INTEGER PRIMARY KEY,
    term_id           INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    translation_id    INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
    default_rendering TEXT NOT NULL,
    translator_note   TEXT,
    UNIQUE (term_id, translation_id)
);

-- ════════════════════════════════════════════════════════════════════
-- Term occurrences
--
-- Anchored to a specific edition (the physical text the spans live
-- in). `work_id` is denormalized from editions.work_id so Q2-style
-- queries don't have to join through editions just to filter by work,
-- and so the eventual cross-edition relink path has a stable work-
-- level address regardless of which edition rows survive.
--
-- `tradition` (nullable) tags an occurrence with the interpretive
-- tradition it belongs to ("platonic", "stoic", "johannine", …) so
-- one Term row can house its full lexical family while each
-- occurrence carries its semantic context. Free-text today, promoted
-- to a controlled vocabulary later. See the design discussion in
-- docs/term-identity.md.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS term_occurrences (
    id                     INTEGER PRIMARY KEY,
    term_id                INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    edition_id             INTEGER NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
    -- Denormalized: must equal (SELECT work_id FROM editions WHERE id = edition_id).
    -- Cheap insurance; lets shadow-address lookups go straight to work-
    -- level scoping when needed.
    work_id                INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    -- Physical anchor — chunks.chunk_id (a content hash). May be
    -- repointed by the relink path on re-ingest.
    source_chunk_id        TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    source_start           INTEGER NOT NULL,
    source_end             INTEGER NOT NULL,
    context_snippet        TEXT NOT NULL,
    -- Structured locator. `location_sort_key` is computed by
    -- minerva.locations.format_sort_key — version tracked by
    -- SORT_KEY_VERSION in that module. A bump is an explicit reindex
    -- event for this column.
    location_kind          TEXT NOT NULL CHECK (location_kind IN
        ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph')),
    location_payload       TEXT NOT NULL,   -- JSON-as-TEXT
    location_sort_key      TEXT NOT NULL,
    -- Interpretive tradition for this site. Free-text until the
    -- vocabulary firms up.
    tradition              TEXT,
    -- Shadow address (work_id, location_sort_key, source_form_snapshot,
    -- instance_index). The UNIQUE constraint is keyed on edition_id
    -- — the physical unique site is per-edition. work_id is the
    -- broader scope used by the relink path when an edition row is
    -- rebuilt.
    source_form_snapshot   TEXT NOT NULL,
    instance_index         INTEGER NOT NULL CHECK (instance_index >= 1),
    CHECK (source_end > source_start),
    UNIQUE (edition_id, location_sort_key, source_form_snapshot, instance_index)
);

CREATE TABLE IF NOT EXISTS occurrence_renderings (
    id                       INTEGER PRIMARY KEY,
    occurrence_id            INTEGER NOT NULL REFERENCES term_occurrences(id) ON DELETE CASCADE,
    translation_id           INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
    translation_chunk_id     TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    translation_start        INTEGER NOT NULL,
    translation_end          INTEGER NOT NULL,
    rendered_text            TEXT NOT NULL,
    notes                    TEXT,
    UNIQUE (occurrence_id, translation_id),
    CHECK (translation_end > translation_start)
);

-- ════════════════════════════════════════════════════════════════════
-- Indexes
-- ════════════════════════════════════════════════════════════════════

-- Q1: hover lookup
CREATE INDEX IF NOT EXISTS term_occ_by_chunk
    ON term_occurrences(source_chunk_id);

-- Q2: "every occurrence of term T in work W, in canonical order".
-- Goes through work_id (denormalized) — see schema notes.
CREATE INDEX IF NOT EXISTS term_occ_by_work_term
    ON term_occurrences(work_id, term_id, location_sort_key);

-- Per-edition variant of Q2 for the curator tool, which usually wants
-- to focus on the edition it's actively annotating.
CREATE INDEX IF NOT EXISTS term_occ_by_edition_term
    ON term_occurrences(edition_id, term_id, location_sort_key);

-- Shadow-address lookup during the re-ingest relink path. Logically
-- already covered by the UNIQUE constraint; named explicitly so the
-- relink query plan is stable.
CREATE INDEX IF NOT EXISTS term_occ_by_shadow
    ON term_occurrences(edition_id, location_sort_key, source_form_snapshot);

-- Rendering-side reads
CREATE INDEX IF NOT EXISTS term_render_by_translation
    ON term_renderings(translation_id);

CREATE INDEX IF NOT EXISTS occ_render_by_occ
    ON occurrence_renderings(occurrence_id);

CREATE INDEX IF NOT EXISTS occ_render_by_translation
    ON occurrence_renderings(translation_id);

CREATE INDEX IF NOT EXISTS occ_render_by_translation_chunk
    ON occurrence_renderings(translation_chunk_id);

-- Discovery
CREATE INDEX IF NOT EXISTS editions_by_work
    ON editions(work_id);

CREATE INDEX IF NOT EXISTS trans_by_work
    ON translations(work_id, language);

CREATE INDEX IF NOT EXISTS term_rel_reverse
    ON term_relations(related_term_id);
