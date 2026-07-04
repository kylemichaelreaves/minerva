"""Parse and validate LLM dual-translation responses."""

from __future__ import annotations

import re

LABELS_RE = re.compile(
    r"^\s*LITERAL\s*:\s*(.*?)\s*LITERARY\s*:\s*(.*?)\s*$",
    re.DOTALL | re.IGNORECASE,
)

REFUSAL_PATTERNS = re.compile(
    r"got cut off|appears? to be cut off|truncated|"
    r"could you (?:paste|provide|share) the (?:full|complete|rest)|"
    r"i need more context|please provide more|"
    r"the (?:source )?passage seems|incomplete|"
    r"(?:i'm |i am )(?:unable|sorry)",
    re.IGNORECASE,
)


def is_dual_translation(text: str) -> bool:
    """True when the response carries the ``LITERAL:/LITERARY:`` labeled
    structure — i.e. the model actually produced a translation rather
    than a prose refusal/clarification."""
    return LABELS_RE.match(text) is not None


def looks_like_refusal(text: str) -> bool:
    """Heuristic refusal detector for an UNSTRUCTURED response.

    Only meaningful on a response that failed to parse as a labeled
    dual-translation — the patterns are substrings that legitimately
    appear inside a real translation's content ("incomplete",
    "truncated", "sorry"), so callers must not run this against a
    parsed translation body or valid output gets blanked (issue #58)."""
    return bool(REFUSAL_PATTERNS.search(text))


def parse_dual_translation(text: str) -> tuple[str, str]:
    """Pull (literal, literary) out of the LLM's labeled response."""

    m = LABELS_RE.match(text)
    if m is None:
        return ("", text.strip())
    literal = m.group(1).strip()
    literary = m.group(2).strip()
    return (literal, literary)
