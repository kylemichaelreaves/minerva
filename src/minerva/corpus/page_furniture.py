"""Separate page furniture from body text in PDF-extracted works.

The extractor walks each PDF page in reading order, so one chunk is roughly
one page and arrives as `[running head] [body] [footnote block] [page number]`
concatenated into a single string (#533). These three functions pull the
furniture back off. They are pure and take plain strings so they can be tested
without a PDF.

The note split is deliberately conservative. A trailing `4. ` only starts a
note block if marker `4` appears earlier in the same chunk, either glued to
a word (`too.4`) or standalone as its own space-separated token (`thus 31
fi...`) — both are attested renderings of the same superscript marker in
this extraction. It also refuses when the text right before it ends in a
colon, since that's Hegel introducing his own enumeration, not an editor
opening a note. An over-eager split deletes Hegel's prose silently, which
is far worse than leaving a note in place.
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


#: A page number (or two — recto/verso running heads sometimes carry both)
#: can precede the running head itself, e.g. `138 139 INTRODUCTION, 1830--1`.
#: Capped at two so a table-of-contents listing (a dozen-plus numbers ahead
#: of a title-like phrase) still fails to match and is correctly left alone.
_LEADING_PAGE_NUMBERS_RE = r"(?:\d{2,3}\s+){0,2}"


def strip_running_head(text: str, heads: tuple[str, ...]) -> str:
    """Remove a leading running head. Returns *text* unchanged if absent."""

    for pattern in heads:
        m = re.match(rf"\s*{_LEADING_PAGE_NUMBERS_RE}{pattern}\s*", text, re.IGNORECASE)
        if m:
            return text[m.end() :].lstrip()
    return text


def _marker_present(text: str, number: str, before: int) -> bool:
    """Is footnote marker *number* attested before offset *before*?

    The printed marker is superscript; the extractor usually renders it as a
    bare digit run glued to the preceding word — `too.4`, `religion, 76`,
    `Saxony67` — but frequently renders it as its own space-separated token
    instead — `thus 31 finite`, `conflict. 42 So`. Both license the split.
    Either way the digit run must not be the tail or head of a longer
    number, so a page number or a year doesn't masquerade as the marker.
    Requiring *some* attested form upstream is what keeps the split honest.
    """

    upstream = text[:before]
    n = re.escape(number)
    # Glued: the required letter/comma/period immediately before the digits
    # already rules out a longer number extending backward; `(?!\d)` rules
    # one out extending forward. Standalone: whitespace required on both
    # sides does the same job without a word to glue to.
    pattern = rf"(?:[a-zA-Z,.]{n}(?!\d)|(?<=\s){n}(?=\s|$))"
    return re.search(pattern, upstream) is not None


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
        # A colon right before the candidate means Hegel is introducing his
        # own enumeration ("...three developments ... us: 1. ... 2. ... 3.
        # ..."), not an editor opening a note — a bare "1" upstream can
        # still satisfy _marker_present by coincidence (ord 461, work 712).
        # Measured across all 279 splits this licensed before the guard:
        # exactly one had a colon here, and it was that bad one — this is a
        # targeted rule backed by that count, not a guess. Refuse the whole
        # chunk outright rather than searching for a later candidate: ord
        # 461 does have one (a genuinely glued marker further down), but by
        # then the text between the enumeration and that later note is
        # already a tangle of headings and more prose that this function
        # was never designed to pick apart — leaving the whole chunk alone
        # is the safe call once a chunk has shown itself this irregular.
        if body.endswith(":"):
            return text, None
        return body, notes
    return text, None


def strip_trailing_page_number(text: str) -> str:
    """Remove a bare page number at the end of *text*."""

    return _TRAILING_PAGE_RE.sub("", text).rstrip()
