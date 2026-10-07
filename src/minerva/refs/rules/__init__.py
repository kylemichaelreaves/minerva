"""Rule-based cross-reference detection (Phase 2).

Per-author rule modules live in this package (``aquinas.py``,
``augustine.py``, ``hegel.py``, ``spinoza.py``, ``kant.py``). Each
module exports a ``RULES: tuple[Rule, ...]`` constant — rules that
apply when the source author matches the module name. The shared
runner (:func:`apply_rules_to_chunk`) dispatches a chunk to the
correct module based on its ``author``.

Phase 2 rule families:

* :class:`AuthorMentionRule` — fires on any of a configured set of
  surface forms (Latin declensions, German conjugations, Greek
  morphology). Weak by itself (`source_method='rule_weak'`,
  confidence around 0.4–0.55); a curator review pass + the embedding
  / LLM verifier (Phases 3–4) is what promotes the strong ones.

* :class:`StrongMentionRule` — a name-mention rule for a high-
  confidence convention (Aquinas's "Philosophus" → Aristotle,
  Spinoza's "Cartesius" → Descartes). Stronger than the surface-form
  default because the convention itself is unambiguous within its
  corpus.

Additional rule shapes (work-title proximity, Bekker / Stephanus /
KrV locator regex, Aristotle commentary structural hook) are sketched
in the cross-reference plan and arrive incrementally — the framework
in this module is designed to accept them without refactor.

Output format: every rule emits ``Candidate`` rows. The runner pipes
them through :func:`upsert_candidate` (or its id-returning wrapper
:func:`insert_candidate`) which:

* resolves the target via :func:`refs.schema.ensure_target` (creates
  the ``reference_targets`` row on first use; auto-links to a
  ``works`` row when the (author, work) pair matches);
* dedupes against existing rows with the same logical content key
  (``source_chunk_id``, ``target_id``, ``reference_type``,
  ``source_form_snapshot``, ``quoted_phrase``) so re-running the
  rules doesn't accrete duplicate auto-rows alongside curator-
  approved ones — and refreshes a matched row instead of leaving it:
  an unverified rule-tier row takes the rule's current confidence and
  tier (#518), a stale span moves to the candidate's (#715);
* inserts via :func:`refs.schema.insert_cross_reference` with
  ``curator_status='auto'`` and the rule-supplied confidence /
  source_method.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any, Protocol

from .. import schema as refs_schema

# ──────────────────────────────────────────────────────────────────
# Candidate shape
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """One rule-flagged candidate cross-reference. The runner converts
    these into ``cross_references`` rows after target resolution + dedup.

    All fields mirror the corresponding columns on ``cross_references``
    plus the convenience pair (``target_author``, ``target_work``) used
    by :func:`refs.schema.ensure_target` to resolve / create the
    reference_targets row.
    """

    source_chunk_id: str
    source_span_start: int | None
    source_span_end: int | None
    source_form_snapshot: str | None
    target_author: str
    target_work: str
    target_locator: str | None
    reference_type: str
    confidence: float
    source_method: str  # 'rule_weak' | 'rule_strong'
    quoted_phrase: str | None = None
    note: str | None = None
    # When non-None, the rule is making a definitional chunk-level
    # claim (e.g. "Matth. 5-48" → the exact Vulgate Matt 5:48 chunk).
    # When None and ``target_locator`` is set, `insert_candidate`
    # tries to resolve a matching chunk via (target_author,
    # target_work, target_locator); a miss leaves the field NULL and
    # downstream verifiers can take a shot.
    target_chunk_id: str | None = None


# ──────────────────────────────────────────────────────────────────
# Rule protocol
# ──────────────────────────────────────────────────────────────────


class Rule(Protocol):
    """A rule that emits :class:`Candidate` objects for one chunk.

    Implementations are typically dataclass-style configuration with a
    :meth:`scan` method. The runner dispatches per chunk based on the
    chunk's source author; the rule itself is language-aware (most
    Latin rules don't apply to a German chunk and vice versa) via the
    ``langs`` attribute on the concrete rule classes.
    """

    name: str

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]: ...


@dataclass(frozen=True)
class ChunkInfo:
    """The minimum chunk metadata a rule needs. Built once per chunk
    by the runner and passed to every applicable rule, so the
    per-row DB lookups happen once per chunk rather than per rule."""

    chunk_id: str
    author: str
    work: str
    lang: str
    section: str | None
    text: str


# ──────────────────────────────────────────────────────────────────
# Rule classes — author-mention + strong-mention
# ──────────────────────────────────────────────────────────────────


# Compile pattern with case-sensitivity off by default for Latin and
# German (where capitalization on proper nouns is meaningful but not
# reliable across editions). Each rule can override.
#
# The cache keys on the full (forms, ignore_case) input, so two rules
# that happen to share a name but differ in forms can never silently
# share whichever pattern compiled first.
@cache
def _compile_forms(forms: tuple[str, ...], *, ignore_case: bool) -> re.Pattern[str]:
    # Longest alternative first — re alternation is first-match-wins,
    # so without the sort a shorter form ("Locke") would shadow a
    # longer one ("Locke's") and the span snapshot would under-cover.
    #
    # Leading word-boundary plus trailing `(?!\w)` so "Philosophus"
    # doesn't match inside "Philosophusculus". A trailing `\b` would
    # be wrong here: it makes apostrophe-final forms ("Sokrates'")
    # unmatchable before a space (no word/non-word transition after
    # the apostrophe), while `(?!\w)` accepts them. The boundary
    # metachars are unicode-aware in Python's re — works for Greek too.
    body = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(rf"\b(?:{body})(?!\w)", flags)


@dataclass(frozen=True)
class AuthorMentionRule:
    """Fires when any of ``forms`` appears in the chunk text — the
    standard "author-name surface forms" rule from the plan.

    Yields one :class:`Candidate` per textual match. Confidence
    defaults to 0.45 (low — name-mention without further evidence is
    a weak signal; the curator review pass and the embedding /
    LLM verifier filter the noise). Override on a per-rule basis when
    the surface form is unambiguous within its source corpus.
    """

    name: str
    target_author: str
    forms: tuple[str, ...]
    target_work: str = ""  # empty = "no specific work known"; ensure_target falls back to "*"
    reference_type: str = "cites"
    confidence: float = 0.45
    source_method: str = "rule_weak"
    langs: tuple[str, ...] = ()  # empty = all languages
    ignore_case: bool = False
    note: str | None = None

    def _pattern(self) -> re.Pattern[str]:
        # re.Pattern isn't hashable so it can't live on the frozen
        # dataclass; `_compile_forms` is cached on the inputs,
        # making this a dict lookup after the first scan.
        return _compile_forms(self.forms, ignore_case=self.ignore_case)

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Target-author self-reference: if this rule's target matches
        # the chunk's own author, skip — we don't want to surface
        # "Augustine quotes Augustine" or similar self-mentions.
        if self.target_author == chunk.author:
            return
        for m in self._pattern().finditer(chunk.text):
            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_author,
                target_work=self.target_work,
                target_locator=None,
                reference_type=self.reference_type,
                confidence=self.confidence,
                source_method=self.source_method,
                note=self.note,
            )


@dataclass(frozen=True)
class StrongMentionRule(AuthorMentionRule):
    """Same shape as :class:`AuthorMentionRule` but defaults to
    `source_method='rule_strong'` and a higher confidence.

    The plan calls these out for unambiguous corpus-internal
    conventions: Aquinas's "Philosophus" almost always means
    Aristotle; Spinoza's "Cartesius" always means Descartes. The
    convention itself is the signal, not just the name.
    """

    confidence: float = 0.92
    source_method: str = "rule_strong"


# ──────────────────────────────────────────────────────────────────
# Per-chunk dispatch
# ──────────────────────────────────────────────────────────────────


# Lazy import to avoid a top-level cycle (the per-author modules
# import Rule classes from this module). Populated on first call.
_AUTHOR_RULES_CACHE: dict[str, tuple[Rule, ...]] = {}


def _rules_for_author(author: str) -> tuple[Rule, ...]:
    cached = _AUTHOR_RULES_CACHE.get(author)
    if cached is not None:
        return cached

    from .loader import load_author_rules_from_yaml, spec_path_for_author

    module_name = author.lower().replace(" ", "_")
    yaml_path = spec_path_for_author(author)
    try:
        mod = __import__(f"minerva.refs.rules.{module_name}", fromlist=["RULES"])
    except ImportError:
        mod = None
    if yaml_path.is_file() and mod is not None:
        # A YAML spec used to silently win over the .py module — a
        # 4-rule proof-of-concept hegel.yaml shadowed the 31-rule
        # hegel.py for every rescan. The YAML loader also can't express
        # everything the modules can (strong rules, per-rule langs,
        # source_method), so coexistence is always a mistake.
        raise RuntimeError(
            f"refs rules for {author!r} are defined twice: "
            f"specs/{yaml_path.name} and rules/{module_name}.py — "
            "delete one of them"
        )
    if yaml_path.is_file():
        rules = load_author_rules_from_yaml(yaml_path, prefix=module_name)
    elif mod is not None:
        rules = tuple(getattr(mod, "RULES", ()))
    else:
        rules = ()

    _AUTHOR_RULES_CACHE[author] = rules
    return rules


# Fingerprints are pure functions of the rule tuple, but computing one
# walks every rule's fields, class config and referenced module globals.
# `record_scan_state` asks for it once per 500-chunk flush, so it is
# cached beside the rules themselves rather than recomputed.
_RULES_FINGERPRINT_CACHE: dict[str, str] = {}


def rules_fingerprint(author: str) -> str:
    """Hex digest of the compiled rule set that applies to ``author``.

    Stored per chunk in ``refs_scan_state.rules_hash`` and compared on
    the next scan, so that editing a rules module invalidates exactly
    the chunks that module can match — instead of nothing, which is
    what the text-hash-only predicate did (#287). See
    :mod:`refs.rules.fingerprint` for what the digest covers.
    """

    cached = _RULES_FINGERPRINT_CACHE.get(author)
    if cached is not None:
        return cached

    from .fingerprint import fingerprint_rules

    fp = fingerprint_rules(_rules_for_author(author))
    _RULES_FINGERPRINT_CACHE[author] = fp
    return fp


def _reset_rules_caches() -> None:
    """Drop both memo caches. For tests that install or edit rule
    modules mid-process — the fingerprint is derived from the rules, so
    clearing one without the other leaves them disagreeing."""

    _AUTHOR_RULES_CACHE.clear()
    _RULES_FINGERPRINT_CACHE.clear()


def apply_rules_to_chunk(chunk: ChunkInfo) -> list[Candidate]:
    """Dispatch one chunk to its source-author's rule module + collect
    every candidate. Idempotent given identical chunk input — rule
    pattern matching is content-pure, no DB state."""

    rules = _rules_for_author(chunk.author)
    out: list[Candidate] = []
    for rule in rules:
        out.extend(rule.scan(chunk))
    return out


# ──────────────────────────────────────────────────────────────────
# Insert with content-key dedup
# ──────────────────────────────────────────────────────────────────


def insert_candidate(
    conn: sqlite3.Connection,
    cand: Candidate,
    *,
    skip_if_manual_exists: bool = True,
) -> int | None:
    """Resolve the candidate's target + insert it as a cross-reference
    row with ``curator_status='auto'``. Returns the new row id, or
    ``None`` when a content-equivalent row already exists (which
    :func:`upsert_candidate` may have refreshed — #518)."""

    outcome, row_id = upsert_candidate(conn, cand, skip_if_manual_exists=skip_if_manual_exists)
    return row_id if outcome == "inserted" else None


# Tiers a rule wrote and nothing has verified since. Only these follow a
# re-tuned rule: a verifier's tier records a judgement the rule cannot
# overrule, and refreshing one would downgrade it back into the
# llm-verify queue — 11,265 rows key-matched a candidate when #518 was
# measured.
_RULE_TIERS = frozenset({"rule_strong", "rule_weak"})


def upsert_candidate(
    conn: sqlite3.Connection,
    cand: Candidate,
    *,
    insert: bool = True,
    skip_if_manual_exists: bool = True,
) -> tuple[str, int | None]:
    """Insert ``cand``, or refresh the row it matches. Returns
    ``(outcome, row_id)``, outcome one of ``inserted``, ``refreshed``,
    ``unchanged``, ``blocked`` (a curator row at the site), or ``absent``
    (no match and ``insert=False``).

    A matched row is refreshed in two independent ways (#518, #715):

    * **Verdict columns** — ``confidence`` and ``source_method`` follow
      the rule when the row is still a rule's own: rule tier,
      ``curator_status='auto'``, no ``curated_by``, and the candidate is
      itself a rule's. Before this, a re-tuned rule corrected new rows
      and left old ones at the old value forever (510 rows, #518).
    * **Span** — moved to the candidate's when the stored slice of the
      chunk no longer reads the snapshot *and* the candidate's does.
      A span is a fact about the text, not a verdict, so this applies to
      verified rows too; the two-part test keeps a span that sits on a
      repeated occurrence of the form from churning.

    ``insert=False`` is the refresh-only backfill mode: nothing new is
    written, so a rescan cannot add the duplicates #801 describes.

    Dedup key: ``(source_chunk_id, target_id, reference_type,
    source_form_snapshot, quoted_phrase, target_chunk_id)`` with
    NULL-safe equality. ``target_chunk_id`` is included so author-level
    allusion candidates that share every other field don't collapse to
    a single row (issue #44). This means a curator-approved manual row
    at the same logical site is preserved unchanged
    and we don't grow a parallel auto-row alongside it on every
    `refs build` run — the curator's work survives subsequent passes.

    ``skip_if_manual_exists`` is the default but can be set False by
    callers that explicitly want every rule match recorded (e.g. a
    detection-quality eval pass)."""

    target = refs_schema.ensure_target(
        conn,
        canonical_author=cand.target_author,
        # ensure_target requires non-empty work text; fall back to
        # the author's "*" wildcard when the rule didn't know which
        # work to attach. This creates ("Aristotle", "*") rows for
        # bare Philosophus mentions — those can be refined later when
        # a locator-validating rule attaches the specific work.
        canonical_work=cand.target_work or "*",
    )

    # Definitional chunk-level resolution: when the rule names a
    # specific locator (scripture cites: "Matth. 5-48" → Matt 5:48),
    # bind the target chunk_id by exact (author, work, section)
    # lookup. A miss is fine — leave NULL and downstream
    # embed/llm verifiers can take a shot.
    bound_chunk_id = cand.target_chunk_id
    if bound_chunk_id is None and cand.target_locator and cand.target_work:
        row = conn.execute(
            "SELECT chunk_id FROM chunks_full "
            "WHERE author = ? AND work = ? AND section = ? "
            # Deterministic pick when a (author, work, section) maps to
            # more than one chunk, so re-runs bind the same chunk_id and
            # don't grow parallel auto-rows through the dedup key below.
            "ORDER BY chunk_id LIMIT 1",
            (cand.target_author, cand.target_work, cand.target_locator),
        ).fetchone()
        if row is not None:
            bound_chunk_id = row[0]

    # ``target_chunk_id`` is part of the dedup identity: author-level
    # allusion candidates (target_work="*") share target_id / type /
    # NULL form / NULL phrase and would otherwise collapse to one row,
    # dropping the other top-k chunk matches (issue #44). Including the
    # bound chunk keeps distinct target chunks distinct; it can only
    # make rows MORE distinct, never merge previously-separate ones.
    existing = conn.execute(
        "SELECT id FROM cross_references "
        "WHERE source_chunk_id = ? "
        "  AND target_id = ? "
        "  AND reference_type = ? "
        "  AND source_form_snapshot IS ? "
        "  AND quoted_phrase IS ? "
        "  AND target_chunk_id IS ?",
        (
            cand.source_chunk_id,
            target.id,
            cand.reference_type,
            cand.source_form_snapshot,
            cand.quoted_phrase,
            bound_chunk_id,
        ),
    ).fetchone()
    if existing is not None:
        return (
            "refreshed" if _refresh_matched(conn, existing[0], cand) else "unchanged"
        ), existing[0]
    if not insert:
        return "absent", None

    if skip_if_manual_exists:
        # Block auto rows that overlap a curator's manual entry even
        # if the source_form differs slightly — same chunk + same
        # target + same type with curator_status manual/approved wins.
        manual = conn.execute(
            "SELECT id FROM cross_references "
            "WHERE source_chunk_id = ? "
            "  AND target_id = ? "
            "  AND reference_type = ? "
            "  AND curator_status IN ('manual', 'approved')",
            (
                cand.source_chunk_id,
                target.id,
                cand.reference_type,
            ),
        ).fetchone()
        if manual is not None:
            return "blocked", None

    # cand.note is rule-level documentation (a one-line description of the
    # rule's intent, e.g. "Aquinas cites Augustine constantly across ST and
    # SCG"). It's the same string across every row a rule produces, so
    # stamping it into curator_note creates thousands of duplicate notes
    # in the corpus browser. The note belongs in the rule definition as a
    # code comment — not in row data. The LLM verifier writes a genuinely
    # per-row observation to curator_note in Phase 4; hand-curated rows
    # have their own per-row notes from the YAML spec.
    new_id = refs_schema.insert_cross_reference(
        conn,
        source_chunk_id=cand.source_chunk_id,
        target_id=target.id,
        target_chunk_id=bound_chunk_id,
        target_locator=cand.target_locator,
        reference_type=cand.reference_type,
        source_span_start=cand.source_span_start,
        source_span_end=cand.source_span_end,
        source_form_snapshot=cand.source_form_snapshot,
        quoted_phrase=cand.quoted_phrase,
        confidence=cand.confidence,
        source_method=cand.source_method,
        curator_status="auto",
        curator_note=None,
    )
    return "inserted", new_id


def _refresh_matched(conn: sqlite3.Connection, row_id: int, cand: Candidate) -> bool:
    """Apply :func:`upsert_candidate`'s two refreshes to a matched row.
    Returns whether anything changed."""

    row = conn.execute(
        "SELECT xr.confidence, xr.source_method, xr.curator_status, xr.curated_by, "
        "       xr.source_span_start, xr.source_span_end, xr.source_form_snapshot, c.text "
        "FROM cross_references xr JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "WHERE xr.id = ?",
        (row_id,),
    ).fetchone()
    if row is None:
        return False
    conf, method, status, curated_by, start, end, snapshot, text = row
    sets: dict[str, object] = {}

    if (
        method in _RULE_TIERS
        and cand.source_method in _RULE_TIERS
        and status == "auto"
        and curated_by is None
        and (conf, method) != (cand.confidence, cand.source_method)
    ):
        sets["confidence"] = cand.confidence
        sets["source_method"] = cand.source_method

    if _span_is_stale(text, start, end, snapshot, cand):
        sets["source_span_start"] = cand.source_span_start
        sets["source_span_end"] = cand.source_span_end

    if not sets:
        return False
    assignments = ", ".join(f"{col} = ?" for col in sets)
    conn.execute(
        f"UPDATE cross_references SET {assignments} WHERE id = ?",
        (*sets.values(), row_id),
    )
    return True


def _reads(text: str, start: int | None, end: int | None, snapshot: str) -> bool:
    """Whether ``text[start:end]`` reads the snapshot. Contained-in counts:
    #414's accepted rows keep a snapshot wider than their span."""
    if start is None or end is None:
        return False
    piece = text[start:end]
    return bool(piece) and (piece == snapshot or piece in snapshot)


def _span_is_stale(
    text: str, start: int | None, end: int | None, snapshot: str | None, cand: Candidate
) -> bool:
    if snapshot is None or start is None or end is None:
        return False
    if (start, end) == (cand.source_span_start, cand.source_span_end):
        return False
    return not _reads(text, start, end, snapshot) and _reads(
        text, cand.source_span_start, cand.source_span_end, snapshot
    )


# ──────────────────────────────────────────────────────────────────
# Bulk runner
# ──────────────────────────────────────────────────────────────────


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _fingerprint_for(author: str, cache: dict[str, str]) -> str:
    fp = cache.get(author)
    if fp is None:
        fp = cache[author] = rules_fingerprint(author)
    return fp


def iter_chunks_for_rules(
    conn: sqlite3.Connection,
    *,
    source_author: str | None = None,
    limit: int | None = None,
    rescan_all: bool = False,
) -> Iterable[ChunkInfo]:
    """Stream chunks suitable for rule-based detection. Joins through
    ``chunks_full`` to surface (author, work, lang, section) in one
    query. Filters:

    * ``source_author`` — restrict to one author (faster targeted re-runs).
    * ``limit`` — cap the row count for smoke / debug runs.
    * ``rescan_all`` — when False (default), skip chunks whose current
      ``sha1(text)`` matches the stored hash in ``refs_scan_state`` *and*
      whose author's rule set fingerprints the same as it did at that
      scan (Phase 6a — nothing changed on either side → rule output would
      be identical and get deduped, so the work is pure overhead). Set
      True to force a pass regardless.

      The rules half of that predicate is #287: before it, editing
      ``refs/rules/<author>.py`` invalidated nothing, and the next build
      skipped every chunk whose text was unchanged while the new rule
      never fired. Invalidation is per author, so a Renan edit re-scans
      Renan's ~20K chunks rather than the corpus's 428K markers — the
      distinction that makes this worth more than the ``--rescan-all``
      it replaces. #287 covered a rule's configuration only; #304 added
      the logic of the methods, so a rewritten ``scan`` body invalidates
      too. What the fingerprint covers is in
      :mod:`refs.rules.fingerprint`.

    Lazy — yields rows one at a time so the rule runner doesn't
    materialize the whole corpus in memory.
    """

    # When the scan_state table is absent (DB predates migration 0020),
    # behave as if `rescan_all` were True. We don't want to hard-fail
    # a `refs build` against an old snapshot the user is testing
    # against.
    has_scan_state = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='refs_scan_state'"
        ).fetchone()
        is not None
    )
    use_skip = (not rescan_all) and has_scan_state
    # Same tolerance one migration down: a DB at 0020 but not 0028 has
    # the table and not the column. Falling back to the text-only
    # predicate keeps that DB working exactly as it did before; treating
    # the absent column as a mismatch would instead make every run a
    # full-corpus pass forever, since such a DB can never store a hash.
    has_rules_hash = has_scan_state and _has_column(conn, "refs_scan_state", "rules_hash")

    sql = "SELECT chunk_id, author, work, lang, section, text FROM chunks_full "
    params: list[Any] = []
    if source_author is not None:
        sql += "WHERE author = ? "
        params.append(source_author)
    sql += "ORDER BY chunk_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    stored: dict[str, tuple[str, str | None]] = {}
    if use_skip:
        # Cache the stored hashes in memory so the per-chunk check is
        # a dict lookup, not a per-row SELECT. Even for the full
        # ~344K-chunk corpus the table is three TEXT columns; ~50 MB
        # max, comfortably small.
        cols = "chunk_id, text_hash, " + ("rules_hash" if has_rules_hash else "NULL")
        stored = {
            row[0]: (row[1], row[2]) for row in conn.execute(f"SELECT {cols} FROM refs_scan_state")
        }

    import hashlib

    # One fingerprint per author per pass, not per chunk — `rules_fingerprint`
    # memoizes, but the dict lookup here keeps the hot loop free of it.
    fp_by_author: dict[str, str] = {}

    for row in conn.execute(sql, params):
        if use_skip:
            prior = stored.get(row["chunk_id"])
            if prior is not None:
                cur_hash = hashlib.sha1(
                    row["text"].encode("utf-8"), usedforsecurity=False
                ).hexdigest()
                # A NULL `rules_hash` is a marker written before #287
                # existed. It compares unequal to any fingerprint, which
                # is the intended one-time rescan per author rather than
                # a migration that synthesises hashes for 428,606 rows.
                if prior[0] == cur_hash and (
                    not has_rules_hash or prior[1] == _fingerprint_for(row["author"], fp_by_author)
                ):
                    continue
        yield ChunkInfo(
            chunk_id=row["chunk_id"],
            author=row["author"],
            work=row["work"],
            lang=row["lang"],
            section=row["section"],
            text=row["text"],
        )


def record_scan_state(
    conn: sqlite3.Connection,
    chunks: Iterable[ChunkInfo],
) -> int:
    """Upsert ``refs_scan_state`` rows for every chunk in ``chunks``.

    Called by the ``refs build`` runner after a chunk has been
    scanned, so the next run's :func:`iter_chunks_for_rules` can skip
    it cheaply. Records both halves of that run's skip predicate: the
    same ``sha1(text)`` the iterator computes on read, and the
    fingerprint of the rule set that just ran against the chunk (#287),
    so a re-scan is a no-op only while *both* still hold.

    Idempotent. Safely no-ops when the ``refs_scan_state`` table is
    missing (pre-migration-0020 DB), and falls back to writing the text
    hash alone when the table exists without the ``rules_hash`` column
    (pre-0028), so the writer doesn't need to branch on schema state.
    """

    has_table = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='refs_scan_state'"
        ).fetchone()
        is not None
    )
    if not has_table:
        return 0
    has_rules_hash = _has_column(conn, "refs_scan_state", "rules_hash")

    import hashlib

    fp_by_author: dict[str, str] = {}
    rows = [
        (
            ch.chunk_id,
            hashlib.sha1(ch.text.encode("utf-8"), usedforsecurity=False).hexdigest(),
            _fingerprint_for(ch.author, fp_by_author) if has_rules_hash else None,
        )
        for ch in chunks
    ]
    if not rows:
        return 0
    if has_rules_hash:
        conn.executemany(
            "INSERT INTO refs_scan_state(chunk_id, text_hash, rules_hash) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(chunk_id) DO UPDATE SET "
            "  text_hash = excluded.text_hash, "
            "  rules_hash = excluded.rules_hash, "
            "  scanned_at = CURRENT_TIMESTAMP",
            rows,
        )
    else:
        conn.executemany(
            "INSERT INTO refs_scan_state(chunk_id, text_hash) VALUES (?, ?) "
            "ON CONFLICT(chunk_id) DO UPDATE SET "
            "  text_hash = excluded.text_hash, "
            "  scanned_at = CURRENT_TIMESTAMP",
            [(cid, th) for cid, th, _ in rows],
        )
    return len(rows)
