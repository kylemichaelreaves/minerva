-- 0024_chunk_syntax.sql
-- ════════════════════════════════════════════════════════════════════
-- Dependency-syntax storage for the Reader's close-reading overlay.
-- See docs/syntax-annotation-plan.md.
--
-- `chunk_lemmas` already answers "what is this word" — 26M rows with
-- surface form, lemma, UPOS and raw UD feats. Nothing answers "how do
-- these words hang together": there is no head, no deprel, and no
-- sentence boundary anywhere in the schema. The dependency step is
-- switched off in every pipeline (`disable=["parser"]`, and Stanza at
-- `tokenize,pos,lemma`) for throughput.
--
-- WHY A SEPARATE TABLE, not columns on chunk_lemmas
-- --------------------------------------------------------------------
-- chunk_lemmas was tokenized by spaCy. Syntax is parsed by Stanza,
-- which tokenizes differently (a 284-char Nietzsche chunk: spaCy 45
-- tokens, Stanza 53) and segments sentences that spaCy never marked.
-- Bolting head/deprel onto chunk_lemmas would force one tokenization
-- to win, and chunk_lemmas' (chunk_id, token_index) is load-bearing
-- for term_occurrences, the glossary importer and the concordance.
-- A separate table keeps both layers intact; they align through the
-- character offsets both of them already carry into chunks.text.
--
-- FILLED LAZILY. There is no bulk backfill here. A chunk is parsed the
-- first time someone opens the overlay on it (or via
-- `minerva syntax parse`), and cached thereafter. Parsing all 26M
-- tokens up front would cost an hour to produce trees for text nobody
-- has read.
-- ════════════════════════════════════════════════════════════════════

-- The machine parse. Immutable once written: corrections are a
-- separate append-only log replayed over this, so "what did the parser
-- actually say" stays answerable forever.
CREATE TABLE IF NOT EXISTS chunk_syntax (
    chunk_id      TEXT    NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    -- 0-based sentence within the chunk. A chunk is a paragraph and
    -- routinely holds several sentences; CoNLL-U ids restart at 1 in
    -- each, so the sentence ordinal is part of a token's identity.
    sent_ord      INTEGER NOT NULL,
    -- 1-based within the sentence, as in the CoNLL-U ID column.
    tok_id        INTEGER NOT NULL,
    form          TEXT    NOT NULL,
    lemma         TEXT,
    upos          TEXT,
    xpos          TEXT,
    -- Raw UD feature string, `Case=Nom|Gender=Masc|Number=Sing`. Same
    -- convention as chunk_lemmas.feats (migration 0008) so the reader's
    -- existing morph formatter can render either.
    feats         TEXT,
    misc          TEXT,
    -- 0 = attaches to the sentence root. NULL is CoNLL-U's `_`,
    -- genuinely unparsed — collapsing the two would invent a second
    -- root and trip the single-root invariant the editor enforces.
    head          INTEGER,
    deprel        TEXT,
    -- Character offsets into chunks.text, same convention as
    -- chunk_lemmas.surface_start/end. This is the only thing tying the
    -- Stanza token layer back to the words the Reader renders.
    surface_start INTEGER NOT NULL,
    surface_end   INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, sent_ord, tok_id),
    CHECK (surface_end >= surface_start)
);

-- Which parser produced a chunk's trees, and when. Separate from
-- chunk_syntax so "parsed and genuinely empty" is distinguishable from
-- "never parsed" — an empty chunk would otherwise look uncached
-- forever and be re-parsed on every open.
CREATE TABLE IF NOT EXISTS chunk_syntax_state (
    chunk_id  TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    parser    TEXT NOT NULL,   -- e.g. 'stanza-de-1.13.0'
    parsed_at REAL NOT NULL
);

-- Hand corrections, append-only. Replayed in id order over the pristine
-- parse to materialise the current tree.
--
-- DELIBERATELY NO FOREIGN KEY. Every other derived table cascades from
-- chunks, because everything else can be recomputed. These rows cannot:
-- they are human judgement about a sentence, and this repo has lost
-- annotation to re-ingest three times already (see docs/MEMORY.md, the
-- 0013 cascade relaxation, and the lemma/xref snapshot machinery in
-- store/preserved_state.py). A correction must survive `index --reset`
-- even when the chunk it refers to is rewritten; a correction pointing
-- at a chunk_id that no longer exists is inert, which is the right
-- failure mode. store/preserved_state.py snapshots this table.
CREATE TABLE IF NOT EXISTS chunk_syntax_corrections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id   TEXT    NOT NULL,
    sent_ord   INTEGER NOT NULL,
    tok_id     INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('head', 'deprel')),
    -- The value at the time of the edit, for provenance and for
    -- detecting that the underlying parse moved beneath a patch.
    -- Stored as TEXT for both kinds; 'head' round-trips through int().
    from_val   TEXT,
    to_val     TEXT    NOT NULL,
    created_at REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_syntax_by_chunk
    ON chunk_syntax(chunk_id);

-- Replay reads a whole chunk's corrections in insertion order.
CREATE INDEX IF NOT EXISTS chunk_syntax_corrections_by_chunk
    ON chunk_syntax_corrections(chunk_id, id);
