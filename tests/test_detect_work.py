"""Work + corpus auto-detection from a query (retrieval scoping)."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.agent import detect_corpus, detect_work
from minerva.agent.detect import named_passage_labels, work_titles


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE works (id INTEGER PRIMARY KEY, author TEXT, title TEXT)")
    c.execute(
        "CREATE TABLE translations "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
    )
    c.execute(
        "CREATE TABLE editions "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
    )
    # Detection-only aliases (migration 0025) — a work whose stored title
    # is not a name anyone types, and cross-language pairs `title_local`
    # cannot express because it holds one value per (work, language).
    c.execute(
        "CREATE TABLE work_aliases "
        "(work_id INTEGER NOT NULL, alias TEXT NOT NULL, PRIMARY KEY (work_id, alias))"
    )
    # Passages known by a label their own text never uses (migration
    # 0034, #182) — a separate table from `work_aliases` because a label
    # names one passage of a work, not another name FOR the work.
    c.execute(
        "CREATE TABLE named_passages "
        "(work_id INTEGER NOT NULL, label TEXT NOT NULL, "
        "section_start TEXT, section_end TEXT, tradition TEXT NOT NULL, "
        "PRIMARY KEY (work_id, label))"
    )
    c.executemany(
        "INSERT INTO works (id, author, title) VALUES (?, ?, ?)",
        [
            (1, "Nietzsche", "Zur Genealogie der Moral"),
            (2, "Nietzsche", "Jenseits von Gut und Böse"),
            (3, "Nietzsche", "Der Antichrist"),
            (4, "Nietzsche", "Briefe"),
            (5, "Kant", "Kritik der reinen Vernunft"),
            # A work whose title names another corpus's author — the
            # collision runs in this direction too (#170).
            (6, "Nietzsche", "Homer und die klassische Philologie"),
            # The corpus id is `marcus_aurelius`; the author is not.
            # Binding the id matched no rows at all (#174).
            (7, "Marcus Aurelius", "Meditations"),
            # `presocratic` is nine authors, so the mapping is
            # one-to-many and a rename could not have expressed it.
            (8, "Heraclitus", "Fragments (DK 22)"),
            # Plato, canonicalised to Latinized-Greek titles (migration 0023).
            (10, "Plato", "Politeia"),
            (11, "Plato", "Phaidros"),
            (12, "Plato", "Nomoi"),
            # Titles whose only significant token is an ordinary word (#168).
            (13, "Plato", "Erastai"),
            (14, "Plato", "Epistole I"),
            (15, "Plato", "Epistole VII"),
            # Same title_local as Plato 11, different author: only the
            # corpus filter keeps these apart.
            (20, "Aesop", "Phaedrus"),
            # Two works of one author sharing a title_local — the
            # ambiguity case detect_work must refuse to guess at.
            (30, "Twinauthor", "Erstes Werk"),
            (31, "Twinauthor", "Zweites Werk"),
            # Two works of ONE author sharing a title_local. `detect_work`
            # must refuse to pick one, but the *corpus* is unambiguous —
            # the distinction the work-title fallback turns on (#194).
            (32, "Plato", "Diplous A"),
            (33, "Plato", "Diplous B"),
            # A title_local two DIFFERENT authors answer to, neither of
            # them named by an author keyword. Genuine ambiguity.
            (34, "Plato", "Peri Tinos"),
            (35, "Kant", "Über Etwas"),
            # Works whose stored title is not a name a reader would type:
            # a translator surname baked in, and a work split by volume.
            # `title_local` cannot fix either — it is what the reader
            # displays, and it holds one value per (work, language) (#195).
            (40, "Hegel", "Phenomenology of Spirit (Pinkard)"),
            (41, "Hegel", "Phänomenologie des Geistes"),
            (42, "Marx", "Das Kapital, Band I"),
            (43, "Marx", "Das Kapital, Band II"),
        ],
    )
    c.executemany(
        "INSERT INTO work_aliases (work_id, alias) VALUES (?, ?)",
        [
            (40, "Phenomenology of Spirit"),
            (40, "Phänomenologie des Geistes"),
            (41, "Phenomenology of Spirit"),
            (42, "Das Kapital"),
            (43, "Das Kapital"),
        ],
    )
    c.executemany(
        "INSERT INTO translations (work_id, language, title_local) VALUES (?, ?, ?)",
        [
            (10, "eng", "Republic"),
            (11, "eng", "Phaedrus"),
            (12, "eng", "Laws"),
            (13, "eng", "Lovers"),
            (14, "eng", "Letter I"),
            (15, "eng", "Letter VII"),
            (30, "eng", "Twin Work"),
            (31, "eng", "Twin Work"),
            (32, "eng", "Twin Dialogue"),
            (33, "eng", "Twin Dialogue"),
            (34, "eng", "Shared Treatise"),
            (35, "eng", "Shared Treatise"),
            # A translation row carrying no local title must not match.
            (1, "eng", None),
        ],
    )
    c.executemany(
        "INSERT INTO editions (work_id, language, title_local) VALUES (?, ?, ?)",
        [
            (10, "deu", "Der Staat"),
            (11, "grc", None),
        ],
    )
    c.executemany(
        "INSERT INTO named_passages "
        "(work_id, label, section_start, section_end, tradition) VALUES (?, ?, ?, ?, ?)",
        [
            (10, "the divided line", "509d", "511e", "scholarly"),
            # Same shape as Kant's Kritik/Critique pair (#182): one label
            # seeded on two works of the SAME author must not let
            # `detect_work` guess between them, while `detect_corpus`'s
            # same-author-tie fallback still resolves.
            (32, "the twin doctrine", None, None, "scholarly"),
            (33, "the twin doctrine", None, None, "scholarly"),
            # And the cross-author case: two DIFFERENT authors must stay
            # genuinely ambiguous.
            (34, "the paradox", None, None, "scholarly"),
            (35, "the paradox", None, None, "scholarly"),
        ],
    )
    return c


def test_detects_named_work(conn):
    assert detect_work(conn, "Wo spricht er in Die Genealogie der Moral?", "nietzsche") == 1


def test_requires_all_significant_tokens(conn):
    # "Moral" alone is not enough to scope to the Genealogie.
    assert detect_work(conn, "Was sagt Nietzsche über Moral?", "nietzsche") is None


def test_stopwords_do_not_trigger(conn):
    # A bare "der" must not match "Der Antichrist".
    assert detect_work(conn, "Was ist der Mensch?", "nietzsche") is None


def test_scoped_to_corpus(conn):
    # The Kant title's tokens aren't in the query; also corpus-scoped.
    assert detect_work(conn, "Die Genealogie der Moral", "kant") is None


def test_prefers_most_specific(conn):
    # Mentioning the full Jenseits title scopes to it (3 sig tokens),
    # not to anything shorter.
    assert detect_work(conn, "in Jenseits von Gut und Böse", "nietzsche") == 2


def test_no_match_returns_none(conn):
    assert detect_work(conn, "a question about nothing in particular", "nietzsche") is None


def test_detects_work_by_english_translation_title(conn):
    # "Republic" lives in translations.title_local, not works.title.
    assert detect_work(conn, "the divided line in Plato's Republic", "plato") == 10


def test_detects_work_by_german_edition_title(conn):
    # "Der Staat" lives in editions.title_local; "der" is a stopword,
    # so "Staat" alone has to carry the match.
    assert detect_work(conn, "Wo steht das in Platons Der Staat?", "plato") == 10


def test_canonical_title_still_detected_alongside_local_titles(conn):
    assert detect_work(conn, "the divided line in Plato's Politeia", "plato") == 10


def test_local_title_is_corpus_scoped(conn):
    # Aesop's Phaedrus (the fabulist) and Plato's Phaidros both answer to
    # "Phaedrus"; only the corpus filter keeps them apart.
    assert detect_work(conn, "what does Phaedrus say", "plato") == 11
    assert detect_work(conn, "what does Phaedrus say", "aesop") == 20


def test_ambiguous_local_title_returns_none(conn):
    # Two works of one author share "Twin Work". detect_work is
    # conservative: refuse to narrow rather than pick by row order.
    assert detect_work(conn, "in Twin Work he argues", "twinauthor") is None


def test_null_local_title_does_not_match(conn):
    # translations/editions rows with NULL title_local must contribute
    # no tokens — otherwise they'd match every query.
    assert detect_work(conn, "a question about nothing in particular", "plato") is None
    assert detect_work(conn, "was sagt er über Moral?", "nietzsche") is None


# ---------- common-word titles need a capital (#168) ----------


def test_common_word_title_does_not_match_running_prose(conn):
    # The three cases #168 reports, verbatim. None of them is a request
    # for the dialogue whose English name they happen to contain.
    assert detect_work(conn, "what does Plato say about lovers", "plato") is None
    assert detect_work(conn, "I read a letter of Plato", "plato") is None
    assert detect_work(conn, "what are the laws of thought in Plato", "plato") is None


def test_common_word_title_matches_when_capitalised(conn):
    # Naming the work is still naming the work.
    assert detect_work(conn, "the argument of Plato's Laws", "plato") == 12
    assert detect_work(conn, "in the Lovers he asks", "plato") == 13


def test_uncommon_single_token_title_matches_in_any_casing(conn):
    # The #164 population: a title token that is not an ordinary word
    # carries the match by itself, capitalised or not. Only ~40 of 182
    # single-token names need the cue; these are the other ~140.
    assert detect_work(conn, "the divided line in Plato's Republic", "plato") == 10
    assert detect_work(conn, "the divided line in plato's republic", "plato") == 10


def test_roman_numeral_letters_still_resolve(conn):
    # "i" is a stopword now, so Letter I is a one-token name and needs
    # the capital; Letter VII keeps a numeral of its own and stays
    # specific enough to win outright.
    assert detect_work(conn, "in Plato's Letter VII he describes", "plato") == 15
    assert detect_work(conn, "in Plato's Letter I he describes", "plato") == 14
    # The pronoun alone must not reach Letter I any more.
    assert detect_work(conn, "I asked about a letter", "plato") is None


# ---------- detect_corpus: work titles that name another author (#170) ----------
#
# These use the real AUTHOR_KEYWORDS registry against the fixture's works,
# because the collision is precisely between the two.


def test_work_title_naming_another_author_still_scopes(conn):
    # "phaedrus" is an Aesop author keyword (the Latin fabulist) and the
    # English name of Plato's Phaidros. Before #170 the two-corpora guard
    # saw two authors here and scoped to neither.
    assert detect_corpus("Plato's Phaedrus on rhetoric", conn) == "plato"


def test_collision_resolves_in_the_other_direction(conn):
    # Same shape reversed: Nietzsche wrote *about* Homer, who is his own
    # corpus. The essay's author must win over the essay's subject.
    q = "in Nietzsches Homer und die klassische Philologie"
    assert detect_corpus(q, conn) == "nietzsche"


def test_two_genuine_authors_still_refuse_to_scope(conn):
    # The guard must survive the fix: neither author's works are titled
    # after the other, so nothing explains the second mention away.
    assert detect_corpus("Compare Plato and Aristotle on virtue", conn) is None


def test_unexplained_collision_returns_none(conn):
    # Plato has no work titled "Kant"; the query names two authors.
    assert detect_corpus("Kant reading Plato", conn) is None


def test_collision_without_a_connection_stays_unscoped(conn):
    # No index to consult — fall back to the conservative pre-#170
    # behaviour rather than guessing.
    assert detect_corpus("Plato's Phaedrus on rhetoric") is None


def test_single_corpus_match_needs_no_connection():
    # The common path must not require an index at all.
    assert detect_corpus("Plato on the forms") == "plato"
    assert detect_corpus("what does Phaedrus say about the wolf") == "aesop"


# ---------- corpus ids that are not author names (#174) ----------


def test_detects_work_for_a_slug_corpus_id(conn):
    # `LOWER(author) = 'marcus_aurelius'` matched nothing, so work
    # detection could never fire for this corpus however it was asked.
    assert detect_work(conn, "in the Meditations book 4", "marcus_aurelius") == 7


def test_detects_work_across_a_multi_author_corpus(conn):
    assert detect_work(conn, "the Fragments (DK 22) on flux", "presocratic") == 8


def test_slug_corpus_still_refuses_an_unnamed_work(conn):
    assert detect_work(conn, "a question about nothing", "marcus_aurelius") is None


# ---------- work_titles, the shared name↔work mapping (#183) ----------


def test_work_titles_spans_canonical_and_local_names(conn):
    """All three sources, so one work answers to every name it has."""

    politeia = {t for wid, t in work_titles(conn, "plato") if wid == 10}
    assert politeia == {
        "Politeia",  # works.title
        "Republic",  # translations.title_local
        "Der Staat",  # editions.title_local
    }


def test_work_titles_scopes_to_the_corpus(conn):
    assert not [t for _wid, t in work_titles(conn, "kant") if t == "Der Antichrist"]


def test_work_titles_unscoped_spans_every_author(conn):
    """`corpus=None` reads as no filter, matching retrieval (`--corpus any`)."""

    by_corpus = {t for _wid, t in work_titles(conn, "nietzsche")}
    unscoped = {t for _wid, t in work_titles(conn, None)}
    assert "Kritik der reinen Vernunft" in unscoped
    assert "Kritik der reinen Vernunft" not in by_corpus
    assert by_corpus < unscoped
    assert sorted(work_titles(conn, "any")) == sorted(work_titles(conn, None))


def test_work_titles_drops_blank_local_titles(conn):
    """A work with a blank local title must not answer to "".

    An empty name matches every query. `detect_work` skipped it via its
    own significant-token check; `eval_runner` maps names to works, and
    would otherwise key a whole alias set on the empty string.
    """

    conn.execute(
        "INSERT INTO translations (work_id, language, title_local) VALUES (10, 'fra', '   ')"
    )
    assert all(t.strip() for _wid, t in work_titles(conn, "plato"))


# ---------- work-title fallback for corpus detection (#194) ----------


def test_a_named_work_resolves_the_corpus(conn):
    """Naming the work, not the author, scopes retrieval.

    This is #194: `detect_corpus` matched author keywords only, so the
    most natural way to refer to a text resolved to no corpus — which
    silently switched off corpus filtering, work scoping, AND concept
    expansion at once.
    """

    assert detect_corpus("the divided line in the Republic", conn) == "plato"
    assert detect_corpus("where is the cave in the Politeia", conn) == "plato"


def test_named_work_resolves_a_corpus_whose_id_is_not_the_author(conn):
    """The author of a resolved work is not always a corpus id (#174)."""

    assert detect_corpus("in the Meditations book 4", conn) == "marcus_aurelius"
    assert detect_corpus("the Fragments (DK 22) on flux", conn) == "presocratic"


def test_work_title_fallback_keeps_detect_work_conservatism(conn):
    """A one-ordinary-word title still needs capitalising.

    Without this the fallback would re-open #168 one level up: "the laws
    of thought" would scope the whole query to Plato.
    """

    assert detect_corpus("what are the laws of thought", conn) is None
    assert detect_corpus("the preludes in the Laws", conn) == "plato"


def test_work_title_fallback_resolves_a_same_author_tie(conn):
    """Two works of one author tying is not corpus ambiguity.

    `detect_work` must refuse to pick between them; the corpus is still
    unambiguous, so the fallback resolves it.
    """

    q = "a question about the Twin Dialogue"
    assert detect_work(conn, q, "plato") is None
    assert detect_corpus(q, conn) == "plato"


def test_work_title_fallback_refuses_a_cross_author_tie(conn):
    """Two different authors answering to one title is real ambiguity."""

    assert detect_corpus("a question about the Shared Treatise", conn) is None


def test_work_title_fallback_refuses_an_author_outside_every_corpus(conn):
    """A resolved work whose author maps to no corpus cannot scope."""

    assert detect_corpus("a question about the Twin Work", conn) is None


def test_author_keywords_still_take_precedence(conn):
    """The fallback runs only when NO author keyword matched.

    A query naming authors is about those authors; letting a title match
    override that would undo #170's disambiguation and re-scope genuine
    two-author questions.
    """

    # One author named — unchanged fast path, no DB consulted.
    assert detect_corpus("Cicero on the republic", conn) == "cicero"
    # Two genuine authors — must stay unscoped, not fall through to a title.
    assert detect_corpus("Compare Plato and Aristotle on virtue", conn) is None
    assert detect_corpus("Kant reading Plato", conn) is None


def test_work_title_fallback_needs_a_connection(conn):
    """Without an index there is nothing to resolve a title against."""

    assert detect_corpus("the divided line in the Republic") is None


# ── detection-only aliases (#195) ──────────────────────────────────────


def test_work_whose_title_carries_a_translator_surname_names_its_corpus(conn):
    """The #195 miss. Hegel's `works.title` bakes the translator into the
    name, so the bare title matched nothing — every significant token has
    to appear in the query, and 'pinkard' never does — and #194's
    work-title fallback had no name to resolve the corpus from."""

    q = "the master-slave dialectic in the Phenomenology of Spirit"
    assert detect_corpus(q, conn) == "hegel"


def test_alias_carries_a_second_language_without_taking_the_display_title(conn):
    """The cross-language case `title_local` structurally cannot serve:
    work 40 answers to its German name too, while keeping its own."""

    assert detect_corpus("was steht in der Phänomenologie des Geistes", conn) == "hegel"


def test_volume_split_work_names_its_corpus_but_not_a_volume(conn):
    """Both Bände answer to 'Das Kapital', and that is the right outcome
    rather than a collision: #194 judges ambiguity at the CORPUS level, so
    two works of one author still resolve `marx`, while `detect_work`
    returns None and retrieval stays corpus-scoped instead of guessing a
    volume."""

    q = "commodity fetishism in Das Kapital"
    assert detect_corpus(q, conn) == "marx"
    assert detect_work(conn, q, "marx") is None


def test_ambiguity_across_authors_still_refuses_to_scope(conn):
    """An alias must not become a back door around #194's corpus-level
    ambiguity rule — two authors sharing a name still scopes to neither."""

    assert detect_corpus("in the Shared Treatise", conn) is None


def test_aliases_are_corpus_scoped_like_every_other_name(conn):
    assert detect_work(conn, "the Phenomenology of Spirit", "plato") is None


def test_work_titles_includes_aliases(conn):
    names = {name for wid, name in work_titles(conn, "hegel") if wid == 40}
    assert "Phenomenology of Spirit (Pinkard)" in names  # canonical
    assert "Phenomenology of Spirit" in names  # alias
    assert "Phänomenologie des Geistes" in names  # cross-language alias


# ── named passages: a label the text never uses (#182) ─────────────────


def test_named_passage_label_resolves_the_work(conn):
    """The bare label, with the work correctly scoped already, resolves
    the passage's own work — the failure #182 measured is that nothing
    upstream ever gets this far, not that this step is unreachable."""

    assert detect_work(conn, "the divided line", "plato") == 10


def test_named_passage_label_resolves_the_corpus(conn):
    """Naming only the label, no author or work — #182's actual gap.
    Goes through the same work-title fallback #194 built for corpus
    detection, so a passage label gets it for free."""

    assert detect_corpus("the divided line", conn) == "plato"


def test_named_passage_label_is_corpus_scoped(conn):
    """A label lives on one author's work; it must not leak into a
    different corpus's title matching."""

    assert detect_work(conn, "the divided line", "kant") is None


def test_named_passage_label_needs_every_significant_token(conn):
    """ "Line" alone is not the passage; both words have to be present,
    same conservatism `detect_work` already applies to titles."""

    assert detect_work(conn, "draw me a line", "plato") is None


def test_named_passage_labels_are_not_work_titles(conn):
    """A label is not another name FOR the work — `work_titles` (what
    `eval_runner` scores `expected_works` against, #183) must not carry
    it, even though `_best_title_matches` (via `detect_work`) does."""

    names = {name for _wid, name in work_titles(conn, "plato")}
    assert "the divided line" not in names


def test_named_passage_labels_function_scopes_to_corpus(conn):
    assert (10, "the divided line") in named_passage_labels(conn, "plato")
    assert named_passage_labels(conn, "hegel") == []


def test_named_passage_labels_function_unscoped_spans_every_author(conn):
    assert (10, "the divided line") in named_passage_labels(conn, None)
    assert sorted(named_passage_labels(conn, "any")) == sorted(named_passage_labels(conn, None))


def test_named_passage_tie_across_same_author_works_refuses_work_but_resolves_corpus(conn):
    """The Kant Kritik/Critique shape: one label on two works of the same
    author must not let `detect_work` guess between them — but the
    corpus is still unambiguous, so the #194 fallback resolves it."""

    q = "consider the twin doctrine here"
    assert detect_work(conn, q, "plato") is None
    assert detect_corpus(q, conn) == "plato"


def test_named_passage_cross_author_tie_refuses_to_scope(conn):
    """Two different authors' works sharing a label is genuine
    ambiguity, same as two authors sharing a `title_local`."""

    assert detect_corpus("a question about the paradox", conn) is None
