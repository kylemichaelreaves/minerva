"""Shared text-window helpers — occurrence-finding and context snippets.

Consolidated from `glossary_import` and the `terms` CLI (#71).
"""

from .snippet import build_kwic, build_mark_snippet, find_occurrences, plain_window

__all__ = [
    "build_kwic",
    "build_mark_snippet",
    "find_occurrences",
    "plain_window",
]
