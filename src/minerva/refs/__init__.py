"""Cross-reference data layer.

Phase 1 ships:
* ``schema`` — CRUD helpers for ``reference_targets`` + ``cross_references``,
  including the shadow-address insert pattern lifted from ``terms.py``.
* ``spec`` — YAML curator-spec loader for canonical hand-curated
  references (mirrors ``glossary_spec.py``).

Detection modules (``rules/``, ``embed_verify``, ``llm_verify``) arrive
in Phases 2–4 and are intentionally absent here.
"""

from __future__ import annotations
