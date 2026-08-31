"""Labels scholarship gave a passage that its own text never uses.

"The divided line" never appears in the Politeia; Plato's nearest words
are 509d's "a line divided into two unequal sections", reversed. Because
the label shares no vocabulary with the passage it names, a query using
only the label competes as ordinary prose against the rest of the corpus
and the target never surfaces (#182). `detect_work` already resolves an
arbitrary name to a `work_id` when every significant token of that name
appears in the query — this file is the same mechanism's data, for names
that point at a *passage* rather than a *work*.

Why not `work_aliases` (migration 0025): an alias is another name FOR
the work — "Das Kapital" names all of Marx's Kapital, not one chapter of
it — and `work_aliases.py`'s own docstring rules out anything else.
"The divided line" is not a name for the Republic; it names 509d–511e of
it. Keyed the same way regardless — `(author, works.title)`, a natural
key, because `works.id` is a surrogate that `index --reset` reshuffles
(#193) — but stored separately (migration 0034) so the semantic
distinction survives contact with the schema.

Seeded narrowly. Only labels that were actually measured against the
live retrieval pipeline belong here — #182's own history is a caution:
three successive ad hoc measurements of this issue gave three different
answers before one finally ran the real `prepare_chat_turn` sequence.
"Master and slave" (Hegel) is deliberately NOT seeded: #182 could not
build a target set for it (the Phenomenology's `section` values are not
range-selectable), and a corpus-wide scan shows "master" and "slave"
co-occurring in Plato's *Nomoi* (26 chunks), Epictetus's *Discourses*
(20), Aristotle's *Politics* (18), Locke's *Second Treatise* (9) and
more, all discussing literal slavery rather than Hegel's dialectic.
Seeding it today would misattribute an unrelated question about
Aristotle or Locke to Hegel every time neither author is named — a
regression, not a fix. See #463 for what seeding it needs first: a
distinctiveness check before a *label* is seeded, not just before a
single common *word* is — `detect_work` already guards that narrower
case with `_COMMON_TITLE_TOKENS`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NamedPassage:
    label: str
    section_start: str | None
    section_end: str | None
    tradition: str


# (author, works.title) -> the passages that work's text is known by a
# name it never uses. One work may carry more than one.
NAMED_PASSAGES: dict[tuple[str, str], tuple[NamedPassage, ...]] = {
    # Measured #182: absent corpus-wide under every unscoped phrasing,
    # rank 3-6 once the work resolves — inside `_best_title_matches`'
    # reach because "divided" and "line" are neither of them stopwords
    # nor in `_COMMON_TITLE_TOKENS`, and the pair together is specific
    # enough not to need that guard (`_COMMON_TITLE_TOKENS` only fires
    # for a title with exactly one significant token).
    ("Plato", "Politeia"): (NamedPassage("the divided line", "509d", "511e", "scholarly"),),
    # Measured #182: "the slave boy" alone is absent corpus-wide;
    # "Meno's slave boy" already resolves via `title_local` today, this
    # closes the one phrasing that named neither the work nor "Meno".
    ("Plato", "Menon"): (NamedPassage("the slave boy", "82b", "85b", "scholarly"),),
    # Measured #182: absent corpus-wide, rank 3-4 once the work
    # resolves — the third confirmed instance, and the first evidence
    # the failure generalises beyond Plato.
    #
    # Kant's Critique of Pure Reason is TWO `works` rows, not one work
    # with a `translations.title_local` row like Politeia/Menon above —
    # ``Kritik der reinen Vernunft`` (deu, 1489 chunks) and
    # ``Critique of Pure Reason`` (eng, 1138 chunks) are separate
    # entries with no `work_aliases` link between them. Seeding the
    # label on the German row alone pins `detect_work` to a `work_id`
    # with zero English chunks — under the default `lang="eng"`,
    # retrieval then finds nothing at all, which is worse than the
    # pre-fix behaviour of searching unscoped. Seeded on both rows
    # instead: `detect_work` sees them tie and (correctly, per
    # `test_work_title_fallback_resolves_a_same_author_tie`) refuses to
    # pick one, while `detect_corpus`'s same-author-tie fallback still
    # resolves "kant" — so the query stays corpus-scoped rather than
    # falsely work-scoped, matching how the already-passing
    # author-named phrasing behaves.
    ("Kant", "Kritik der reinen Vernunft"): (
        NamedPassage("the Copernican revolution", None, None, "scholarly"),
    ),
    ("Kant", "Critique of Pure Reason"): (
        NamedPassage("the Copernican revolution", "Bxvi", "Bxviii", "scholarly"),
    ),
}
