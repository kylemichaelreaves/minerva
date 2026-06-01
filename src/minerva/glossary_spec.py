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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """Raised when the YAML doesn't satisfy the schema."""


@dataclass(frozen=True)
class TranslationApply:
    """One per-translator rendering attached to an `apply_to` entry."""

    translation_id: int
    rendering: str
    note: str | None = None


@dataclass(frozen=True)
class WorkApply:
    """One (work, edition) target a term should be applied to.

    `translations` is empty when no rendering data is supplied —
    fine for terms in works that have no English translation loaded
    (e.g. Kant KrV). The TermCard handles a missing renderings list
    via the sparse-grid layout.
    """

    work_title: str
    edition_id: int
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
    edition_id = _require_int(a, "edition_id", path, where)
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
    translation_id = _require_int(tr, "id", path, where)
    rendering = _require_str(tr, "rendering", path, where)
    note = tr.get("note")
    if note is not None and not isinstance(note, str):
        raise SpecError(f"{where}: note must be a string or null")
    return TranslationApply(translation_id=translation_id, rendering=rendering, note=note)


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


def validate_against_db(spec: GlossarySpec, conn: sqlite3.Connection) -> list[str]:
    """Cross-check the spec against ``works``/``editions``/``translations``
    rows. Returns a list of human-readable errors; empty list means the
    spec can be imported safely. Does not raise — the caller (CLI or
    test) decides whether to abort or proceed."""

    errors: list[str] = []
    conn.row_factory = sqlite3.Row
    for term in spec.terms:
        for apply in term.apply_to:
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
    return errors


def load_specs(paths: Sequence[Path]) -> list[GlossarySpec]:
    """Parse multiple files in one call. Lemmas are required to be
    unique within a file; the importer further deduplicates across
    files via the (source_form, source_language) DB upsert."""

    return [load_spec(p) for p in paths]
