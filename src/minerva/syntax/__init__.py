"""Dependency-syntax parsing and storage for the Reader's close-reading
overlay. See ``docs/syntax-annotation-plan.md``.

Two halves, deliberately separable:

* :mod:`minerva.syntax.parse` wraps Stanza. It is the only thing here that
  needs the ``[lemma]`` extra, and it is imported lazily so the rest of the
  package works without it — CI has no Stanza at all.
* :mod:`minerva.syntax.queries` is storage and replay, and depends on nothing
  but ``sqlite3``.
"""
