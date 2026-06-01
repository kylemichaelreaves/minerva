"""Reader read queries — SQL and response shaping for the Read API."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import store
from ..author_ordering import author_sort_key, lang_sort_key
from ..authors.quran_works import find_surah_by_transliteration as _find_surah
from ..errors import BadRequestError, NotFoundError
from ..locations import BCV_BOOK_ORDINAL, TANAKH_BOOK_ORDINAL
from ..transliterate import display_text, display_title
from .display import trilingual_display
from .window import (
    empty_window_response,
    fetch_chunk_ids_in_window,
    parse_limit_only,
    parse_window_params,
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

    rows = conn.execute(
            "SELECT cf.work_id, cf.corpus, cf.author, cf.work, cf.lang, COUNT(*) AS n "
            "FROM chunks_full cf "
            "GROUP BY cf.work_id, cf.corpus, cf.author, cf.work, cf.lang"
        ).fetchall()

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


def work_range(conn: sqlite3.Connection, work_id: str, query: dict[str, str]) -> dict[str, Any]:
    """Return a contiguous range of chunks for one (work, lang), ordered
    by `ord`. Used by the reader to render a passage in its source
    language with line numbers / section locators preserved.

    When `around=<chunk_id>` is set, the server resolves the chunk's
    `ord` and centers a `limit`-wide window on it. Other params (lang,
    from) are ignored in that mode so the client doesn't have to know
    the chunk's offset to deep-link from a citation.
    """

    around = query.get("around")
    limit = parse_limit_only(query)

    conn.row_factory = sqlite3.Row
    if around:
        focus_row = conn.execute(
            "SELECT work, lang, ord FROM chunks_full WHERE chunk_id=?",
            (around,),
        ).fetchone()
        if focus_row is None:
            raise NotFoundError( "unknown chunk_id")
        resolved_work = focus_row["work"]
        lang = focus_row["lang"]
        half = limit // 2
        offset = max(0, focus_row["ord"] - half)
    else:
        resolved_work = work_id
        lang = query.get("lang", "grc")
        try:
            offset = int(query.get("from", "0"))
        except ValueError:
            raise BadRequestError( "invalid 'from' query param") from None
        if offset < 0:
            raise BadRequestError( "'from' must be >= 0")
    meta_row = conn.execute(
        "SELECT work_id, corpus, author, work, lang, COUNT(*) AS n "
        "FROM chunks_full WHERE work=? AND lang=? "
        "GROUP BY work_id, corpus, author, work, lang",
        (resolved_work, lang),
    ).fetchone()
    if meta_row is None:
        raise NotFoundError( "no chunks for that (work, lang)")
    rows = conn.execute(
        "SELECT chunk_id, section, book, page, speaker, text, ord "
        "FROM chunks_full WHERE work=? AND lang=? "
        "ORDER BY ord LIMIT ? OFFSET ?",
        (resolved_work, lang, limit, offset),
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
        }
        for r in rows
    ],
    }


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

    conn.row_factory = sqlite3.Row
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
        """Build a whitespace-normalised window around an occurrence
        and report where in the resulting string the matched surface
        starts/ends. Letting the frontend wrap `<mark>` around that
        slice without doing string-search heuristics — string-search
        is fragile when the lemma appears multiple times inside the
        same snippet (very common for high-frequency lemmas).

        Whitespace between the surface and an adjacent punctuation
        token (`,` `.` `;` etc.) is suppressed so `Erklärung,` doesn't
        render as `Erklärung ,`. The same rule applies on the leading
        side for opening brackets — `(Geist` instead of `( Geist`.
        """

        # Closing punctuation that should hug the preceding word.
        _ATTACHED_TRAIL = ",.;:!?)]}"
        # Opening punctuation that should hug the following word.
        _ATTACHED_LEAD = "([{«"

        lo = max(0, start - radius)
        hi = min(len(text), end + radius)
        before = " ".join(text[lo:start].split())
        match = text[start:end]
        after = " ".join(text[end:hi].split())
        # Insert a single space between non-empty segments — unless
        # the adjacent character is "attached" punctuation that
        # belongs to the surface itself.
        if before:
            sep = "" if before[-1] in _ATTACHED_LEAD else " "
            prefix = f"{before}{sep}"
        else:
            prefix = ""
        if after:
            sep = "" if after[0] in _ATTACHED_TRAIL else " "
            suffix = f"{sep}{after}"
        else:
            suffix = ""
        snippet = f"{prefix}{match}{suffix}"
        return {
            "snippet": snippet,
            "match_start": len(prefix),
            "match_end": len(prefix) + len(match),
        }

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
