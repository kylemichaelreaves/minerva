"""Load + validate a curator-authored YAML glossary spec.

A spec is one YAML file per author per language under ``data/glossary/``
(e.g. ``data/glossary/hegel.deu.yaml``). Each file lists `terms`, and
each term lists `apply_to` work targets carrying edition + translation
ids. The :class:`GlossarySpec` dataclass holds the parsed shape; the
glossary importer (`minerva.glossary_import`) consumes it and writes
to the DB.

Validation is intentionally strict: a typo in `edition_id` or a
language mismatch silently corrupting the term graph is the kind of
bug we want surfaced at import time, not when a curator wonders why
their occurrences disappeared.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """Raised when the YAML doesn't satisfy the schema."""


@dataclass(frozen=True)
class TranslationApply:
    """One per-translator rendering attached to an `apply_to` entry.

    Anchored by `translator` (matching `translations.translator_name`),
    optionally narrowed by `year` and `work` when one translator has
    rendered several works for the same author. `translation_id` is the
    numeric escape hatch and is also where
    :func:`resolve_against_db` writes the resolved id.
    """

    rendering: str
    translation_id: int | None = None
    translator_name: str | None = None
    year: int | None = None
    work_title: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class WorkApply:
    """One (work, edition) target a term should be applied to.

    Anchored by `work` + `edition` (matching `editions.name`), optionally
    narrowed by `edition_year`. `edition_id` is the numeric escape hatch
    and is also where :func:`resolve_against_db` writes the resolved id.

    `translations` is empty when no rendering data is supplied —
    fine for terms in works that have no English translation loaded
    (e.g. Kant KrV). The TermCard handles a missing renderings list
    via the sparse-grid layout.
    """

    work_title: str
    edition_id: int | None = None
    edition_name: str | None = None
    edition_year: int | None = None
    translations: tuple[TranslationApply, ...] = ()


@dataclass(frozen=True)
class RelatedLemma:
    """A pointer to another term by its lemma (resolved at import
    time against the source language of the parent term)."""

    lemma: str
    relation_kind: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Term:
    """One curated term. The matching key for occurrence-finding is
    `lemma`; the curator can supply `search_forms` as a fallback
    when the lemmatizer isn't available for the language (current
    state for grc) or when it misses (rare verb forms, proper nouns).
    """

    lemma: str
    source_form: str
    short_gloss: str
    long_description: str
    transliteration: str | None = None
    search_forms: tuple[str, ...] = ()
    apply_to: tuple[WorkApply, ...] = ()
    related: tuple[RelatedLemma, ...] = ()


@dataclass(frozen=True)
class GlossarySpec:
    """One parsed spec file. `language` and `author` are spec-level
    defaults — they apply to every term in `terms` unless the
    schema later grows per-term overrides (which it doesn't today)."""

    version: int
    language: str
    author: str
    terms: tuple[Term, ...] = field(default_factory=tuple)
    source_path: Path | None = None


# ──────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────


def load_spec(path: Path) -> GlossarySpec:
    """Parse and validate one YAML spec file. Raises :class:`SpecError`
    on any structural issue (missing required field, unknown key,
    duplicate term, malformed apply_to). DB-level cross-checks (does
    `edition_id` exist? does it belong to the named work?) happen in
    :func:`validate_against_db` so this function stays DB-free."""

    # Local import keeps `import minerva.glossary_spec` cheap on
    # plain installs that don't have the lemma extras.
    try:
        import yaml
    except ImportError as exc:
        raise SpecError(
            "PyYAML not installed; install the lemma extras: "
            "uv pip install -e '.[lemma]'"
        ) from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpecError(f"{path}: top-level must be a mapping")

    version = _require_int(data, "version", path)
    if version != 1:
        raise SpecError(f"{path}: unsupported version {version}; this build expects 1")
    language = _require_str(data, "language", path)
    author = _require_str(data, "author", path)
    raw_terms = data.get("terms", [])
    if not isinstance(raw_terms, list):
        raise SpecError(f"{path}: `terms` must be a list")

    seen_lemmas: set[str] = set()
    terms: list[Term] = []
    for i, t in enumerate(raw_terms):
        if not isinstance(t, dict):
            raise SpecError(f"{path}: terms[{i}] must be a mapping")
        term = _parse_term(t, path, i)
        if term.lemma in seen_lemmas:
            raise SpecError(
                f"{path}: duplicate lemma {term.lemma!r} at terms[{i}] — "
                "list each lemma once and use multiple apply_to entries"
            )
        seen_lemmas.add(term.lemma)
        terms.append(term)

    return GlossarySpec(
        version=version,
        language=language,
        author=author,
        terms=tuple(terms),
        source_path=path,
    )


def _parse_term(t: dict[str, Any], path: Path, idx: int) -> Term:
    """Pure parse step. No DB lookups; structural validation only."""

    where = f"{path}: terms[{idx}]"
    lemma = _require_str(t, "lemma", path, where)
    source_form = t.get("source_form") or lemma
    short_gloss = _require_str(t, "short_gloss", path, where)
    long_description = _require_str(t, "long_description", path, where)
    transliteration = t.get("transliteration")
    raw_search = t.get("search_forms", [])
    if not isinstance(raw_search, list):
        raise SpecError(f"{where}: search_forms must be a list")
    search_forms = tuple(str(s) for s in raw_search if s)

    raw_apply = t.get("apply_to", [])
    if not isinstance(raw_apply, list):
        raise SpecError(f"{where}: apply_to must be a list")
    apply_to = tuple(_parse_apply(a, path, idx, i) for i, a in enumerate(raw_apply))

    raw_related = t.get("related", [])
    if not isinstance(raw_related, list):
        raise SpecError(f"{where}: related must be a list")
    related = tuple(_parse_related(r, path, idx, i) for i, r in enumerate(raw_related))

    return Term(
        lemma=lemma,
        source_form=source_form,
        short_gloss=short_gloss,
        long_description=long_description,
        transliteration=transliteration,
        search_forms=search_forms,
        apply_to=apply_to,
        related=related,
    )


def _parse_apply(a: object, path: Path, term_idx: int, apply_idx: int) -> WorkApply:
    where = f"{path}: terms[{term_idx}].apply_to[{apply_idx}]"
    if not isinstance(a, dict):
        raise SpecError(f"{where}: must be a mapping")
    work_title = _require_str(a, "work", path, where)
    # Exactly one anchor. `edition` (the edition's name) is the natural
    # key and the one a curator should reach for; `edition_id` is a
    # surrogate that a re-ingest reshuffles (#193), kept only as an
    # escape hatch for genuinely ambiguous rows.
    edition_name = a.get("edition")
    has_id = "edition_id" in a
    if bool(edition_name) == has_id:
        raise SpecError(
            f"{where}: give exactly one of `edition:` (the edition name, "
            f"preferred) or `edition_id:` (numeric, reshuffled by "
            f"`index --reset`)"
        )
    edition_id = _require_int(a, "edition_id", path, where) if has_id else None
    if edition_name is not None and not isinstance(edition_name, str):
        raise SpecError(f"{where}: field 'edition' must be a string")
    edition_year = _optional_int(a, "edition_year", path, where)
    raw_translations = a.get("translations", [])
    if not isinstance(raw_translations, list):
        raise SpecError(f"{where}: translations must be a list")
    translations = tuple(
        _parse_translation(tr, path, term_idx, apply_idx, j)
        for j, tr in enumerate(raw_translations)
    )
    return WorkApply(
        work_title=work_title,
        edition_id=edition_id,
        edition_name=edition_name,
        edition_year=edition_year,
        translations=translations,
    )


def _parse_translation(
    tr: object,
    path: Path,
    term_idx: int,
    apply_idx: int,
    tr_idx: int,
) -> TranslationApply:
    where = (
        f"{path}: terms[{term_idx}].apply_to[{apply_idx}].translations[{tr_idx}]"
    )
    if not isinstance(tr, dict):
        raise SpecError(f"{where}: must be a mapping")
    translator_name = tr.get("translator")
    has_id = "id" in tr
    if bool(translator_name) == has_id:
        raise SpecError(
            f"{where}: give exactly one of `translator:` (the translator "
            f"name, preferred) or `id:` (numeric, reshuffled by "
            f"`index --reset`)"
        )
    translation_id = _require_int(tr, "id", path, where) if has_id else None
    if translator_name is not None and not isinstance(translator_name, str):
        raise SpecError(f"{where}: field 'translator' must be a string")
    rendering = _require_str(tr, "rendering", path, where)
    note = tr.get("note")
    if note is not None and not isinstance(note, str):
        raise SpecError(f"{where}: note must be a string or null")
    # `work` narrows the search when ingest filed a translation under its
    # own works row rather than the edition's — see the note in
    # `_resolve_translation`.
    work_title = tr.get("work")
    if work_title is not None and not isinstance(work_title, str):
        raise SpecError(f"{where}: field 'work' must be a string")
    return TranslationApply(
        translation_id=translation_id,
        translator_name=translator_name,
        year=_optional_int(tr, "year", path, where),
        work_title=work_title,
        rendering=rendering,
        note=note,
    )


def _parse_related(
    r: object,
    path: Path,
    term_idx: int,
    rel_idx: int,
) -> RelatedLemma:
    where = f"{path}: terms[{term_idx}].related[{rel_idx}]"
    if not isinstance(r, dict):
        raise SpecError(f"{where}: must be a mapping")
    lemma = _require_str(r, "lemma", path, where)
    relation_kind = r.get("relation_kind")
    if relation_kind is not None and not isinstance(relation_kind, str):
        raise SpecError(f"{where}: relation_kind must be a string or null")
    note = r.get("note")
    if note is not None and not isinstance(note, str):
        raise SpecError(f"{where}: note must be a string or null")
    return RelatedLemma(lemma=lemma, relation_kind=relation_kind, note=note)


def _require_str(d: dict[str, Any], key: str, path: Path, where: str = "") -> str:
    if key not in d:
        loc = where or str(path)
        raise SpecError(f"{loc}: missing required field {key!r}")
    val = d[key]
    if not isinstance(val, str) or not val.strip():
        loc = where or str(path)
        raise SpecError(f"{loc}: field {key!r} must be a non-empty string")
    return val


def _optional_int(d: dict[str, Any], key: str, path: Path, where: str) -> int | None:
    """``_require_int`` for keys that may be absent or explicitly null."""

    if key not in d or d[key] is None:
        return None
    return _require_int(d, key, path, where)


def _require_int(d: dict[str, Any], key: str, path: Path, where: str = "") -> int:
    if key not in d:
        loc = where or str(path)
        raise SpecError(f"{loc}: missing required field {key!r}")
    val = d[key]
    # YAML parses 1 as int but `version: "1"` as str — be strict.
    if isinstance(val, bool) or not isinstance(val, int):
        loc = where or str(path)
        raise SpecError(f"{loc}: field {key!r} must be an integer, got {type(val).__name__}")
    return val


# ──────────────────────────────────────────────────────────────────
# DB-level validation
# ──────────────────────────────────────────────────────────────────


def resolve_against_db(
    spec: GlossarySpec, conn: sqlite3.Connection
) -> tuple[GlossarySpec, list[str]]:
    """Turn every natural-key anchor in ``spec`` into the surrogate id it
    names, returning the filled-in spec plus any errors.

    This exists because the ids are not stable. `editions.id` and
    `translations.id` are assigned by insertion order, so
    ``minerva index --reset`` reshuffles them — which is how
    ``aristotle.grc.yaml``'s edition 58 came to name Homer's Iliad
    (#193). A spec that stores the id records where the work happened to
    sit; a spec that stores the name records which work the curator
    meant.

    Entries that already carry an explicit id are passed through
    untouched — the numeric form stays available for rows the natural
    key cannot separate. :func:`validate_against_db` then cross-checks
    those against the work they claim, which is the guard that kept the
    rotted ids from silently importing.
    """

    errors: list[str] = []
    resolved_terms: list[Term] = []
    for term in spec.terms:
        applies: list[WorkApply] = []
        for apply in term.apply_to:
            applies.append(_resolve_apply(conn, spec, term, apply, errors))
        resolved_terms.append(replace(term, apply_to=tuple(applies)))
    return replace(spec, terms=tuple(resolved_terms)), errors


def _resolve_apply(
    conn: sqlite3.Connection,
    spec: GlossarySpec,
    term: Term,
    apply: WorkApply,
    errors: list[str],
) -> WorkApply:
    """Resolve one apply_to target's edition and every rendering under it."""

    edition_id = apply.edition_id
    if edition_id is None:
        edition_id = _resolve_edition(conn, spec, term, apply, errors)
    translations = tuple(
        tr
        if tr.translation_id is not None
        else replace(
            tr,
            translation_id=_resolve_translation(conn, spec, term, apply, tr, errors),
        )
        for tr in apply.translations
    )
    return replace(apply, edition_id=edition_id, translations=translations)


def _resolve_edition(
    conn: sqlite3.Connection,
    spec: GlossarySpec,
    term: Term,
    apply: WorkApply,
    errors: list[str],
) -> int | None:
    """Look up ``editions.id`` from (author, work title, language, name).

    ``editions`` is UNIQUE (work_id, name, year), so a name is unique
    within a work unless the same edition was ingested under two years —
    which `edition_year` disambiguates.
    """

    rows = conn.execute(
        "SELECT e.id, e.year FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.author = ? AND w.title = ? AND e.language = ? AND e.name = ?",
        (spec.author, apply.work_title, spec.language, apply.edition_name),
    ).fetchall()
    if apply.edition_year is not None:
        rows = [r for r in rows if r["year"] == apply.edition_year]
    if len(rows) == 1:
        return int(rows[0]["id"])
    if not rows:
        available = conn.execute(
            "SELECT e.name, e.year FROM editions e JOIN works w ON w.id = e.work_id "
            "WHERE w.author = ? AND w.title = ? AND e.language = ? ORDER BY e.name",
            (spec.author, apply.work_title, spec.language),
        ).fetchall()
        errors.append(
            f"{term.lemma}: no {spec.language!r} edition named "
            f"{apply.edition_name!r} for {spec.author} — {apply.work_title}. "
            f"{_candidates('Editions in the DB', [(r['name'], r['year']) for r in available])}"
        )
        return None
    errors.append(
        f"{term.lemma}: {len(rows)} editions named {apply.edition_name!r} for "
        f"{spec.author} — {apply.work_title}; add `edition_year:` to pick one "
        f"({', '.join(str(r['year']) for r in rows)})"
    )
    return None


def _resolve_translation(
    conn: sqlite3.Connection,
    spec: GlossarySpec,
    term: Term,
    apply: WorkApply,
    tr: TranslationApply,
    errors: list[str],
) -> int | None:
    """Look up ``translations.id`` from (author, translator name, …).

    Searched work-first, then author-wide. The fallback is not laziness:
    ingest predating the glossary sometimes files a translation under its
    OWN ``works`` row rather than the edition's — work 127 "Phenomenology
    of Spirit (Pinkard)" sits beside work 130 "Phänomenologie des
    Geistes" — so a translation is often not under the work title its
    edition uses. That is the same asymmetry
    :func:`validate_against_db` documents when it declines to cross-check
    ``translation.work_id``.

    An author-wide match that finds several rows is reported rather than
    guessed; the curator adds `work:` or `year:` to say which.
    """

    scoped_title = tr.work_title or apply.work_title
    rows = _translation_rows(conn, spec.author, tr.translator_name, tr.year, scoped_title)
    if not rows and tr.work_title is None:
        rows = _translation_rows(conn, spec.author, tr.translator_name, tr.year, None)
    if len(rows) == 1:
        return int(rows[0]["id"])
    if not rows:
        available = conn.execute(
            "SELECT DISTINCT t.translator_name AS name, t.year FROM translations t "
            "JOIN works w ON w.id = t.work_id WHERE w.author = ? ORDER BY name",
            (spec.author,),
        ).fetchall()
        errors.append(
            f"{term.lemma}: no translation by {tr.translator_name!r} for "
            f"{spec.author}. "
            f"{_candidates('Translators in the DB', [(r['name'], r['year']) for r in available])}"
        )
        return None
    errors.append(
        f"{term.lemma}: {len(rows)} translations by {tr.translator_name!r} for "
        f"{spec.author}; add `work:` or `year:` to pick one ("
        + ", ".join(f"{r['title']} {r['year']}" for r in rows)
        + ")"
    )
    return None


def _translation_rows(
    conn: sqlite3.Connection,
    author: str,
    translator_name: str | None,
    year: int | None,
    work_title: str | None,
) -> list[sqlite3.Row]:
    sql = (
        "SELECT t.id, t.year, w.title FROM translations t "
        "JOIN works w ON w.id = t.work_id "
        "WHERE w.author = ? AND t.translator_name = ?"
    )
    params: list[object] = [author, translator_name]
    if work_title is not None:
        sql += " AND w.title = ?"
        params.append(work_title)
    if year is not None:
        sql += " AND t.year IS ?"
        params.append(year)
    return list(conn.execute(sql, params).fetchall())


def _candidates(label: str, rows: list[tuple[str, int | None]], limit: int = 8) -> str:
    """Render the near-miss list that turns 'not found' into 'here is
    what you probably meant' — these names are long and easy to mistype
    ('Aristotle in 23 Volumes, Vol. 19, translated by H. Rackham.')."""

    if not rows:
        return f"{label}: (none)."
    shown = ", ".join(f"{name!r} ({year})" for name, year in rows[:limit])
    more = f" … and {len(rows) - limit} more" if len(rows) > limit else ""
    return f"{label}: {shown}{more}."


def resolve_and_validate(
    spec: GlossarySpec, conn: sqlite3.Connection
) -> tuple[GlossarySpec, list[str]]:
    """Resolve natural-key anchors, then cross-check the result.

    The importer needs the resolved spec, not just the verdict — this is
    the entry point ``minerva terms import`` uses. Returns the spec with
    every ``edition_id`` / ``translation_id`` filled in, plus the errors
    from both passes. A non-empty error list means some ids are ``None``
    and the spec must not be imported.
    """

    resolved, errors = resolve_against_db(spec, conn)
    errors.extend(_validate_resolved(resolved, conn))
    return resolved, errors


def validate_against_db(spec: GlossarySpec, conn: sqlite3.Connection) -> list[str]:
    """The errors from :func:`resolve_and_validate`, for callers that
    want the verdict without the resolved spec."""

    return resolve_and_validate(spec, conn)[1]


def _validate_resolved(spec: GlossarySpec, conn: sqlite3.Connection) -> list[str]:
    """Cross-check a RESOLVED spec against ``works``/``editions``/
    ``translations`` rows. Returns a list of human-readable errors; empty
    list means the spec can be imported safely. Does not raise — the
    caller (CLI or test) decides whether to abort or proceed."""

    errors: list[str] = []
    for term in spec.terms:
        for apply in term.apply_to:
            if apply.edition_id is None:
                # Resolution already reported why, with candidates.
                continue
            ed = conn.execute(
                "SELECT e.id, e.language, w.title FROM editions e "
                "JOIN works w ON w.id = e.work_id WHERE e.id = ?",
                (apply.edition_id,),
            ).fetchone()
            if ed is None:
                errors.append(
                    f"{term.lemma}: edition_id {apply.edition_id} does not exist"
                )
                continue
            if ed["language"] != spec.language:
                errors.append(
                    f"{term.lemma}: edition {apply.edition_id} is "
                    f"{ed['language']!r}, spec language is {spec.language!r}"
                )
            if ed["title"] != apply.work_title:
                errors.append(
                    f"{term.lemma}: edition {apply.edition_id} belongs to "
                    f"{ed['title']!r}, spec says {apply.work_title!r}"
                )
            for tr in apply.translations:
                if tr.translation_id is None:
                    continue
                trow = conn.execute(
                    "SELECT t.id, t.work_id, w.title FROM translations t "
                    "JOIN works w ON w.id = t.work_id WHERE t.id = ?",
                    (tr.translation_id,),
                ).fetchone()
                if trow is None:
                    errors.append(
                        f"{term.lemma}: translation_id {tr.translation_id} does not exist"
                    )
                    continue
                # Existence-only — we deliberately do NOT require
                # `translation.work_id == apply.work_id`. The corpus
                # ingest predating this importer often creates a
                # separate `works` row per translation (e.g. work 127
                # "Phenomenology of Spirit (Pinkard)" sibling to work
                # 130 "Phänomenologie des Geistes"). Rejecting that
                # would make rendering grids unbuildable for affected
                # German Hegel works. The curator's explicit
                # `translation.id` carries enough intent.
                #
                # Note this is why a rotted `translation_id` is worse
                # than a rotted `edition_id`: no cross-check catches it,
                # so it imports silently as a wrong rendering. Anchoring
                # on `translator:` is the fix — the name cannot rot.
    return errors


def load_specs(paths: Sequence[Path]) -> list[GlossarySpec]:
    """Parse multiple files in one call. Lemmas are required to be
    unique within a file; the importer further deduplicates across
    files via the (source_form, source_language) DB upsert."""

    return [load_spec(p) for p in paths]
