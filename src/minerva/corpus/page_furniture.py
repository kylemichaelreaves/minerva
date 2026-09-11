"""Separate page furniture from body text in PDF-extracted works.

The extractor walks each PDF page in reading order, so one chunk is roughly
one page and arrives as `[running head] [body] [footnote block] [page number]`
concatenated into a single string (#533). These three functions pull the
furniture back off. They are pure and take plain strings so they can be tested
without a PDF.

The note split is deliberately conservative. A trailing `4. ` only starts a
note block if marker `4` appears glued to a word earlier in the same chunk
(`too.4`); otherwise the text is left alone. An over-eager split deletes
Hegel's prose silently, which is far worse than leaving a note in place.
"""

from __future__ import annotations

import re

#: Running heads in Hegel's *Lectures on the Philosophy of World History*
#: (work 712), OCR-tolerant. `1R22` and `1&28` for `1822`, `l`/`I` for `L`,
#: `f` for `F` are all attested in that extraction.
RUNNING_HEADS_LWH: tuple[str, ...] = (
    r"TH[EF]\s+[lLI]ECTURES\s+O[FfP]\s+1[R8&]22\s*[-–]\s*3",
    r"INTRODUCTORY\s+FRAGMENT[,.\s]+1[R8&]22[,.\s]+1[8&][0-9]{2}",
    r"M[A.]{1,3}N[UV]SCR[Il1]PTS\s+OF\s+THE\s+[lI1]NTRODUCT[Il1]ON",
    r"INTRODUCTION[,.\s]+1[8&][0-9O]{2}\s*[-–]{1,2}\s*[0-9l]+",
)

#: A note block opens with `<n>. ` and a capital, an opening bracket, or a
#: quote. Anchored to a sentence boundary so a decimal or a list item
#: mid-sentence does not qualify.
_NOTE_OPEN_RE = re.compile(r"(?:(?<=\.)|(?<=^)|(?<=\s))(\d{1,3})\.\s+(?=[A-Z(\[\"'])")

#: A bare page number at the very end: whitespace, then a 2-3 digit run that
#: is not the tail of a longer number. The `(?<!\d)` guard sits on the DIGITS,
#: not before the whitespace — putting it before the whitespace inspects the
#: preceding sentence's full stop and rejects "…the age. 135", which is the
#: commonest case there is.
_TRAILING_PAGE_RE = re.compile(r"\s+(?<!\d)(\d{2,3})\s*$")


def strip_running_head(text: str, heads: tuple[str, ...]) -> str:
    """Remove a leading running head. Returns *text* unchanged if absent."""

    for pattern in heads:
        m = re.match(rf"\s*{pattern}\s*", text, re.IGNORECASE)
        if m:
            return text[m.end() :].lstrip()
    return text


def _marker_present(text: str, number: str, before: int) -> bool:
    """Is footnote marker *number* glued to a word before offset *before*?

    The printed marker is superscript; the extractor renders it as a bare
    digit run against the preceding word — `too.4`, `religion, 76`,
    `Saxony67`. Requiring it is what keeps the split honest.
    """

    upstream = text[:before]
    return re.search(rf"[a-zA-Z,.]{re.escape(number)}(?![0-9])", upstream) is not None


def split_trailing_notes(text: str) -> tuple[str, str | None]:
    """Split a trailing editors' note block off *text*.

    Returns `(body, notes)`; `notes` is None when nothing qualifies, in which
    case `body is text`.
    """

    for m in _NOTE_OPEN_RE.finditer(text):
        number = m.group(1)
        if not _marker_present(text, number, m.start()):
            continue
        body = text[: m.start()].rstrip()
        notes = text[m.start() :].strip()
        if not body or not notes:
            return text, None
        return body, notes
    return text, None


def strip_trailing_page_number(text: str) -> str:
    """Remove a bare page number at the end of *text*."""

    return _TRAILING_PAGE_RE.sub("", text).rstrip()
