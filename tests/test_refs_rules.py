"""Unit tests for `minerva.refs.rules` — the rule classes that fire
per chunk + the `apply_rules_to_chunk` dispatcher + `insert_candidate`
dedup/manual-protection.

Most rule tests construct `ChunkInfo` directly and assert on the
generator output without touching the database. `insert_candidate`
needs a real conn; those tests reuse the `populated_db` fixture.
"""

from __future__ import annotations

import sqlite3

from minerva.refs import schema as refs_schema
from minerva.refs.rules import (
    AuthorMentionRule,
    Candidate,
    ChunkInfo,
    StrongMentionRule,
    apply_rules_to_chunk,
    insert_candidate,
)
from minerva.refs.rules.aquinas import StructuralCommentaryRule
from minerva.refs.rules.scripture_cite import (
    FormulaicQuoteRule,
    ScriptureCiteRule,
)

# ════════════════════════════════════════════════════════════════════
# AuthorMentionRule / StrongMentionRule
# ════════════════════════════════════════════════════════════════════


def _chunk(
    text: str,
    *,
    chunk_id: str = "c1",
    author: str = "Aquinas",
    work: str = "Summa Theologica",
    lang: str = "lat",
    section: str | None = "Ia q.1 a.1",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id=chunk_id,
        author=author,
        work=work,
        lang=lang,
        section=section,
        text=text,
    )


class TestAuthorMentionRule:
    # Rule names are unique per test — the rules module caches compiled
    # patterns by `name`, so reusing a name across tests with different
    # `forms` would leak the first test's pattern into later ones.

    def test_emits_candidate_per_match_with_span(self) -> None:
        rule = AuthorMentionRule(
            name="t_author_mention_span",
            target_author="Plato",
            forms=("Platonis", "Platone"),
        )
        chunk = _chunk("ut dicit Platonis dialogus, sed apud Platone scribitur ...")
        cands = list(rule.scan(chunk))
        assert len(cands) == 2
        assert cands[0].source_form_snapshot == "Platonis"
        assert cands[0].source_span_start is not None
        assert chunk.text[cands[0].source_span_start : cands[0].source_span_end] == "Platonis"
        assert cands[1].source_form_snapshot == "Platone"

    def test_word_boundary_rejects_substrings(self) -> None:
        # "Philosophusculus" must not match "Philosophus".
        rule = AuthorMentionRule(
            name="t_author_mention_boundary",
            target_author="Aristotle",
            forms=("Philosophus",),
        )
        assert list(rule.scan(_chunk("Philosophusculus stat in agro"))) == []

    def test_language_filter_skips_other_langs(self) -> None:
        rule = AuthorMentionRule(
            name="t_author_mention_lang",
            target_author="Plato",
            forms=("Plato",),
            langs=("lat",),
        )
        assert list(rule.scan(_chunk("Plato writes", lang="eng"))) == []
        assert len(list(rule.scan(_chunk("Plato scripsit", lang="lat")))) == 1

    def test_self_reference_skipped(self) -> None:
        # Author A's rule pointing at A itself should silently skip —
        # we don't want "Augustine quotes Augustine" surface forms.
        rule = AuthorMentionRule(
            name="t_author_mention_self",
            target_author="Augustine",
            forms=("Augustinus",),
        )
        assert list(rule.scan(_chunk("ut dicit Augustinus", author="Augustine"))) == []


class TestStrongMentionRule:
    def test_inherits_higher_confidence_and_method(self) -> None:
        rule = StrongMentionRule(
            name="t_strong_mention_defaults",
            target_author="Aristotle",
            forms=("Philosophus",),
        )
        cands = list(rule.scan(_chunk("ut dicit Philosophus in libro 2")))
        assert len(cands) == 1
        assert cands[0].source_method == "rule_strong"
        assert cands[0].confidence == 0.92


# ════════════════════════════════════════════════════════════════════
# ScriptureCiteRule
# ════════════════════════════════════════════════════════════════════


class TestScriptureCiteRule:
    def test_book_chapter_verse_emits_full_locator(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("sicut dicitur Matth. 5-48: estote ergo")))
        assert len(cands) == 1
        c = cands[0]
        assert c.target_author == "Vulgate"
        assert c.target_work == "Matthew"
        assert c.target_locator == "Matt 5:48"
        assert c.confidence == 0.90
        assert c.source_method == "rule_strong"

    def test_chapter_only_lower_confidence(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("vide Matth. 5 ubi Christus loquitur")))
        assert len(cands) == 1
        c = cands[0]
        assert c.target_locator == "Matt 5"
        assert c.confidence == 0.75

    def test_ordinal_prefix_disambiguates_numbered_book(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("ut habetur I Cor. 13-4: caritas patiens est")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        # Ordinal prefix removes the ambiguity penalty.
        assert cands[0].confidence == 0.90

    def test_bare_ambiguous_abbrev_low_confidence(self) -> None:
        rule = ScriptureCiteRule()
        # "Cor." without I/II is ambiguous; rule fires at the low-conf band.
        cands = list(rule.scan(_chunk("vide Cor. 13-4: caritas patiens est")))
        assert len(cands) == 1
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_skips_non_latin_chunks(self) -> None:
        rule = ScriptureCiteRule()
        assert list(rule.scan(_chunk("Matth. 5-48", lang="eng"))) == []

    def test_vulgate_chunks_skipped_self_reference(self) -> None:
        rule = ScriptureCiteRule()
        # A Vulgate chunk containing a cite syntax should be ignored —
        # Genesis citing Genesis is not a useful cross-reference.
        assert (
            list(
                rule.scan(
                    _chunk("Matth. 5-48 et sequentia", author="Vulgate"),
                )
            )
            == []
        )


# ════════════════════════════════════════════════════════════════════
# FormulaicQuoteRule
# ════════════════════════════════════════════════════════════════════


class TestFormulaicQuoteRule:
    def test_psalm_introducer_captures_quoted_phrase(self) -> None:
        rule = FormulaicQuoteRule(
            name="t_formulaic_quote_psalm",
            target_author="Vulgate",
            target_work="Psalms",
            introducer_patterns=(r"in\s+Psalmo", r"Psalmista"),
        )
        text = (
            "ut dicit in Psalmo: tu autem domine in aeternum permanes. "
            "Et sequitur..."
        )
        cands = list(rule.scan(_chunk(text)))
        assert len(cands) == 1
        c = cands[0]
        assert c.target_work == "Psalms"
        assert c.target_locator is None  # embed-verify Pass A binds it
        assert c.reference_type == "quotes"
        assert c.quoted_phrase is not None
        assert "tu autem domine" in c.quoted_phrase

    def test_below_min_quote_length_rejected(self) -> None:
        # Quote shorter than 15 chars between colon and terminator
        # should not emit.
        rule = FormulaicQuoteRule(
            name="t_formulaic_quote_minlen",
            target_author="Vulgate",
            target_work="Psalms",
            introducer_patterns=(r"in\s+Psalmo",),
        )
        assert list(rule.scan(_chunk("in Psalmo: brevis."))) == []


# ════════════════════════════════════════════════════════════════════
# StructuralCommentaryRule (Aquinas)
# ════════════════════════════════════════════════════════════════════


class TestStructuralCommentaryRule:
    def test_commentary_chunk_emits_comments_on_with_roman_book(self) -> None:
        rule = StructuralCommentaryRule()
        cands = list(
            rule.scan(
                _chunk(
                    "Lectio incipit ...",
                    work="Sententia libri Ethicorum",
                    section="Sent. Ethic., lib. 3, lect. 14",
                )
            )
        )
        assert len(cands) == 1
        c = cands[0]
        assert c.target_author == "Aristotle"
        assert c.target_work == "Nicomachean Ethics"
        assert c.target_locator == "III"
        assert c.reference_type == "comments_on"
        assert c.source_method == "rule_strong"

    def test_prooemium_emits_work_level_with_no_locator(self) -> None:
        rule = StructuralCommentaryRule()
        cands = list(
            rule.scan(
                _chunk(
                    "Prooemium ...",
                    work="Sententia libri Metaphysicae",
                    section="Sent. Metaphys., pr.",
                )
            )
        )
        assert len(cands) == 1
        assert cands[0].target_locator is None

    def test_non_commentary_work_skipped(self) -> None:
        rule = StructuralCommentaryRule()
        assert (
            list(
                rule.scan(
                    _chunk("...", work="Summa Theologica", section="Ia q.1 a.1"),
                )
            )
            == []
        )


# ════════════════════════════════════════════════════════════════════
# apply_rules_to_chunk dispatch
# ════════════════════════════════════════════════════════════════════


class TestDispatch:
    def test_aquinas_chunk_routes_to_aquinas_module_rules(self) -> None:
        # "Philosophus" is one of Aquinas's strong rules; it should fire.
        cands = apply_rules_to_chunk(
            _chunk(
                "ut dicit Philosophus in II Ethicorum",
                author="Aquinas",
                lang="lat",
            )
        )
        # Either Philosophus rule alone fires, or it co-fires with the
        # "II Ethic." cite — we only care that at least one Aristotle
        # candidate emerges via the dispatch.
        aristotle_hits = [c for c in cands if c.target_author == "Aristotle"]
        assert aristotle_hits, "expected aquinas dispatch to fire on Philosophus"

    def test_unknown_author_returns_no_candidates(self) -> None:
        # No rule module for "Anonymous" — dispatch silently returns ().
        assert apply_rules_to_chunk(_chunk("...", author="Anonymous")) == []

    def test_multiword_author_dispatch_normalizes_spaces(self) -> None:
        # "Marcus Aurelius" must resolve to marcus_aurelius.py.
        # Without space→underscore normalization in the dispatcher
        # the import silently fails and zero candidates emerge —
        # the bug that left Marcus Aurelius with no outgoing xrefs
        # on the 2026-05-21 ingest round.
        cands = apply_rules_to_chunk(
            _chunk(
                "Παρὰ Ἐπικτήτου ἔμαθον...",
                author="Marcus Aurelius",
                lang="grc",
            )
        )
        assert any(c.target_author == "Epictetus" for c in cands), (
            "Marcus Aurelius dispatch must reach marcus_aurelius.py — "
            "regression guard for the space-vs-underscore module lookup."
        )


# ════════════════════════════════════════════════════════════════════
# insert_candidate — target resolution + dedup
# ════════════════════════════════════════════════════════════════════


def _make_candidate(**overrides: object) -> Candidate:
    base: dict[str, object] = {
        "source_chunk_id": "rep-509d",
        "source_span_start": 5,
        "source_span_end": 13,
        "source_form_snapshot": "divided",
        "target_author": "Aristotle",
        "target_work": "Nicomachean Ethics",
        "target_locator": None,
        "reference_type": "cites",
        "confidence": 0.7,
        "source_method": "rule_weak",
    }
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


class TestInsertCandidate:
    def test_insert_creates_row_and_resolves_target(
        self, populated_db: sqlite3.Connection
    ) -> None:
        new_id = insert_candidate(populated_db, _make_candidate())
        assert new_id is not None
        row = populated_db.execute(
            "SELECT source_chunk_id, target_id, source_method, curator_status "
            "FROM cross_references WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert row[0] == "rep-509d"
        assert row[2] == "rule_weak"
        assert row[3] == "auto"
        # Target resolution created a reference_targets row.
        target = refs_schema.find_target_by_id(populated_db, row[1])
        assert target is not None
        assert target.canonical_author == "Aristotle"

    def test_dedup_on_content_key_returns_none(
        self, populated_db: sqlite3.Connection
    ) -> None:
        cand = _make_candidate()
        first = insert_candidate(populated_db, cand)
        assert first is not None
        # Second insert with identical content key is a no-op.
        second = insert_candidate(populated_db, cand)
        assert second is None
        # Sanity: only one row in cross_references for this content key.
        count = populated_db.execute(
            "SELECT COUNT(*) FROM cross_references "
            "WHERE source_chunk_id = ? AND source_form_snapshot = ?",
            (cand.source_chunk_id, cand.source_form_snapshot),
        ).fetchone()[0]
        assert count == 1

    def test_manual_row_blocks_auto_with_different_form(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Pre-seed a manual row at this (source, target, type) site.
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            reference_type="cites",
            source_form_snapshot="Aristoteles",
            confidence=1.0,
            source_method="manual",
            curator_status="manual",
        )
        populated_db.commit()

        # Even though the auto candidate has a different surface form
        # ("Philosophus" vs the manual row's "Aristoteles"), the
        # manual-protection clause should keep it from being written.
        auto = _make_candidate(
            source_form_snapshot="Philosophus",
            source_method="rule_strong",
            confidence=0.95,
        )
        assert insert_candidate(populated_db, auto) is None

    def test_manual_protection_can_be_disabled(
        self, populated_db: sqlite3.Connection
    ) -> None:
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            reference_type="cites",
            source_form_snapshot="Aristoteles",
            confidence=1.0,
            source_method="manual",
            curator_status="manual",
        )
        populated_db.commit()

        auto = _make_candidate(source_form_snapshot="Philosophus")
        new_id = insert_candidate(populated_db, auto, skip_if_manual_exists=False)
        assert new_id is not None
