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


def looks_like_refusal(text: str) -> bool:
    return bool(REFUSAL_PATTERNS.search(text))


def parse_dual_translation(text: str) -> tuple[str, str]:
    """Pull (literal, literary) out of the LLM's labeled response."""

    m = LABELS_RE.match(text)
    if m is None:
        return ("", text.strip())
    literal = m.group(1).strip()
    literary = m.group(2).strip()
    return (literal, literary)
