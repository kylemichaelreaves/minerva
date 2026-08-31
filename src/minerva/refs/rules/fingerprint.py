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

4. **The logic of the methods themselves** (#304). Rewriting the body of
   ``scan`` without touching any field or constant it reads used to leave
   the digest unmoved, so every already-scanned chunk stayed skipped —
   the original complaint, narrowed rather than fixed. The input is the
   function's **AST with attributes stripped**, taken over the same
   walked set as (3), so a helper edit counts as much as a ``scan`` edit.

   #304 recorded a reason not to do this, and it was wrong: "bytecode
   carries line numbers, so a reformat would invalidate the corpus". A
   code *object* does — ``co_firstlineno`` and the line table — but
   ``co_code`` itself does not, and an AST dumped with
   ``include_attributes=False`` carries no position information at all.
   Comments never reach the tree, and docstrings are stripped before
   hashing, which matters because a docstring-and-comment-only commit is
   a shape this repo produces (dd30678 was one). So batch 7's reformat
   moves no digest. AST is preferred over ``co_code`` for the one cost
   bytecode really does carry: bytecode differs between CPython
   versions, which would turn an interpreter upgrade into a full-corpus
   rescan.

   Source is read with ``inspect.getsource``. A rule class with no source
   file — built by ``exec``, or shipped in a zip — degrades to the
   configuration-only digest rather than raising, since a fingerprint
   that raises takes the whole ``refs build`` with it.

Every unknown is resolved toward *over*-invalidation where it can be
(a value we cannot canonicalize is recorded by type, so swapping it for
another type still changes the digest) — a spurious rescan costs one
pass, a missed one is the defect.

``--rescan-all`` therefore no longer has a case that needs it, and is
kept only as an escape hatch for a fingerprint that is itself wrong.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import re
import textwrap
from types import CodeType, FunctionType, ModuleType
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

    referenced, reachable = _walk_methods(cls)
    for key, canon in sorted(referenced.items()):
        parts.append(f"global:{key}={canon}")
    for key, digest in sorted(reachable.items()):
        parts.append(f"logic:{key}={digest}")

    return parts


def _walk_methods(cls: type) -> tuple[dict[str, str], dict[str, str]]:
    """One walk over everything the class's methods can reach, returning
    the two things a digest needs from it: the module globals they read,
    and the logic of the functions themselves.

    Both are keyed on ``<module>.<name>`` so two modules' identically-named
    constants — or helpers — stay distinct. The walk follows calls into
    helper functions inside the project: the Latin formulaic rule's
    ``_pattern`` reaches its regex fragments only through
    ``_formulaic_pattern``, and its *logic* lives there too.

    Kept as one traversal rather than two because the second would have
    to repeat the first's boundary and cycle rules exactly, and a copy
    that drifts is how one of the two ends up covering less than it
    claims.
    """

    globals_read: dict[str, str] = {}
    logic: dict[str, str] = {}
    pending: list[FunctionType] = []
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name, value in vars(klass).items():
            # Dunders are compiler-generated plumbing here — no rules
            # class defines one by hand, and the `__init__`/`__eq__` a
            # frozen dataclass generates are derived from the fields the
            # digest already covers. Following them reached CPython's own
            # `dataclasses.__replace__`, which put four stdlib internals
            # (`MISSING`, `_FIELDS`, …) into every author's digest and
            # made an interpreter upgrade a full-corpus rescan.
            if name.startswith("__"):
                continue
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
        logic[f"{module}.{func.__qualname__}"] = _logic_digest(func)
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
                globals_read[f"{module}.{name}"] = canon
    return globals_read, logic


# Keyed on the code object, not on a qualified name: a reimported module
# produces a new code object, so an edited function can never read a
# predecessor's digest out of this cache. That is what makes the memo
# safe to keep for the process's lifetime.
_LOGIC_CACHE: dict[CodeType, str] = {}


def _logic_digest(func: FunctionType) -> str:
    """Digest of what ``func`` *does*, insensitive to how it is written.

    ``ast.dump(..., include_attributes=False)`` drops every line and
    column number, comments never enter the tree, and the docstring is
    removed first — so reformatting, re-wrapping and rewritten prose all
    leave this unchanged while a rewritten expression does not.
    """

    code = func.__code__
    cached = _LOGIC_CACHE.get(code)
    if cached is not None:
        return cached

    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        # No source file: a dataclass-generated `__init__`/`__eq__`
        # (compiled from a string), an `exec`-defined class, a zipped
        # install. Recorded as a constant so it neither invalidates on
        # every run nor pretends to have checked something.
        digest = "<no-source>"
    else:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # `getsource` returns whole lines, which for a lambda inside
            # a larger expression is not parsable on its own.
            digest = "<unparsable>"
        else:
            _strip_docstrings(tree)
            digest = hashlib.sha256(
                ast.dump(tree, include_attributes=False).encode("utf-8")
            ).hexdigest()[:16]

    _LOGIC_CACHE[code] = digest
    return digest


def _strip_docstrings(tree: ast.AST) -> None:
    """Drop the docstring from every scope in ``tree``, in place.

    Prose is not behaviour, and this repo revises it constantly — one
    commit in the rules package's history (dd30678) changed nothing but
    comments and docstrings. Hashing those would have invalidated 16
    authors' markers for a change that could not alter a single row.
    """

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            del body[0]


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
