"""A content hash over an author's *compiled* rule set (#287).

`refs_scan_state` used to answer one question — "has this chunk, with
this text, been scanned before?" — and skip the chunk when the answer
was yes. It never asked whether the rules that would run against the
chunk had changed since. So editing ``refs/rules/<author>.py`` invalidated
nothing: the next `refs build --strategy rules` skipped every chunk whose
text was unchanged and the new rule never fired, exiting 0 with a report
indistinguishable from a correctly-skipped run. `--rescan-all` was the
documented workaround; nothing *detected* the situation.

This module turns "the rules changed since this chunk was scanned" into
a computable condition. :func:`fingerprint_rules` reduces the rule tuple
:func:`refs.rules._rules_for_author` hands back to one hex digest, stored
per chunk in ``refs_scan_state.rules_hash`` and compared alongside
``text_hash``.

WHY THE COMPILED RULE SET AND NOT THE `.py` SOURCE
--------------------------------------------------------------------
Source text is the obvious input and it is wrong twice over.

*Not all rules are Python.* ``loader.load_author_rules_from_yaml``
compiles ``specs/<author>.yaml`` into the same rule instances, and two
authors (Boulainvilliers, Gobineau) are defined that way today. A hash
over ``.py`` source ignores every YAML-defined rule, which reproduces
exactly the bug this fixes for a subset of authors while looking fixed
everywhere — the "check that runs but validates nothing" shape. The
compiled rule set is the one representation both sources converge on.

*Source churns on edits that change no behaviour.* Comments and
reformatting would invalidate the whole corpus; batch 7 of the close-out
plan reformats these files.

WHAT IS HASHED, AND — THE PART THAT MATTERS — WHAT IS NOT
--------------------------------------------------------------------
Rules keep behaviour-affecting configuration in three places, and all
three are covered:

1. **Instance fields.** ``AuthorMentionRule.forms`` / ``confidence`` /
   ``langs`` / ``target_author``, ``FormulaicQuoteRule.introducer_patterns``.
   Every rule class in this package is a frozen dataclass, so
   ``dataclasses.fields`` enumerates these.

2. **Class-level configuration.** The scripture-cite rules put their real
   parametrization on ``ClassVar``s — ``lexicon``, ``cite_re``,
   ``ambiguous_bare``, ``non_disambiguating_prefixes`` — declared on the
   subclass, not passed per instance (see ``scripture_cite/_base.py``).
   A fields-only hash would miss a lexicon edit entirely.

3. **Module globals the rule methods read.** ``StructuralCommentaryRule``
   holds nothing at all: its behaviour is ``_COMMENTARY_TARGETS`` and
   ``_SECTION_LIB_RE`` in ``aquinas.py``. Same for the Quran rule's
   ``_RUN_RE`` / ``_LOCATOR_RE`` and the Latin formulaic rule's
   introducer fragments. These are reached by walking the method
   bytecode's ``co_names`` against the defining module's globals, and
   recursing through the ``minerva.refs.rules`` helper functions those
   methods call (``_formulaic_pattern`` → ``_FORMULAIC_QUOTE_END_RE``,
   ``_parse_cite_num`` → ``_ROMAN_VALUES``).

**Not hashed: the rule logic itself.** Rewriting the body of a ``scan``
method without touching any constant it reads leaves the fingerprint
unchanged, and that chunk stays skipped. Bytecode would catch it, but
bytecode carries line numbers, so a reformat would invalidate the corpus
— the property (2) and (3) exist to avoid. Editing rule *code* rather
than rule *data* therefore still wants ``--rescan-all``; #304 tracks
whether that gap is worth closing.

Every unknown is resolved toward *over*-invalidation where it can be
(a value we cannot canonicalize is recorded by type, so swapping it for
another type still changes the digest) — a spurious rescan costs one
pass, a missed one is the defect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from types import FunctionType, ModuleType
from typing import Any

# Only walk helper functions defined inside this project. Recursing into
# `re`, `dataclasses` or the stdlib would be unbounded and would hash
# nothing that a rules edit can change. The package boundary would be
# too tight: the Quran rule reaches its surah table through
# `minerva.authors.quran_works.find_surah`, and a canon-table edit
# changes what that rule emits.
_WALKABLE_PREFIX = "minerva."

# Module-global names that are process state rather than configuration.
# `_AUTHOR_RULES_CACHE` is not reachable from any rule method today —
# no rule calls `_rules_for_author` — but it lives in the same namespace
# the AuthorMentionRule methods resolve against, and a fingerprint that
# varied with which authors had been loaded would invalidate the cache on
# every run instead of never.
_UNSTABLE_GLOBALS = frozenset({"_AUTHOR_RULES_CACHE"})


def fingerprint_rules(rules: tuple[Any, ...]) -> str:
    """Hex digest over ``rules`` — stable across processes, sensitive to
    any configuration change in any of them.

    Order-sensitive by design: rules run in tuple order, and reordering
    ``RULES`` can change which of two overlapping rules attributes a
    match. Also sensitive to a rule being added or removed, which is the
    common case (``--rescan-all``'s original reason for existing).
    """

    h = hashlib.sha256()
    for rule in rules:
        h.update(b"\x1e")  # record separator between rules
        for part in _rule_parts(rule):
            h.update(part.encode("utf-8"))
            h.update(b"\x1f")  # unit separator between parts
    return h.hexdigest()


def _rule_parts(rule: Any) -> list[str]:
    """Every string that should feed the digest for one rule, in a
    deterministic order."""

    cls = type(rule)
    parts = [f"class={cls.__module__}.{cls.__qualname__}"]

    field_names = set()
    if dataclasses.is_dataclass(rule):
        for field in sorted(dataclasses.fields(rule), key=lambda f: f.name):
            field_names.add(field.name)
            parts.append(f"field:{field.name}={_canon(getattr(rule, field.name, None))}")

    # Class-level configuration. `ClassVar`-annotated attributes never
    # appear in `dataclasses.fields`, so a scripture rule's whole lexicon
    # and cite regex would otherwise be invisible. Walk the MRO so a
    # subclass that leaves `non_disambiguating_prefixes` at the base
    # default still hashes the default it inherited.
    seen_attrs: set[str] = set()
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name in sorted(vars(klass)):
            if name.startswith("__") or name in field_names or name in seen_attrs:
                continue
            value = vars(klass)[name]
            canon = _canon_or_none(value)
            if canon is None:
                continue
            seen_attrs.add(name)
            parts.append(f"classattr:{name}={canon}")

    for key, canon in sorted(_referenced_globals(cls).items()):
        parts.append(f"global:{key}={canon}")

    return parts


def _referenced_globals(cls: type) -> dict[str, str]:
    """Canonicalized module globals the class's methods read.

    Keyed on ``<module>.<name>`` so two modules' identically-named
    constants stay distinct. Follows calls into helper functions inside
    the rules package — the Latin formulaic rule's ``_pattern`` reaches
    its regex fragments only through ``_formulaic_pattern``.
    """

    out: dict[str, str] = {}
    pending: list[FunctionType] = []
    for klass in cls.__mro__:
        if klass is object:
            continue
        for value in vars(klass).values():
            func = _as_function(value)
            if func is not None:
                pending.append(func)

    visited: set[int] = set()
    while pending:
        func = pending.pop()
        if id(func) in visited:
            continue
        visited.add(id(func))
        globs = func.__globals__
        module = globs.get("__name__", "?")
        for name in func.__code__.co_names:
            if name in _UNSTABLE_GLOBALS or name not in globs:
                continue
            value = globs[name]
            helper = _as_function(value)
            if helper is not None:
                if getattr(helper, "__module__", "").startswith(_WALKABLE_PREFIX):
                    pending.append(helper)
                continue
            canon = _canon_or_none(value)
            if canon is not None:
                out[f"{module}.{name}"] = canon
    return out


def _as_function(value: Any) -> FunctionType | None:
    """Unwrap ``value`` to a plain function, or None if it isn't one.

    ``functools.cache`` is used on the pattern compilers in this package
    (``_compile_forms``, ``_formulaic_pattern``); the wrapper has no
    ``__code__``, so the walk would stop there without the unwrap.
    """

    value = getattr(value, "__wrapped__", value)
    value = getattr(value, "__func__", value)
    return value if isinstance(value, FunctionType) else None


def _canon_or_none(value: Any) -> str | None:
    """Canonical form for configuration data; None for anything that is
    code or a namespace rather than configuration."""

    if isinstance(value, (ModuleType, type)):
        return None
    if _as_function(value) is not None or callable(value):
        return None
    return _canon(value)


def _canon(value: Any) -> str:
    """Deterministic text for a configuration value.

    Containers are sorted rather than taken in iteration order, so a dict
    literal reordered without changing its content does not invalidate
    the corpus. Anything we cannot decompose is recorded by type name —
    which still catches a swap for a different type, and never claims
    equality it hasn't checked.
    """

    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return f"{type(value).__name__}:{value!r}"
    if isinstance(value, re.Pattern):
        return f"re:{value.pattern!r}/{value.flags}"
    if isinstance(value, (tuple, list)):
        return "[" + ",".join(_canon(v) for v in value) + "]"
    if isinstance(value, (set, frozenset)):
        return "{" + ",".join(sorted(_canon(v) for v in value)) + "}"
    if isinstance(value, dict):
        return "{" + ",".join(sorted(f"{_canon(k)}:{_canon(v)}" for k, v in value.items())) + "}"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        inner = ",".join(
            f"{f.name}={_canon(getattr(value, f.name, None))}"
            for f in sorted(dataclasses.fields(value), key=lambda f: f.name)
        )
        return f"{type(value).__qualname__}({inner})"
    return f"<{type(value).__name__}>"
