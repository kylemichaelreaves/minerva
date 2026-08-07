"""Locator-driven commands: `find`, `tag`, `suggest-locator`.

These three together implement the curator's main loop: name a
passage (`find` → chunk_id), record an occurrence inside it (`tag`),
and — when the chunk's auto-derived section doesn't match the work's
citation system — get a sibling-translation hint (`suggest-locator`)
to choose the right `--locator` override.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from typing import Any

from ... import locations, terms
from ...text.snippet import find_occurrences, plain_window
from ._io import _emit, _with_db


@_with_db
def cmd_terms_find(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Resolve a (work, lang, section) locator to a chunk_id. Used as
    a precursor to ``terms tag``: the curator names a passage, this
    command emits the chunk_id to feed into ``--chunk``."""

    sql = "SELECT chunk_id, section, text FROM chunks_full WHERE work = ? AND lang = ?"
    params: list[Any] = [args.work, args.lang]
    if args.section:
        sql += " AND section = ?"
        params.append(args.section)
    sql += " ORDER BY ord LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print(
            f"no chunks match work={args.work!r} lang={args.lang!r} section={args.section!r}",
            file=sys.stderr,
        )
        return 1
    output = [(r["chunk_id"], r["section"], (r["text"] or "").replace("\n", " ")) for r in rows]
    _emit(output, ("chunk_id", "section", "text"), args.json)
    return 0


@_with_db
def cmd_terms_tag(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Mark an occurrence of a term in a specific chunk.

    Workflow: the curator runs ``terms find ...`` to identify the
    chunk_id, then calls ``terms tag --term ID --chunk CID``. This
    command resolves the chunk's containing edition, parses its
    section into the structured location payload via the work's
    citation_system, locates the term's source_form in the chunk
    text, and inserts an occurrence at the requested instance.
    """

    # Resolve term. The match-form is what we search for inside the
    # chunk text; for Greek terms the curator stores the polytonic
    # form in `source_form` (for display) and the Perseus beta-code
    # equivalent in `transliteration` (to match chunks). For Latin-
    # script languages they're typically the same, so `transliteration`
    # is null and we fall back to `source_form`.
    term = conn.execute(
        "SELECT source_form, transliteration FROM terms WHERE id = ?",
        (args.term,),
    ).fetchone()
    if term is None:
        print(f"no term with id={args.term}", file=sys.stderr)
        return 1
    match_form: str = term["transliteration"] or term["source_form"]

    # Resolve chunk to its edition + section + text.
    chunk = conn.execute(
        "SELECT chunk_id, edition_id, section, text FROM chunks WHERE chunk_id = ?",
        (args.chunk,),
    ).fetchone()
    if chunk is None:
        print(f"no chunk with chunk_id={args.chunk!r}", file=sys.stderr)
        return 1
    if chunk["edition_id"] is None:
        print(
            "chunk belongs to a translation, not a source edition — "
            "term occurrences are anchored to source-language chunks only",
            file=sys.stderr,
        )
        return 1

    # Resolve edition → work → citation_system.
    citation_system_row = conn.execute(
        "SELECT w.citation_system FROM editions e JOIN works w ON w.id = e.work_id WHERE e.id = ?",
        (chunk["edition_id"],),
    ).fetchone()
    if citation_system_row is None:
        print(f"edition {chunk['edition_id']} not found", file=sys.stderr)
        return 1
    citation_system = citation_system_row[0]

    # Parse the locator into a structured payload. Three sources, in
    # priority order:
    #   1. Explicit --locator on the CLI (e.g., "A123" for KrV when
    #      the chunk's auto-derived section doesn't carry A/B info).
    #   2. The chunk's section field, parsed under the work's
    #      citation_system.
    #   3. Error out — no fallback to a different system, because the
    #      curator MUST know which citation scheme they're tagging in.
    locator_source = "chunk"
    locator_value = chunk["section"]
    if args.locator:
        locator_value = args.locator
        locator_source = "cli"
    if not locator_value:
        print(
            "chunk has no `section` value — pass --locator to tag this "
            "occurrence with an explicit citation locator",
            file=sys.stderr,
        )
        return 1
    try:
        payload = locations.parse_section(citation_system, locator_value)
    except locations.LocationError as exc:
        hint = (
            ""
            if locator_source == "cli"
            else f" (pass --locator <value> to override the chunk's section "
            f"if it doesn't carry a {citation_system!r}-shaped locator)"
        )
        print(
            f"can't parse {locator_value!r} as {citation_system}: {exc}{hint}",
            file=sys.stderr,
        )
        return 1
    sort_key = locations.format_sort_key(citation_system, payload)

    # Find the match-form's nth occurrence in the chunk's text.
    # allow_overlap=True so a curator can address any textual position,
    # even inside a self-overlapping form (shared finder, issue #71).
    text = chunk["text"]
    positions = find_occurrences(text, match_form, allow_overlap=True)
    if not positions:
        hint = (
            ""
            if term["transliteration"]
            else " (hint: for Greek terms, set --transliteration to the "
            "Perseus beta-code form — the chunk text is encoded that way)"
        )
        print(
            f"match-form {match_form!r} does not appear in chunk text{hint}",
            file=sys.stderr,
        )
        return 1
    nth = args.occurrence
    if nth < 1 or nth > len(positions):
        print(
            f"occurrence index {nth} out of range (found {len(positions)} matches in chunk)",
            file=sys.stderr,
        )
        return 1
    start_offset = positions[nth - 1]
    end_offset = start_offset + len(match_form)

    # Build a context snippet: ~40 chars on either side of the match
    # (shared window helper, whitespace-collapsed + truncation ellipsis).
    snippet = plain_window(text, start_offset, end_offset, radius=40, ellipsis=True)

    try:
        occ_id = terms.insert_occurrence(
            conn,
            term_id=args.term,
            edition_id=chunk["edition_id"],
            source_chunk_id=chunk["chunk_id"],
            source_start=start_offset,
            source_end=end_offset,
            context_snippet=snippet,
            location_kind=citation_system,
            location_payload=payload,
            location_sort_key=sort_key,
            # Snapshot the form that ACTUALLY appears in the chunk —
            # the match-form. The relink path on re-ingest searches
            # the new chunk text for this same string.
            source_form_snapshot=match_form,
            tradition=args.tradition,
        )
        conn.commit()
    except terms.TermsError as exc:
        print(f"could not insert occurrence: {exc}", file=sys.stderr)
        return 1
    print(f"created occurrence id={occ_id} at {chunk['section']} (instance {nth}/{len(positions)})")
    return 0


_AA_PAGE_RE = re.compile(r"\[(\d{1,4})\]")


@_with_db
def cmd_terms_suggest_locator(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Suggest an A/B (or other) locator for a chunk whose section
    doesn't carry one. Useful for German KrV chunks: the zeno source
    doesn't preserve Kant's original A/B pagination, so chunks land
    with structural-paragraph sections instead. This command finds
    sibling-translation chunks at the same relative position in the
    work and reports their section values as candidate locators.

    The alignment is approximate — chunk density varies across editions
    (German has 1560 KrV chunks, English Guyer/Wood has 1139), so the
    curator should treat the results as a starting window to browse,
    not a final answer. When the source chunk carries inline ``[NN]``
    Akademie-Ausgabe page markers, those are surfaced separately as a
    second anchor the curator can cross-walk by hand.
    """

    src = conn.execute(
        "SELECT c.chunk_id, c.edition_id, c.translation_id, c.lang, "
        "       c.section, c.ord, c.text "
        "FROM chunks c WHERE c.chunk_id = ?",
        (args.chunk,),
    ).fetchone()
    if src is None:
        print(f"no chunk with chunk_id={args.chunk!r}", file=sys.stderr)
        return 1

    if src["edition_id"] is not None:
        work_row = conn.execute(
            "SELECT work_id FROM editions WHERE id = ?",
            (src["edition_id"],),
        ).fetchone()
    else:
        work_row = conn.execute(
            "SELECT work_id FROM translations WHERE id = ?",
            (src["translation_id"],),
        ).fetchone()
    if work_row is None:
        print("can't resolve chunk to a work", file=sys.stderr)
        return 1
    work_id = work_row["work_id"]

    # The (author, original_language, citation_system) triple is how we
    # find sibling translations across separate `works` rows — KrV German
    # and KrV English live under different work_ids but share author and
    # the kant_ab citation system, so they're aligned here.
    src_work = conn.execute(
        "SELECT author, original_language, citation_system FROM works WHERE id = ?",
        (work_id,),
    ).fetchone()

    total_src = conn.execute(
        "SELECT COUNT(*), MIN(ord), MAX(ord) FROM chunks WHERE "
        + ("edition_id = ?" if src["edition_id"] is not None else "translation_id = ?"),
        (src["edition_id"] if src["edition_id"] is not None else src["translation_id"],),
    ).fetchone()
    _n_src, min_src, max_src = total_src
    span_src = max(1, (max_src or 0) - (min_src or 0))
    rel = (src["ord"] - (min_src or 0)) / span_src if span_src else 0.0

    # Find sibling translations / editions, including ones under a
    # different `works` row that share the original-text identity.
    sibling_works = conn.execute(
        """
        SELECT id FROM works
        WHERE author = ? AND original_language = ?
          AND citation_system = ? AND id != ?
        """,
        (
            src_work["author"],
            src_work["original_language"],
            src_work["citation_system"],
            work_id,
        ),
    ).fetchall()
    sibling_work_ids = [r["id"] for r in sibling_works] + [work_id]
    placeholders = ",".join("?" for _ in sibling_work_ids)

    siblings = conn.execute(
        f"""
        SELECT t.id, t.language, t.translator_name, t.year, 'translation' AS kind
        FROM translations t
        WHERE t.work_id IN ({placeholders}) AND t.id IS NOT ?
        UNION ALL
        SELECT e.id AS id, e.language, NULL AS translator_name, e.year,
               'edition' AS kind
        FROM editions e
        WHERE e.work_id IN ({placeholders}) AND e.id IS NOT ?
        """,
        (
            *sibling_work_ids,
            src["translation_id"],
            *sibling_work_ids,
            src["edition_id"],
        ),
    ).fetchall()

    if not siblings:
        print(f"no sibling translations/editions for work_id={work_id}", file=sys.stderr)
        return 1

    aa_anchors = _AA_PAGE_RE.findall(src["text"] or "")
    if aa_anchors:
        first_aa = aa_anchors[0]
        print(
            f"# inline AA-page anchor: [{first_aa}] "
            f"(volume page from Akademie-Ausgabe; not a B-page locator)",
            file=sys.stderr,
        )

    out_rows: list[tuple[Any, ...]] = []
    for sib in siblings:
        col = "translation_id" if sib["kind"] == "translation" else "edition_id"
        bounds = conn.execute(
            f"SELECT MIN(ord), MAX(ord), COUNT(*) FROM chunks WHERE {col} = ?",
            (sib["id"],),
        ).fetchone()
        if not bounds or not bounds[2]:
            continue
        b_min, b_max, _b_n = bounds
        b_span = max(1, b_max - b_min)
        target_ord = round(b_min + rel * b_span)

        # Pull the 7 closest chunks (≈ ±3 pages of B-text) so the curator
        # can browse a window rather than commit to a single suggestion.
        rows = conn.execute(
            f"""
            SELECT ord, section, SUBSTR(text, 1, 100) AS preview FROM chunks
            WHERE {col} = ? AND section IS NOT NULL
            ORDER BY ABS(ord - ?) LIMIT 7
            """,
            (sib["id"], target_ord),
        ).fetchall()
        # Order by ord so the curator sees them in document order.
        for r in sorted(rows, key=lambda x: x["ord"]):
            label = sib["translator_name"] or "(source edition)"
            out_rows.append(
                (
                    sib["language"],
                    label,
                    r["section"],
                    f"ord={r['ord']}",
                    r["preview"],
                )
            )

    if not out_rows:
        print("no sibling chunks with section markers found", file=sys.stderr)
        return 1

    headers = ("lang", "translation", "section", "ord", "preview")
    _emit(out_rows, headers, getattr(args, "json", False))
    return 0
