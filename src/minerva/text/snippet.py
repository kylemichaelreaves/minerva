"""Whitespace-normalised text windows around a span match."""

from __future__ import annotations

# Closing punctuation that should hug the preceding word (no leading space).
ATTACHED_TRAIL = ",.;:!?)]}»"
# Opening punctuation that should hug the following word.
ATTACHED_LEAD = "([{«"


def _window_bounds(
    text: str, start: int, end: int, radius: int
) -> tuple[int, int, str, str, str]:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    before = " ".join(text[lo:start].split())
    match = text[start:end]
    after = " ".join(text[end:hi].split())
    return lo, hi, before, match, after


def build_mark_snippet(
    text: str, start: int, end: int, *, radius: int = 40
) -> dict[str, int | str]:
    """Return a single snippet string plus ``match_start`` / ``match_end``."""

    if start < 0 or end < start or end > len(text):
        return {"snippet": text, "match_start": 0, "match_end": len(text)}

    _lo, _hi, before, match, after = _window_bounds(text, start, end, radius)
    if before:
        sep = "" if before[-1] in ATTACHED_LEAD else " "
        prefix = f"{before}{sep}"
    else:
        prefix = ""
    if after:
        sep = "" if after[0] in ATTACHED_TRAIL else " "
        suffix = f"{sep}{after}"
    else:
        suffix = ""
    snippet = f"{prefix}{match}{suffix}"
    return {
        "snippet": snippet,
        "match_start": len(prefix),
        "match_end": len(prefix) + len(match),
    }


def build_kwic(
    text: str, start: int, end: int, radius: int
) -> dict[str, str]:
    """Return left / match / right KWIC columns with truncation ellipses."""

    if start < 0 or end < start or end > len(text):
        return {"kwic_left": "", "kwic_match": text, "kwic_right": ""}

    lo, hi, left, match, right = _window_bounds(text, start, end, radius)
    left_sep = "" if left and left[-1] in ATTACHED_LEAD else " " if left else ""
    right_sep = "" if right and right[0] in ATTACHED_TRAIL else " " if right else ""
    leading_ellipsis = "… " if lo > 0 else ""
    trailing_ellipsis = " …" if hi < len(text) else ""
    return {
        "kwic_left": f"{leading_ellipsis}{left}{left_sep}".rstrip(),
        "kwic_match": match,
        "kwic_right": f"{right_sep}{right}{trailing_ellipsis}".lstrip(),
    }
