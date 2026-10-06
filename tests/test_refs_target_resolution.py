"""Unit tests for how ``refs_schema.ensure_target`` resolves a
free-text ``(canonical_author, canonical_work)`` pair onto a ``works``
row.

The resolution was an exact string match on ``works.title``, which is
silent when it misses: the target is created with
``in_corpus_work_id = NULL`` and reads as out-of-corpus. Four of
migration 0012's ``_OUT_OF_CORPUS_SEED`` rows are held out of the
corpus that way by capitalization alone — ``'Tusculanae disputationes'``
against the in-corpus ``'Tusculanae Disputationes'`` differs by one
letter's case (#493, claim 3).

Normalizing is only safe because it is unambiguous over this corpus:
all 866 works have distinct normalized ``(author, title)`` keys. The
ambiguity test below pins the behaviour for a corpus where that stops
being true.
"""

from __future__ import annotations

import sqlite3

from minerva.refs import schema as refs_schema


class TestNormalizedWorkResolution:
    def test_exact_title_links_to_the_work(self, populated_db: sqlite3.Connection) -> None:
        expected = populated_db.execute(
            "SELECT id FROM works WHERE author = 'Aristotle' AND title = 'Nicomachean Ethics'"
        ).fetchone()[0]

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )

        assert target.in_corpus_work_id == expected

    def test_case_drifted_title_links_to_the_work(self, populated_db: sqlite3.Connection) -> None:
        """The live shape: ``De natura deorum`` against ``De Natura Deorum``."""

        expected = populated_db.execute(
            "SELECT id FROM works WHERE author = 'Aristotle' AND title = 'Nicomachean Ethics'"
        ).fetchone()[0]

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="nicomachean ethics",
        )

        assert target.in_corpus_work_id == expected

    def test_punctuation_and_accent_drift_links_to_the_work(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """``De republica`` reaches ``De Re Publica``: the normalized key
        drops spacing as well as case, and accents with it."""

        expected = populated_db.execute(
            "SELECT id FROM works WHERE author = 'Hegel' AND title = 'Phänomenologie des Geistes'"
        ).fetchone()[0]

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Hegel",
            canonical_work="Phanomenologie-des-Geistes",
        )

        assert target.in_corpus_work_id == expected

    def test_unknown_title_stays_out_of_corpus(self, populated_db: sqlite3.Connection) -> None:
        """Cicero is not in ``populated_db``; normalizing must not
        invent a link."""

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Cicero",
            canonical_work="De Officiis",
        )

        assert target.in_corpus_work_id is None

    def test_normalizing_does_not_cross_authors(self, populated_db: sqlite3.Connection) -> None:
        """A title that exists under a *different* author must not link."""

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Plato",
            canonical_work="nicomachean ethics",
        )

        assert target.in_corpus_work_id is None

    def test_ambiguous_normalized_title_stays_null(self, populated_db: sqlite3.Connection) -> None:
        """Two works whose titles normalize to the same key are not a
        link — picking either would be arbitrary. Leaving NULL keeps the
        target visibly unresolved, which is the same choice
        ``verify_quoted_references`` makes for an unlocatable phrase."""

        populated_db.execute(
            "INSERT INTO works (author, title, original_language, citation_system) "
            "VALUES ('Aristotle', 'NICOMACHEAN ETHICS', 'grc', 'bekker')"
        )
        populated_db.commit()

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="nicomachean ethics",
        )

        assert target.in_corpus_work_id is None

    def test_citation_system_is_inherited_on_a_normalized_match(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """The exact-match path inherits ``citation_system`` from the
        works row when the caller gives none; the normalized path must
        not quietly drop it."""

        expected = populated_db.execute(
            "SELECT citation_system FROM works "
            "WHERE author = 'Aristotle' AND title = 'Nicomachean Ethics'"
        ).fetchone()[0]

        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="nicomachean ethics",
        )

        assert target.citation_system == expected

    def test_caller_supplied_citation_system_still_wins(
        self, populated_db: sqlite3.Connection
    ) -> None:
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="nicomachean ethics",
            citation_system="paragraph",
        )

        assert target.citation_system == "paragraph"
