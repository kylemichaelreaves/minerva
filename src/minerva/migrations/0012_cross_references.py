"""0012_cross_references.py — add the cross-reference layer schema.

Two new tables:

* ``reference_targets`` — canonical "thing being referenced". One row
  per (canonical_author, canonical_work) pair. May or may not be in
  the local corpus: in-corpus targets carry ``in_corpus_work_id``
  pointing at ``works.id``; out-of-corpus targets (Cicero, Plotinus,
  Vergil, Boethius, Avicenna, Averroes, Maimonides, Ambrose,
  Porphyry) have ``in_corpus_work_id = NULL`` and are seeded by this
  migration.

* ``cross_references`` — directed source→target edges, anchored to a
  ``source_chunk_id`` (often with span offsets) and resolving to a
  ``target_id`` row in ``reference_targets`` (and optionally a
  specific ``target_chunk_id`` when the target is in-corpus). Carries
  ``reference_type`` (cites / quotes / paraphrases / alludes /
  comments_on / translates / disputes / corrects), ``confidence``,
  and ``source_method`` (manual / rule_strong / rule_weak / rule+embed
  / rule+embed+llm / embed_only). The shadow address (edition_id,
  sort_key, source_form_snapshot, instance_index) mirrors
  ``term_occurrences`` so re-ingest preserves curator work — see
  [[sqlite_migration_pragma_dance]] for the rationale.

Phase 1 ships this schema with manual curation only. The auto-detection
methods (rule_*, embed_*, llm_*) are not used until Phase 2 lights up
``src/minerva/refs/rules/``.

Seed data:

* **In-corpus targets are NOT seeded by this migration.** Earlier
  drafts auto-seeded from the ``works`` table, but ``insert_chunks``
  (the ``minerva index`` write path) does a wholesale DELETE of
  ``works`` / ``editions`` / ``translations`` / ``chunks`` before
  re-inserting, which reassigns every ``works.id``. In-corpus targets
  are instead created lazily by :func:`refs.schema.ensure_target`
  (which auto-links to a ``works`` row by matching author + title) the
  first time a curator or detection rule references the work.

  ⚠ This paragraph used to say the ``ON DELETE SET NULL`` cascade on
  ``in_corpus_work_id`` "strips the link ... on the very next index
  run", i.e. that the wipe degrades safely to NULL. **It does not
  fire.** ``insert_chunks`` runs the whole delete/re-insert block
  inside ``foreign_keys_off_for_transaction``, so no cascade executes
  and the stale integer survives, now pointing at whichever work
  inherited that id. That left 104 of 160 targets (65%) aimed at an
  unrelated work, 47 at a different author's, and mis-scoped
  embed-verify Pass A into binding Aquinas's Psalm quotations to Ezra
  (issue #273). ``store.chunks._rebind_reference_targets`` now
  re-resolves the column explicitly after every ingest, and
  ``_assert_reference_targets_resolve`` fails the transaction if it
  ever drifts again. Do not rely on the cascade below.
* **Out-of-corpus authors**: nine canonical authors × their most-
  cited works, hand-listed below. The seed lets the curator attach
  references to these authors without typo drift on day one.

This migration is additive (no table rebuilds, no CHECK widening), so
it doesn't need the PRAGMA-dance pattern from 0009 / 0010 / 0011.
"""

from __future__ import annotations

import sqlite3


_REFERENCE_TARGETS = """
CREATE TABLE reference_targets (
    id                  INTEGER PRIMARY KEY,
    canonical_author    TEXT NOT NULL,
    canonical_work      TEXT NOT NULL,
    -- Locator system the target uses, when known. Loose — set per
    -- target by the curator or detection rule that creates the row;
    -- NULL means "we don't know / there isn't a canonical one".
    -- The same values the works.citation_system CHECK accepts plus
    -- 'bekker' / 'stephanus' for out-of-corpus targets that use those.
    citation_system     TEXT,
    -- Non-NULL when the target work is indexed locally — lets the
    -- ReferenceCard's "Open in reader →" affordance resolve.
    -- ON DELETE SET NULL is meant to preserve the reference_targets row
    -- if the works row goes away (e.g. corpus is rebuilt from a
    -- different ingest); the references attached to it still point at a
    -- stable canonical_author / canonical_work even when their preview
    -- link briefly breaks.
    -- ⚠ But this cascade does NOT fire on the path that matters:
    -- insert_chunks wipes works inside
    -- foreign_keys_off_for_transaction, so the id is left stale rather
    -- than NULL'd. store.chunks._rebind_reference_targets re-resolves
    -- it after every ingest instead. See the ⚠ note in the module
    -- docstring and issue #273.
    in_corpus_work_id   INTEGER REFERENCES works(id) ON DELETE SET NULL,
    notes               TEXT,
    UNIQUE (canonical_author, canonical_work)
);
"""

_CROSS_REFERENCES = """
CREATE TABLE cross_references (
    id                       INTEGER PRIMARY KEY,
    -- Source side: where the reference appears.
    source_chunk_id          TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    source_span_start        INTEGER,   -- nullable: whole-chunk references (structural commentary)
    source_span_end          INTEGER,
    source_form_snapshot     TEXT,      -- literal trigger phrase ("Philosophus", "ut Plato dicit")
    quoted_phrase            TEXT,      -- literal quoted text when the reference is a quotation
    -- Target side: what's being referenced.
    target_id                INTEGER NOT NULL REFERENCES reference_targets(id),
    target_chunk_id          TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
                                        -- non-NULL when target is a specific in-corpus chunk;
                                        -- NULL for work-or-section-level targets or out-of-corpus
    target_locator           TEXT,      -- canonical citation string ('Republic 514a', 'Met. Λ.7')
    target_locator_payload   TEXT,      -- JSON-as-TEXT; parsed via locations.py
    target_sort_key          TEXT,      -- via locations.format_sort_key for ordered lookups
    -- Reference semantics.
    reference_type           TEXT NOT NULL CHECK (reference_type IN
        ('cites', 'quotes', 'paraphrases', 'alludes',
         'comments_on', 'translates', 'disputes', 'corrects')),
    confidence               REAL NOT NULL DEFAULT 1.0
                             CHECK (confidence BETWEEN 0 AND 1),
    source_method            TEXT NOT NULL DEFAULT 'manual'
                             CHECK (source_method IN
        ('manual', 'rule_strong', 'rule_weak', 'rule+embed',
         'rule+embed+llm', 'embed_only')),
    curator_status           TEXT NOT NULL DEFAULT 'manual'
                             CHECK (curator_status IN
        ('auto', 'approved', 'rejected', 'manual')),
    curator_note             TEXT,
    -- Shadow address for re-ingest stability (mirrors term_occurrences;
    -- see migration 0005). At least one of source_edition_id /
    -- source_translation_id is expected to be non-NULL for any insert
    -- that wants the shadow-relink to survive a re-ingest; the
    -- UNIQUE constraint is keyed on edition_id since that's the
    -- physical anchor.
    source_edition_id        INTEGER REFERENCES editions(id) ON DELETE CASCADE,
    source_translation_id    INTEGER REFERENCES translations(id) ON DELETE CASCADE,
    source_sort_key          TEXT,
    source_instance_index    INTEGER CHECK (source_instance_index IS NULL OR source_instance_index >= 1),
    UNIQUE (source_edition_id, source_sort_key, source_form_snapshot, source_instance_index),
    CHECK (source_span_start IS NULL OR source_span_end IS NULL OR source_span_end > source_span_start)
);
"""

_INDEXES = [
    # Q1: "what does this chunk reference?" — the reader's per-line
    # gutter-marker lookup. Maps source_chunk_id → outgoing list.
    "CREATE INDEX xref_by_source_chunk ON cross_references(source_chunk_id);",
    # Q2: "what references this chunk?" — the incoming view; populates
    # the "Plato is referenced by …" panel and the reference-graph view.
    "CREATE INDEX xref_by_target_chunk ON cross_references(target_chunk_id);",
    # Q3: "every reference to (Plato, Republic)" — for aggregate views
    # and the by-author route.
    "CREATE INDEX xref_by_target_id ON cross_references(target_id);",
    # Q4: curator approve/reject queues, plus the reader's default
    # filter (status IN approved/manual/auto-with-high-confidence).
    "CREATE INDEX xref_by_status ON cross_references(curator_status);",
    # Q5: shadow-address relink path during re-ingest. Logically
    # covered by the UNIQUE constraint; named explicitly so the
    # relink query plan is stable.
    "CREATE INDEX xref_by_shadow "
    "ON cross_references(source_edition_id, source_sort_key, source_form_snapshot);",
]


# Out-of-corpus canonical authors + their most-referenced works.
# Curator can add more via `minerva refs add` (auto-creates the row
# on first use) — this seed exists so the obvious targets are
# available without typo drift on day one. Each row: (author, work,
# citation_system, notes).
_OUT_OF_CORPUS_SEED: list[tuple[str, str, str | None, str | None]] = [
    # Cicero — Augustine's main classical interlocutor. Hortensius is
    # famously the spark of Augustine's philosophical conversion in
    # Conf. III.4.7; the dialogue itself is lost.
    ("Cicero", "Hortensius", None, "Lost dialogue; Augustine Conf. III.4 cites the call to philosophy."),
    ("Cicero", "De republica", None, None),
    ("Cicero", "Tusculanae disputationes", None, None),
    ("Cicero", "De finibus bonorum et malorum", None, None),
    ("Cicero", "De natura deorum", None, None),
    # Plotinus — Augustine via Porphyry's Latin abridgment. Cited
    # heavily in Conf. VII.
    ("Plotinus", "Enneads", None, "Augustine reads via Porphyry / Marius Victorinus."),
    # Vergil — pervasive Augustinian quotation.
    ("Vergil", "Aeneid", None, None),
    ("Vergil", "Eclogae", None, None),
    ("Vergil", "Georgica", None, None),
    # Boethius — bridges late-antiquity philosophy into the
    # scholastic vocabulary; Aquinas cites his Aristotle commentaries.
    ("Boethius", "Consolatio Philosophiae", None, None),
    ("Boethius", "In Categorias Aristotelis", None, "Aquinas's source for logical apparatus."),
    ("Boethius", "De Trinitate", None, "Distinct from Augustine's De Trinitate; the Aquinas commentary is on this work."),
    # Avicenna (Ibn Sīnā) — Aquinas's primary Arabic interlocutor on
    # psychology and metaphysics.
    ("Avicenna", "Liber de anima", None, "Aquinas cites in De ente, Sentence-commentary, ST psychology."),
    ("Avicenna", "Metaphysica", None, "= the Latin translation of his Kitab al-Shifa metaphysics."),
    # Averroes (Ibn Rushd) — "the Commentator" in Aquinas; cited as
    # often as the Philosopher in some treatises.
    ("Averroes", "Commentarium magnum in De anima", None, "Aquinas's foil in De unitate intellectus."),
    ("Averroes", "Commentarium magnum in Metaphysicam", None, None),
    # Maimonides (Moses ben Maimon) — Aquinas reads in Latin trans.
    ("Maimonides", "Dux perplexorum", None, "= Guide for the Perplexed; Aquinas cites in the Sentences and ST."),
    # Ambrose — Augustine's Milan-era teacher; cited throughout Conf.
    ("Ambrose", "Hexaemeron", None, None),
    ("Ambrose", "De officiis ministrorum", None, None),
    # Porphyry — Plotinus's editor + Augustine's Isagoge route to
    # neoplatonism + the standard logic primer Aquinas inherits via
    # Boethius's translation.
    ("Porphyry", "Isagoge", None, "Standard logic primer; lemma source for Boethius's Aristotle commentary."),
]


def apply(conn: sqlite3.Connection) -> None:
    # Use `execute` (not `executescript`) for the CREATE TABLEs so the
    # migration runner's implicit transaction stays open — same
    # convention as 0009 / 0010 / 0011.
    conn.execute(_REFERENCE_TARGETS)
    conn.execute(_CROSS_REFERENCES)
    for stmt in _INDEXES:
        conn.execute(stmt)

    # DO NOT auto-seed in-corpus targets from `works`. The DELETE that
    # `insert_chunks` does on every `minerva index` run reassigns every
    # `works.id`, so a seeded `in_corpus_work_id` goes stale immediately
    # (it does NOT cascade to NULL — see the ⚠ note in the module
    # docstring). The curator-driven `refs.schema.ensure_target` (auto-links to a
    # works row on first reference) is the correct path.

    # Seed out-of-corpus canonical targets.
    conn.executemany(
        "INSERT INTO reference_targets "
        "(canonical_author, canonical_work, citation_system, in_corpus_work_id, notes) "
        "VALUES (?, ?, ?, NULL, ?)",
        _OUT_OF_CORPUS_SEED,
    )

    conn.commit()
