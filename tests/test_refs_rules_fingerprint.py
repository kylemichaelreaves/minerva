"""The rules half of the `refs build` skip predicate (#287).

Two layers. `fingerprint_rules` has to notice every place a rule keeps
behaviour-affecting configuration — instance fields, class-level
``ClassVar`` config, and module globals the rule's methods read — because
a fingerprint that misses one of those is the "check that runs but
validates nothing" shape the issue was filed about. Then the iterator
has to actually invalidate on it, per author rather than corpus-wide.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest
from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.refs import rules as refs_rules
from minerva.refs.rules import (
    AuthorMentionRule,
    ChunkInfo,
    StrongMentionRule,
    iter_chunks_for_rules,
    record_scan_state,
    rules_fingerprint,
)
from minerva.refs.rules import fingerprint as fingerprint_mod
from minerva.refs.rules.fingerprint import fingerprint_rules
from minerva.refs.rules.scripture_cite import lat

# ══════════════════════════════════════════════════════════════════
# What the digest covers
# ══════════════════════════════════════════════════════════════════


def _mention(**kw: object) -> AuthorMentionRule:
    base: dict = {
        "name": "r",
        "target_author": "Aristotle",
        "forms": ("Philosophus",),
    }
    base.update(kw)
    return AuthorMentionRule(**base)  # type: ignore[arg-type]


def test_fingerprint_is_stable_across_equal_rule_sets() -> None:
    """Same configuration, distinct objects — the digest is a function of
    the configuration, not of object identity, or it would change every
    process and never skip anything."""

    assert fingerprint_rules((_mention(),)) == fingerprint_rules((_mention(),))


def test_fingerprint_of_empty_rule_set_is_stable() -> None:
    """Authors with no rules module at all (Plato today) still get a
    marker written, so the empty tuple needs a stable digest."""

    assert fingerprint_rules(()) == fingerprint_rules(())


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param({"forms": ("Philosophus", "Peripateticus")}, id="forms"),
        pytest.param({"confidence": 0.9}, id="confidence"),
        pytest.param({"langs": ("lat",)}, id="langs"),
        pytest.param({"target_author": "Plato"}, id="target-author"),
        pytest.param({"target_work": "Ethica"}, id="target-work"),
        pytest.param({"ignore_case": True}, id="ignore-case"),
        pytest.param({"reference_type": "quotes"}, id="reference-type"),
    ],
)
def test_fingerprint_changes_on_any_instance_field(changed: dict) -> None:
    """Every configured field is part of the digest. `forms` is the one
    the #223 Renan case turned on, but a confidence or langs edit changes
    the output rows just as much."""

    assert fingerprint_rules((_mention(),)) != fingerprint_rules((_mention(**changed),))


def test_fingerprint_changes_when_a_rule_is_added_or_removed() -> None:
    one = (_mention(),)
    two = (_mention(), _mention(name="r2", target_author="Plato", forms=("Plato",)))
    assert fingerprint_rules(one) != fingerprint_rules(two)
    assert fingerprint_rules(()) != fingerprint_rules(one)


def test_fingerprint_changes_when_rules_are_reordered() -> None:
    """Rules run in tuple order and two overlapping rules can attribute
    the same span differently depending on which runs first, so order is
    part of the configuration."""

    a = _mention(name="a")
    b = _mention(name="b", target_author="Plato", forms=("Plato",))
    assert fingerprint_rules((a, b)) != fingerprint_rules((b, a))


def test_fingerprint_distinguishes_rule_classes_with_identical_fields() -> None:
    """`StrongMentionRule` differs from its parent only in defaults — but
    swapping one for the other changes every row's `source_method` and
    confidence, so the class itself is in the digest."""

    common: dict = {"name": "r", "target_author": "Aristotle", "forms": ("Philosophus",)}
    weak = AuthorMentionRule(**common, confidence=0.5, source_method="rule_weak")
    strong = StrongMentionRule(**common, confidence=0.5, source_method="rule_weak")
    assert fingerprint_rules((weak,)) != fingerprint_rules((strong,))


# ── class-level (ClassVar) configuration ─────────────────────────────
#
# The scripture-cite rules keep their lexicon and cite regex as class
# attributes, not instance fields, so `dataclasses.fields` cannot see
# them. A fields-only digest would call a lexicon edit "no change".


@dataclass(frozen=True)
class _ClassConfiguredRule:
    name: str = "cfg"
    lexicon: ClassVar[dict[str, str]] = {"Matth": "Matthaeus"}
    cite_re: ClassVar[re.Pattern[str]] = re.compile(r"\d+")
    ambiguous_bare: ClassVar[frozenset[str]] = frozenset({"Cor"})

    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        return ()


def test_fingerprint_covers_classvar_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    before = fingerprint_rules((_ClassConfiguredRule(),))
    monkeypatch.setattr(
        _ClassConfiguredRule, "lexicon", {"Matth": "Matthaeus", "Marc": "Marcus"}
    )
    assert fingerprint_rules((_ClassConfiguredRule(),)) != before


def test_fingerprint_covers_classvar_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    before = fingerprint_rules((_ClassConfiguredRule(),))
    monkeypatch.setattr(_ClassConfiguredRule, "cite_re", re.compile(r"\d+", re.IGNORECASE))
    assert fingerprint_rules((_ClassConfiguredRule(),)) != before, (
        "same pattern text, different flags — the compiled regex differs"
    )


def test_fingerprint_ignores_dict_ordering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Containers are canonicalized by sorting: a lexicon literal whose
    entries were shuffled without changing content must not invalidate
    the corpus."""

    monkeypatch.setattr(_ClassConfiguredRule, "lexicon", {"a": "1", "b": "2"})
    forward = fingerprint_rules((_ClassConfiguredRule(),))
    monkeypatch.setattr(_ClassConfiguredRule, "lexicon", {"b": "2", "a": "1"})
    assert fingerprint_rules((_ClassConfiguredRule(),)) == forward


# ── module globals the rule reads ───────────────────────────────────
#
# `StructuralCommentaryRule` (aquinas.py) holds no configuration at all:
# its entire behaviour is two module globals. `FormulaicQuoteRule`
# (scripture_cite/lat.py) reaches its regex fragments only through a
# helper function, one call deeper.

_TARGETS = {"Sent. Ethic.": "Ethica Nicomachea"}


@dataclass(frozen=True)
class _GlobalReadingRule:
    name: str = "glob"

    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        _TARGETS.get(chunk.work)
        return ()


def test_fingerprint_covers_module_globals_a_rule_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding a fifth Aristotle commentary to `_COMMENTARY_TARGETS` is a
    rules change even though no rule object changes."""

    before = fingerprint_rules((_GlobalReadingRule(),))
    monkeypatch.setitem(_TARGETS, "Sent. Metaphys.", "Metaphysica")
    assert fingerprint_rules((_GlobalReadingRule(),)) != before


def test_fingerprint_follows_helper_functions_one_call_deep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real Latin formulaic rule, whose quote-length bounds are read
    by `_formulaic_pattern` — a module function its `_pattern` method
    calls — and never by the rule's own bytecode. A walk that stopped at
    the rule's own methods would call a bounds change "no change", and
    the bounds decide which matches survive.
    """

    rule = lat.FormulaicQuoteRule(
        name="t",
        target_author="Vulgate",
        target_work="Psalmi",
        introducer_patterns=("in Psalmo",),
    )
    before = fingerprint_rules((rule,))
    monkeypatch.setattr(lat, "_FORMULAIC_MAX_QUOTE_CHARS", 300)
    assert fingerprint_rules((rule,)) != before


def test_fingerprint_terminates_on_recursive_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The global walk follows calls, so mutually recursive helpers must
    not hang it. Guarded by a visited set rather than a depth cap.

    The walkable-module prefix is widened to everything for this test —
    otherwise the two helpers below, living in a test module, would be
    skipped before the guard was ever reached and the test would pass
    without exercising it.
    """

    monkeypatch.setattr(fingerprint_mod, "_WALKABLE_PREFIX", "")
    assert fingerprint_rules((_RecursiveRule(),))


_escape = re.escape


@dataclass(frozen=True)
class _StdlibCallingRule:
    name: str = "std"

    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        _escape(chunk.text)
        return ()


def test_global_walk_stops_at_the_project_boundary() -> None:
    """The walk follows calls, so it needs a boundary or it would descend
    through `re` and `dataclasses` into the stdlib — hashing a great deal
    that no rules edit can change. Project modules only."""

    assert fingerprint_rules((_StdlibCallingRule(),))


@dataclass(frozen=True)
class _FieldlessRule:
    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        return ()


class _PlainClassRule:
    """The `Rule` protocol asks only for `name` and `scan`. Every rule in
    the package happens to be a frozen dataclass today, but nothing
    requires it, and `dataclasses.fields` raises on anything else."""

    name = "plain"
    forms = ("Sokrates",)

    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        return ()


def test_non_dataclass_rule_fingerprints_from_its_class_attributes() -> None:
    """A rule that is not a dataclass must not crash the digest, and its
    configuration must still reach it — as class attributes, which is
    where a plain-class rule keeps everything."""

    before = fingerprint_rules((_PlainClassRule(),))
    assert before != fingerprint_rules(())

    original = _PlainClassRule.forms
    try:
        _PlainClassRule.forms = ("Sokrates", "Sokratem")
        assert fingerprint_rules((_PlainClassRule(),)) != before
    finally:
        _PlainClassRule.forms = original


def test_rule_with_no_fields_still_fingerprints() -> None:
    """`StructuralCommentaryRule` is one `name` field away from this: a
    rule can be entirely behaviour. The class identity is what carries
    the digest then, so adding or removing such a rule still registers."""

    assert fingerprint_rules((_FieldlessRule(),)) != fingerprint_rules(())


def _ping(n: int) -> int:  # pragma: no cover - never run
    return _pong(n)


def _pong(n: int) -> int:  # pragma: no cover - never run
    return _ping(n)


@dataclass(frozen=True)
class _RecursiveRule:
    name: str = "rec"

    def scan(self, chunk: ChunkInfo):  # pragma: no cover - never run
        _ping(1)
        return ()


# ── the real rule modules ───────────────────────────────────────────


def test_real_author_fingerprints_are_stable_and_distinct() -> None:
    """Two live modules — one Python (`aquinas.py`), one YAML spec
    (`gobineau.yaml`). The YAML half is the point: hashing `.py` source
    would return the same digest for every spec-defined author no matter
    what the spec said."""

    refs_rules._reset_rules_caches()
    aquinas = rules_fingerprint("Aquinas")
    gobineau = rules_fingerprint("Gobineau")
    assert aquinas and gobineau
    assert aquinas != gobineau

    refs_rules._reset_rules_caches()
    assert rules_fingerprint("Aquinas") == aquinas
    assert rules_fingerprint("Gobineau") == gobineau


def test_fingerprint_is_independent_of_which_authors_are_loaded() -> None:
    """The walk reaches into the rules package's own module namespace,
    which is where `_AUTHOR_RULES_CACHE` lives. If that cache leaked into
    the digest, an author's fingerprint would depend on load order and
    the skip cache would invalidate on every run."""

    refs_rules._reset_rules_caches()
    alone = rules_fingerprint("Aquinas")

    refs_rules._reset_rules_caches()
    rules_fingerprint("Nietzsche")
    rules_fingerprint("Renan")
    assert rules_fingerprint("Aquinas") == alone


def test_unknown_author_fingerprints_as_the_empty_rule_set() -> None:
    refs_rules._reset_rules_caches()
    assert rules_fingerprint("Nobody At All") == fingerprint_rules(())


# ══════════════════════════════════════════════════════════════════
# The skip predicate
# ══════════════════════════════════════════════════════════════════


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "scan.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="aq-1",
                    author="Aquinas",
                    text="Philosophus dixit virtus est habitus electivus.",
                ),
                make_chunk(
                    chunk_id="ni-1",
                    author="Nietzsche",
                    lang="deu",
                    text="Sokrates war ein Plebejer und ein Décadent.",
                ),
            ]
        )
    )
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def test_edited_rules_reyield_only_that_authors_chunks(tmp_path: Path) -> None:
    """The defect and its fix, end to end. Text is unchanged on both
    chunks; only Aquinas's rules moved. Before #287 neither chunk came
    back; a global hash would have brought back both — which is what
    `--rescan-all` already did, and the reason per-author was worth
    building."""

    db = _seed(tmp_path)
    conn = store.open_db(db)
    try:
        refs_rules._reset_rules_caches()
        first = list(iter_chunks_for_rules(conn))
        assert {c.chunk_id for c in first} == {"aq-1", "ni-1"}
        record_scan_state(conn, first)
        conn.commit()

        assert list(iter_chunks_for_rules(conn)) == [], "nothing changed → no rescan"

        # Edit Aquinas's rules: the shape of "add a surface form to
        # refs/rules/aquinas.py", without touching the file on disk.
        refs_rules._reset_rules_caches()
        original = refs_rules._rules_for_author("Aquinas")
        refs_rules._AUTHOR_RULES_CACHE["Aquinas"] = (
            *original,
            AuthorMentionRule(
                name="aquinas_new", target_author="Averroes", forms=("Commentator",)
            ),
        )

        again = list(iter_chunks_for_rules(conn))
        assert {c.chunk_id for c in again} == {"aq-1"}, (
            "the edited author's chunks rescan; every other author's stay skipped"
        )

        # And the rescan settles: recording the new fingerprint makes the
        # following run a no-op again.
        record_scan_state(conn, again)
        conn.commit()
        assert list(iter_chunks_for_rules(conn)) == []
    finally:
        conn.close()
        refs_rules._reset_rules_caches()


def test_null_rules_hash_forces_exactly_one_rescan(tmp_path: Path) -> None:
    """The migration adds the column without backfilling it, so every
    pre-#287 marker carries NULL. NULL must mean "rescan once", not
    "rescan forever"."""

    db = _seed(tmp_path)
    conn = store.open_db(db)
    try:
        refs_rules._reset_rules_caches()
        first = list(iter_chunks_for_rules(conn))
        record_scan_state(conn, first)
        # Simulate markers written before the column existed.
        conn.execute("UPDATE refs_scan_state SET rules_hash = NULL")
        conn.commit()

        stale = list(iter_chunks_for_rules(conn))
        assert {c.chunk_id for c in stale} == {"aq-1", "ni-1"}

        record_scan_state(conn, stale)
        conn.commit()
        assert list(iter_chunks_for_rules(conn)) == [], "one rescan, then settled"
    finally:
        conn.close()
        refs_rules._reset_rules_caches()


def test_record_scan_state_writes_the_fingerprint(tmp_path: Path) -> None:
    db = _seed(tmp_path)
    conn = store.open_db(db)
    try:
        refs_rules._reset_rules_caches()
        record_scan_state(conn, list(iter_chunks_for_rules(conn)))
        conn.commit()
        stored = dict(
            conn.execute("SELECT chunk_id, rules_hash FROM refs_scan_state")
        )
        assert stored["aq-1"] == rules_fingerprint("Aquinas")
        assert stored["ni-1"] == rules_fingerprint("Nietzsche")
        assert stored["aq-1"] != stored["ni-1"]
    finally:
        conn.close()
        refs_rules._reset_rules_caches()


def test_pre_0028_db_falls_back_to_the_text_only_predicate(tmp_path: Path) -> None:
    """A DB with the table but not the column — an old snapshot someone
    is testing against. It must behave exactly as it did before #287,
    not treat the absent column as a permanent mismatch: such a DB can
    never store a hash, so that reading would make every run a full pass
    forever.
    """

    db = tmp_path / "pre0028.sqlite"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE chunks_full (chunk_id TEXT, author TEXT, work TEXT, "
            "lang TEXT, section TEXT, text TEXT)"
        )
        conn.execute(
            "INSERT INTO chunks_full VALUES ('c1', 'Aquinas', 'ST', 'lat', NULL, 'x')"
        )
        conn.execute(
            "CREATE TABLE refs_scan_state (chunk_id TEXT PRIMARY KEY, "
            "text_hash TEXT NOT NULL, scanned_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()

        refs_rules._reset_rules_caches()
        first = list(iter_chunks_for_rules(conn))
        assert [c.chunk_id for c in first] == ["c1"]
        assert record_scan_state(conn, first) == 1
        conn.commit()
        assert list(iter_chunks_for_rules(conn)) == []
    finally:
        conn.close()
        refs_rules._reset_rules_caches()
