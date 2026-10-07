"""Parser for the OCR'd plain-text of Diels's *Vorsokratiker* (3rd
edition, 1912, volume 1).

The source is a single text file containing every philosopher's
chapter back-to-back, with the structure:

    <N>. <NAME>.                      ← chapter heading
    A. LEHRE.                         ← testimonia block (skipped)
    <numbered A-fragments>
    B. FRAGMENTE.                     ← B-fragments block (kept)
    <NAME>OY ΠΕΡΙ ΦΥΣΕΩΣ.             ← optional Greek subtitle (ignored)
    1. [<old-num>] <SourceCite> <Greek text>
    2. [<old-num>] <SourceCite> <Greek text>
    ...
    1. <German translation of 1>
    2. <German translation of 2>
    ...
    <line-number> <apparatus footnote text>     ← skipped
    <next page running head>                    ← skipped
    1. [<old-num>] <SourceCite> ...             ← continuation on next page

Greek and German fragments share the same fragment number; this
parser collects both sides and emits two ``Chunk`` objects per
fragment (one ``grc``, one ``deu``).

Key heuristics:

* **Chapter heading**: ``^N. NAME.$`` where NAME matches the Phase-1
  philosopher list (case-insensitive). OCR mis-reads N sometimes
  (32→92, 38→98) so the primary match is on NAME.
* **Fragment-start (Greek)**: ``^N. [<old-num>] ...`` — opens a new
  Greek block. The leading source citation (e.g.,
  "Sext. adv. math. vii 132") runs up to the first Greek-script
  character and is captured into ``chunk.book``.
* **Fragment-start (German)**: ``^N. <capital-letter-word>`` — German
  translation of fragment N. Discriminator vs. Greek fragments is
  the immediate ``[`` after ``N. ``.
* **Apparatus**: ``^N <word>`` (number NOT followed by period) is a
  footnote-style line reference. It stays apparatus, however the
  following lines look, until the page ends; the apparatus is emitted
  as ``block_type='editorial'`` chunks beside the fragment it follows.
  A leading number also marks every fifth *verse* (#680), so a numbered
  line that follows Greek text and carries no apparatus signature is
  text, with its margin number stripped.
* **Page layout**: Greek, then German, then apparatus, then the footer
  and the next running head. Greek after the German on the same page is
  apparatus (#673); German that resumes at the top of a page, before
  any German opener, continues the last German fragment.
* **Doubtful / spurious / forged fragments**: the ``ZWEIFELHAFTES``,
  ``UNECHTES`` and ``GEFÄLSCHTE FRAGMENTE`` sections at the end of a
  chapter's B-fragments. Kept, but every fragment from the first one
  after such a heading is typed ``block_type='spurious'``, in both
  languages, so it is not counted as the author's words (#683).
* **Latin**: a few fragments survive only in Latin (Parmenides B 18,
  Heraclitus B 67a, Empedocles B 94). Latin prose in the text column is
  kept in the Greek edition's chunk, where the lemmatizer's cross-script
  pass gives it the Latin model (#430).

``chunks.section`` is a Diels–Kranz locator, ``<chapter> B <fragment>``:

* the **chapter** number is Kranz's (DK 6th ed.), not the 1912 source's;
  the map lives in ``presocratic_works._PHASE_1``;
* the **fragment** number is the 1912 source's as printed, mapped to
  DK's by ``_DK_RENUMBERED`` / ``_DK_SPLITS`` where the two differ
  (Parmenides B 2–5, Empedocles B 3–5, Heraclitus B 84 → 84a/84b;
  #738). Before that map this docstring called the whole locator
  Kranz's while the fragment number was 1912's, which is how the
  difference went unnoticed. The text itself is still the 1912 edition,
  which is what ``edition_year`` says.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import NamedTuple

from minerva.authors.presocratic_works import _PHASE_1, find_by_chapter_heading
from minerva.tei import Chunk, _make_chunk_id, _norm_text

# A fragment's number and letter: (67, "a") is DK B 67a, (67, "") is B 67.
FragKey = tuple[int, str]


class _Raw(NamedTuple):
    """One fragment opener as the OCR printed it, before the parser has
    decided which fragment it opens (`_resolve_key`)."""

    num: int
    # "" plain; "a"/"b" an explicit letter (OCR `°` and `%` are "a");
    # "digit" a last digit that may be OCR for "a" (`675,` = 67a);
    # "next" no number at all, the fragment after the last one.
    mark: str
    # A comma for the full stop: the number must fit the sequence (#681).
    checked: bool
    body: str
    # Printed jointly with the opener before it (`77. 78. [`): the two
    # fragments share one text, in DK as on the page (#737).
    joint: bool = False


# Chapter heading: `12. HERAKLEITOS.` — uppercase Latin name, optional
# trailing junk. The source has many variants:
#  * `12. HERAKLEITOS.`           — clean
#  * `1. THALES. 3`               — trailing page number
#  * `21. EMPEDOKLES,.`           — OCR garble (stray comma)
#  * `3. ANAXIMENES. 17 A. LEBEN UND LEHRE.` — page + next section fused
#  * `51. DIOGENES VON APOLLONIA.` — multi-word name
# We capture the leading integer + first uppercase-name token. Anything
# after that is ignored; validation happens against the Phase-1 lookup
# table (a stray match like `1. SEXT.` won't resolve to a real
# philosopher and is dropped).
_CHAPTER_HEADING_RE = re.compile(
    # Integer permissive of common OCR substitutions: `5l.` for `51.`
    # (line-end `l` looks like `1`), `1O.` for `10.` (O for zero). The
    # captured integer is unused — name lookup against the Phase-1
    # table is the validation step.
    r"^\s*[\dlIO]{1,4}\.\s+([A-ZÄÖÜ]{3,}[A-ZÄÖÜ]?)\b"
)
# Running-head with leading page number — distinct from a real chapter
# heading because the integer is followed by whitespace (not period).
# Examples: `78 12. HERAKLEITOS.`, `194 21. EMPEDOKLES.`.
_RUNNING_HEAD_CHAPTER_RE = re.compile(r"^\s*\d+\s+\d{1,3}\.\s+[A-ZÄÖÜ]{3,}")

# `B. FRAGMENTE.` opens the canonical B-fragments block. We accept
# both the standalone form (Heraclitus, Anaximenes) and the running-
# head form (`B. FRAGMENTE. 1—4. 175`, used by Zeno / Empedocles
# where Diels skipped the standalone marker). The transition is
# idempotent — re-firing inside an already-in_b state is a no-op.
# OCR also reads the running head as `B, FRAGMENTE` and with a Greek
# capital beta (`Β. FRAGMENTE`), and Diels abbreviates it `B. FR.` on
# crowded pages; missing any of those misses the page break.
_B_FRAGMENTS_RE = re.compile(r"^\s*[BΒ][.,]\s+FR(?:AGMENTE\b|\.)")

# `A. LEHRE.` or `A. ANGEBLICHE FRAGMENTE.` — testimonia, skip until B.
_A_LEHRE_RE = re.compile(r"^\s*A\.\s+(LEHRE|ANGEBLICHE\s+FRAGMENTE)\b")

# `C. IMITATION.` — end of canonical B-fragments inside a chapter.
_C_IMITATION_RE = re.compile(r"^\s*C\.\s+IMITATION", re.IGNORECASE)

# DK's non-canonical sections, after the genuine fragments: doubtful
# (`ZWEIFELHAFTES.`), false, spurious (`UNECHTES.`) and forged
# (`GEFÄLSCHTE FRAGMENTE.`), alone or combined (`ZWEIFELHAFTE, FALSCHE UND
# GEFÄLSCHTE FRAGMENTE.`), in OCR forms (`UNECHTES,.`, `GEFALSCHTES.`).
# Every fragment from the first one after the heading is typed `spurious`
# (#683). Capitals only: the words occur in the notes' prose too. The
# heading may share its line with the fragment it heads (`ZWEIFELHAFTES.
# 154. Das war …`) or end the line of the one before (`41. Grube.
# ZWEIFELHAFTE FRAGMENTE.`). Running heads that name the sections
# (`154—157 ZWEIFELHAFTES UND UNECHTES. 281`) start and end with numbers.
_NONCANON_WORD = r"(?:ZWEIFELHAFTE|GEF[AÄ]LSCHTE|UNECHTE|FALSCHE)S?"
_NONCANON_HEADING = (
    rf"{_NONCANON_WORD}\b(?:,?\s+(?:UND|{_NONCANON_WORD}|FRAGMENTE|SCHRIFTEN)\b)*[,.]*"
)
_NONCANON_HEADING_RE = re.compile(rf"^\s*{_NONCANON_HEADING}")
_TRAILING_NONCANON_RE = re.compile(rf"\s{_NONCANON_HEADING}\s*$")

# Optional leading print-line-number prefix. The 1912 typesetting
# numbers every 5th line of Greek poetry in the margin; OCR linearizes
# those into the start of fragment lines. Examples:
#   `25 1. [1—32. 52—57 Karst.] ...` — print line 25, fragment 1
#   `5 1. [...] ...`                  — print line 5, fragment 1
# Stripped at classification time so fragment-start regexes see a clean
# `\d+\.` opener (or `15 101%.`, an "a" fragment behind its line number).
_LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s+(?=\d+[°%ab]?[.,]\s)")

# A title in capitals ahead of the first opener on its line: `FRAGMENTE
# ÜBER DIE NATUR. 1. Pausanias, …` heads Empedocles's German (#737).
_LEADING_TITLE_RE = re.compile(r"^\s*(?:[A-ZÄÖÜ]{2,}\s+)+[A-ZÄÖÜ]{2,}\.\s+(?=\d{1,3}[.,]\s)")

# Fragment-start opener: `<N>. <rest>` where rest begins with either:
#   * a `[<cross-ref>]` bracket (Heraclitus / Empedocles / Parmenides
#     style — most chapters with widely-cited old numbering systems);
#   * the source citation immediately (Milesian style — Thales /
#     Anaximander / Anaximenes lack widely-known old numberings, so
#     Diels skipped the cross-ref brackets);
#   * the German translation prose.
#
# We discriminate Greek-fragment vs. German-translation by the
# presence of Greek-script characters anywhere in the line. The
# optional `[cross-ref]` is stripped from the captured body when
# present so downstream source-citation extraction sees clean text.
# Fragment numbers are capped at 3 digits. The largest pre-Socratic
# B-fragment set in DK is Empedocles with ~150 entries; nothing
# legitimately exceeds 999. A fourth digit is the OCR's reading of an
# "a" (`1262.` is 126a), as a third can be (`675,` is 67a), and the
# letter itself comes through as `°`, `%` or `a` (#681). OCR also reads
# the full stop as a comma, and a comma opener's number is only trusted
# when it fits the sequence (`_resolve_key`).
_FRAG_OPENER_RE = re.compile(r"^\s*(\d{1,4})([°%ab]?)([.,])\s+(.*)$")
_LEADING_CROSSREF_RE = re.compile(r"^\[[^\]]*\]\s*")
# Fragments Diels prints under one opener, `77. 78. [366. 367 K. …]` and
# `148. 149. 150. [`, Greek or German: the numbers after the first.
_JOINT_NUMBERS_RE = re.compile(r"^(\s*\d{1,3}\.)\s+((?:\d{1,3}\.\s+)+)(?=\[|[A-ZÄÖÜ])")
_MAX_FRAG = 999
_SUFFIX_MARKS = {"°": "a", "%": "a", "?": "a", "a": "a", "b": "b"}
# How far past the last fragment a comma opener's number may run and
# still be taken as printed: fragments missing from one language make
# small gaps, and OCR misreadings (`48` for 43, `94` for 24) large ones.
_SEQUENCE_SLACK = 3

# A ditto opener that lost its fragment number: `[86] — — iii 14 …`, the
# old number in brackets, then the source (repeated as dashes). The OCR
# moved the numbers into a margin column on that page (#681).
_NUMBERLESS_OPENER_RE = re.compile(r"^\s*\[\d[^\]]*\]\s*(?:[—-]\s*[—-]|[A-Z])")

# A source cited in capitals (`3. OLYMPIODOR. de arte sacra …`, `94,
# SUETONIUS …`) opens the Greek side even before any Greek script: no
# German translation in the source opens with a word in capitals.
_CAPS_SOURCE_RE = re.compile(r"[A-ZÄÖÜ][A-ZÄÖÜ-]{3,}\b")

# A German translation opener starts with a capital, sometimes behind an
# opening quote (`152. “Der Abend …`); a cross-reference with `=` (`138,
# = Poseidippos …`); or mid-sentence, on an ellipsis (`3. ... zu wahren`).
_GERMAN_START_RE = re.compile(r"=\s+[A-ZÄÖÜ]|\.{2,}[\s.]*[a-zäöüß]|[“„\"‘]?[A-ZÄÖÜ]")
# `9... . während`: the opener's full stop runs into the ellipsis.
_STOP_INTO_ELLIPSIS_RE = re.compile(r"^(\s*\d{1,3})\.(?=\.\.)")
# A German word, not an abbreviated source (`Ausust. de …`), to open with.
_GERMAN_WORD_START_RE = re.compile(r"[“„\"‘]?[A-ZÄÖÜ][a-zäöüß]+(?![\w.])")
# German with a few OCR Greek letters in it (`ὦ. h.` for `d. h.`, `(Ὁ)`
# for `(?)`) is still German: at most this many, and a quarter of its
# Latin letters.
_STRAY_GREEK_MAX = 10

# Crammed-line split (Greek): in Xenophanes (and intermittently
# elsewhere) the OCR linearizes multiple Greek B-fragments onto ONE
# long text line — `25. 3 K., 14 Cr.] ... Kpadalveı. 26. [4 K., 15
# Cr.) ... 27. [8 K., 11 Cr.) ...`. We split at every interior
# occurrence of whitespace + digits + period + space + opening
# bracket. The bracket requirement avoids false-splitting on
# cross-references like `[A 31, 9` (A-fragment refs that have a Latin
# letter, not digits, before the comma). An "a"/"b" fragment may take a
# comma (`154b, [0]`); a plain number needs its full stop.
_CRAMMED_FRAG_SPLIT_RE = re.compile(r"\s+(\d{1,3})(?:\.|([°%ab])[.,])\s+\[")

# Crammed-line split (German): the German translation block packs
# fragments back-to-back on long OCR lines too, e.g.
# `11. Alles, was da kreucht ... 12. Wer in dieselben Fluten ...
# 13. Am Dreck sich ergetzen.`. The discriminator is a leading
# integer + dot-OR-comma (OCR sometimes reads `12.` as `12,`) + space
# + Latin capital + Latin lowercase. The capital-lowercase pair
# avoids splitting on incidental numbers inside the German prose.
# The OCR reads an "a" as `?` here too, and its stop as `.,` (`154?.,
# Wehen …`, Empedocles B 154a).
_CRAMMED_GERMAN_SPLIT_RE = re.compile(r"\s+(\d{1,3})([°%ab?]?)(?:[.,]|\.,)\s+(?=[A-ZÄÖÜ][a-zäöüß])")


def _inner_raw(m: re.Match[str], body: str) -> _Raw:
    """An opener found inside a line: its number is taken as printed."""

    return _Raw(int(m.group(1)), _SUFFIX_MARKS.get(m.group(2) or "", ""), False, body)


def _split_crammed_greek(first: _Raw, body: str) -> list[_Raw]:
    """Split a Greek-fragment line that crams multiple ``N. [...]``
    openers onto one OCR-linearized text line. Returns the openers in
    source order, ``first`` carrying the text before the first split.

    The first fragment's body runs from the start of the input to the
    first inner split position; each subsequent split takes the
    fragment number from the matched group and the body up to the next
    split (or end of input). The leading cross-ref bracket is stripped
    from every body via the same regex used for the single-fragment
    case.
    """

    matches = list(_CRAMMED_FRAG_SPLIT_RE.finditer(body))
    if not matches:
        return [first._replace(body=_LEADING_CROSSREF_RE.sub("", body))]

    first_body = body[: matches[0].start()]
    out = [first._replace(body=_LEADING_CROSSREF_RE.sub("", first_body))]
    for i, m in enumerate(matches):
        # Body of this inner fragment starts at the `[` we matched
        # and runs until the next split (or end).
        body_start = m.end() - 1  # `m.end()` is one past `[`
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append(_inner_raw(m, _LEADING_CROSSREF_RE.sub("", body[body_start:body_end])))
    return out


def _split_crammed_german(first: _Raw, body: str) -> list[_Raw]:
    """German analog of :func:`_split_crammed_greek`. Splits a German
    translation block on interior ``N. <CapitalizedWord>`` markers.

    Unlike the Greek splitter, there is no leading cross-ref bracket
    to strip — the German block is plain prose.
    """

    matches = _german_splits(body, _sequence_bases(first))
    if not matches:
        return [first._replace(body=body.strip())]

    out = [first._replace(body=body[: matches[0].start()].strip())]
    for i, m in enumerate(matches):
        body_start = m.end()  # past the `N. ` separator
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append(_inner_raw(m, body[body_start:body_end].strip()))
    return out


def _sequence_bases(raw: _Raw) -> tuple[int, ...]:
    """The numbers an opener may stand for, for what follows it: `675`
    is 675 or 67a."""

    return (raw.num, raw.num // 10) if raw.mark == "digit" else (raw.num,)


def _german_splits(body: str, bases: tuple[int, ...]) -> list[re.Match[str]]:
    """The ``N. <Word>`` markers in German prose that open fragments.

    Only one that carries the numbering on from the opener before it
    counts: an ordinal in the prose, `(d. i. im 7. und 10. Monat …)`
    inside Empedocles B 69, is not B 10 (#737)."""

    out: list[re.Match[str]] = []
    for m in _CRAMMED_GERMAN_SPLIT_RE.finditer(body):
        num = int(m.group(1))
        if bases and not any(b <= num <= b + _SEQUENCE_SLACK for b in bases):
            continue
        out.append(m)
        bases = (num,)
    return out


def _read_number(digits: str, mark: str, comma: bool) -> _Raw | None:
    """The opener's number as printed, or None if it cannot be one."""

    if mark:
        return _Raw(int(digits), _SUFFIX_MARKS[mark], False, "") if len(digits) < 4 else None
    if len(digits) >= 3 and digits[-1] in "25":
        return _Raw(int(digits), "digit", comma, "")
    if len(digits) == 4:
        return None
    return _Raw(int(digits), "", comma, "")


def _in_sequence(num: int, last: FragKey) -> bool:
    return last[0] < num <= last[0] + _SEQUENCE_SLACK


def _is_digit_suffix(num: int, last: FragKey) -> bool:
    # `675` right after 67 is 67a; `125` right after 124 is 125.
    return num // 10 == last[0] and not _in_sequence(num, last)


def _suffixed(num: int, mark: str, buf: dict[FragKey, list[str]]) -> FragKey:
    # The OCR prints 126a and 126b both as `126°`, and 154c as `154°`
    # after `154b,`: an "a" already taken is the next letter free.
    letter = mark
    while mark == "a" and (num, letter) in buf:
        letter = chr(ord(letter) + 1)
    return (num, letter)


def _file_openers(
    buf: dict[FragKey, list[str]], last: FragKey | None, raws: list[_Raw]
) -> list[FragKey] | None:
    """File each opener's text under its fragment, returning the
    fragments opened. None, filing nothing, when the first opener opens
    none (`_resolve_key`); one found inside a line always does."""

    keys: list[FragKey] = []
    for raw in raws:
        key = _resolve_key(raw, buf, last)
        if key is None:
            return None
        if raw.joint and last is not None and key not in buf:
            # One list for both: what follows on later lines is theirs too.
            buf[key] = buf[last]
        else:
            buf.setdefault(key, []).append(raw.body)
        keys.append(key)
        last = key
    return keys


def _resolve_key(raw: _Raw, buf: dict[FragKey, list[str]], last: FragKey | None) -> FragKey | None:
    """The fragment an opener opens, given the language's fragments so
    far, or None when it opens none and is text after all."""

    if raw.mark == "next":
        return None if last is None else (last[0] + 1, "")
    if raw.mark in ("a", "b"):
        return _suffixed(raw.num, raw.mark, buf)
    if raw.mark == "digit" and last is not None and _is_digit_suffix(raw.num, last):
        return _suffixed(raw.num // 10, "a", buf)
    if raw.num > _MAX_FRAG:
        return None
    if last is None or _in_sequence(raw.num, last):
        return (raw.num, "")
    return _resolve_out_of_sequence(raw, buf, last)


def _resolve_out_of_sequence(
    raw: _Raw, buf: dict[FragKey, list[str]], last: FragKey
) -> FragKey | None:
    """:func:`_resolve_key` for an opener that does not continue the
    language's sequence: a repeat, a misread number, or text after all."""

    if raw.num == last[0]:
        # `154. Die zuerst …` after `154?.,` (154a) is 154b: a number
        # repeated inside a lettered run takes the next letter (#737).
        return _suffixed(raw.num, "a", buf) if last[1] else (raw.num, "")
    if not raw.checked:
        return _misread_as(raw.num, last, buf) or (raw.num, "")
    # A misread number (`48,` for 43, between 42 and 44) is the next
    # fragment, unless that one is already there.
    nxt = (last[0] + 1, "")
    return None if nxt in buf else nxt


# Digits the OCR reads one for another in fragment numbers, printed →
# true, each pair measured in the source (#737): `85.` for 35, `90.` for
# 20 and 30, `11.` for 71, `79.` for 75, `156.` for 125.
_OCR_DIGIT_MISREADS = frozenset(
    {
        ("8", "3"),
        ("9", "3"),
        ("9", "2"),
        ("1", "7"),
        ("9", "5"),
        ("5", "2"),
        ("6", "5"),
        ("0", "6"),
        ("4", "7"),
    }
)


def _misreadings(printed: str, true: str) -> int | None:
    """How many OCR misreadings turn ``true`` into ``printed``, or None
    if they can't: digits misread one for another, or one stray digit
    (`297.` for 27)."""

    if len(printed) == len(true) + 1:
        strays = (printed[:i] + printed[i + 1 :] for i in range(len(printed)))
        return 1 if true in strays else None
    if len(printed) != len(true):
        return None
    pairs = [(p, t) for p, t in zip(printed, true, strict=True) if p != t]
    return len(pairs) if all(pair in _OCR_DIGIT_MISREADS for pair in pairs) else None


def _misread_as(num: int, last: FragKey, buf: dict[FragKey, list[str]]) -> FragKey | None:
    """The fragment an out-of-sequence full-stop opener stands for: one
    just after the last, not there yet, that the OCR could have misread
    as ``num``. Two misread digits only for the very next fragment.
    Nothing for a plain jump (Heraclitus German 18 → 26, the 19–25
    between them lost), which is why the sequence alone never decides."""

    for true in range(last[0] + 1, last[0] + _SEQUENCE_SLACK + 1):
        if (true, "") in buf:
            continue
        misread = _misreadings(str(num), str(true))
        if misread == 1 or (misread == 2 and true == last[0] + 1):
            return (true, "")
    return None


# An apparatus note on two consecutive print lines, `4. 5 (16, 1. 2)
# erg. *:` or `2. 3 παῖδες ἀπορραίσαντε]`, looks like an opener of
# fragment 4 or 2 (#737). An opener whose bracket the OCR lost has an old
# number after its own, rarely the next one, and then with the edition's
# siglum (`7. 8 K., 6 Cr.]`, Xenophanes B 7; Karsten, Stein, Crusius).
_LINE_RANGE_RE = re.compile(r"^\s*(\d{1,3})\.\s+(\d{1,3})(?=[\s(])(?!\s*(?:K|St|Cr)\.)")


def _is_line_range(line: str) -> bool:
    m = _LINE_RANGE_RE.match(line)
    return m is not None and int(m.group(2)) == int(m.group(1)) + 1


# Apparatus footnote: `N <word>` — integer NOT followed by period.
# Skipped. Note: lines starting `N. ` (period) are fragment-starts, not
# apparatus. The trailing space + word distinguishes apparatus from
# bare page numbers (which are `\d+` alone, also skipped).
_APPARATUS_RE = re.compile(r"^\s*\d+\s+\S")

# The same leading integer is a print line number, and Diels prints one
# beside every fifth verse, so it marks verse lines too (#680). Inside
# Greek text, a numbered Greek line is verse unless it carries one of
# the apparatus signatures below. The number itself is no guide: OCR
# garbles it (`16` for 15, `0`, `80` for 30).
_LEADING_LINE_NUMBER_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
# What an apparatus note has and a verse line does not: a lemma bracket,
# Diels's `*` for his own conjecture, a siglum or scholar's name before
# the `:` separating variant readings, and the commonest abbreviations.
# The siglum must be Latin-script: OCR renders Greek high stops as `:`.
# A line can also end on a bare siglum (`22 αἵματ᾽ ἐγένοντο F`).
_APPARATUS_SIGNATURE_RE = re.compile(
    r"\]|\*|[A-Za-z][\w.]*\s?:|\bHss?\.|\b[Vv]gl\.|\bverb\.|\berg\.|\bfehlt\b|\bübr|\bmeisten\b"
)
_TRAILING_SIGLUM_RE = re.compile(r"\s[A-Z]{1,3}\s*$")


def _has_apparatus_signature(text: str) -> bool:
    return bool(_APPARATUS_SIGNATURE_RE.search(text) or _TRAILING_SIGLUM_RE.search(text))


# Page footer: `Diels, Fragm. d. Vorsokr. I. 3. Aufl. 17`, and the
# `17*` signature mark on the first page of each sheet. Without its own
# kind the footer was routed as German text, and ` 3. Aufl.` split off
# a phantom German fragment 3.
_PAGE_FOOT_RE = re.compile(r"^\s*(?:Diels,\s*Fragm\..*|\d+\*\s*)$")

# German prose, told apart from a Latin source citation: two or more
# German function words. Used only for a non-Greek line met while the
# parser is still in Greek text at the top of a page.
_GERMAN_FUNCTION_WORD_RE = re.compile(
    r"\b(?:der|die|das|des|den|dem|und|ist|nicht|sich|sie|er|es|ein|eine|einer|zu|von|mit|auf|aber"
    r"|als|wie|wenn|denn|noch|auch|so|im|daß)\b",
    re.IGNORECASE,
)


# Diels's own insertions in the text, `[Β 6]`, `[Arist. phys. …]`. Their
# brackets are paired, unlike an apparatus lemma bracket, and their
# Latin script says nothing about the line around them.
_BRACKETED_RE = re.compile(r"\[[^\]]*\]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-zÄÖÜäöüß]")


def _numbered_verse(line: str) -> str | None:
    """The verse text of a numbered line, or None if it is apparatus."""

    m = _LEADING_LINE_NUMBER_RE.match(line)
    if m is None:
        return None
    body = m.group(2).strip()
    bare = _BRACKETED_RE.sub("", body)
    # Verse is Greek: a German note that quotes a Greek word is not.
    if len(_GREEK_CHAR_RE.findall(bare)) <= len(_LATIN_LETTER_RE.findall(bare)):
        return None
    if _has_apparatus_signature(bare) and not _looks_like_text(body):
        return None
    return body


def _looks_like_text(line: str) -> bool:
    """Running Greek, with Latin-script letters under a tenth of it.

    Apparatus quotes Greek, but always among sigla, scholars' names and
    German, and runs at about 1.5 Latin letters per Greek one. Text keeps
    a few, from OCR reading Greek capitals as Latin (`TPOTOV`, `TE`);
    the highest measured in the source is 0.08. A line like this after
    the apparatus has begun is text on a page whose running head the OCR
    lost, and it outweighs a stray `]` or `:` from the OCR.
    """

    body = _BRACKETED_RE.sub("", line)
    greek = len(_GREEK_CHAR_RE.findall(body))
    return greek >= 30 and len(_LATIN_LETTER_RE.findall(body)) <= greek / 10


# Latin quotations in the notes trip the German list through OCR (`sic`
# read as `sie`, `in` as `im`), so German must also outnumber these.
_LATIN_FUNCTION_WORD_RE = re.compile(
    r"\b(?:et|est|sunt|in|ad|ex|de|cum|qui|quae|quod|ut|non|sed|enim|autem|atque"
    r"|nam|nec|si|aut|vel)\b"
)


def _looks_latin(text: str) -> bool:
    """Latin prose, as opposed to German or a bare source citation
    (`Theophr. p. 5. 7. ed. Paris.`, no function word at all)."""

    latin = len(_LATIN_FUNCTION_WORD_RE.findall(text))
    return latin >= 1 and latin > len(_GERMAN_FUNCTION_WORD_RE.findall(text))


def _looks_german(text: str) -> bool:
    german = len(_GERMAN_FUNCTION_WORD_RE.findall(text))
    return german >= 2 and german > len(_LATIN_FUNCTION_WORD_RE.findall(text))


def _greek_is_stray(text: str) -> bool:
    """Whether the Greek letters in a line are too few to make it Greek."""

    greek = len(_GREEK_CHAR_RE.findall(text))
    return greek <= _STRAY_GREEK_MAX and greek * 4 <= len(_LATIN_LETTER_RE.findall(text))


def _is_greek_text(text: str) -> bool:
    """Greek, as opposed to German that the OCR sprinkled with a Greek
    letter or two (`ΟἹ, Meerwasser ist …` for `61. Meerwasser …`)."""

    if not _GREEK_CHAR_RE.search(text):
        return False
    return not (_greek_is_stray(text) and _looks_german(text))


def _is_german_opener_body(body: str) -> bool:
    """A translation opener, whatever stray Greek letters it carries. An
    opener's first word is evidence too: German translations of single
    words (`148. Menschenumgebenden Erdstoff …`) have no function words."""

    if not _GERMAN_START_RE.match(body):
        return False
    if not _GREEK_CHAR_RE.search(body):
        return True
    return _greek_is_stray(body) and bool(_looks_german(body) or _GERMAN_WORD_START_RE.match(body))


# Greek script Unicode ranges. The source citation runs up to the
# first Greek-script character; everything from there to end of block
# is the actual fragment text.
_GREEK_CHAR_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")

# A "pure Greek token": one or more Greek letters / polytonic
# combining marks / apostrophe variants used in elision (e.g.
# `τοῦδ᾽`), surrounded by optional punctuation. Used to locate the
# start of real fragment text past OCR-confused Roman numerals
# (`vii` → `ναι`) and editorial parentheticals like
# `(Vgl. Α 4. 16. B51)`. Punctuation stripping is conservative —
# we strip a closed set of common punctuation and brackets, NOT
# anything that could overlap Latin letters.
_GREEK_CORE_RE = re.compile(r"^[Ͱ-Ͽἀ-῿̀-ͯ᾽'’]+$")
_GREEK_TOKEN_PUNCT = "().,;:·!?\"'’«»"


def _is_greek_token(tok: str) -> bool:
    core = tok.strip(_GREEK_TOKEN_PUNCT)
    return bool(core) and bool(_GREEK_CORE_RE.match(core))


def _strip_source_citation(raw: str) -> tuple[str | None, str]:
    """Split a Greek-fragment block into ``(source_citation,
    fragment_text)``.

    Naive heuristic: cut at the first Greek character. That fails on
    OCR-confused Roman numerals — Latin lowercase `v`/`i`/`x` get
    rendered as Greek `ν`/`ι`/`χ`, so a source citation like
    ``Sext. adv. math. vii 132`` linearizes to
    ``Sext. adv. math. ναι 132`` and the naive cut starts the body
    at ``ναι 132 ...``, leaking the location reference into the
    Greek text.

    Better heuristic: find the first PAIR of consecutive pure-Greek
    tokens (whitespace-separated). Real fragment text always has
    several Greek words in a row; OCR'd Roman numerals are isolated
    pseudo-Greek tokens surrounded by Latin or digits.

    Falls back to the naive cut when no pair is found (rare; some
    fragments preserve only a Latin paraphrase, e.g. Albertus Magnus
    on Heraclitus B 4).
    """

    tokens_with_pos = [(m.group(0), m.start()) for m in re.finditer(r"\S+", raw)]
    if not tokens_with_pos:
        return None, _norm_text(raw)

    real_start: int | None = None
    for i in range(len(tokens_with_pos) - 1):
        tok_a, _ = tokens_with_pos[i]
        tok_b, _ = tokens_with_pos[i + 1]
        if _is_greek_token(tok_a) and _is_greek_token(tok_b):
            real_start = i
            break

    if real_start is None:
        # No pair of consecutive Greek tokens found — fall back to the
        # naive "first Greek char" cut. Latin-only Heraclitus B 4
        # (Albertus Magnus paraphrase) lands here too: no Greek at
        # all, so return the whole text as-is.
        m = _GREEK_CHAR_RE.search(raw)
        if m is None:
            return None, _norm_text(raw)
        head = raw[: m.start()].rstrip().rstrip(",;:")
        body = raw[m.start() :]
        body = re.sub(r"\s*\[[^\]]*\]\s*$", "", body)
        return (head or None), _norm_text(body)

    if real_start == 0:
        # No source citation prefix at all — the line opened with
        # Greek text directly.
        body = re.sub(r"\s*\[[^\]]*\]\s*$", "", raw)
        return None, _norm_text(body)

    _, body_start = tokens_with_pos[real_start]
    head = raw[:body_start].rstrip().rstrip(",;:")
    body = raw[body_start:]
    body = re.sub(r"\s*\[[^\]]*\]\s*$", "", body)
    return (head or None), _norm_text(body)


def _dehyphenate(text: str) -> str:
    """Join soft-hyphenated words split across (formerly) two lines.

    OCR commonly produces ``probieren mit\nWorten`` → flattened to
    ``probier-\n en`` then linearized to ``probier- en``. We rejoin
    ``WORD- WORD`` patterns where the hyphenated word is German.
    Conservative: only joins when the suffix begins with a lowercase
    Latin letter to avoid joining across actual em-dashes or Greek.
    """

    # ``foo- bar`` → ``foobar`` (German pattern; Greek doesn't break this way
    # in the source).
    return re.sub(r"(\w)-\s+([a-zäöüß])", r"\1\2", text)


# Openers the OCR lost or garbled beyond any rule, restored by the text
# they open (#737): the content is the key, never a line number, so a
# re-OCR that fixes or moves a line leaves the entry inert.
_OCR_REPAIRS: tuple[tuple[str, str], ...] = (
    # Heraclitus B 19–25: the German page lost its numbers to a margin
    # column (`19.` `20.` `21.` on lines of their own), and 22 and 23
    # share a line.
    ("Leute, die weder zu hören", "19. Leute, die weder zu hören"),
    ("Heraklit scheint die Geburt", "20. Heraklit scheint die Geburt"),
    ("Tod ist alles, was wir im Wachen", "21. Tod ist alles, was wir im Wachen"),
    ("Denn die Goldgräber schaufeln", "22. Denn die Goldgräber schaufeln"),
    ("und finden wenig. Gäb’ es jenes", "und finden wenig. 23. Gäb’ es jenes"),
    ("Im Kriege Gefallene ehren", "24. Im Kriege Gefallene ehren"),
    ("Größerer Tod empfängt", "25. Größerer Tod empfängt"),
    # Heraclitus B 61's German, its number read as Greek letters.
    ("ΟἹ, Meerwasser ist", "61. Meerwasser ist"),
    # Empedocles B 89's Greek, inside B 88's line, its bracket read `1`.
    ("ὄψ. 89. 1267 K., 281 St.)", "ὄψ. 89. [267 K., 281 St.)"),
    # Heraclitus B 85's Greek, its 5 read as a Greek letter.
    ("8ὅ. [105] Pur. Coriol.", "85. [105] Pur. Coriol."),
    # Heraclitus B 126b's Greek, `126b` read as four digits.
    ("1960, [0] Anonym.", "126b, [0] Anonym."),
    # Parmenides's Greek 1912 B 2 (DK B 4), read `3.`: it merged into B 3,
    # the next opener, which the misreading made a repeat of it (#738).
    ("3. [89---92 K., 37—40 St.]", "2. [89---92 K., 37—40 St.]"),
)


def _repair_ocr(line: str) -> str:
    for garbled, repaired in _OCR_REPAIRS:
        if garbled in line:
            line = line.replace(garbled, repaired, 1)
    return line


def _classify_chrome(line: str) -> str | None:
    """'blank', 'page_num', 'running_head' or 'page_foot', else None."""

    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.isdigit():
        return "page_num"
    if _RUNNING_HEAD_CHAPTER_RE.match(line):
        # `78 12. HERAKLEITOS.` — page-number running head, not a real
        # chapter transition.
        return "running_head"
    if _PAGE_FOOT_RE.match(line):
        return "page_foot"
    return None


def _split_noncanon_heading(line: str) -> tuple[str, str] | None:
    """``(before, after)``: the text sharing a line with a non-canonical
    section heading, or None if the line has none."""

    m = _NONCANON_HEADING_RE.match(line)
    if m is not None:
        return "", line[m.end() :].strip()
    m = _TRAILING_NONCANON_RE.search(line)
    if m is not None:
        return line[: m.start()].strip(), ""
    return None


def _is_chapter_heading(line: str, m: re.Match[str]) -> bool:
    """A Phase-1 philosopher's name, or an unknown one on a line of its
    own. An unknown capitalised name with text after it is a source
    cited in capitals (`3. OLYMPIODOR. de arte sacra …`, Anaximenes B 3),
    so the line is a fragment opener."""

    if find_by_chapter_heading(None, m.group(1).upper()) is not None:
        return True
    return not any(ch.islower() for ch in line[m.end() :])


def _classify_opener(candidate: str) -> tuple[str, list[_Raw]] | None:
    """A `N. …` fragment opener, Greek or German, or None.

    A leading `[<crossref>]` bracket is a reliable signal of a Greek
    B-fragment opener (old-numbering reference: Bywater, Karsten,
    Crusius, ...), even when this OCR line carries only the Latin source
    citation. Otherwise Greek script makes it Greek, unless the line is
    German with a few OCR Greek letters in it (#681). German openers
    start with a capital, so `1. p. 96` page refs are neither. Either
    side may cram several fragments onto one OCR line.
    """

    candidate, joint = _split_joint_numbers(candidate)
    m = _FRAG_OPENER_RE.match(candidate)
    if m is None:
        return None
    digits, mark, stop, body = m.groups()
    first = _read_number(digits, mark, stop == ",")
    if first is None:
        return None
    kind = _opener_kind(body, stop)
    if kind is None:
        return None
    split = _split_crammed_greek if kind == "frag_greek" else _split_crammed_german
    raws = split(first, body)
    raws[1:1] = [_Raw(n, "", False, "", joint=True) for n in joint]
    return kind, raws


def _split_joint_numbers(candidate: str) -> tuple[str, list[int]]:
    """``77. 78. [ …`` as ``77. [ …``, and the numbers it shares with."""

    m = _JOINT_NUMBERS_RE.match(candidate)
    if m is None:
        return candidate, []
    joint = [int(n) for n in re.findall(r"\d+", m.group(2))]
    return f"{m.group(1)} {candidate[m.end() :]}", joint


def _opener_kind(body: str, stop: str) -> str | None:
    """Whether an opener's text opens the Greek or the German side."""

    if body.startswith("[") or _CAPS_SOURCE_RE.match(body):
        return "frag_greek"
    if _is_german_opener_body(body):
        return "frag_german"
    # A comma opener is taken only with a bracket, a source or as German.
    if stop == "." and _GREEK_CHAR_RE.search(body):
        return "frag_greek"
    return None


def _classify_line(line: str) -> tuple[str, object]:
    """Classify one line. Returns (kind, payload) where kind is one of:
    'chapter', 'b_marker', 'a_marker', 'c_marker', 'noncanon',
    'frag_greek', 'frag_german', 'apparatus', 'running_head',
    'page_num', 'page_foot', 'blank', 'heading', 'continuation'.
    """

    chrome = _classify_chrome(line)
    if chrome is not None:
        return chrome, None

    # B-marker matches both the standalone `B. FRAGMENTE.` line AND
    # the running-head `B. FRAGMENTE. 1—4. 175` form. Either suffices
    # to transition into in_b mode; for chapters where Diels skipped
    # the standalone (Zeno, Empedocles, etc.) the running head is the
    # only signal.
    if _B_FRAGMENTS_RE.match(line):
        return "b_marker", None
    if _A_LEHRE_RE.match(line):
        return "a_marker", None
    if _C_IMITATION_RE.match(line):
        return "c_marker", None
    heading = _split_noncanon_heading(line)
    if heading is not None:
        return "noncanon", heading

    # Chapter heading: ALL-UPPERCASE name token (Latin only). Source-
    # citation openers like `1. Pur. de prim.` or `1. Dioc. ix 1—17.`
    # have mixed-case after the first uppercase letter, so they
    # don't match the chapter regex (`[A-ZÄÖÜ]{3,}` needs 3
    # consecutive uppercase chars). Checked BEFORE the fragment
    # opener so `12. HERAKLEITOS.` isn't misclassified as a
    # German-translation fragment.
    m = _CHAPTER_HEADING_RE.match(line)
    if m is not None and _is_chapter_heading(line, m):
        name = m.group(1).upper().rstrip(".")
        return "chapter", (None, name)
    return _classify_text_line(line)


def _classify_text_line(line: str) -> tuple[str, object]:
    """:func:`_classify_line` for a line that is no marker or heading:
    a fragment opener, apparatus, or text."""

    # Strip an optional leading print-line-number prefix before
    # fragment-start detection. Without this, lines like
    # `25 1. [1—32. 52—57 Karst.] ...` (Parmenides B 1) hit the
    # apparatus regex and the actual fragment-start is dropped.
    candidate = _LEADING_TITLE_RE.sub("", _LINE_NUMBER_PREFIX_RE.sub("", line))
    candidate = _STOP_INTO_ELLIPSIS_RE.sub(r"\1. ", candidate)
    if _is_line_range(candidate):
        return "apparatus", line.strip()
    opener = _classify_opener(candidate)
    if opener is not None:
        return opener[0], (opener[1], line.strip())
    if _NUMBERLESS_OPENER_RE.match(line) and _GREEK_CHAR_RE.search(line):
        raw = _Raw(0, "next", False, _LEADING_CROSSREF_RE.sub("", line.strip()))
        return "frag_greek", ([raw], line.strip())

    if _APPARATUS_RE.match(line):
        return "apparatus", line.strip()

    # No lowercase letter in either script: a section heading
    # (`GEFÄLSCHTE FRAGMENTE.`, `UNECHTES.`) or a running head OCR ran
    # together (`FR. 8-10. GEFÄLSCHTE FR. 11—12. …`). Never text.
    if not any(ch.islower() for ch in line):
        return "heading", None

    return "continuation", line.strip()


# A bare fragment number on a line of its own (`19.`), and any line that
# starts with a number and a stop, as a mangled opener does.
_BARE_OPENER_RE = re.compile(r"^\s*\d{1,3}[.,]\s*$")
_OPENER_LIKE_START_RE = re.compile(r"^\s*\d{1,3}\s*[.,°]")

# A fragment opener the classifier missed because OCR read its full stop
# as a comma (`80, [62] Orıc. c. Cels. …`, Heraclitus B 80).
_OPENER_SHAPED_RE = re.compile(r"^\s*\d{1,3}[.,]\s+\[")


def _resumes_text(line: str) -> bool:
    """Whether a line met in the apparatus is really the text again."""

    return _looks_like_text(line) or bool(_OPENER_SHAPED_RE.match(line))


# 1912's fragment numbers where Diels–Kranz's differ (#738), by DK
# chapter. The chapter number has always been Kranz's; the fragment
# number was 1912's until these maps. Only the measured differences
# are here (DK 1960 Bd I, which prints them as `2 (früher 4)` and `3
# (4)`; matched against el.wikisource for Heraclitus and Anaxagoras).
# Everything else is the same number in both. Two known gaps:
# * Diogenes of Apollonia (64) is unverified: DK Bd II could not be read,
#   so his numbers are 1912's as printed, taken to be DK's.
# * Anaximenes's DK B 2a was an A-testimonium in 1912, so it is no
#   B-fragment here, and none is invented for it.
_DK_RENUMBERED: dict[int, dict[int, int]] = {
    28: {2: 4, 3: 5, 4: 2, 5: 3},  # Parmenides
    31: {3: 5, 4: 3, 5: 4},  # Empedocles
}
# 1912 fragments DK divides in two, and where each language divides:
# Heraclitus 1912 B 84 `[83. 82]` is DK 84a `[83]` and 84b `[82]`. The
# conjunction joining them is Plotinus's and Diels's, and neither DK
# fragment's.
_DK_SPLITS: dict[tuple[int, FragKey], tuple[FragKey, FragKey, dict[str, re.Pattern[str]]]] = {
    (22, (84, "")): (
        (84, "a"),
        (84, "b"),
        {
            "grc": re.compile(r"\s+καὶ\s+(?=κάματός)"),
            "deu": re.compile(r"\s+und\s+(?=Es ist ermattend)"),
        },
    ),
}


def _dk_key(dk_chapter: int, key: FragKey) -> FragKey:
    """DK's number for a 1912 fragment (the first half, if DK splits it)."""

    split = _DK_SPLITS.get((dk_chapter, key))
    if split is not None:
        return split[0]
    num = _DK_RENUMBERED.get(dk_chapter, {}).get(key[0], key[0])
    return (num, key[1])


def _divide(text: str, at: re.Pattern[str], lang: str) -> tuple[str, str] | None:
    """A 1912 fragment's text as DK's two, or None if it won't divide.
    The Greek source citation heads both halves."""

    m = at.search(text)
    if m is None:
        return None
    first, second = text[: m.start()], text[m.end() :]
    if lang == "grc":
        cite, _ = _strip_source_citation(_dehyphenate(first))
        second = f"{cite} {second}" if cite else second
    return first, second


def _to_dk(dk_chapter: int, buf: dict[FragKey, list[str]], lang: str) -> dict[FragKey, list[str]]:
    """A language's fragments keyed by DK's numbers instead of 1912's."""

    out: dict[FragKey, list[str]] = {}
    for key, parts in buf.items():
        split = _DK_SPLITS.get((dk_chapter, key))
        halves = None if split is None else _divide(" ".join(parts), split[2][lang], lang)
        if split is not None and halves is not None:
            out[split[0]], out[split[1]] = [halves[0]], [halves[1]]
        elif split is not None:
            out[key] = parts  # undivided: 1912's number, which is honest
        else:
            out[_dk_key(dk_chapter, key)] = parts
    return out


def parse_file(
    path: Path,
    *,
    philosophers: Sequence[tuple[int, int, str, str]] = _PHASE_1,
) -> Iterator[Chunk]:
    """Yield Chunks for every B-fragment of every Phase-1 philosopher
    in the OCR'd source. Two chunks per fragment: one ``grc``, one
    ``deu``.

    Philosophers not in the Phase-1 list are silently skipped — Phase
    2 will widen the list incrementally.
    """

    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    parser = _Parser(path.name)
    for line in text.split("\n"):
        yield from parser.feed(line)
    # Final flush for the last chapter in the file.
    yield from parser.flush_chapter()


class _Parser:
    """The line-at-a-time state machine behind `parse_file`, one method
    per line kind."""

    def __init__(self, source_file: str) -> None:
        self.source_file = source_file
        self.current_phil: tuple[int, int, str, str] | None = None
        self.mode: str = "outside"  # outside | pre_b | in_b | in_c
        self.block: str = "none"  # none | greek | german | apparatus
        # Two separate "last fragment number" trackers, one per language.
        # The page layout interleaves apparatus + page-break running heads
        # between a fragment's Greek lines and its German translation;
        # routing continuations by the language they look like (Greek
        # script vs Latin/German) is more robust than tracking a single
        # cur_frag. See `_classify_line` + `_on_continuation`.
        self.last_greek_frag: FragKey | None = None
        self.last_german_frag: FragKey | None = None
        self.greek_buf: dict[FragKey, list[str]] = {}
        self.german_buf: dict[FragKey, list[str]] = {}
        # Apparatus, keyed by the Greek fragment it follows on the page.
        self.apparatus_buf: dict[FragKey, list[str]] = {}
        # Whether a German opener has been seen since the last page
        # break: until one has, German at the top of a page is the last
        # German fragment carrying on.
        self.german_opened_on_page = False
        # Set when the OCR has put the page's fragment numbers in a
        # margin column (`19.` `20.` `21.` on lines of their own): the
        # German below them has lost its openers, so none of it may be
        # taken for the last fragment resuming. Cleared by a real opener.
        self.german_openers_lost = False
        # The chapter's first doubtful/spurious/forged fragment, whether a
        # section heading is waiting for it, and the fragments opened
        # since (#683). A fragment is spurious when it is numbered from the
        # first and was opened after the heading: the German has no heading
        # of its own, and an OCR misreading earlier in the chapter (`90.`
        # for Xenophanes B 20) must not take a genuine fragment with it.
        self.noncanon_from: FragKey | None = None
        self.noncanon_pending = False
        self.opened_after_heading: set[FragKey] = set()

    def flush_chapter(self) -> Iterator[Chunk]:
        if self.current_phil is None:
            return
        dk = self.current_phil[1]
        greek = _to_dk(dk, self.greek_buf, "grc")
        # Apparatus follows the Greek: under the first half of a split.
        apparatus = {_dk_key(dk, k): v for k, v in self.apparatus_buf.items()}
        spurious = {_dk_key(dk, k) for k in self._spurious_keys()}
        yield from _emit_chapter_chunks(
            self.current_phil,
            greek,
            _to_dk(dk, self.german_buf, "deu"),
            self.source_file,
            apparatus,
            spurious,
        )
        self.greek_buf = {}
        self.german_buf = {}
        self.apparatus_buf = {}
        self.last_greek_frag = None
        self.last_german_frag = None
        self.noncanon_from = None
        self.noncanon_pending = False
        self.opened_after_heading = set()

    def _spurious_keys(self) -> set[FragKey]:
        first = self.noncanon_from
        return {k for k in self.opened_after_heading if first is not None and k >= first}

    def _reset_blocks(self) -> None:
        self.block = "none"
        self.last_greek_frag = None
        self.last_german_frag = None

    def feed(self, line: str) -> Iterator[Chunk]:
        line = _repair_ocr(line)
        kind, payload = _classify_line(line)

        if kind == "chapter":
            yield from self._on_chapter(payload)
            return
        if self.current_phil is None or self.mode == "outside":
            return
        if self.mode == "in_c":
            yield from self._on_imitation(kind, payload)
            return
        if kind in ("a_marker", "b_marker", "c_marker", "noncanon"):
            yield from self._on_marker(kind, payload)
            return
        if kind == "heading" and _BARE_OPENER_RE.match(line):
            self.german_openers_lost = True
        if kind in ("blank", "heading"):
            return
        if kind in ("running_head", "page_num", "page_foot"):
            # Page chrome — never opens or interrupts a fragment, but
            # it does end the page's German and apparatus.
            self._on_page_break()
            return
        # In pre-B mode (skipping testimonia + apparatus), only B-marker
        # transitions matter; everything else is dropped.
        if self.mode == "pre_b":
            return

        # mode == "in_b" beyond this point.
        if kind == "apparatus":
            assert isinstance(payload, str)
            self._on_numbered(payload)
        elif kind == "frag_greek":
            self._on_frag_greek(payload)  # type: ignore[arg-type]
        elif kind == "frag_german":
            self._on_frag_german(payload)  # type: ignore[arg-type]
        elif kind == "continuation":
            assert isinstance(payload, str)
            self._on_continuation(payload)

    def _on_chapter(self, payload: object) -> Iterator[Chunk]:
        # Chapter heading: switch to new philosopher (and flush prior)
        # only when the captured name resolves to a Phase-1 entry.
        # A regex match that doesn't resolve is treated as noise (an
        # uppercase token that happens to follow `N. ` — e.g. a
        # quoted SEXT abbreviation in an A-fragment that we want to
        # ignore in pre_b mode).
        chap_int, name = payload  # type: ignore[misc]
        entry = find_by_chapter_heading(chap_int, name)
        # A philosopher we don't ingest (`47. AROHELAOS.`, OCR and all)
        # still ends the chapter before him (#736). The mode must be
        # `outside`, not `pre_b`: his running heads say `B. FRAGMENTE.`
        # too, and would reopen the B-fragments under the last author.
        if entry is None:
            yield from self._close_chapter()
            return
        # The same philosopher's running head — a page break.
        if entry == self.current_phil:
            self._on_page_break()
            return
        # New Phase-1 philosopher — flush prior chapter's chunks.
        yield from self.flush_chapter()
        self.current_phil = entry
        self.mode = "pre_b"
        self._reset_blocks()

    def _close_chapter(self) -> Iterator[Chunk]:
        yield from self.flush_chapter()
        self.current_phil = None
        self.mode = "outside"
        self._reset_blocks()

    def _on_marker(self, kind: str, payload: object = None) -> Iterator[Chunk]:
        if kind == "a_marker":
            self.mode = "pre_b"
            self._reset_blocks()
        elif kind == "b_marker":
            # First entry into in_b: reset block state. A running-head
            # b_marker re-fire while ALREADY in_b must NOT reset block
            # state — otherwise a page-break running head between a
            # fragment's apparatus and its Greek continuation would
            # erase the `last_greek_frag` we need to resume into.
            #
            # The non-canonical sections are not a block state: they run
            # to the end of the chapter, across these running heads.
            if self.mode != "in_b":
                self.mode = "in_b"
                self._reset_blocks()
            else:
                self._on_page_break()
        elif kind == "c_marker":
            # C-fragments aren't canonical B, but the page's German can
            # still be to come below them (Xenophanes B 43–45, #737):
            # `_on_imitation` keeps that and closes the chapter at the
            # page's end.
            self.mode = "in_c"
            self.block = "none"
        elif self.mode == "in_b":
            # A doubtful/spurious/forged section heading; the testimonia
            # have headings of their own, which say nothing here.
            yield from self._on_noncanon(payload)  # type: ignore[arg-type]

    def _on_imitation(self, kind: str, payload: object) -> Iterator[Chunk]:
        # Below `C. IMITATION.` only the German of the last B-fragments
        # is the chapter's: an opener that carries the German numbering
        # on, and the lines that continue it. The imitations' own numbers
        # start again at 1. Page chrome or a marker ends the chapter.
        if kind in ("running_head", "page_num", "page_foot") or kind.endswith("marker"):
            yield from self._close_chapter()
        elif kind == "frag_german" and self._continues_german(payload):  # type: ignore[arg-type]
            self._on_frag_german(payload)  # type: ignore[arg-type]
        elif kind == "continuation" and self.block == "german":
            assert isinstance(payload, str)
            if not _GREEK_CHAR_RE.search(payload):
                self._on_continuation(payload)

    def _continues_german(self, payload: tuple[list[_Raw], str]) -> bool:
        last = self.last_german_frag
        return last is not None and _in_sequence(payload[0][0].num, last)

    def _on_noncanon(self, payload: tuple[str, str]) -> Iterator[Chunk]:
        # The next fragment opened, in either language, is the first of
        # the section; every one numbered from it is typed spurious.
        before, after = payload
        if before:
            yield from self.feed(before)
        self.noncanon_pending = True
        # `UNECHTES. 217`: a margin number, not a page, and not a fragment.
        if _OPENER_LIKE_START_RE.match(after):
            yield from self.feed(after)

    def _note_opened(self, keys: list[FragKey]) -> None:
        if self.noncanon_pending:
            first = self.noncanon_from
            self.noncanon_from = keys[0] if first is None else min(first, keys[0])
            self.noncanon_pending = False
        if self.noncanon_from is not None:
            self.opened_after_heading.update(keys)

    def _file_greek(self, raws: list[_Raw]) -> bool:
        keys = _file_openers(self.greek_buf, self.last_greek_frag, raws)
        if keys is None:
            return False
        # The "current" Greek fragment for continuation routing is the
        # LAST one on the line: page-break Greek tails belong to it.
        self.last_greek_frag = keys[-1]
        self._note_opened(keys)
        return True

    def _file_german(self, raws: list[_Raw]) -> bool:
        keys = _file_openers(self.german_buf, self.last_german_frag, raws)
        if keys is None:
            return False
        self.last_german_frag = keys[-1]
        self._note_opened(keys)
        return True

    def _on_frag_greek(self, payload: tuple[list[_Raw], str]) -> None:
        # One opener for a normal line, several when the OCR crammed
        # fragments onto one text line.
        raws, line = payload
        if not self._file_greek(raws):
            self._on_continuation(line)
            return
        self.block = "greek"

    def _on_frag_german(self, payload: tuple[list[_Raw], str]) -> None:
        raws, line = payload
        if not self._file_german(raws):
            self._on_continuation(line)
            return
        self.block = "german"
        self.german_opened_on_page = True
        self.german_openers_lost = False

    def _on_page_break(self) -> None:
        # A page's German and apparatus both end with it. The fragment
        # trackers survive: text resumes into them on the next page.
        if self.block in ("german", "apparatus"):
            self.block = "none"
        self.german_opened_on_page = False

    def _on_numbered(self, line: str) -> None:
        # A numbered line in Greek text is a verse line when it looks
        # like one (#680), and opens the apparatus only when it carries
        # an apparatus signature. Anything else there, typically a
        # numbered Latin testimony, is skipped as it always was, rather
        # than opening an apparatus that would swallow what follows.
        verse = _numbered_verse(line)
        if self.block in ("greek", "none"):
            if not _GREEK_CHAR_RE.search(line):
                return
            if verse is not None:
                self._on_continuation(verse)
            elif _has_apparatus_signature(_BRACKETED_RE.sub("", line)):
                self._to_apparatus(line)
            return
        # After the German a leading number is itself apparatus evidence:
        # it takes a clean line that is plainly text to overrule it.
        bare = _BRACKETED_RE.sub("", verse or "")
        if verse is not None and not _has_apparatus_signature(bare) and _looks_like_text(verse):
            self._on_continuation(verse)
            return
        self._to_apparatus(line)

    def _to_apparatus(self, text: str) -> None:
        self.block = "apparatus"
        if self.last_greek_frag is not None:
            self.apparatus_buf.setdefault(self.last_greek_frag, []).append(text)

    def _on_continuation(self, text_payload: str) -> None:
        # Within a page, German with a stray OCR Greek letter is German
        # (#681). At the top of one nothing says which column resumes, and
        # a text column can itself be German: Anaxagoras B 20 is Galen by
        # way of Hebrew, and its next page would join the German of B 19.
        if self.block == "none":
            has_greek = bool(_GREEK_CHAR_RE.search(text_payload))
        else:
            has_greek = _is_greek_text(text_payload)
        # A `N. [` fragment opener ends any apparatus, so a page break
        # the parser missed cannot swallow the next fragment.
        if has_greek and self._split_crammed_greek_continuation(text_payload):
            return
        # Apparatus runs to the end of the page, and Greek below the
        # page's German is apparatus too (#673): the layout is Greek,
        # German, apparatus. A line that is plainly text means the page
        # break went unseen, and it resumes the text.
        # A stray OCR Greek letter (`ΟἹ,` for 61) doesn't make a line Greek.
        greek_below_german = (
            self.block == "german" and len(_GREEK_CHAR_RE.findall(text_payload)) >= 5
        )
        in_apparatus = self.block == "apparatus" or greek_below_german
        if in_apparatus and not _resumes_text(text_payload):
            self._to_apparatus(text_payload)
            return
        if not has_greek and self.block == "greek" and self._german_resumes(text_payload):
            self.block = "german"
        if not has_greek and self._split_crammed_german_continuation(text_payload):
            return
        self._route_by_content(text_payload, has_greek)

    def _split_crammed_greek_continuation(self, text_payload: str) -> bool:
        # Continuation lines can themselves contain interior
        # `N. [<crossref>]` markers when the OCR linearizes a
        # Greek poem followed by mid-line new fragments. Detect
        # and split: the prefix continues the prior Greek
        # fragment; each subsequent split begins a new one.
        first_split = _CRAMMED_FRAG_SPLIT_RE.search(text_payload)
        if first_split is None:
            return False
        prefix = text_payload[: first_split.start()].strip()
        if prefix and self.block in ("apparatus", "german"):
            self._to_apparatus(prefix)
        elif prefix and self.last_greek_frag is not None:
            self.greek_buf[self.last_greek_frag].append(prefix)
        # The first inner fragment + any further crammed
        # ones get split via the shared helper. Note
        # `first_split.end() - 1` backs up to the `[`.
        rest = text_payload[first_split.end() - 1 :]
        raws = _split_crammed_greek(_inner_raw(first_split, ""), rest)
        self._file_greek(raws)
        self.block = "greek"
        return True

    def _split_crammed_german_continuation(self, text_payload: str) -> bool:
        # German continuation can ALSO contain crammed interior
        # `N. <CapitalizedWord>` markers (Heraclitus has many).
        # Split + route similarly to the Greek case.
        if self.block not in ("german", "none"):
            return False
        last = self.last_german_frag
        splits = _german_splits(text_payload, () if last is None else (last[0],))
        if not splits:
            return False
        first_split = splits[0]
        prefix = text_payload[: first_split.start()]
        if prefix.strip() and self.last_german_frag is not None:
            self.german_buf[self.last_german_frag].append(prefix.strip())
        rest = text_payload[first_split.end() :]
        raws = _split_crammed_german(_inner_raw(first_split, ""), rest)
        self._file_german(raws)
        self.block = "german"
        return True

    def _route_by_content(self, text_payload: str, has_greek: bool) -> None:
        # Route the continuation by its CONTENT (Greek vs. Latin)
        # rather than by the block-state machine. After the German
        # block + apparatus + page-break running heads, a Greek
        # poem can resume mid-fragment; routing by content lets us
        # pick that up without an explicit page-break marker. Latin
        # prose in the text column is text too: some fragments survive
        # only in Latin (Parmenides B 18, #683), and a source's Latin
        # context belongs with it as its Greek context does.
        latin = not has_greek and self.block in ("greek", "none") and _looks_latin(text_payload)
        if (has_greek or latin) and self.last_greek_frag is not None:
            self.greek_buf[self.last_greek_frag].append(text_payload)
            self.block = "greek"
        elif (
            not has_greek and self.last_german_frag is not None and self.block in ("german", "none")
        ):
            self.german_buf[self.last_german_frag].append(text_payload)
            self.block = "german"
        # else: dropped (no anchor fragment yet, or ambiguous).

    def _german_resumes(self, text_payload: str) -> bool:
        # In Greek text, a non-Greek line is usually a Latin source
        # citation, which must not jump to the German. The exception is
        # the top of a page, where the Greek carried on from the last
        # page and the German now does the same: German prose, before
        # any German opener on this page. A line that starts like an
        # opener (`32, Eins …`, `152. “Der Abend …`) is a fragment whose
        # opener the OCR mangled, not the last one resuming.
        return (
            self.last_german_frag is not None
            and not self.german_opened_on_page
            and not self.german_openers_lost
            and not _OPENER_LIKE_START_RE.match(text_payload)
            and _looks_german(text_payload)
        )


def _emit_chapter_chunks(
    philosopher: tuple[int, int, str, str],
    greek_buf: dict[FragKey, list[str]],
    german_buf: dict[FragKey, list[str]],
    source_file: str,
    apparatus_buf: dict[FragKey, list[str]],
    spurious: set[FragKey] | frozenset[FragKey] = frozenset(),
) -> Iterator[Chunk]:
    _dk_old, dk_mod, _src_name, canonical = philosopher
    work_title = f"Fragments (DK {dk_mod})"

    # Emit fragments in numeric order so chunk ord (assigned downstream
    # by store.insert_chunks) reflects the canonical fragment sequence;
    # 67a sorts between 67 and 68.
    frag_keys = sorted(set(greek_buf) | set(german_buf))
    for n in frag_keys:
        section = f"{dk_mod} B {n[0]}{n[1]}"
        # Not an input to the id, so a fragment typed spurious keeps its
        # chunk_id, and with it its embedding and lemma state.
        block_type = "spurious" if n in spurious else None

        # ── Greek edition chunk ───────────────────────────────────
        if n in greek_buf:
            raw = " ".join(greek_buf[n])
            source_cite, body = _strip_source_citation(_dehyphenate(raw))
            text = unicodedata.normalize("NFC", body)
            if text:
                yield Chunk(
                    chunk_id=_make_chunk_id(
                        source_file,
                        work_title,
                        "grc",
                        str(dk_mod),
                        section,
                        "",
                        text[:120],
                    ),
                    corpus="presocratic",
                    author=canonical,
                    work=work_title,
                    lang="grc",
                    section=section,
                    book=source_cite,
                    page=None,
                    speaker=None,
                    text=text,
                    source_file=source_file,
                    translator="(Original)",
                    edition_year="1912",
                    citation_system="diels_kranz",
                    block_type=block_type,
                )

        # ── Critical apparatus, kept but typed editorial ──────────
        if n in apparatus_buf:
            yield from _editorial_chunk(philosopher, section, apparatus_buf[n], source_file)

        # ── German translation chunk ──────────────────────────────
        if n in german_buf:
            raw = " ".join(german_buf[n])
            text = unicodedata.normalize("NFC", _norm_text(_dehyphenate(raw)))
            if text:
                yield Chunk(
                    chunk_id=_make_chunk_id(
                        source_file,
                        work_title,
                        "deu",
                        str(dk_mod),
                        section,
                        "",
                        text[:120],
                    ),
                    corpus="presocratic",
                    author=canonical,
                    work=work_title,
                    lang="deu",
                    section=section,
                    book=None,
                    page=None,
                    speaker=None,
                    text=text,
                    source_file=source_file,
                    translator="Hermann Diels",
                    edition_year="1912",
                    citation_system="diels_kranz",
                    block_type=block_type,
                )


def _editorial_chunk(
    philosopher: tuple[int, int, str, str],
    section: str,
    lines: list[str],
    source_file: str,
) -> Iterator[Chunk]:
    """The apparatus that follows a fragment on the page, as one
    ``block_type='editorial'`` chunk in the Greek edition.

    Typed rather than dropped so it stays readable; the lemmatizer and
    retrieval both leave editorial chunks out of the author's words
    (#674). The block type is part of the id, so it cannot collide with
    the fragment's own Greek chunk.
    """

    _dk_old, dk_mod, _src_name, canonical = philosopher
    work_title = f"Fragments (DK {dk_mod})"
    # Never empty: every line reaching the apparatus was stripped non-empty.
    text = unicodedata.normalize("NFC", _norm_text(_dehyphenate(" ".join(lines))))
    yield Chunk(
        chunk_id=_make_chunk_id(
            source_file, work_title, "grc", str(dk_mod), section, "editorial", text[:120]
        ),
        corpus="presocratic",
        author=canonical,
        work=work_title,
        lang="grc",
        section=section,
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file=source_file,
        translator="(Original)",
        edition_year="1912",
        citation_system="diels_kranz",
        block_type="editorial",
    )


def parse_dir(path: Path) -> Iterator[Chunk]:
    """Treat ``path`` as a single OCR text file (not a directory) and
    parse it. Provided for symmetry with the other ingest parsers; the
    CLI passes the file path directly."""

    if path.is_dir():
        # Allow a directory containing one OCR file (forward-looking;
        # current source is a single file).
        for entry in sorted(path.glob("*.txt")):
            yield from parse_file(entry)
    else:
        yield from parse_file(path)
