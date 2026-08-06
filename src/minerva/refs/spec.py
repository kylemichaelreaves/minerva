"""Curator-authored YAML spec for hand-curated cross-references.

A spec is one YAML file under ``data/glossary/refs/`` (e.g.
``data/glossary/refs/aquinas.yaml``). Each file lists ``references``;
each reference identifies a source chunk + a target + a kind. Loaded
via ``minerva refs load-spec`` (see ``cli/refs/load_spec.py``).

Spec shape (version 1):

    version: 1
    references:
      - source:
          # one of:
          chunk_id: "<content-hash>"
          # OR:
          work: "Summa Theologiae"
          lang: lat
          section: "ST I, q. 84, a. 7"
        target:
          author: Aristotle
          work: "De anima"
          # optional in-corpus chunk:
          chunk_id: "<content-hash>"
          # OR locator + sort-key:
          locator: "III.7"
          locator_payload: { book: 3, chapter: 7 }
        type: cites          # see _ALLOWED_TYPES
        quoted_phrase: "phantasmata"
        source_form: "Philosophus"
        note: "the locus classicus on Aquinas's appropriation…"

This module is structural validation only — no DB access. The CLI
loader (``cli/refs/load_spec.py``) resolves source / target ids
against the live DB at insert time.

Mirrors the shape of ``glossary_spec.py`` (single version field,
strict-int / strict-str helpers, ``SpecError`` for any structural
issue surfaced at load time rather than at insert time).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ALLOWED_TYPES: frozenset[str] = frozenset(
    {
        "cites",
        "quotes",
        "paraphrases",
        "alludes",
        "comments_on",
        "translates",
        "disputes",
        "corrects",
    }
)


class SpecError(ValueError):
    """Raised when the YAML doesn't satisfy the cross-reference schema."""


@dataclass(frozen=True)
class SourceRef:
    """How a spec identifies the source chunk. Exactly one of
    ``chunk_id`` or the ``(work, lang, section)`` triple must be set —
    the loader will resolve to a chunk_id at insert time when the
    triple form is used."""

    chunk_id: str | None
    work: str | None
    lang: str | None
    section: str | None


@dataclass(frozen=True)
class TargetRef:
    """How a spec identifies the reference target. The (author, work)
    pair resolves to a ``reference_targets`` row (auto-created on
    first use). The optional ``chunk_id`` / ``locator`` /
    ``locator_payload`` carry more specific intra-target addressing
    when known."""

    author: str
    work: str
    chunk_id: str | None
    locator: str | None
    locator_payload: dict[str, Any] | None
    sort_key: str | None


@dataclass(frozen=True)
class ReferenceSpec:
    """One spec entry (one cross_references row, post-insert)."""

    source: SourceRef
    target: TargetRef
    type: str
    quoted_phrase: str | None = None
    source_form: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CrossRefSpec:
    """One parsed spec file."""

    version: int
    references: tuple[ReferenceSpec, ...] = field(default_factory=tuple)
    source_path: Path | None = None


# ──────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────


def load_spec(path: Path) -> CrossRefSpec:
    """Parse + validate one YAML spec file. Raises :class:`SpecError`
    on any structural issue. DB-level validation (does the source
    chunk_id exist? does the target work resolve?) happens at insert
    time in the CLI."""

    try:
        import yaml
    except ImportError as exc:
        raise SpecError(
            "PyYAML not installed; install the lemma extras: uv pip install -e '.[lemma]'"
        ) from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpecError(f"{path}: top-level must be a mapping")

    version = _require_int(data, "version", path)
    if version != 1:
        raise SpecError(f"{path}: unsupported version {version}; this build expects 1")

    raw_refs = data.get("references", [])
    if not isinstance(raw_refs, list):
        raise SpecError(f"{path}: `references` must be a list")

    parsed: list[ReferenceSpec] = []
    for i, r in enumerate(raw_refs):
        if not isinstance(r, dict):
            raise SpecError(f"{path}: references[{i}] must be a mapping")
        parsed.append(_parse_reference(r, path, i))

    return CrossRefSpec(
        version=version,
        references=tuple(parsed),
        source_path=path,
    )


def load_specs(paths: Sequence[Path]) -> list[CrossRefSpec]:
    """Parse multiple files in one call. References are NOT required
    to be unique across files at parse time — the DB-side shadow
    UNIQUE handles dedup at insert time."""

    return [load_spec(p) for p in paths]


# ──────────────────────────────────────────────────────────────────
# Per-reference parsing
# ──────────────────────────────────────────────────────────────────


def _parse_reference(r: dict[str, Any], path: Path, idx: int) -> ReferenceSpec:
    where = f"{path}: references[{idx}]"

    raw_source = r.get("source")
    if not isinstance(raw_source, dict):
        raise SpecError(f"{where}: `source` must be a mapping")
    source = _parse_source(raw_source, path, where)

    raw_target = r.get("target")
    if not isinstance(raw_target, dict):
        raise SpecError(f"{where}: `target` must be a mapping")
    target = _parse_target(raw_target, path, where)

    ref_type = _require_str(r, "type", path, where)
    if ref_type not in _ALLOWED_TYPES:
        raise SpecError(f"{where}: type {ref_type!r} not in {sorted(_ALLOWED_TYPES)}")

    quoted_phrase = _optional_str(r, "quoted_phrase", path, where)
    source_form = _optional_str(r, "source_form", path, where)
    note = _optional_str(r, "note", path, where)

    return ReferenceSpec(
        source=source,
        target=target,
        type=ref_type,
        quoted_phrase=quoted_phrase,
        source_form=source_form,
        note=note,
    )


def _parse_source(d: dict[str, Any], path: Path, parent_where: str) -> SourceRef:
    """Source must be either { chunk_id: "..." } OR
    { work: ..., lang: ..., section: ... }. Mixing the two is allowed
    (chunk_id takes precedence at resolve time), but neither shape is
    not allowed."""

    where = f"{parent_where}.source"
    chunk_id = _optional_str(d, "chunk_id", path, where)
    work = _optional_str(d, "work", path, where)
    lang = _optional_str(d, "lang", path, where)
    section = _optional_str(d, "section", path, where)

    has_chunk = chunk_id is not None
    has_triple = bool(work and lang and section)
    if not (has_chunk or has_triple):
        raise SpecError(
            f"{where}: must provide either `chunk_id` OR all of (`work`, `lang`, `section`)"
        )

    return SourceRef(chunk_id=chunk_id, work=work, lang=lang, section=section)


def _parse_target(d: dict[str, Any], path: Path, parent_where: str) -> TargetRef:
    """Target must always carry (author, work). Optional addressing:
    chunk_id (a specific in-corpus chunk), locator (a citation string),
    locator_payload (parsed locator JSON)."""

    where = f"{parent_where}.target"
    author = _require_str(d, "author", path, where)
    work = _require_str(d, "work", path, where)
    chunk_id = _optional_str(d, "chunk_id", path, where)
    locator = _optional_str(d, "locator", path, where)
    sort_key = _optional_str(d, "sort_key", path, where)

    raw_payload = d.get("locator_payload")
    if raw_payload is not None and not isinstance(raw_payload, dict):
        raise SpecError(f"{where}: locator_payload must be a mapping or null")
    locator_payload: dict[str, Any] | None = raw_payload  # type: ignore[assignment]

    return TargetRef(
        author=author,
        work=work,
        chunk_id=chunk_id,
        locator=locator,
        locator_payload=locator_payload,
        sort_key=sort_key,
    )


# ──────────────────────────────────────────────────────────────────
# Tiny strict-type helpers (mirrors glossary_spec.py)
# ──────────────────────────────────────────────────────────────────


def _require_str(d: dict[str, Any], key: str, path: Path, where: str = "") -> str:
    if key not in d:
        loc = where or str(path)
        raise SpecError(f"{loc}: missing required field {key!r}")
    val = d[key]
    if not isinstance(val, str) or not val.strip():
        loc = where or str(path)
        raise SpecError(f"{loc}: field {key!r} must be a non-empty string")
    return val


def _optional_str(d: dict[str, Any], key: str, path: Path, where: str = "") -> str | None:
    if key not in d:
        return None
    val = d[key]
    if val is None:
        return None
    if not isinstance(val, str):
        loc = where or str(path)
        raise SpecError(f"{loc}: field {key!r} must be a string or null")
    return val if val.strip() else None


def _require_int(d: dict[str, Any], key: str, path: Path, where: str = "") -> int:
    if key not in d:
        loc = where or str(path)
        raise SpecError(f"{loc}: missing required field {key!r}")
    val = d[key]
    if isinstance(val, bool) or not isinstance(val, int):
        loc = where or str(path)
        raise SpecError(f"{loc}: field {key!r} must be an integer, got {type(val).__name__}")
    return val
