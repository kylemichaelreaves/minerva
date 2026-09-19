"""URL slugs for reader work routes (#602).

Reader URLs used to carry the raw work title as a path segment, so three
encoders fired on a single title — spaces, punctuation, and non-ASCII letters —
and Kant arrived as
``#/r/Beantwortung%20der%20Frage%3A%20Was%20ist%20Aufkl%C3%A4rung%3F``.

This module is HALF of the algorithm. The other half is ``web/src/slug.ts``,
and the two must agree exactly or a link the client builds will not resolve on
the server. They are pinned together by ``data/authors/work_slugs.json``, a
generated artifact both test suites assert against.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

from ..errors import NotFoundError

# NFKD decomposes an accented letter into base + combining mark, which step 3
# then strips. It does NOT touch these — they are atomic codepoints with no
# canonical decomposition — so they would survive to the `[^a-z0-9]+` pass and
# be deleted rather than folded: `bloßen` -> `blo-en`, not `blossen`.
_UNDECOMPOSED = (
    ("ß", "ss"),
    ("æ", "ae"),
    ("Æ", "ae"),
    ("œ", "oe"),
    ("Œ", "oe"),
    ("ø", "o"),
    ("Ø", "o"),
)

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Fold ``text`` to a lowercase ASCII ``[a-z0-9-]`` slug.

    The steps are ordered, and the order matters: the expansions above must
    run BEFORE combining marks are stripped, because two of them (``ø``, ``ß``)
    are single codepoints that NFKD leaves alone.
    """
    text = unicodedata.normalize("NFKD", text)
    for src, dst in _UNDECOMPOSED:
        text = text.replace(src, dst)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_SLUG.sub("-", text.lower()).strip("-")


class SlugCollisionError(RuntimeError):
    """Two works fold to the same ``<authorSlug>/<titleSlug>`` pair.

    Zero collisions is a property of the corpus as it stands, not of the
    algorithm — measured 866/866 distinct over 866 works (#602). A newly
    ingested work can break it, which is what ``make check-authors`` is for:
    the failure has to arrive at ingest time, not as a reader URL that opens
    the wrong book.
    """


def work_key(author: str, title: str) -> str:
    """The ``#/r/<authorSlug>/<titleSlug>`` path, without the ``#/r/``."""

    return f"{slugify(author)}/{slugify(title)}"


def work_slug_table(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Map every work's slug pair to its canonical ``author``/``title``.

    Raises :class:`SlugCollisionError` rather than silently keeping one of a
    colliding pair — a last-wins dict would resolve half the links to the
    wrong work with nothing to show for it.
    """

    table: dict[str, dict[str, str]] = {}
    for author, title in conn.execute("SELECT author, title FROM works ORDER BY author, title"):
        key = work_key(author, title)
        prior = table.get(key)
        if prior is not None:
            raise SlugCollisionError(
                f"{key!r} is the slug of both "
                f"{prior['author']!r}/{prior['title']!r} and {author!r}/{title!r}"
            )
        table[key] = {"author": author, "title": title}
    return table


def validate_slug_snapshot(snapshot: dict[str, dict[str, str]]) -> list[str]:
    """Check a snapshot against itself — the only check CI can run.

    ``data/index.sqlite`` is gitignored, so in CI there is nothing to compare
    the committed table to. What survives without the index is that every key
    is genuinely the slug of the author/title it maps to, which is exactly the
    property the two slugify implementations are pinned to.
    """

    errors: list[str] = []
    for key, entry in snapshot.items():
        expected = work_key(entry["author"], entry["title"])
        if expected != key:
            errors.append(
                f"{key!r} is not the slug of {entry['author']!r}/{entry['title']!r} "
                f"(that slugs to {expected!r})"
            )
        elif any(part == "" for part in key.split("/")):
            errors.append(f"{key!r} has an empty slug on one side")
    return errors


def slug_snapshot_drift(
    conn: sqlite3.Connection,
    snapshot: dict[str, dict[str, str]],
) -> list[str]:
    """Compare the committed table to the live index. Local runs only."""

    live = work_slug_table(conn)
    added = sorted(set(live) - set(snapshot))
    removed = sorted(set(snapshot) - set(live))
    if not added and not removed:
        return []
    parts = []
    if added:
        parts.append(f"missing from the snapshot: {', '.join(added[:5])}")
    if removed:
        parts.append(f"no longer in the index: {', '.join(removed[:5])}")
    return [f"work slugs have drifted — {'; '.join(parts)}. Run `make generate-authors`"]


def resolve_work_slug(
    conn: sqlite3.Connection, author_slug: str, title_slug: str
) -> tuple[str, str]:
    """Resolve a ``<authorSlug>/<titleSlug>`` pair to canonical ``(author, title)``.

    Resolution is a scan — a slug cannot be matched in SQL, because the fold is
    Unicode-aware and SQLite's ``LOWER`` is ASCII-only. At 866 rows that is
    free next to the range query it precedes; if the corpus grows an order of
    magnitude this wants a stored column, not a cleverer query.

    ``make check-authors`` is what keeps the first match from being ambiguous:
    it fails if any two works share a pair.
    """

    wanted = f"{author_slug}/{title_slug}"
    for author, title in conn.execute("SELECT author, title FROM works"):
        if work_key(author, title) == wanted:
            return author, title
    raise NotFoundError(f"no work with slug {wanted!r}")


def resolve_title_slug(conn: sqlite3.Connection, title_slug: str) -> str | None:
    """Resolve an author-less ``<titleSlug>`` to a canonical title.

    Ambiguity is possible here in a way it is not for a pair — two authors can
    share a title slug — and is resolved the same way the author-less title
    lookup in :func:`~minerva.reader.queries.work_range` already resolves it:
    deterministically, by taking the first. Returns ``None`` rather than
    raising, because the caller has an exact-title reading to fall back on.
    """

    for (title,) in conn.execute("SELECT DISTINCT title FROM works ORDER BY title"):
        if slugify(title) == title_slug:
            return title
    return None
