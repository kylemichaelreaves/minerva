"""Engine that turns a :class:`~minerva.glossary_spec.GlossarySpec` into
``terms`` / ``term_renderings`` / ``term_relations`` / ``term_occurrences``
rows. Driven by ``minerva terms import``.

Matching strategy per term:

* If the language has a lemmatizer (``minerva.lemmatize.is_supported``)
  AND the term has no ``search_forms`` override, occurrences come from
  ``chunk_lemmas`` joined on ``lemma``.
* Otherwise (current Greek path), occurrences come from a surface-form
  scan of ``chunks.text`` using the term's ``search_forms`` list, the
  same way ``scripts/seed_terms.py`` worked before this refactor.

Idempotency: every occurrence insert checks the natural identity
``(term_id, source_chunk_id, source_start, source_end,
source_form_snapshot)`` and skips if a row already exists. Re-running
an importer on the same spec is a no-op.
"""

from __future__ import annotations

import contextlib
import itertools
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Any

from . import locations
from . import terms as terms_mod
from .glossary_spec import GlossarySpec, Term, WorkApply
from .lemmatize import is_supported
from .text.snippet import find_occurrences, plain_window


@dataclass(frozen=True)
class ImportReport:
    """Summary of one import pass — what the CLI prints."""

    terms_upserted: int
    renderings_upserted: int
    relations_upserted: int
    occurrences_inserted: int
    occurrences_skipped_duplicate: int
    occurrences_unparseable_locator: int
    per_work_counts: dict[str, dict[str, int]]


# ──────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────


def apply_spec(
    conn: sqlite3.Connection,
    spec: GlossarySpec,
    *,
    dry_run: bool = False,
    only_work: str | None = None,
) -> ImportReport:
    """Apply one spec to the database. With ``dry_run=True`` no rows
    are written — the report still counts what *would* have been
    inserted so the CLI's --dry-run can give meaningful output.

    ``only_work`` filters apply_to entries by work title — useful when
    a curator just added a new work and wants to import only its
    occurrences without re-touching other works in the same author's
    file (though the existing idempotency check makes the full pass
    cheap too)."""

    use_lemmas = is_supported(spec.language)

    if not dry_run:
        conn.execute("BEGIN")
    try:
        # Map source_form → term_id for cross-term references in
        # `related` blocks (handled after all terms upserted).
        term_ids: dict[str, int] = {}

        terms_upserted = 0
        renderings_upserted = 0
        for term in spec.terms:
            term_id = _ensure_term(conn, spec.language, term, dry_run=dry_run)
            term_ids[term.source_form] = term_id
            terms_upserted += 1
            for apply in term.apply_to:
                for tr in apply.translations:
                    _ensure_rendering(
                        conn,
                        term_id=term_id,
                        translation_id=tr.translation_id,
                        rendering=tr.rendering,
                        note=tr.note,
                        dry_run=dry_run,
                    )
                    renderings_upserted += 1

        # term_relations after all terms exist so we can resolve the
        # related-lemma → term_id lookup correctly.
        relations_upserted = 0
        for term in spec.terms:
            for rel in term.related:
                target = _lookup_term_id(conn, rel.lemma, spec.language)
                if target is None:
                    # Related lemma not in this spec and not in DB —
                    # skip silently rather than fail. The curator can
                    # author the related term later; the relation just
                    # won't be drawn until then.
                    continue
                _ensure_relation(
                    conn,
                    term_id=term_ids[term.source_form],
                    related_term_id=target,
                    relation_kind=rel.relation_kind,
                    note=rel.note,
                    dry_run=dry_run,
                )
                relations_upserted += 1

        # Occurrences.
        inserted = 0
        skipped = 0
        unparseable = 0
        per_work: dict[str, dict[str, int]] = {}
        for term in spec.terms:
            term_id = term_ids[term.source_form]
            # Decide once per term: lemma-cache join or surface-form scan.
            # search_forms takes precedence — that's the curator's
            # explicit way to say "skip the lemmatizer, use these
            # exact strings".
            term_use_lemmas = use_lemmas and not term.search_forms

            for apply in term.apply_to:
                if only_work is not None and apply.work_title != only_work:
                    continue
                stats = per_work.setdefault(apply.work_title, {"ins": 0, "skip": 0})
                chunk_id_set = _chunks_in_apply(conn, apply)
                if not chunk_id_set:
                    continue
                citation_system = _citation_system_for(conn, apply.work_title)
                for chunk_id, section, text in _chunk_rows(conn, chunk_id_set):
                    norm = unicodedata.normalize("NFC", text)
                    loc = _section_payload(citation_system, section)
                    if loc is None:
                        unparseable += 1
                        continue
                    if term_use_lemmas:
                        sites = _lemma_sites(conn, chunk_id, term.lemma)
                    else:
                        sites = _surface_sites(norm, term.search_forms or (term.source_form,))
                    for start, end, form in sites:
                        already = conn.execute(
                            "SELECT 1 FROM term_occurrences "
                            "WHERE term_id = ? AND source_chunk_id = ? "
                            "AND source_start = ? AND source_end = ? "
                            "AND source_form_snapshot = ?",
                            (term_id, chunk_id, start, end, form),
                        ).fetchone()
                        if already is not None:
                            skipped += 1
                            stats["skip"] += 1
                            continue
                        if not dry_run:
                            terms_mod.insert_occurrence(
                                conn,
                                term_id=term_id,
                                edition_id=apply.edition_id,
                                source_chunk_id=chunk_id,
                                source_start=start,
                                source_end=end,
                                context_snippet=_context_snippet(norm, start, end),
                                location_kind=loc["payload"]["kind"],
                                location_payload=loc["payload"],
                                location_sort_key=loc["sort_key"],
                                source_form_snapshot=form,
                            )
                        inserted += 1
                        stats["ins"] += 1

        # Commit only when we actually opened a transaction. Dry-run
        # mode skipped the BEGIN above, so there is nothing to commit
        # or roll back here.
        if not dry_run:
            conn.execute("COMMIT")
        return ImportReport(
            terms_upserted=terms_upserted,
            renderings_upserted=renderings_upserted,
            relations_upserted=relations_upserted,
            occurrences_inserted=inserted,
            occurrences_skipped_duplicate=skipped,
            occurrences_unparseable_locator=unparseable,
            per_work_counts=per_work,
        )
    except Exception:
        # Only roll back when we actually opened a transaction. In
        # dry-run mode the BEGIN was skipped, so ROLLBACK would itself
        # raise OperationalError("no transaction is active"); suppress
        # is the clean way to express "best-effort rollback."
        if not dry_run:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ROLLBACK")
        raise


# ──────────────────────────────────────────────────────────────────
# Insert helpers (absorbed from scripts/seed_terms.py)
# ──────────────────────────────────────────────────────────────────

# Dry-run sentinel ids for terms that don't exist yet: a decrementing
# counter starting at -1, so every sentinel is strictly negative and
# never collides with a real (positive) PK.
_DRY_RUN_IDS = itertools.count(-1, -1)


def _ensure_term(
    conn: sqlite3.Connection,
    language: str,
    term: Term,
    *,
    dry_run: bool,
) -> int:
    """Upsert into ``terms`` by ``(source_form, source_language)``. On
    dry-run, returns the existing id when present and a negative
    sentinel when not (always < 0, so it can't collide with a real
    AUTOINCREMENT PK — the previous hash-based sentinel could land on
    0 and varied under hash randomization)."""

    row = conn.execute(
        "SELECT id FROM terms WHERE source_form = ? AND source_language = ?",
        (term.source_form, language),
    ).fetchone()
    if row is not None:
        if not dry_run:
            conn.execute(
                "UPDATE terms SET transliteration = ?, lemma = ?, "
                "short_gloss = ?, long_description = ? WHERE id = ?",
                (
                    term.transliteration,
                    term.lemma,
                    term.short_gloss,
                    term.long_description,
                    row[0],
                ),
            )
        return int(row[0])
    if dry_run:
        # Synthetic id for the dry-run report; unique per call is fine
        # because each spec term hits this at most once per run.
        return next(_DRY_RUN_IDS)
    cur = conn.execute(
        "INSERT INTO terms (source_form, source_language, transliteration, "
        "lemma, short_gloss, long_description) VALUES (?, ?, ?, ?, ?, ?)",
        (
            term.source_form,
            language,
            term.transliteration,
            term.lemma,
            term.short_gloss,
            term.long_description,
        ),
    )
    return int(cur.lastrowid)


def _ensure_rendering(
    conn: sqlite3.Connection,
    *,
    term_id: int,
    translation_id: int,
    rendering: str,
    note: str | None,
    dry_run: bool,
) -> None:
    """Upsert a per-translator default rendering."""

    row = conn.execute(
        "SELECT id FROM term_renderings WHERE term_id = ? AND translation_id = ?",
        (term_id, translation_id),
    ).fetchone()
    if row is not None:
        if not dry_run:
            conn.execute(
                "UPDATE term_renderings SET default_rendering = ?, translator_note = ? "
                "WHERE id = ?",
                (rendering, note, row[0]),
            )
        return
    if dry_run:
        return
    conn.execute(
        "INSERT INTO term_renderings (term_id, translation_id, default_rendering, "
        "translator_note) VALUES (?, ?, ?, ?)",
        (term_id, translation_id, rendering, note),
    )


def _ensure_relation(
    conn: sqlite3.Connection,
    *,
    term_id: int,
    related_term_id: int,
    relation_kind: str | None,
    note: str | None,
    dry_run: bool,
) -> None:
    """Upsert a ``term_relations`` row keyed on (term_id, related_term_id)."""

    if dry_run:
        return
    conn.execute(
        "INSERT OR REPLACE INTO term_relations "
        "(term_id, related_term_id, relation_kind, notes) VALUES (?, ?, ?, ?)",
        (term_id, related_term_id, relation_kind, note),
    )


def _lookup_term_id(conn: sqlite3.Connection, lemma: str, language: str) -> int | None:
    """Find a term row by (source_form, source_language). Used to
    resolve `related` pointers."""

    row = conn.execute(
        "SELECT id FROM terms WHERE source_form = ? AND source_language = ?",
        (lemma, language),
    ).fetchone()
    return int(row[0]) if row else None


# ──────────────────────────────────────────────────────────────────
# Occurrence finders
# ──────────────────────────────────────────────────────────────────


def _lemma_sites(
    conn: sqlite3.Connection,
    chunk_id: str,
    lemma: str,
) -> list[tuple[int, int, str]]:
    """All (start, end, surface_form) sites in `chunk_id` whose
    cached lemma equals `lemma`. Reads from `chunk_lemmas` — the
    `minerva terms lemmatize` step must have run for the chunk's
    language."""

    rows = conn.execute(
        "SELECT surface_start, surface_end, surface_form FROM chunk_lemmas "
        "WHERE chunk_id = ? AND lemma = ? ORDER BY surface_start",
        (chunk_id, lemma),
    ).fetchall()
    return [(r["surface_start"], r["surface_end"], r["surface_form"]) for r in rows]


def _surface_sites(text: str, forms: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """For each surface form, every (start, end, form) it occurs at in
    `text`. Forms are checked in declared order; we don't overlap-prune
    — overlapping matches (longer form contains shorter) are dedup'd
    only by the natural-identity insert check upstream."""

    out: list[tuple[int, int, str]] = []
    for form in forms:
        for idx in find_occurrences(text, form, allow_overlap=False):
            out.append((idx, idx + len(form), form))
    out.sort()
    return out


# ──────────────────────────────────────────────────────────────────
# Section locator handling (also absorbed from scripts/seed_terms.py)
# ──────────────────────────────────────────────────────────────────


_HEGEL_SECTION_RE = re.compile(r"^(?:(.+),\s*)?[¶§]\s*(\d+)\s*$")
_PARAGRAPH_LOCAL_RE = re.compile(r"^(\d+)\.[¶§](\d+)$")


def _section_payload(citation_system: str, section: str) -> dict[str, Any] | None:
    """Map a chunk's `section` string into a (payload, sort_key) pair
    suitable for term_occurrences. Returns None when no parser
    matches — the caller treats that as "skip this chunk."

    Parsers tried, in order:

    1. **Bekker** (Aristotle Perseus, `1094a` / `1094a13`) — via
       :func:`minerva.locations.parse_section`.
    2. **Paragraph-local** (First1KGreek `chapter.¶paragraph`, e.g.
       Aristotle Categories `1.¶1`).
    3. **Hegel paragraph** (`Vorrede, ¶1`, `A. Bewusstsein, ¶100`,
       bare `¶1`). The optional section prefix is preserved in the
       payload so the curator's locator carries semantic context; the
       sort key folds prefix + 5-digit paragraph for monotone ordering
       inside each prefix-bucket.
    4. The declared `citation_system` parser as a last resort — gives
       a clean error path for stephanus / kant_ab / sz_marginal /
       paragraph(§/¶) shapes that none of the above match.

    Bekker-first when the declared system is Bekker; otherwise
    paragraph-local first. Hegel-paragraph and the declared-system
    parser run after both fallbacks fail.
    """

    bekker_first = citation_system == "bekker"
    candidates = ("bekker", "paragraph_local") if bekker_first else ("paragraph_local", "bekker")
    for kind in candidates:
        if kind == "bekker":
            try:
                payload = locations.parse_section("bekker", section)
            except locations.LocationError:
                continue
            return {
                "payload": payload,
                "sort_key": locations.format_sort_key("bekker", payload),
            }
        m = _PARAGRAPH_LOCAL_RE.match(section)
        if m:
            chapter = int(m.group(1))
            paragraph = int(m.group(2))
            return {
                "payload": {
                    "kind": "paragraph",
                    "chapter": chapter,
                    "paragraph": paragraph,
                },
                "sort_key": f"v0:paragraph:{chapter:04d}.{paragraph:04d}",
            }

    # Hegel-style (optional prefix + paragraph marker). Catches both
    # `¶1` and `Vorrede, ¶1` / `A. Bewusstsein, ¶100`.
    m = _HEGEL_SECTION_RE.match(section)
    if m:
        prefix = (m.group(1) or "").strip()
        paragraph = int(m.group(2))
        payload = {"kind": "paragraph", "paragraph": paragraph}
        if prefix:
            payload["section"] = prefix
        # Prefix string is sorted lexically and is roughly in document
        # order for Hegel (Vorrede < Einleitung < A < B < C). Imperfect
        # but the Q2 ordering query only needs reasonable monotonicity
        # within a single work.
        return {
            "payload": payload,
            "sort_key": f"v0:paragraph:{prefix}::{paragraph:05d}",
        }

    try:
        payload = locations.parse_section(citation_system, section)
    except locations.LocationError:
        return None
    return {
        "payload": payload,
        "sort_key": locations.format_sort_key(citation_system, payload),
    }


def _context_snippet(text: str, start: int, end: int, *, radius: int = 40) -> str:
    """Whitespace-cleaned window around an occurrence."""

    return plain_window(text, start, end, radius=radius)


# ──────────────────────────────────────────────────────────────────
# Chunk lookups (private; tied to chunks_full view shape)
# ──────────────────────────────────────────────────────────────────


def _chunks_in_apply(conn: sqlite3.Connection, apply: WorkApply) -> list[str]:
    """All chunk_ids in `apply`'s edition. Cached lookup per apply so
    we don't re-query for every term."""

    rows = conn.execute(
        "SELECT chunk_id FROM chunks_full WHERE work = ? AND edition_id = ? ORDER BY ord",
        (apply.work_title, apply.edition_id),
    ).fetchall()
    return [r["chunk_id"] for r in rows]


# Stay under SQLite's historical 999-bound-variable cap (the limit on
# builds predating 3.32; modern builds allow ~32k but the old cap is
# the portable floor). Psalms alone spans ~2,500 chunks, so the
# IN-list must be batched.
_IN_LIST_BATCH = 900


def _chunk_rows(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[tuple[str, str, str]]:
    """Fetch (chunk_id, section, text) rows for the given ids, in
    ``ord`` order. Batches the IN-list so works larger than SQLite's
    bound-variable cap (e.g. Psalms ≈ 2,500 chunks) don't blow up."""

    if not chunk_ids:
        return []
    rows: list[sqlite3.Row] = []
    for i in range(0, len(chunk_ids), _IN_LIST_BATCH):
        batch = chunk_ids[i : i + _IN_LIST_BATCH]
        placeholders = ",".join("?" * len(batch))
        rows.extend(
            conn.execute(
                f"SELECT chunk_id, section, text, ord FROM chunks_full "
                f"WHERE chunk_id IN ({placeholders})",
                batch,
            ).fetchall()
        )
    rows.sort(key=lambda r: r["ord"])
    return [(r["chunk_id"], r["section"], r["text"]) for r in rows]


def _citation_system_for(conn: sqlite3.Connection, work_title: str) -> str:
    row = conn.execute(
        "SELECT citation_system FROM works WHERE title = ?", (work_title,)
    ).fetchone()
    if row is None:
        # If the work isn't in `works`, validate_against_db would have
        # caught it earlier. Default to 'paragraph' to give us *some*
        # path through `_section_payload`.
        return "paragraph"
    return str(row[0])
