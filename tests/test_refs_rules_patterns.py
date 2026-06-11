"""Tests for the `_compile_forms` pattern semantics + cache keying in
`minerva.refs.rules`.

Pins the 2026-06 audit fixes:

* alternation sorted longest-first so "Locke's" isn't shadowed by
  "Locke" (span snapshots used to under-cover);
* trailing ``(?!\\w)`` instead of ``\\b`` so apostrophe-final forms
  ("Sokrates'") can match before a space;
* pattern cache keyed on (forms, ignore_case) rather than rule name,
  so two rules sharing a name never share the wrong pattern.
"""

from __future__ import annotations

from minerva.refs.rules import AuthorMentionRule, ChunkInfo


def _chunk(text: str, *, lang: str = "eng") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="c1",
        author="Hegel",
        work="W",
        lang=lang,
        section=None,
        text=text,
    )


class TestCompileFormsSemantics:
    def test_longest_alternative_wins_span(self) -> None:
        # "Locke" listed BEFORE "Locke's" — the longer form must
        # still win so the span covers the whole surface form.
        rule = AuthorMentionRule(
            name="t_longest_wins",
            target_author="Locke",
            forms=("Locke", "Locke's"),
        )
        text = "In Locke's Essay we read"
        cands = list(rule.scan(_chunk(text)))
        assert len(cands) == 1
        assert cands[0].source_form_snapshot == "Locke's"
        assert text[cands[0].source_span_start : cands[0].source_span_end] == "Locke's"

    def test_apostrophe_final_form_matches_before_space(self) -> None:
        # "Sokrates'" ends in a non-word char; the old trailing \b
        # could never match it before a space.
        rule = AuthorMentionRule(
            name="t_apostrophe_final",
            target_author="Socrates",
            forms=("Sokrates'",),
        )
        text = "in Sokrates' Worten liegt"
        cands = list(rule.scan(_chunk(text, lang="deu")))
        assert len(cands) == 1
        assert cands[0].source_form_snapshot == "Sokrates'"

    def test_no_mid_word_match(self) -> None:
        # Trailing (?!\w) must still reject in-word suffix runs —
        # "Philosophus" inside "Philosophusculus".
        rule = AuthorMentionRule(
            name="t_no_midword",
            target_author="Aristotle",
            forms=("Philosophus",),
        )
        assert list(rule.scan(_chunk("Philosophusculus stat in agro", lang="lat"))) == []
        # And no left-anchored mid-word match either.
        assert list(rule.scan(_chunk("Pseudophilosophus dicit", lang="lat"))) == []


class TestPatternCacheKeying:
    def test_same_name_different_forms_use_distinct_patterns(self) -> None:
        # Two rules with the SAME name but different forms used to
        # silently share whichever pattern compiled first.
        rule_a = AuthorMentionRule(
            name="t_shared_name",
            target_author="Plato",
            forms=("Plato",),
        )
        rule_b = AuthorMentionRule(
            name="t_shared_name",
            target_author="Aristotle",
            forms=("Aristoteles",),
        )
        # Compile A first, then B must still match its own forms…
        assert len(list(rule_a.scan(_chunk("Plato writes")))) == 1
        assert len(list(rule_b.scan(_chunk("Aristoteles writes")))) == 1
        # …and must NOT match A's forms.
        assert list(rule_b.scan(_chunk("Plato writes"))) == []

    def test_ignore_case_part_of_cache_key(self) -> None:
        sensitive = AuthorMentionRule(
            name="t_case_key",
            target_author="Plato",
            forms=("Plato",),
        )
        insensitive = AuthorMentionRule(
            name="t_case_key",
            target_author="Plato",
            forms=("Plato",),
            ignore_case=True,
        )
        assert list(sensitive.scan(_chunk("plato writes"))) == []
        assert len(list(insensitive.scan(_chunk("plato writes")))) == 1
        # The case-sensitive rule must still be case-sensitive after
        # the insensitive twin compiled.
        assert list(sensitive.scan(_chunk("plato writes"))) == []
