"""Work + corpus auto-detection from a query (retrieval scoping)."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.agent import detect_corpus, detect_work


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE works (id INTEGER PRIMARY KEY, author TEXT, title TEXT)"
    )
    c.execute(
        "CREATE TABLE translations "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
    )
    c.execute(
        "CREATE TABLE editions "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
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
