"""Reader read queries — SQL and response shaping for the Read API."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import store
from ..author_ordering import author_sort_key, lang_sort_key
from ..authors.quran_works import find_surah_by_transliteration as _find_surah
from ..errors import BadRequestError, NotFoundError
from ..locations import BCV_BOOK_ORDINAL, TANAKH_BOOK_ORDINAL
from ..text import build_mark_snippet
from ..transliterate import display_text, display_title
from .display import trilingual_display
from .window import (
    empty_window_response,
    fetch_chunk_ids_in_window,
    parse_limit_only,
    parse_window_params,
)

# Per-(work, lang) chunk counts for the reader's work picker.
#
# Grouped on `chunks` alone and joined to `works` afterwards, NOT through
# `chunks_full`. In that view `corpus`, `author` and `work` are
# `LOWER(w.author)`, `w.author` and `w.title` — each functionally determined
# by `work_id` — so naming them in the GROUP BY adds nothing but work, and
# the view's LEFT JOINs to `editions`/`translations` supply no column read
# here. Grouping through it made SQLite run that three-way join once per
# chunk, then sort the result in a temp B-tree, to produce ~1,000 rows.
#
# Measured on the live corpus (428,982 chunks -> 1,046 result rows):
#
#     through the view   median  243.8 ms
#     this query         median   12.6 ms     identical result set
#
# The worst single request recorded beforehand spent 5,569 ms in SQLite.
# The inner GROUP BY is now answered entirely from
# `idx_chunks_work_lang_ord`; `tests/test_server_reader.py` pins that plan,
# because the plan is the property that makes it fast.
#
# Column ORDER is load-bearing: `works_list` unpacks these rows positionally.
WORK_COUNTS_SQL = (
    "SELECT g.work_id AS work_id, LOWER(w.author) AS corpus, w.author AS author, "
    "w.title AS work, g.lang AS lang, g.n AS n "
    "FROM (SELECT work_id, lang, COUNT(*) AS n FROM chunks GROUP BY work_id, lang) g "
    "JOIN works w ON w.id = g.work_id"
)


def works_list(conn: sqlite3.Connection) -> dict[str, Any]:
    """List distinct (corpus, author, work, lang) tuples for the
    reader picker.

    Ordering is chronological by author (Thales → Hegel) per
    ``author_ordering.AUTHOR_ORDINAL``, then by canonical work order
    within each author. For biblical "authors" (Septuagint, NT,
    Vulgate) the work order is the BCV canon (Genesis → Revelation
    + appendices) via ``locations.BCV_BOOK_ORDINAL``. Everywhere else
    we fall back to alphabetical-by-title since philosophical
    corpora don't have a canonical per-author work sequence in the
    way scripture does.

    Languages within a single (author, work) sort source-first:
    ``grc → lat → deu → fra → eng`` (see
    ``author_ordering.LANG_ORDINAL``).
    """

    rows = conn.execute(WORK_COUNTS_SQL).fetchall()

    # Per-edition/translation local title, keyed on (work_id, lang). This is
    # the language's own name for the work — "Republic"/"Laws" on the English
    # translations of Politeia/Nomoi — kept subordinate to the canonical
    # (Latinized-Greek) title in `works.title`. Populated only for Plato
    # today (see authors/plato_titles + migration 0023); everywhere else it
    # is NULL and the row falls through to the existing display logic.
    local_titles: dict[tuple[int, str], str] = {}
    for wid, lang, local in conn.execute(
        "SELECT work_id, language, title_local FROM editions "
        "WHERE title_local IS NOT NULL "
        "UNION ALL "
        "SELECT work_id, language, title_local FROM translations "
        "WHERE title_local IS NOT NULL"
    ).fetchall():
        local_titles[(wid, lang)] = local

    def sort_key(row: tuple[int, str, str, str, str, int]) -> tuple:
        _work_id, _corpus, author, work, lang, _n = row
        # Per-author work ordering:
        #   * Hebrew Bible    → Tanakh canon (Torah → Nevi'im → Ketuvim)
        #   * Quran           → Mushaf order (surah number 1..114)
        #   * LXX / NT / Vulg → Christian / Vulgate BCV ordinal
        #   * everyone else   → alphabetical-by-title (fall through 9999)
        # The bcv ordinal stays the cross-corpus alignment key — only
        # the per-author display sequence changes here.
        if author == "Hebrew Bible":
            work_ord = TANAKH_BOOK_ORDINAL.get(work, 9999)
        elif author == "Quran":
            surah = _find_surah(work)
            work_ord = surah.number if surah is not None else 9999
        else:
            work_ord = BCV_BOOK_ORDINAL.get(work, 9999)
        return (
            author_sort_key(author),
            work_ord,
            work,
            lang_sort_key(lang),
        )

    rows_sorted = sorted(rows, key=sort_key)

    out_works = []
    for (work_id, c, a, w, lang, n) in rows_sorted:
        local = local_titles.get((work_id, lang))
        if local:
            # This language has its own name for the work (English
            # "Republic", German "Der Staat"). Show it as the primary
            # label and keep the canonical Latinized-Greek title
            # ("Politeia") as the subordinate original.
            dt, ds = local, (w if local != w else None)
        else:
            dt, ds = trilingual_display(a, w, display_title(w, lang))
        out_works.append(
            {
                # `work_id` is the integer surrogate from the `works`
                # table — use this for the new term-glossary endpoints
                # like /api/works/:id/term_occurrences. `work` (the
                # title string) remains the id for /api/works/<work>
                # because the SPA hash routes pre-date the works table
                # and the title round-trips through URL encoding.
                "work_id": work_id,
                "corpus": c,
                "author": a,
                "work": w,
                "lang": lang,
                "chunks": n,
                # display_title is the primary label rendered in the
                # sidebar + Reader heading h1. Greek beta-code works
                # carry the polytonic Unicode form; Hebrew Bible works
                # carry the Hebrew-script title; everything else equals
                # `work`. Clients use `work` as the canonical id.
                "display_title": dt,
                # display_subtitle is an optional secondary label
                # rendered as a small subtitle line under the h1 in
                # the Reader heading. Populated for Hebrew Bible
                # (transliteration + English) and null elsewhere.
                "display_subtitle": ds,
            }
        )
    return {"works": out_works}


# Human-readable source-language names for edition labels. Superset of
# translate.prompts.LANG_NAME (which is target-only): the reader also
# surfaces Greek/Latin/Hebrew/Arabic originals.
_LANG_DISPLAY = {
    "grc": "Greek",
    "lat": "Latin",
    "heb": "Hebrew",
    "ara": "Arabic",
    "eng": "English",
    "deu": "German",
    "fra": "French",
}


def _edition_selector(edition_id: int | None, translation_id: int | None) -> str:
    """Opaque per-edition key the reader echoes back to scope the range.

    Exactly one of ``edition_id`` / ``translation_id`` is set on every
    chunk (CHECK constraint), so ``e<id>`` / ``t<id>`` uniquely names the
    edition a chunk belongs to — the unit the reader pages over (#50)."""
    if edition_id is not None:
        return f"e{edition_id}"
    if translation_id is not None:
        return f"t{translation_id}"
    raise NotFoundError("chunk belongs to neither an edition nor a translation")


def _parse_edition_selector(sel: str) -> tuple[int | None, int | None]:
    """``"e123"`` → ``(123, None)``; ``"t456"`` → ``(None, 456)``."""
    if len(sel) >= 2 and sel[1:].isdigit():
        n = int(sel[1:])
        if sel[0] == "e":
            return n, None
        if sel[0] == "t":
            return None, n
    raise BadRequestError(f"invalid edition selector {sel!r}")


def _default_edition(
    conn: sqlite3.Connection, work_id: int, lang: str
) -> tuple[int | None, int | None]:
    """Pick the default (edition_id, translation_id) for a work in one
    language when the caller didn't name one (legacy bookmarks).

    Decision (#50): the most-recent TRANSLATION in the requested language;
    failing that, the canonical original-language edition (then newest,
    then lowest id). Deterministic — never the old behavior of paging
    across every same-(work, lang) chunk concatenated together."""

    rows = conn.execute(
        "SELECT cf.edition_id, cf.translation_id, cf.edition_year AS yr, "
        "       COALESCE(e.is_canonical, 0) AS canon "
        "FROM chunks_full cf "
        "LEFT JOIN editions e ON e.id = cf.edition_id "
        "WHERE cf.work_id = ? AND cf.lang = ? "
        "GROUP BY cf.edition_id, cf.translation_id",
        (work_id, lang),
    ).fetchall()
    if not rows:
        raise NotFoundError("no chunks for that (work, lang)")
    translations = [r for r in rows if r["translation_id"] is not None]
    if translations:
        best = max(translations, key=lambda r: ((r["yr"] or 0), -(r["translation_id"])))
        return None, best["translation_id"]
    best = max(rows, key=lambda r: (r["canon"], (r["yr"] or 0), -(r["edition_id"] or 0)))
    return best["edition_id"], best["translation_id"]


def _work_editions(conn: sqlite3.Connection, work_id: int) -> list[dict[str, Any]]:
    """Every edition + translation of ``work_id`` that has chunks — the
    data the reader's segmented edition bar renders (#50). Ordered
    original(s) first, then by language and year."""

    rows = conn.execute(
        "SELECT cf.edition_id, cf.translation_id, cf.lang, cf.is_original, "
        "       cf.edition_year AS yr, cf.work AS work, "
        "       e.name AS edition_name, t.translator_name AS translator, "
        "       COALESCE(t.title_local, e.title_local) AS title_local, "
        "       COUNT(*) AS n "
        "FROM chunks_full cf "
        "LEFT JOIN editions e ON e.id = cf.edition_id "
        "LEFT JOIN translations t ON t.id = cf.translation_id "
        "WHERE cf.work_id = ? "
        "GROUP BY cf.edition_id, cf.translation_id "
        "ORDER BY cf.is_original DESC, cf.lang, cf.edition_year, cf.edition_id",
        (work_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        lang_disp = _LANG_DISPLAY.get(r["lang"], r["lang"].upper())
        year = r["yr"]
        local = r["title_local"]
        if r["is_original"]:
            # Tab stays concise (the language); the full recension name
            # (OCT, Teubner, "Platonis Opera, ed. Burnet"…) rides in the
            # label. An edition named after the work title carries no
            # extra info, so it degrades to just "Original · <lang>".
            name = r["edition_name"]
            named = bool(name) and name != r["work"]
            short = local or lang_disp
            label = (name + " · " if named else "Original · ") + lang_disp
        elif local:
            # A translation with its own local title (canonical work
            # "Politeia" → English "Republic"): lead with that title, the
            # translator/lang trails in the label (#50).
            who = r["translator"] or "Translation"
            short = local
            label = f"{local} · {who}"
        else:
            who = r["translator"] or "Translation"
            short = who.split()[-1] if who.split() else who
            label = who
        if year:
            label = f"{label} · {year}"
        out.append(
            {
                "selector": _edition_selector(r["edition_id"], r["translation_id"]),
                "lang": r["lang"],
                "is_original": bool(r["is_original"]),
                "translator": r["translator"] or r["edition_name"],
                "year": year,
                "label": label,
                "short": short,
                "n_chunks": r["n"],
            }
        )
    return out


def work_range(conn: sqlite3.Connection, work_id: str, query: dict[str, str]) -> dict[str, Any]:
    """Return a contiguous range of chunks for ONE edition of a work,
    ordered by ``ord``. Used by the reader to render a passage with line
    numbers / section locators preserved, plus the list of sibling
    editions so it can offer a switcher (#50).

    ``work_id`` (the path segment) is the work TITLE string — the SPA
    hash routes pre-date the works table. Since #602 the reader sends a
    title SLUG instead, and ``_handle_work_range`` folds it to a title
    before calling this; an exact title is still tried first and is never
    reinterpreted, so pre-slug callers are unaffected.

    The range is scoped to a single edition, never ``(work_id, lang)``:
    two translations of one work share that key and used to page across
    the concatenation, silently walking from one translator into another.
    Edition resolution, in precedence order:

    * ``edition=<selector>`` (``e<id>`` / ``t<id>``) — an explicit pick
      from the switcher.
    * ``around=<chunk_id>`` — deep-link from a citation; the chunk's own
      edition is used and the window centers on it.
    * otherwise the default edition for ``(title, lang[, author])`` via
      :func:`_default_edition`.

    ``at_section=<locator>`` centers the window on the first chunk with
    that section in the resolved edition (falling back to the top) —
    used to preserve reading position across an edition switch. The
    optional ``author`` param disambiguates same-titled works.
    """

    around = query.get("around")
    edition_sel = query.get("edition")
    at_section = query.get("at_section")
    limit = parse_limit_only(query)

    if around:
        focus_row = conn.execute(
            "SELECT work_id, lang, ord, edition_id, translation_id "
            "FROM chunks_full WHERE chunk_id=?",
            (around,),
        ).fetchone()
        if focus_row is None:
            raise NotFoundError("unknown chunk_id")
        resolved_work_id = focus_row["work_id"]
        lang = focus_row["lang"]
        edition_id, translation_id = focus_row["edition_id"], focus_row["translation_id"]
        pos = conn.execute(
            "SELECT COUNT(*) FROM chunks_full "
            "WHERE edition_id IS ? AND translation_id IS ? AND ord < ?",
            (edition_id, translation_id, focus_row["ord"]),
        ).fetchone()[0]
        offset = max(0, pos - limit // 2)
    elif edition_sel is not None:
        edition_id, translation_id = _parse_edition_selector(edition_sel)
        head = conn.execute(
            "SELECT work_id, lang FROM chunks_full "
            "WHERE edition_id IS ? AND translation_id IS ? LIMIT 1",
            (edition_id, translation_id),
        ).fetchone()
        if head is None:
            raise NotFoundError("unknown edition selector")
        resolved_work_id, lang = head["work_id"], head["lang"]
        offset = _resolve_offset(conn, edition_id, translation_id, at_section, query, limit)
    else:
        lang = query.get("lang", "grc")
        author = query.get("author")
        sql = "SELECT DISTINCT work_id FROM chunks_full WHERE work=? AND lang=?"
        params: list[Any] = [work_id, lang]
        if author:
            sql += " AND author=?"
            params.append(author)
        id_rows = conn.execute(sql + " ORDER BY work_id", params).fetchall()
        if not id_rows:
            raise NotFoundError("no chunks for that (work, lang)")
        resolved_work_id = id_rows[0][0]
        edition_id, translation_id = _default_edition(conn, resolved_work_id, lang)
        offset = _resolve_offset(conn, edition_id, translation_id, at_section, query, limit)

    meta_row = conn.execute(
        "SELECT work_id, corpus, author, work, lang, COUNT(*) AS n "
        "FROM chunks_full WHERE edition_id IS ? AND translation_id IS ? "
        "GROUP BY work_id, corpus, author, work, lang",
        (edition_id, translation_id),
    ).fetchone()
    if meta_row is None:
        raise NotFoundError("no chunks for that edition")
    rows = conn.execute(
        "SELECT chunk_id, section, book, page, speaker, text, ord, block_type "
        "FROM chunks_full WHERE edition_id IS ? AND translation_id IS ? "
        "ORDER BY ord LIMIT ? OFFSET ?",
        (edition_id, translation_id, limit, offset),
    ).fetchall()
    lang_out = meta_row["lang"]
    dt, ds = trilingual_display(
        meta_row["author"],
        meta_row["work"],
        display_title(meta_row["work"], lang_out),
    )
    return {
        # `work_id` is the integer surrogate from the `works` table.
        # The reader needs it to call work-id-keyed endpoints like
        # /api/works/<work_id>/occurrence_map without an extra round
        # trip through the works listing.
        "work_id": meta_row["work_id"],
        "corpus": meta_row["corpus"],
        "author": meta_row["author"],
        "work": meta_row["work"],
        "display_title": dt,
        "display_subtitle": ds,
        "lang": lang_out,
        "total": meta_row["n"],
        "offset": offset,
        "limit": limit,
        # The edition currently rendered + every edition of this work,
        # so the reader can draw the switcher without a second round trip.
        "edition": _edition_selector(edition_id, translation_id),
        "editions": _work_editions(conn, resolved_work_id),
        "chunks": [
            {
                "chunk_id": r["chunk_id"],
                "section": r["section"],
                "book": r["book"],
                "page": r["page"],
                "speaker": r["speaker"],
                # Perseus-sourced Greek chunks are stored in beta-code
                # (see README "Bilingual storage"); transliterate on
                # the way out so the Reader renders polytonic Unicode.
                # First1KGreek chunks lack the marker glyphs and pass
                # through unchanged.
                "text": display_text(r["text"], lang_out),
                "ord": r["ord"],
                "block_type": r["block_type"],
            }
            for r in rows
        ],
    }


def _resolve_offset(
    conn: sqlite3.Connection,
    edition_id: int | None,
    translation_id: int | None,
    at_section: str | None,
    query: dict[str, str],
    limit: int,
) -> int:
    """Offset into an edition's ord-ordered chunks. ``at_section`` centers
    the window on the first chunk carrying that locator (preserving place
    across an edition switch, #50); otherwise the ``from`` param, default
    0. A locator absent from the target edition falls back to the top."""

    if at_section:
        row = conn.execute(
            "SELECT MIN(ord) AS o FROM chunks_full "
            "WHERE edition_id IS ? AND translation_id IS ? AND section = ?",
            (edition_id, translation_id, at_section),
        ).fetchone()
        if row is not None and row["o"] is not None:
            pos = conn.execute(
                "SELECT COUNT(*) FROM chunks_full "
                "WHERE edition_id IS ? AND translation_id IS ? AND ord < ?",
                (edition_id, translation_id, row["o"]),
            ).fetchone()[0]
            return max(0, pos - limit // 2)
        return 0
    try:
        offset = int(query.get("from", "0"))
    except ValueError:
        raise BadRequestError("invalid 'from' query param") from None
    if offset < 0:
        raise BadRequestError("'from' must be >= 0")
    return offset


def _parse_morph_feats(feats: str | None) -> dict[str, str]:
    """Parse a UD morph-features string (`Key=Val|Key=Val|...`) into
    a flat dict. The lemmatizer cache stores the raw string; callers
    that want one feature reach for it through this helper. Empty
    input or ``"_"`` (the UD sentinel for "no features") both return
    an empty dict.
    """

    if not feats or feats == "_":
        return {}
    out: dict[str, str] = {}
    for part in feats.split("|"):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key and value:
            out[key] = value
    return out


def word_lookup(conn: sqlite3.Connection, query: dict[str, str]) -> dict[str, Any]:
    """Look up one token in chunk_lemmas, then summarise its lemma's
    footprint in the same edition.

    Powers the Reader's word-click rail. Given the chunk_id the user
    clicked into and the surface_start offset of the word, returns
    the lemma + a count of occurrences of that lemma across the
    edition + a handful of sample sites (locator + cleaned snippet)
    the UI can list as cheap "see also" anchors. Curated terms
    (those in the `terms` table) get their own popover via the
    term-card flow; this endpoint is the fallback for any non-curated
    word — every word in a lemmatised chunk should produce something
    useful here.
    """

    chunk_id = query.get("chunk_id")
    offset_raw = query.get("offset")
    if not chunk_id or offset_raw is None:
        raise BadRequestError(
            "both 'chunk_id' and 'offset' query params are required",
        )
    try:
        offset = int(offset_raw)
    except ValueError:
        raise BadRequestError( "'offset' must be an integer") from None
    try:
        samples_limit = int(query.get("samples_limit", "5"))
    except ValueError:
        raise BadRequestError( "'samples_limit' must be an integer"
        ) from None
    # Cap at 100 so a Show-more click can fetch a meaningful next
    # batch but the response stays bounded for very-common lemmas
    # (e.g. German `der` has ~24 k sites — we don't want one click
    # paging in every single one).
    samples_limit = max(0, min(100, samples_limit))
    try:
        samples_offset = int(query.get("samples_offset", "0"))
    except ValueError:
        raise BadRequestError( "'samples_offset' must be an integer"
        ) from None
    if samples_offset < 0:
        raise BadRequestError( "'samples_offset' must be >= 0")

    # Resolve the click into a (chunk, edition) + the lemma at
    # that offset. The chunk_lemmas row is keyed by chunk_id +
    # token_index, but we know offsets; a direct WHERE on
    # surface_start hits the (chunk_id, lemma) index well enough
    # because chunk_id is highly selective.
    focus = conn.execute(
        "SELECT cl.surface_form, cl.lemma, cl.surface_start, cl.surface_end, "
        "       cl.pos, cl.feats, "
        "       cf.edition_id, cf.translation_id, cf.work_id, "
        "       cf.work AS work_title, cf.lang "
        "FROM chunk_lemmas cl "
        "JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id "
        "WHERE cl.chunk_id = ? AND cl.surface_start = ?",
        (chunk_id, offset),
    ).fetchone()
    if focus is None:
        raise NotFoundError(
            "no lemma cache entry at that (chunk_id, offset). Run "
            "`minerva terms lemmatize --lang <lang>` for the chunk's edition.",
        )
    # Every chunk belongs to exactly one of edition / translation
    # (never both, never neither — enforced by 0001's schema).
    # We filter cross-chunk searches on whichever side is non-null
    # so a Latin Meditationes click only surfaces Latin samples,
    # and a French Luynes click only surfaces Luynes samples —
    # the two sit in adjacent works but on different source
    # families. Using `IS ?` (not `= ?`) is the null-safe
    # equality SQLite needs when one side of the binding is None.
    edition_id = focus["edition_id"]
    translation_id = focus["translation_id"]
    lemma = focus["lemma"]

    count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM chunk_lemmas cl "
        "JOIN chunks c ON c.chunk_id = cl.chunk_id "
        "WHERE c.edition_id IS ? AND c.translation_id IS ? "
        "  AND cl.lemma = ?",
        (edition_id, translation_id, lemma),
    ).fetchone()
    occurrence_count = int(count_row["n"]) if count_row else 0

    samples_rows: list[sqlite3.Row] = []
    if samples_limit > 0:
        samples_rows = conn.execute(
            "SELECT cl.chunk_id, cl.surface_start, cl.surface_end, "
            "       cl.surface_form, cf.section, cf.text "
            "FROM chunk_lemmas cl "
            "JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id "
            "WHERE cf.edition_id IS ? AND cf.translation_id IS ? "
            "  AND cl.lemma = ? "
            "ORDER BY cf.ord, cl.surface_start "
            "LIMIT ? OFFSET ?",
            (edition_id, translation_id, lemma, samples_limit, samples_offset),
        ).fetchall()

    def _snippet(
        text: str, start: int, end: int, radius: int = 40
    ) -> dict[str, Any]:
        return build_mark_snippet(text, start, end, radius=radius)

    feats_dict = _parse_morph_feats(focus["feats"])
    return {
        "surface": focus["surface_form"],
        "lemma": lemma,
        "lang": focus["lang"],
        "edition_id": edition_id,
        "work_id": focus["work_id"],
        "work_title": focus["work_title"],
        # Morphology. `pos` is the UD coarse code (NOUN, VERB, …);
        # `gender` / `number` are pulled from feats for direct
        # rendering; `feats` is the raw UD string for clients that
        # want to render other features (case, mood, tense, …)
        # without a new endpoint round-trip. All four are nullable —
        # legacy `chunk_lemmas` rows from before migration 0008 carry
        # NULL pos/feats until the next `terms lemmatize --all` pass.
        "pos": focus["pos"],
        "gender": feats_dict.get("Gender"),
        "number": feats_dict.get("Number"),
        "feats": focus["feats"],
        "occurrence_count": occurrence_count,
        # `samples_offset` echoes the request cursor so the client
        # knows where its current page started; `next_samples_offset`
        # is null when there are no more samples to fetch.
        "samples_offset": samples_offset,
        "next_samples_offset": (
            samples_offset + len(samples_rows)
            if samples_offset + len(samples_rows) < occurrence_count
            else None
        ),
        "samples": [
            {
                "chunk_id": r["chunk_id"],
                "section": r["section"],
                "surface": r["surface_form"],
                "surface_start": r["surface_start"],
                "surface_end": r["surface_end"],
                **_snippet(r["text"], r["surface_start"], r["surface_end"]),
            }
            for r in samples_rows
        ],
    }


def lemma_highlights(
    conn: sqlite3.Connection,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    """For one (lemma, work, lang) tuple, return every (chunk_id,
    surface_start, surface_end) where that lemma appears in the
    reader-window slice. Powers the Reader's in-text highlighting:
    when the user clicks a word, every other site of the same lemma
    on the visible page lights up.

    Window-scoped on purpose. The same data with no window would be
    fine for Categories (66 chunks) but ballooning for "der" in
    Hegel's PhG (~24 k sites edition-wide). The frontend asks for
    exactly the chunks it just laid out via /api/works/.../range.
    """

    lemma = query.get("lemma")
    if not lemma:
        raise BadRequestError( "lemma query param required")
    window = parse_window_params(query)
    chunk_ids = fetch_chunk_ids_in_window(
        conn, work_id, window.lang, window.from_ord, window.limit,
    )
    if not chunk_ids:
        return empty_window_response(work_id, window, extra={"lemma": lemma})
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT chunk_id, surface_start, surface_end "
        f"FROM chunk_lemmas "
        f"WHERE lemma = ? AND chunk_id IN ({placeholders}) "
        f"ORDER BY chunk_id, surface_start",
        (lemma, *chunk_ids),
    ).fetchall()
    by_chunk: dict[str, list[dict[str, int]]] = {}
    for r in rows:
        by_chunk.setdefault(r["chunk_id"], []).append(
            {"start": r["surface_start"], "end": r["surface_end"]}
        )
    return {
        "work_id": work_id,
        "lang": window.lang,
        "lemma": lemma,
        "from": window.from_ord,
        "limit": window.limit,
        "by_chunk": by_chunk,
    }


def chunk_context(
    conn: sqlite3.Connection,
    chunk_id: str,
    query: dict[str, str],
) -> dict[str, Any]:
    """Return a single chunk plus its `radius` immediate neighbors in
    document order. Used by the chat UI to expand a marginal citation
    from its truncated preview to the full passage with surrounding
    context. Keeps clients from needing to know each chunk's `ord`."""

    try:
        radius = int(query.get("radius", "1"))
    except ValueError:
        raise BadRequestError( "invalid 'radius' query param") from None
    if radius < 0 or radius > 5:
        raise BadRequestError( "'radius' must be in 0..5")

    focus, before_rows, after_rows = store.fetch_chunk_context(
        conn, chunk_id, radius=radius
    )
    if focus is None:
        raise NotFoundError( "unknown chunk_id")

    focus_lang = focus["lang"]

    def _row_to_chunk(r: sqlite3.Row) -> dict[str, Any]:
        return {
            "chunk_id": r["chunk_id"],
            "section": r["section"],
            "book": r["book"],
            "page": r["page"],
            "speaker": r["speaker"],
            "text": display_text(r["text"], focus_lang),
            "ord": r["ord"],
        }

    return {
        "corpus": focus["corpus"],
        "author": focus["author"],
        "work": focus["work"],
        "display_title": display_title(focus["work"], focus_lang),
        "lang": focus_lang,
        "focus": _row_to_chunk(focus),
        "before": [_row_to_chunk(r) for r in before_rows],
        "after": [_row_to_chunk(r) for r in after_rows],
    }


def landing_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Small payload for the landing page totals strip."""

    authors = conn.execute(
        "SELECT COUNT(DISTINCT author) FROM works"
    ).fetchone()[0]
    works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    xrefs = conn.execute(
        "SELECT COUNT(*) FROM cross_references "
        "WHERE curator_status IN ('approved','manual') "
        "   OR (curator_status='auto' AND confidence >= 0.8)"
    ).fetchone()[0]
    return {
        "authors": int(authors),
        "works": int(works),
        "xrefs": int(xrefs),
    }
