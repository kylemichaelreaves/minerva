"""Corpus + work detection from query keywords."""

from __future__ import annotations

import re
import sqlite3

from ..corpus_registry import AUTHOR_KEYWORDS, corpus_authors, corpus_for_author

_WORD_RE = re.compile(r"\b[\w]+\b", re.UNICODE)


def _phrase_pattern(keyword: str) -> re.Pattern[str]:
    """Match a multi-word keyword across whatever separates its words.

    Built from the keyword's own tokens so `l'antéchrist` matches
    "l'Antéchrist" and `contra celsum` matches "Contra  Celsum".
    """

    tokens = _WORD_RE.findall(keyword.lower())
    return re.compile(
        r"\b" + r"\W+".join(re.escape(t) for t in tokens) + r"\b", re.UNICODE | re.IGNORECASE
    )


# Keywords of more than one word, which the per-token lookup below can
# never see: `AUTHOR_KEYWORDS.get(word)` is called once per `_WORD_RE`
# token, and no such token contains a space or apostrophe. Eight of them
# sat in the manifest doing nothing, including `contra celsum` — the
# only work Origen is in the corpus for (#173).
_PHRASE_KEYWORDS: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (_phrase_pattern(kw), kw, corpus)
    for kw, corpus in sorted(AUTHOR_KEYWORDS.items())
    if len(_WORD_RE.findall(kw)) > 1
)

# Title words too generic to carry scoping signal — articles,
# prepositions, conjunctions across the corpus languages. A work is
# auto-detected only when ALL of its *significant* (non-stopword) title
# tokens appear in the query, so these must be excluded or e.g. "Der
# Antichrist" would match any query containing "der".
_TITLE_STOPWORDS = frozenset(
    {
        # German
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "zur", "zum",
        "von", "vom", "und", "im", "in", "an", "am", "aus", "über", "uber",
        # English
        "the", "a", "of", "on", "to", "and", "or",
        # Latin / French light title words
        "de", "la", "le", "les", "du",
        # The English first-person pronoun, which is also the Roman numeral
        # in "Letter I" — leaving it significant made any query containing
        # "letter" and "I" scope to Epistole I (#168). The other letters
        # still carry their own numerals ("Letter VII"), which are not
        # words, so only this one needed excluding.
        "i",
    }
)

# Derived by scripts/derive_common_title_tokens.py: work-title tokens
# whose corpus-wide PROPN share is under 30% over at least 30 tagged
# occurrences — ordinary words that happen to name a work. 40 of 182
# single-token names, from an index of 428,601 chunks.
#
# A single-token title is not by itself enough to narrow retrieval when
# the token is one of these: "what does Plato say about lovers" is not a
# request for the Erastai (#168). Corpus frequency cannot make this call
# — `lovers` occurs in 170 chunks and `republic` in 371 — but part of
# speech can, since the lemmatizer already tags every token.
_COMMON_TITLE_TOKENS = frozenset(
    {
        "acts", "briefe", "categories", "dreams", "erhabene", "erhabenen", "fato",
        "gesetze", "heavens", "interpretation", "jude", "judges", "lamentations", "laws",
        "legibus", "letter", "lovers", "mark", "mechanics", "morgenröte", "numbers", "nur",
        "officiis", "orator", "oratore", "pensées", "politics", "problems", "proverbs",
        "revelation", "sad", "sophist", "soul", "staat", "staatsmann", "statesman",
        "suppliants", "theages", "topics", "wisdom"
    }
)


# Every name a work answers to: its canonical (for Greek authors,
# Latinized-Greek) title, the per-language `title_local` names that
# migration 0023 put on editions and translations, and the detection-only
# aliases of migration 0025. Display used `title_local` from the start;
# detection did not, so the English name of a canonicalised work was
# unreachable (#164). `work_aliases` covers what `title_local` structurally
# cannot: a work whose stored title is not a name anyone types (Hegel's
# Phenomenology carries its translator's surname; Marx's Kapital is split
# by volume), and cross-language pairs, where one work needs to answer to
# a second language's name without giving up its own display title (#195).
_TITLES_SQL = """
    SELECT w.id, w.title FROM works w WHERE LOWER(w.author) IN ({p})
    UNION
    SELECT w.id, t.title_local FROM works w JOIN translations t ON t.work_id = w.id
     WHERE LOWER(w.author) IN ({p}) AND t.title_local IS NOT NULL
    UNION
    SELECT w.id, e.title_local FROM works w JOIN editions e ON e.work_id = w.id
     WHERE LOWER(w.author) IN ({p}) AND e.title_local IS NOT NULL
    UNION
    SELECT w.id, a.alias FROM works w JOIN work_aliases a ON a.work_id = w.id
     WHERE LOWER(w.author) IN ({p})
"""


def _titles_query(corpus: str) -> tuple[str, tuple[str, ...]]:
    """The titles SQL bound to every author *corpus* is made of.

    A corpus id is not always an author name — `marcus_aurelius` vs
    "Marcus Aurelius" — and `presocratic` is nine of them. Binding the
    id matched no rows at all for those seven (#174).
    """

    authors = corpus_authors(corpus) or (corpus.lower(),)
    placeholders = ",".join("?" * len(authors))
    # One bind group per `{p}` in _TITLES_SQL — four branches since
    # migration 0025 added the alias union. Miscounting here is a
    # ProgrammingError at query time, not a silent wrong answer.
    return _TITLES_SQL.format(p=placeholders), authors * _TITLES_SQL.count("{p}")


# Corpus-unscoped form of `_TITLES_SQL`, for callers that have no corpus
# to narrow to (`minerva eval --corpus any`).
_ALL_TITLES_SQL = """
    SELECT w.id, w.title FROM works w
    UNION
    SELECT w.id, t.title_local FROM works w JOIN translations t ON t.work_id = w.id
     WHERE t.title_local IS NOT NULL
    UNION
    SELECT w.id, e.title_local FROM works w JOIN editions e ON e.work_id = w.id
     WHERE e.title_local IS NOT NULL
    UNION
    SELECT w.id, a.alias FROM works w JOIN work_aliases a ON a.work_id = w.id
"""


# Labels a passage is known by that its own text never uses — "the
# divided line" for Politeia 509d-511e (#182). Deliberately NOT part of
# `_TITLES_SQL`/`work_titles`: a named passage is not another name FOR
# the work (what `work_titles` answers, and what `eval_runner` scores
# `expected_works` against), it names one passage of it. Consulted only
# where `_best_title_matches` resolves a name to a work id, so corpus
# detection's work-title fallback (#194) gets it for free.
_NAMED_PASSAGES_SQL = """
    SELECT w.id, n.label FROM works w JOIN named_passages n ON n.work_id = w.id
     WHERE LOWER(w.author) IN ({p})
"""

_ALL_NAMED_PASSAGES_SQL = """
    SELECT w.id, n.label FROM works w JOIN named_passages n ON n.work_id = w.id
"""


def named_passage_labels(conn: sqlite3.Connection, corpus: str | None) -> list[tuple[int, str]]:
    """Every ``(work_id, label)`` pair a passage of *corpus* is known by.

    Mirrors :func:`work_titles`' corpus-scoping, but reads
    ``named_passages`` rather than titles/aliases — kept separate so a
    passage label never answers `eval_runner`'s "what names this work"
    question, only `_best_title_matches`' "what work does this name".
    """

    if corpus in {None, "any"}:
        rows = conn.execute(_ALL_NAMED_PASSAGES_SQL)
    else:
        authors = corpus_authors(corpus) or (corpus.lower(),)
        placeholders = ",".join("?" * len(authors))
        rows = conn.execute(_NAMED_PASSAGES_SQL.format(p=placeholders), authors)
    return [(int(wid), label) for wid, label in rows if (label or "").strip()]


def work_titles(conn: sqlite3.Connection, corpus: str | None) -> list[tuple[int, str]]:
    """Every ``(work_id, name)`` pair a work of *corpus* answers to.

    One row per name, so a work appears once per alias: its canonical
    ``works.title`` plus each per-language ``title_local`` on its
    editions and translations. ``corpus=None`` (or ``"any"``) spans the
    whole index, matching how retrieval reads an absent corpus filter.

    Public because work detection is not the only thing that has to map
    a name to a work: `eval_runner` scores the gold set's
    ``expected_works`` through the same aliases, having read 0.1 for
    months because it compared raw strings instead (#183).
    """

    if corpus in {None, "any"}:
        rows = conn.execute(_ALL_TITLES_SQL)
    else:
        titles_sql, titles_params = _titles_query(corpus)
        rows = conn.execute(titles_sql, titles_params)
    return [(int(wid), name) for wid, name in rows if (name or "").strip()]


def detect_work(conn: sqlite3.Connection, query: str, corpus: str) -> int | None:
    """Resolve a single ``works.id`` named in ``query`` for ``corpus``.

    A work answers to any of its names: the canonical ``works.title``
    and the per-language ``title_local`` values on its editions and
    translations. So both "Plato's Politeia" and "Plato's Republic"
    resolve to the same work.

    Conservative by design: a title matches only when EVERY significant
    (non-stopword) token of it appears in the lowercased query. When
    several titles qualify (a query naming a long title that contains a
    shorter one), the most specific — most significant tokens — wins.
    Two *different* works tying at that specificity is ambiguity and
    yields ``None``; several titles of one work tying is not. Returns
    ``None`` when nothing matches cleanly, so a passing mention never
    silently narrows scope.

    A title whose one significant token is an ordinary word
    (``_COMMON_TITLE_TOKENS``) additionally has to be capitalised in the
    query to count. "Plato's Laws" scopes to the Nomoi; "the laws of
    thought in Plato" does not (#168). Titles outside that set match in
    any casing, so the all-lowercase queries #164 was fixing keep
    working for the ~140 names that are unambiguous.
    """

    best_ids = _best_title_matches(conn, query, corpus)
    # A tie between two *different* works is genuine ambiguity; several
    # titles of the same work tying is not.
    return next(iter(best_ids)) if len(best_ids) == 1 else None


def _best_title_matches(
    conn: sqlite3.Connection, query: str, corpus: str | None
) -> set[int]:
    """The most specific work titles of *corpus* that *query* names.

    The matching rules documented on :func:`detect_work` live here, so
    the corpus-detection fallback (#194) applies exactly the same
    conservatism rather than a second, drifting copy of it. Returns
    every work tying at the winning specificity — the caller decides
    what a tie means, which differs: two works are ambiguous for work
    detection, but two works of one *author* are not ambiguous for
    corpus detection.

    Named-passage labels (#182) compete in the same race as titles and
    aliases: a query naming "the divided line" resolves Politeia exactly
    as one naming "the Republic" would, so the same specificity and
    stopword rules govern both without a second copy of them.
    """

    query_tokens = set(_WORD_RE.findall(query.lower()))
    # Casing is read from the raw query, before lowercasing.
    capitalised = {t.lower() for t in _WORD_RE.findall(query) if t[:1].isupper()}
    best_ids: set[int] = set()
    best_n = 0
    names = list(work_titles(conn, corpus)) + list(named_passage_labels(conn, corpus))
    for work_id, title in names:
        sig = [t for t in _WORD_RE.findall(title.lower()) if t not in _TITLE_STOPWORDS]
        if not sig or not all(t in query_tokens for t in sig):
            continue
        if len(sig) == 1 and sig[0] in _COMMON_TITLE_TOKENS and sig[0] not in capitalised:
            continue
        if len(sig) > best_n:
            best_ids, best_n = {work_id}, len(sig)
        elif len(sig) == best_n:
            best_ids.add(work_id)
    return best_ids


def _corpus_from_work_title(conn: sqlite3.Connection, query: str) -> str | None:
    """The corpus of the work *query* names, when no author is named.

    Naming a work is the most natural way to refer to a text, and used
    to resolve nothing: `detect_corpus` read author keywords only, so
    "the divided line in the Republic" scoped to no corpus and thereby
    switched off corpus filtering, work scoping, and concept expansion
    at once (#194).

    Ambiguity is judged at the *corpus* level, not the work level. Two
    dialogues of Plato tying still means Plato; one work of Plato and
    one of Kant means nothing, and an author belonging to no corpus
    cannot scope at all.
    """

    ids = _best_title_matches(conn, query, None)
    if not ids:
        return None
    placeholders = ",".join("?" * len(ids))
    corpora = {
        corpus_for_author(author)
        for (author,) in conn.execute(
            f"SELECT author FROM works WHERE id IN ({placeholders})", tuple(ids)
        )
    }
    # A `None` in the set is an author no corpus claims — not a corpus,
    # and not something to silently drop in favour of its co-matches.
    if len(corpora) != 1:
        return None
    return next(iter(corpora))


def _title_tokens(conn: sqlite3.Connection, corpus: str) -> set[str]:
    """Every token of every name every work of *corpus* answers to."""

    toks: set[str] = set()
    for _work_id, title in work_titles(conn, corpus):
        toks.update(_WORD_RE.findall(title.lower()))
    return toks


def detect_corpus(query: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Resolve the single corpus named in *query*, or ``None``.

    A query naming two authors must not be scoped to one of them — half
    the question would be silently dropped. But a *work* title that
    happens to equal another author's name is not a second author, and
    keywords alone cannot tell the two apart: "Plato's Phaedrus" hits
    ``plato`` and (via Phaedrus the Latin fabulist) ``aesop``, and used
    to scope to neither (#170).

    So when more than one corpus matches and *conn* is given, each
    candidate is asked whether it can account for the other candidates'
    keywords as titles of its own works. "Plato's Phaedrus" -> Plato has
    a work called Phaedrus, Aesop has none called Plato, so Plato is the
    author and Phaedrus the work. Exactly one candidate must survive;
    a genuine two-author query leaves none, and stays unscoped. Without
    *conn* the pre-#170 behaviour stands.
    """

    lowered = query.lower()
    matched: dict[str, set[str]] = {}
    for word in _WORD_RE.findall(lowered):
        c = AUTHOR_KEYWORDS.get(word)
        if c:
            matched.setdefault(c, set()).add(word)
    # Multi-word keywords are matched as phrases; the token pass above
    # cannot reach them (#173).
    for pattern, keyword, corpus in _PHRASE_KEYWORDS:
        if pattern.search(lowered):
            matched.setdefault(corpus, set()).update(_WORD_RE.findall(keyword.lower()))

    if len(matched) == 1:
        return next(iter(matched))
    if conn is None:
        return None
    if not matched:
        # No author named — the query may still name a work (#194).
        return _corpus_from_work_title(conn, query)

    survivors = [
        cand
        for cand in matched
        if {w for c, words in matched.items() if c != cand for w in words}
        <= _title_tokens(conn, cand)
    ]
    return survivors[0] if len(survivors) == 1 else None


def strip_author_keywords(query: str, corpus: str) -> str:
    if not query or not corpus:
        return query
    out = query
    # Phrases first: the per-token pass below cannot see them, so
    # "Ernest Renan" would leave "Ernest" behind (#173).
    for pattern, _keyword, kw_corpus in _PHRASE_KEYWORDS:
        if kw_corpus == corpus:
            out = pattern.sub(" ", out)
    out = _WORD_RE.sub(
        lambda m: "" if AUTHOR_KEYWORDS.get(m.group(0).lower()) == corpus else m.group(0),
        out,
    )
    # Removing the name out of a possessive strands its suffix:
    # "Plato's Republic" became "'s Republic", and that orphan went into
    # the embedding query as a token of its own (#165).
    out = re.sub(r"(^|\s)['’]s\b", r"\1", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\s+([,.?!;:])", r"\1", out)
    return out if out else query
