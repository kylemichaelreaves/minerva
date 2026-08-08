"""Lexical binding of a quoted phrase to the verse it quotes (issue #269).

The cases here are the real ones from the live corpus: Aquinas's and
Augustine's formulaic Psalm quotations, and the Clementine Vulgate text
they were bound against.
"""

from __future__ import annotations

from minerva.refs.quote_match import (
    all_lexical_matches,
    best_lexical_match,
    normalize_latin,
)

# Verbatim from data/index.sqlite — Vulgate / Psalms chunks.
PS_7_10 = "Consumetur nequitia peccatorum, et diriges justum, scrutans corda et renes, Deus."
PS_33_9 = "Gustate et videte quoniam suavis est Dominus ; beatus vir qui sperat in eo."
PS_83_3 = (
    "Concupiscit, et deficit anima mea in atria Domini ; "
    "cor meum et caro mea exsultaverunt in Deum vivum."
)
PS_90_11 = "Quoniam angelis suis mandavit de te, ut custodiant te in omnibus viis tuis."
PS_103_24 = (
    "Quam magnificata sunt opera tua, Domine ! omnia in sapientia fecisti ; "
    "impleta est terra possessione tua."
)
PS_135_7 = "Qui fecit luminaria magna : quoniam in æternum misericordia ejus."
PS_135_18 = "et occidit reges fortes : quoniam in æternum misericordia ejus."

PSALTER = [
    ("ps-7-10", PS_7_10),
    ("ps-33-9", PS_33_9),
    ("ps-83-3", PS_83_3),
    ("ps-90-11", PS_90_11),
    ("ps-103-24", PS_103_24),
    ("ps-135-7", PS_135_7),
    ("ps-135-18", PS_135_18),
]

# The genuine ambiguity from #276: the two idol-polemic Psalms share the
# clause verbatim, so a string match cannot say which one was quoted.
PS_113_12 = (
    "Simulacra gentium argentum et aurum, opera manuum hominum. "
    "Os habent, et non loquentur ; oculos habent, et non videbunt."
)
PS_134_15 = (
    "Simulacra gentium argentum et aurum, opera manuum hominum. "
    "Os habent, et non loquentur ; oculos habent, et non videbunt."
)
IDOL_PSALMS = [("ps-113-12", PS_113_12), ("ps-134-15", PS_134_15)]


class TestNormalizeLatin:
    def test_expands_ligatures_and_strips_diacritics(self):
        assert normalize_latin("æternum") == "aeternvm"
        assert normalize_latin("præcinxit") == "praecinxit"
        assert normalize_latin("Œcumenicus") == "oecvmenicvs"

    def test_folds_u_v_and_i_j(self):
        # The whole point: editions disagree and both spellings must
        # compare equal.
        assert normalize_latin("uidete") == normalize_latin("videte")
        assert normalize_latin("iustus") == normalize_latin("justus")

    def test_drops_case_and_punctuation(self):
        assert normalize_latin("Gustate, et VIDETE ;") == "gvstate et videte"

    def test_is_idempotent(self):
        once = normalize_latin(PS_135_7)
        assert normalize_latin(once) == once


class TestBestLexicalMatch:
    def test_binds_the_verse_that_contains_the_quote(self):
        """The headline case from #269 — cosine sent this to Ps 135:7."""

        m = best_lexical_match("omnia in sapientia fecisti", PSALTER)
        assert m is not None
        assert m.chunk_id == "ps-103-24"
        assert m.exact

    def test_litany_psalm_does_not_win_by_attraction(self):
        """Ps 135 is the cosine attractor; lexically it must lose."""

        m = best_lexical_match("scrutans corda et renes Deus", PSALTER)
        assert m is not None
        assert m.chunk_id == "ps-7-10"  # cosine picked ps-135-18

    def test_tolerates_a_one_letter_edition_variant(self):
        """Aquinas writes 'exultaverunt', the Clementine 'exsultaverunt'.

        One differing token splits the contiguous run, so this only binds
        via the near-total-coverage path.
        """

        m = best_lexical_match(
            "cor meum et caro mea exultaverunt in Deum vivum", PSALTER
        )
        assert m is not None
        assert m.chunk_id == "ps-83-3"
        assert not m.exact
        assert m.coverage >= 0.8

    def test_tolerates_a_reordered_tail(self):
        """'quo nos fecit' against the Vulgate's 'qui fecit nos'."""

        m = best_lexical_match(
            "Quoniam angelis suis mandavit de te, ut custodiant te", PSALTER
        )
        assert m is not None
        assert m.chunk_id == "ps-90-11"

    def test_refuses_when_the_wording_genuinely_differs(self):
        """'quam dulcis est' vs the Vulgate's 'quoniam suavis est' is a
        different Psalter recension, not a spelling variant. Binding it
        would be a guess, and #269's whole point is that an unresolved
        target beats a confidently wrong one."""

        m = best_lexical_match(
            "Gustate et uidete quam dulcis est Dominus", PSALTER
        )
        assert m is None

    def test_refuses_a_phrase_absent_from_every_candidate(self):
        assert best_lexical_match("de rerum natura lucretius", PSALTER) is None

    def test_short_common_formula_does_not_bind(self):
        """'in aeternum' appears in both litany verses and identifies
        neither; too short to clear the anchor bar."""

        assert best_lexical_match("in æternum", PSALTER) is None

    def test_empty_phrase_returns_none(self):
        assert best_lexical_match("", PSALTER) is None
        assert best_lexical_match("   ;;;   ", PSALTER) is None

    def test_skips_candidates_with_empty_text(self):
        m = best_lexical_match(
            "omnia in sapientia fecisti",
            [("blank", "   "), ("real", PS_103_24)],
        )
        assert m is not None
        assert m.chunk_id == "real"

    def test_exact_match_beats_a_partial_one(self):
        """Both contain the phrase's words; only one contains the phrase."""

        m = best_lexical_match(
            "omnia in sapientia fecisti",
            [
                ("partial", "omnia quaecumque in sapientia sua fecisti opera"),
                ("exact", PS_103_24),
            ],
        )
        assert m is not None
        assert m.chunk_id == "exact"
        assert m.exact

    def test_ties_break_on_lowest_chunk_id_for_reproducibility(self):
        """Two identical verses must bind the same way on every run, or
        re-runs grow parallel rows through insert_candidate's dedup key."""

        dupes = [("zzz", PS_103_24), ("aaa", PS_103_24)]
        assert best_lexical_match("omnia in sapientia fecisti", dupes).chunk_id == "aaa"
        # Order of the candidate iterable must not matter.
        assert best_lexical_match(
            "omnia in sapientia fecisti", list(reversed(dupes))
        ).chunk_id == "aaa"

    def test_returns_only_the_winner_when_the_match_is_unique(self):
        assert [m.chunk_id for m in all_lexical_matches(
            "omnia in sapientia fecisti", PSALTER
        )] == ["ps-103-24"]

    def test_returns_every_candidate_tied_at_the_winning_strength(self):
        """#276: the quotation really does occur in two verses, so the
        caller must see both rather than a coin flip."""

        tied = all_lexical_matches(
            "simulacra gentium argentum et aurum, opera manuum hominum",
            IDOL_PSALMS,
        )
        assert [m.chunk_id for m in tied] == ["ps-113-12", "ps-134-15"]
        assert all(m.exact for m in tied)

    def test_ties_are_ordered_by_chunk_id_whatever_the_input_order(self):
        """The caller's fallback tie-break is "take the first", so the
        order has to be stable independent of candidate iteration."""

        tied = all_lexical_matches(
            "simulacra gentium argentum et aurum, opera manuum hominum",
            list(reversed(IDOL_PSALMS)),
        )
        assert [m.chunk_id for m in tied] == ["ps-113-12", "ps-134-15"]

    def test_a_weaker_match_is_not_reported_as_tied(self):
        """Only equally-strong candidates tie. A verse that clears the
        bar on a spelling variant is a worse answer, not an alternative
        — so it must be dropped, not offered to the adjudicator."""

        # Same clause, one word in a different orthography: clears the
        # bar by coverage but is not a verbatim containment. Listed last
        # so it is compared against an already-established exact winner.
        variant = (
            "Simulachra gentium argentum et aurum, opera manuum hominum."
        )
        mixed = [*IDOL_PSALMS, ("ps-999-9", variant)]
        tied = all_lexical_matches(
            "simulacra gentium argentum et aurum, opera manuum hominum", mixed
        )
        assert [m.chunk_id for m in tied] == ["ps-113-12", "ps-134-15"]
        # Sanity: on its own the variant does clear the bar, so it really
        # was dropped for being weaker rather than for not matching.
        assert all_lexical_matches(
            "simulacra gentium argentum et aurum, opera manuum hominum",
            [("ps-999-9", variant)],
        )[0].exact is False

    def test_returns_empty_when_nothing_clears_the_bar(self):
        assert all_lexical_matches("de rerum natura lucretius", PSALTER) == []

    def test_best_lexical_match_is_the_first_of_the_tied_set(self):
        """The single-winner API stays, so its callers and its stable
        lowest-chunk_id pick are unchanged."""

        phrase = "simulacra gentium argentum et aurum, opera manuum hominum"
        best = best_lexical_match(phrase, IDOL_PSALMS)
        assert best == all_lexical_matches(phrase, IDOL_PSALMS)[0]

    def test_thresholds_are_tunable(self):
        """The Ps 33:9 recension case binds if the caller insists on a
        looser bar — the defaults are a judgement, not a law."""

        phrase = "Gustate et uidete quam dulcis est Dominus"
        assert best_lexical_match(phrase, PSALTER) is None
        loose = best_lexical_match(
            phrase, PSALTER, min_token_run=3, min_coverage=0.5
        )
        assert loose is not None
        assert loose.chunk_id == "ps-33-9"
