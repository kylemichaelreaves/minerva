"""Reassemble paragraphs in OCR text dumps before they are chunked (#578).

The French archive.org / Gallica volumes arrive as the scan's *lines*,
with the printed page's furniture still standing among them — verbatim
from `histoire_anc_gouv_fra.txt`:

    nir fur le Rhin, il fe rapprocha de Paris, pendant que Louïs ayant promtement refait
                                                     ← blank: the page break
    Y y une                                          ← signature mark + catchword
                                                     ←
    1 3 o Mémoires Historiques.                      ← running head (page number OCR'd `1 3 o`)
                                                     ←
    Lothaire. une armée, vint attaquer le Comte …   ← the sentence continues

`split_by_chapter` makes one chunk per blank-line paragraph, so every hole
a page break leaves becomes a chunk boundary and every piece of furniture
a chunk of its own: 4,595 chunks under 40 characters across five files.

`reflow` puts the paragraphs back together, on the rule `sources/hobbes_la`
established for the Molesworth Latin (#535): **a blank line ends a
paragraph only when the body line before it closed a sentence.** Otherwise
it is the hole a page break left, and the paragraph continues across it.
For that to work the furniture has to be recognised and stepped over
rather than read as text, which is most of this module:

* **running heads** — a work's title, OCR-mangled, with a page number at
  one end (`AUTONOMIE JUIVE. 27`, `51 LlTTRES SUR LES AhCIîNS:`);
* **signature marks** — the binder's gathering letters (`C 4`, `Y y`);
* **catchwords** — the first word of the next page, printed at the foot
  of this one, recognised only when the next page really does begin with
  it (`une` … `Lothaire. une armée`).

The OCR's stray carets (`tempéré^.`, `diT^e`) are deleted first; see
`strip_carets`.

Footnotes are body text of the edition and are kept. A note that sits
between the two halves of a divided paragraph is emitted after the
paragraph rather than in the middle of it.

Everything here is pure string work, so it is tested without the corpus.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class OcrReflow:
    """What a work's running heads say, so they can be told from prose.

    ``titles`` are plain text as printed (`"Histoire du peuple d'Israël"`);
    they are compared after folding case, accents and everything that is
    not a letter, and matched fuzzily because the OCR rarely reads a
    small-caps head the same way twice.

    ``notes`` turns on the rules for Renan's note area, which no other
    scan was measured against (#789, #792): notes whose number the OCR
    mangled (`opens_mangled_note`) are held aside like any other, and a
    note that runs over a page break is carried to its continuation at
    the foot of the next page. Measured ungated, the carry alone took 71
    chunks out of Gobineau.
    """

    titles: tuple[str, ...] = ()
    notes: bool = False


# ── Line shapes ────────────────────────────────────────────────────

#: A line closes a sentence — and so may close a paragraph — when it ends
#: in one of these. Same rule as `sources/hobbes_la`, plus the French
#: closing guillemet.
_SENTENCE_END_RE = re.compile(r"[.?!:]\s*['\"’”»)\]]*\s*$")

#: A word divided at the right margin.
_DIVIDED_RE = re.compile(r"\w-$")

#: A footnote opens `1. `, `(1)`, `( 11 )`, `(i)` or `* ` and a capital.
#: Notes are text and are kept, but they must not be glued into the
#: paragraph they interrupt. The capital after `*` is required because
#: the *Lettres* OCR reads the quotation marks at the head of every quoted
#: line as `*` (`* ' >ï Faut pas oublier`), and those lines are body.
_NOTE_OPEN_RE = re.compile(r"^(?:\(\s?\d{1,3}\s?\)\s|\d{1,2}\.\s|\([ivx]{1,3}\)\s|\*\s+(?=[A-Z]))")

#: A page number as the OCR reads one: a short token, at least one
#: character a digit, the rest drawn from the misreads attested in these
#: scans (`4!`, `3^3`, `Î80`, `45-`, `«3`).
_PAGE_CHARS = frozenset("0123456789IlOoSsiÎî|/()«»•■*^!'-.,")
_PAGE_MAX_CHARS = 9

#: ...or a folio read worse than that, where a digit survived among
#: letters and stray marks: `T9`, `3M`, `12]`, `1C7`, `:{87`. No run of
#: two letters, so it is never a word. Measured on Renan's recto heads,
#: which carry no title to match and so rest on the folio alone (#814).
_MANGLED_FOLIO_RE = re.compile(r"(?=.*\d)(?!.*[^\W\d_]{2})\S{1,5}")

#: A front-matter folio in roman numerals, as the OCR reads them:
#: `XXII`, `xwii`, `XLiv`, `xLviit`. Three characters at least, so the
#: `Il` and `I` of prose are never a page number. Counts only beside a
#: title (`XXII L'ANTECHRIST.`); see `is_running_head`.
_ROMAN_PAGE_RE = re.compile(r"[IVXLCivxlcw]{3,7}t?\.?")

#: The regnal-year bracket Renan's *Origines* print beside the head:
#: `[An 61]`, OCR'd as `[Aq GIJ`, `[Au GIJ`.
_YEAR_BRACKET_RE = re.compile(r"\[[^\]\[]{1,8}[\]J]?")

#: Running heads are short. Anything longer is a line of prose that happens
#: to contain the title.
_HEAD_MAX_CHARS = 60

#: Fuzzy-match floor for a titled running head (`_title_score`). The
#: weakest heads the sweep over all fourteen files dropped score exactly
#: this — `DES BACES HDMAIMKS. -N`, `N DE LiaÉGklATÉ` — and every one of
#: them was read.
_TITLE_MATCH = 0.75

#: A head is its title and little else: in letters, no more than this
#: much longer than the title it matches, and no less than this much of it.
_TITLE_MAX_STRETCH = 1.3
_TITLE_MIN_COVER = 0.72

#: A titled head whose page number the OCR lost entirely must still be
#: long enough that a fuzzy match means something. Without this, prose
#: lines ending a sentence — `Roi de France.`, `de France.` — matched a
#: short title and were dropped in the first sweep.
_UNNUMBERED_MIN_LETTERS = 12

#: ...unless what follows the title is a folio the OCR read as punctuation
#: and stray letters — `VIE DE JÉSUS. :{`, `'25;{`, `2G1`, `S.')`, `l` —
#: which is how a 10-letter title fell under the floor above in 42 *Vie
#: de Jésus* heads (#814). A short token with no run of three letters is
#: no French word; the line before it must be capitals, as a head is.
_FOLIO_DEBRIS_RE = re.compile(r"(?!.*[^\W\d_]{3})\S{1,6}")

#: An untitled head (Renan's recto heads carry the *book* title, which
#: changes every few chapters) must be nearly all capitals and carry a
#: page number.
_HEAD_MIN_UPPER = 0.75
_HEAD_MIN_LETTERS = 6

#: ...and must contain a real word. A footnote's continuation line is also
#: capitals and numbers — `XXXIII, m (16); XXXVI, xv (24).`,
#: `B. J., VI, VI, 2.` — and the first sweep dropped five such lines from
#: *L'Antéchrist* as running heads. A roman numeral is not a word.
_HEAD_WORD_RE = re.compile(r"(?![IVXLCDM]+\b)[^\W\d_]{4,}")

#: A chapter or book heading whose numeral the OCR read as digits —
#: `CHAPITRE ÎI1` in *Histoire du peuple d'Israël* II — has the shape of
#: an untitled head, and is the one thing that must never be dropped.
_STRUCTURAL_RE = re.compile(r"(?i)(?:CHAPITRE|CHAP\.|LIVRE|TOME|PARTIE)\b")

#: `C 4`, `V 17`, `Ci`, `A ij`: gathering letters and a leaf number.
#: The leaf number follows the capitals directly, so `Roi`, `Lui` and
#: `Moi` — a capital, a lower-case letter, then `i` — are not signatures.
_SIGNATURE_RE = re.compile(r"^(?:[A-Z]{1,2}[a-z]?\s?\d{1,2}|[A-Z]{1,2}\s?[ij]{1,3})$")
#: `Y y`, `O o`: a gathering letter doubled — how these printers marked the
#: second alphabet.
_DOUBLED_SIGNATURE_RE = re.compile(r"^([A-Z])\s*(?=[a-z]$)(?i:\1)$")

#: A catchword line: the catchword, optionally after a signature.
_CATCHWORD_MAX_CHARS = 20


def _fold(text: str) -> str:
    """Lower-case letters only, accents removed."""

    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if c.isalpha() and not unicodedata.combining(c)).lower()


def _title_score(body: str, titles: tuple[str, ...]) -> float:
    """Best fuzzy match of ``body`` against a title no shorter than
    `_TITLE_MAX_STRETCH` allows. The length bound is what keeps prose that
    *contains* a title from matching it: `plus belle des races humaines
    (i).` scores 0.78 against `Des races humaines`, and was dropped from
    Gobineau as a head until it was added."""

    folded = _fold(body)
    if not folded:
        return 0.0
    scores = [
        SequenceMatcher(None, folded, title).ratio()
        for title in (_fold(t) for t in titles)
        if _TITLE_MIN_COVER * len(title) <= len(folded) <= _TITLE_MAX_STRETCH * len(title)
    ]
    return max(scores, default=0.0)


def is_running_head(line: str, spec: OcrReflow) -> bool:
    """A work's running head, with or without its page number."""

    stripped = line.strip()
    if not stripped or len(stripped) > _HEAD_MAX_CHARS or _NOTE_OPEN_RE.match(stripped):
        return False
    numbered, roman, body = _split_head(stripped)
    if _title_score(body, spec.titles) >= _TITLE_MATCH and (
        numbered or roman or len(_fold(body)) >= _UNNUMBERED_MIN_LETTERS
    ):
        return True
    title = _title_before_folio_debris(stripped)
    if title and _title_score(title, spec.titles) >= _TITLE_MATCH:
        return True
    # Only an arabic folio licenses the untitled rule. A roman one would
    # make every `CHAPITRE XIII.` a head — which the first attempt did,
    # dropping 150 chapter headings across the fourteen files.
    if not numbered:
        return False
    letters = [c for c in body if c.isalpha()]
    if len(letters) < _HEAD_MIN_LETTERS or not _HEAD_WORD_RE.search(body):
        return False
    if _STRUCTURAL_RE.match(body):
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= _HEAD_MIN_UPPER


def _split_head(line: str) -> tuple[bool, bool, str]:
    """``(has an arabic folio, has a roman one, the rest)`` for a candidate
    head: a folio taken off either end, any regnal-year bracket removed."""

    tokens = line.split()
    arabic = roman = False
    for end in (0, -1):
        if not tokens:
            break
        if _is_page_token(tokens[end]):
            arabic = True
        elif _ROMAN_PAGE_RE.fullmatch(tokens[end]):
            roman = True
        else:
            continue
        tokens.pop(end)
    return arabic, roman, _YEAR_BRACKET_RE.sub(" ", " ".join(tokens)).strip()


def _is_page_token(token: str) -> bool:
    return (
        len(token) <= _PAGE_MAX_CHARS
        and any(c.isdigit() for c in token)
        and all(c in _PAGE_CHARS for c in token)
    ) or bool(_MANGLED_FOLIO_RE.fullmatch(token))


def _title_before_folio_debris(line: str) -> str:
    """The capitals before a trailing folio the OCR mangled, or `""`.

    The debris is left out of the title match: the stray `s` of `S.')`
    alone pulls `VIE DR JIÎSUS.` under `_TITLE_MATCH`."""

    title, _, last = line.rpartition(" ")
    letters = [c for c in title if c.isalpha()]
    if (
        _FOLIO_DEBRIS_RE.fullmatch(last)
        and len(letters) >= _HEAD_MIN_LETTERS
        and sum(c.isupper() for c in letters) / len(letters) >= _HEAD_MIN_UPPER
    ):
        return title
    return ""


# ── Mangled note markers ───────────────────────────────────────────

#: Note numbers as the Renan OCR misreads them, each read in full over
#: the seven volumes (#792): `1` read as `i`, `t`, `l`, `î`, `\\` or a
#: lone full stop (`i. `, `t. `, `\\. `, `(i. `); a stray space before the
#: full stop (`1 . `); `5`/`4` read as `S`/`A` before a capital, since a
#: note opens on its first word; `.3. `; and a superscript caret note
#: call, `^. Tac, Ann.`, which `strip_carets` leaves as `. Tac, Ann.`.
#: A full stop run into a word (`.lean est venu`) is a misread capital.
_MANGLED_NOTE_OPEN_RE = re.compile(
    r"^(?:\(?i ?\. |\d ?\. |[SA]\. (?=[A-ZÉ«])|[tlîo\\]\. |\.\d\. |\. (?=\S))"
)
#: `1` read as the roman numeral, which a heading also opens with.
_ROMAN_ONE_NOTE_RE = re.compile(r"^I\. (?=\S)")
#: A table-of-contents entry carries no punctuation but its dash or
#: leaders (`I. Paul captif à Rome 1`); a note cites (`I. Acl., I, 14.`).
_NOTE_PUNCTUATION = frozenset(".,;:")
_CAPITAL_HEADING_MIN_UPPER = 0.9


def opens_mangled_note(line: str) -> bool:
    """A note whose number the OCR misread, by its first line.

    `I. ` is the one opener a heading shares, so it needs the note's
    shape after it: punctuation, no dash, not in capitals."""

    stripped = line.strip()
    if _MANGLED_NOTE_OPEN_RE.match(stripped):
        return True
    if not _ROMAN_ONE_NOTE_RE.match(stripped):
        return False
    rest = stripped[3:]
    letters = [c for c in rest if c.isalpha()]
    return (
        rest[:1] not in "—-"
        and any(c in _NOTE_PUNCTUATION for c in rest)
        and bool(letters)
        and sum(c.isupper() for c in letters) / len(letters) < _CAPITAL_HEADING_MIN_UPPER
    )


def is_signature(line: str) -> bool:
    stripped = line.strip()
    return bool(_SIGNATURE_RE.match(stripped) or _DOUBLED_SIGNATURE_RE.match(stripped))


# ── Carets ─────────────────────────────────────────────────────────

#: A run of carets and the spaces around it.
_CARET_RUN_RE = re.compile(r"[ \t]*\^+[ \t]*")


def _caret_gap(match: re.Match[str]) -> str:
    """What a caret run leaves behind: a space where it stood between two
    words, or between a word and a number, so neither is fused to the
    other; nothing inside a word, before punctuation, or at a line end."""

    line, (start, end) = match.string, match.span()
    if start == 0 or end == len(line):
        return ""
    left, right = line[start - 1], line[end]
    spaced = match.group() != match.group().strip()
    if spaced or (left.isdigit() != right.isdigit() and left.isalnum() and right.isalnum()):
        return " "
    return ""


def strip_carets(text: str) -> str:
    """The text without the `^` the OCR scatters through these scans.

    Measured over the corpus files (batch 13m), a caret is a superscript
    note call (`tempéré^.`, `moyens ^ Un Juif`) or glyph noise inside a
    word the OCR garbled (`diT^e`), and none a misread circumflex — so it
    is deleted, never replaced by a letter. A line that was nothing but
    carets is removed rather than left blank, because a blank line is a
    paragraph boundary to `reflow`.

    `reflow` applies it to every work it reflows. The third such corpus,
    Boulainvilliers, has no carets at all (measured), so in effect it
    touches Gobineau and Renan only.
    """

    if "^" not in text:
        return text
    lines = text.split("\n")
    stripped = [_CARET_RUN_RE.sub(_caret_gap, line) if "^" in line else line for line in lines]
    return "\n".join(
        new for old, new in zip(lines, stripped, strict=True) if new.strip() or not old.strip()
    )


# ── Classification ─────────────────────────────────────────────────

BODY = "body"
BLANK = "blank"
HEAD = "running head"
SIGNATURE = "signature"
CATCHWORD = "catchword"
#: A line the caller knows is footnote text (`assemble` only; `classify`
#: finds notes by their opening marker instead).
NOTE = "note"


def classify(lines: list[str], spec: OcrReflow) -> list[str]:
    """One kind per line. Furniture kinds are everything but BODY/BLANK."""

    kinds: list[str] = []
    last_text = ""
    for line in lines:
        continues = bool(_DIVIDED_RE.search(last_text.rstrip())) and line.lstrip()[:1].islower()
        kinds.append(_first_pass_kind(line, spec, continues))
        if line.strip():
            last_text = line
    for i in range(len(lines)):
        if kinds[i] == BODY and _is_catchword(lines, kinds, i):
            kinds[i] = CATCHWORD
    return kinds


def _first_pass_kind(line: str, spec: OcrReflow, continues_word: bool) -> str:
    if not line.strip():
        return BLANK
    if continues_word and not _opens_with_folio(line, spec):
        # The second half of a word divided at the margin is text, whatever
        # it looks like: `établisse-` / `ment du christianisme.` is a
        # sentence ending on a title, not a head.
        return BODY
    if is_signature(line):
        return SIGNATURE
    if is_running_head(line, spec):
        return HEAD
    return BODY


def _opens_with_folio(line: str, spec: OcrReflow) -> bool:
    """A head can follow a page that ended on a divided word: its folio,
    OCR'd lower-case (`i36`, `m`, `fi`), is what makes it look like the
    word's second half."""

    first, _, rest = line.strip().partition(" ")
    if _is_page_token(first) or (len(first) <= 5 and any(c.isdigit() for c in first)):
        return True
    return len(first) <= 2 and is_running_head(rest, spec)


def _is_catchword(lines: list[str], kinds: list[str], i: int) -> bool:
    """The last word of line ``i`` is printed again as the first word of
    the next page, and a running head stands between them.

    Requiring the head is what makes this safe: a short line whose last
    word merely recurs at the start of the next line is ordinary verse or
    dialogue; one that recurs across a page break is the catchword.
    """

    tokens = lines[i].split()
    if not tokens or len(lines[i].strip()) > _CATCHWORD_MAX_CHARS or len(tokens) > 3:
        return False
    if any(not _is_signature_token(t) for t in tokens[:-1]):
        return False
    crossed_head = False
    for j in range(i + 1, len(lines)):
        if kinds[j] == HEAD:
            crossed_head = True
        elif kinds[j] == BODY:
            # The first *or second* word: `Histoire` sets its marginal
            # glosses into the first line (`Lothaire. une armée, …` after
            # the catchword `une`).
            return crossed_head and tokens[-1] in lines[j].split()[:2]
    return False


def _is_signature_token(token: str) -> bool:
    return len(token) <= 2 and (token.isalpha() or token.isdigit())


# ── Reassembly ─────────────────────────────────────────────────────

#: See `_Assembler._overlong`.
_MAX_OPEN_CHARS = 3000


def _closes_sentence(line: str) -> bool:
    return bool(_SENTENCE_END_RE.search(line))


_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_LAST_PART_RE = re.compile(r"([^\W\d_]+)-$")
_FIRST_PART_RE = re.compile(r"^([^\W\d_]+)")


class _Compounds:
    """Which words this text hyphenates when it is not dividing them.

    A hyphen at the end of a line is ambiguous: `décré-` / `pitude` is
    one word divided at the margin, `quelques-` / `uns` a compound that
    happens to fall there. Dropping every such hyphen — what the clean
    scripts' `_join_hyphenation` does — writes `quelquesuns`,
    `syrophénicien`. The text itself settles most cases: a compound it
    prints mid-line with its hyphen more often than without keeps it.
    """

    def __init__(self, lines: list[str]) -> None:
        self._seen: dict[str, int] = {}
        for line in lines:
            # The last word of a divided line is a fragment, not a word.
            body = _LAST_PART_RE.sub("", line.rstrip())
            for word in _WORD_RE.findall(body):
                key = word.lower()
                self._seen[key] = self._seen.get(key, 0) + 1

    def keeps_hyphen(self, left: str, right: str) -> bool:
        hyphenated = f"{left}-{right}".lower()
        return self._seen.get(hyphenated, 0) > self._seen.get(f"{left}{right}".lower(), 0)


def _join_lines(lines: list[str], compounds: _Compounds) -> str:
    """One paragraph from its lines, honouring words divided at the margin."""

    out = ""
    for line in (ln.strip() for ln in lines):
        if not out:
            out = line
        elif _DIVIDED_RE.search(out) and line[:1].islower():
            out = _rejoin(out, line, compounds)
        else:
            out = f"{out} {line}"
    return out


def _rejoin(out: str, line: str, compounds: _Compounds) -> str:
    left = _LAST_PART_RE.search(out)
    right = _FIRST_PART_RE.match(line)
    if left and right and compounds.keeps_hyphen(left.group(1), right.group(1)):
        return out + line
    return out[:-1] + line


#: The carry (#789) attaches the page's first unmarked block after its
#: body text to a note left open at the page break only when that block
#: opens lower-case and its first line is at least this long: a short
#: line is as likely the end of the body's own paragraph. Measured over
#: the seven volumes: 136 attachments, 8 wrong, every one read.
_CARRY_MIN_CHARS = 55

#: ...and opens on a lower-case letter, or on a number that is not a note
#: marker (`3 etsuiv., 6-16`, but not `1 Luc, XVII` or `1, Ce beau`). A
#: guillemet, dash or capital opens a quotation or a body paragraph; `■1.`,
#: `<.` and `'I.` are notes whose marker the OCR mangled past recognition.
#: A capitalised block does not end the wait — it is the page's next body
#: paragraph, and the note's continuation comes after the last of them.
_CARRY_OPEN_RE = re.compile(
    # Not a lone letter and full stop (`l.Le Maaka`, `d. Hab.`): a note
    # marker mangled into a letter. Not `1 `/`11 ` before a word: `I`/`Il`
    # opening a line of quoted verse (`11 ne décidera pas`).
    r"(?![A-Za-z]\.\s?[^\W\d_])(?!1{1,2} [a-zà-öø-ÿ])"
    r"(?:[a-zà-öø-ÿ]|\d+(?!\d)(?![ ,.\-]+[A-ZÀ-ÖØ-Ý]))"
)


class _Assembler:
    """Collects body lines into paragraphs, holding notes aside while a
    paragraph is still open.

    Paragraphs are kept as their lines until `finish`, so a note carried
    over a page break (``notes``) can still take its continuation."""

    def __init__(
        self, is_heading: Callable[[str], bool], compounds: _Compounds, *, notes: bool = False
    ) -> None:
        self._is_heading = is_heading
        self._compounds = compounds
        self._notes = notes
        self._out: list[list[str]] = []
        self._para: list[str] = []
        self._note: list[str] = []
        self._note_placed = False
        self._held: list[list[str]] = []
        self._after_blank = True
        # The carry: the last note closed with nothing after it, the note
        # a page break left open, and whether that page has body text yet.
        self._last_note: list[str] | None = None
        self._carry_to: list[str] | None = None
        self._page_has_body = False

    def blank(self) -> None:
        self._close_note()
        if self._para and (_closes_sentence(self._para[-1]) or self._overlong()):
            self._flush()
        self._after_blank = True

    def page_break(self) -> None:
        """A running head: the note last closed may go on overleaf."""

        self._close_note()
        self._carry_to = self._last_note
        self._page_has_body = False

    def _overlong(self) -> bool:
        """A paragraph still open after this many characters has lost the
        full stop that would have closed it, and would otherwise swallow
        the rest of the chapter — `lettres_parlemens_fra.txt`, whose OCR
        drops most of them, produced a 20,283-character chunk."""

        return sum(len(line) for line in self._para) >= _MAX_OPEN_CHARS

    def _opens_note(self, stripped: str) -> bool:
        return bool(_NOTE_OPEN_RE.match(stripped)) or (self._notes and opens_mangled_note(stripped))

    def body(self, line: str) -> None:
        stripped = line.strip()
        opens_note = self._after_blank and self._opens_note(stripped)
        if self._carry_to is not None and self._after_blank and self._page_has_body:
            self._carry(stripped, opens_note)
        # A mangled `I. ` note is tested before the heading it resembles.
        if self._is_heading(line) and not (self._notes and opens_note):
            self._close_note()
            self._flush()
            self._out.append([stripped])
            self._last_note = self._carry_to = None
        elif self._note or opens_note:
            self._note.append(line)
        else:
            self._para.append(line)
            self._last_note = None
            self._page_has_body = True
        self._after_blank = False

    def _carry(self, stripped: str, opens_note: bool) -> None:
        """Attach this block to the note the page break left open, if it
        reads as that note's continuation. A new note ends the wait."""

        if opens_note:
            self._carry_to = None
            return
        if len(stripped) < _CARRY_MIN_CHARS or not _CARRY_OPEN_RE.match(stripped):
            return
        self._note, self._carry_to = self._carry_to, None
        self._note_placed = True

    def note(self, line: str) -> None:
        """A line the caller has placed in a page's note area. A marker
        opens a new note; anything else continues the current one — which
        is how a note carried over from the previous page stays whole."""

        if self._note and _NOTE_OPEN_RE.match(line.strip()):
            self._close_note()
        self._note.append(line)
        self._after_blank = False

    def finish(self) -> list[str]:
        self._close_note()
        self._flush()
        return [_join_lines(lines, self._compounds) for lines in self._out]

    def _close_note(self) -> None:
        if not self._note:
            return
        note, self._note = self._note, []
        self._last_note = note
        if self._note_placed:
            self._note_placed = False
        elif self._para:
            self._held.append(note)
        else:
            self._out.append(note)

    def _flush(self) -> None:
        if self._para:
            self._out.append(self._para)
            self._para = []
        self._out.extend(self._held)
        self._held = []


def _never(_line: str) -> bool:
    return False


def reflow(text: str, spec: OcrReflow, is_heading: Callable[[str], bool] = _never) -> str:
    """The text with its paragraphs reassembled and its furniture removed,
    one paragraph per blank-line-separated block.

    ``is_heading`` names the lines the splitter downstream will cut on;
    they are kept as paragraphs of their own, so a chapter head never
    disappears into the paragraph before it.
    """

    lines = strip_carets(text).split("\n")
    kinds = classify(lines, spec)
    # Furniture is a hole in the page: skipped, and never a paragraph end.
    # A work with ``notes`` keeps its running heads as page breaks.
    kept = (BODY, BLANK, HEAD) if spec.notes else (BODY, BLANK)
    items = [(kind, line) for line, kind in zip(lines, kinds, strict=True) if kind in kept]
    return "\n\n".join(assemble(items, is_heading, notes=spec.notes))


def assemble(
    items: list[tuple[str, str]],
    is_heading: Callable[[str], bool] = _never,
    *,
    notes: bool = False,
) -> list[str]:
    """Paragraphs from ``(kind, line)`` pairs, kind BODY, NOTE, BLANK or
    HEAD (a page break, for ``notes``).

    `reflow` feeds it what `classify` finds; an extractor that can see
    the page (`scripts/extract-essai-pdf.py`) feeds it the note area by
    position, which a text dump cannot tell it.
    """

    compounds = _Compounds([line for kind, line in items if kind in (BODY, NOTE)])
    assembler = _Assembler(is_heading, compounds, notes=notes)
    step = {
        BLANK: lambda _line: assembler.blank(),
        HEAD: lambda _line: assembler.page_break(),
        BODY: assembler.body,
        NOTE: assembler.note,
    }
    for kind, line in items:
        step[kind](line)
    return assembler.finish()


def dropped_lines(text: str, spec: OcrReflow) -> list[tuple[int, str, str]]:
    """``(line number, kind, line)`` for every line `reflow` removes — the
    sweep to read before trusting a change to any rule above."""

    lines = text.split("\n")
    return [
        (i + 1, kind, line)
        for i, (line, kind) in enumerate(zip(lines, classify(lines, spec), strict=True))
        if kind not in (BODY, BLANK)
    ]
