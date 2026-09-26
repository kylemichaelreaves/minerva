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
* **Doubtful / forged fragments**: ``ZWEIFELHAFTE ... FRAGMENTE``
  block — skipped (not part of canonical B-fragments).

The DK chapter number we record in ``chunks.section`` is the
**modern** Kranz 1951 number — universal scholarly citation today
— not the 1912 source number. The map lives in
``presocratic_works._PHASE_1``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from pathlib import Path

from minerva.authors.presocratic_works import _PHASE_1, find_by_chapter_heading
from minerva.tei import Chunk, _make_chunk_id, _norm_text

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

# `ZWEIFELHAFTE ... FRAGMENTE` — doubtful / forged fragments, skipped.
_DOUBTFUL_RE = re.compile(
    r"^\s*ZWEIFELHAFTE",
    re.IGNORECASE,
)

# Optional leading print-line-number prefix. The 1912 typesetting
# numbers every 5th line of Greek poetry in the margin; OCR linearizes
# those into the start of fragment lines. Examples:
#   `25 1. [1—32. 52—57 Karst.] ...` — print line 25, fragment 1
#   `5 1. [...] ...`                  — print line 5, fragment 1
# Stripped at classification time so fragment-start regexes see a clean
# `\d+\.` opener.
_LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s+(?=\d+\.\s)")

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
# legitimately exceeds 999. OCR noise like `1262.` (a mangled `126. 2.`)
# would otherwise be treated as a real opener.
_FRAG_OPENER_RE = re.compile(r"^\s*(\d{1,3})\.\s+(.*)$")
_LEADING_CROSSREF_RE = re.compile(r"^\[[^\]]*\]\s*")

# Crammed-line split (Greek): in Xenophanes (and intermittently
# elsewhere) the OCR linearizes multiple Greek B-fragments onto ONE
# long text line — `25. 3 K., 14 Cr.] ... Kpadalveı. 26. [4 K., 15
# Cr.) ... 27. [8 K., 11 Cr.) ...`. We split at every interior
# occurrence of whitespace + digits + period + space + opening
# bracket. The bracket requirement avoids false-splitting on
# cross-references like `[A 31, 9` (A-fragment refs that have a Latin
# letter, not digits, before the comma).
_CRAMMED_FRAG_SPLIT_RE = re.compile(r"\s+(\d{1,3})\.\s+\[")

# Crammed-line split (German): the German translation block packs
# fragments back-to-back on long OCR lines too, e.g.
# `11. Alles, was da kreucht ... 12. Wer in dieselben Fluten ...
# 13. Am Dreck sich ergetzen.`. The discriminator is a leading
# integer + dot-OR-comma (OCR sometimes reads `12.` as `12,`) + space
# + Latin capital + Latin lowercase. The capital-lowercase pair
# avoids splitting on incidental numbers inside the German prose.
_CRAMMED_GERMAN_SPLIT_RE = re.compile(r"\s+(\d{1,3})[.,]\s+(?=[A-ZÄÖÜ][a-zäöüß])")


def _split_crammed_greek(first_num: int, body: str) -> list[tuple[int, str]]:
    """Split a Greek-fragment line that crams multiple ``N. [...]``
    openers onto one OCR-linearized text line. Returns
    ``[(num, body), ...]`` in source order.

    The first fragment's body runs from the start of the input to the
    first inner split position; each subsequent split takes the
    fragment number from the matched group and the body up to the next
    split (or end of input). The leading cross-ref bracket is stripped
    from every body via the same regex used for the single-fragment
    case.
    """

    matches = list(_CRAMMED_FRAG_SPLIT_RE.finditer(body))
    if not matches:
        return [(first_num, _LEADING_CROSSREF_RE.sub("", body))]

    out: list[tuple[int, str]] = []
    first_body = body[: matches[0].start()]
    out.append((first_num, _LEADING_CROSSREF_RE.sub("", first_body)))
    for i, m in enumerate(matches):
        num = int(m.group(1))
        # Body of this inner fragment starts at the `[` we matched
        # and runs until the next split (or end).
        body_start = m.end() - 1  # `m.end()` is one past `[`
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((num, _LEADING_CROSSREF_RE.sub("", body[body_start:body_end])))
    return out


def _split_crammed_german(first_num: int, body: str) -> list[tuple[int, str]]:
    """German analog of :func:`_split_crammed_greek`. Splits a German
    translation block on interior ``N. <CapitalizedWord>`` markers.

    Unlike the Greek splitter, there is no leading cross-ref bracket
    to strip — the German block is plain prose.
    """

    matches = list(_CRAMMED_GERMAN_SPLIT_RE.finditer(body))
    if not matches:
        return [(first_num, body.strip())]

    out: list[tuple[int, str]] = []
    out.append((first_num, body[: matches[0].start()].strip()))
    for i, m in enumerate(matches):
        num = int(m.group(1))
        body_start = m.end()  # past the `N. ` separator
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((num, body[body_start:body_end].strip()))
    return out


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
    r"\b(?:et|est|sunt|in|ad|ex|de|cum|qui|quae|quod|ut|non|sed|enim|autem|atque)\b"
)


def _looks_german(text: str) -> bool:
    german = len(_GERMAN_FUNCTION_WORD_RE.findall(text))
    return german >= 2 and german > len(_LATIN_FUNCTION_WORD_RE.findall(text))


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


def _classify_line(line: str) -> tuple[str, object]:
    """Classify one line. Returns (kind, payload) where kind is one of:
    'chapter', 'b_marker', 'a_marker', 'c_marker', 'doubtful',
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
    if _DOUBTFUL_RE.match(line):
        return "doubtful", None

    # Chapter heading: ALL-UPPERCASE name token (Latin only). Source-
    # citation openers like `1. Pur. de prim.` or `1. Dioc. ix 1—17.`
    # have mixed-case after the first uppercase letter, so they
    # don't match the chapter regex (`[A-ZÄÖÜ]{3,}` needs 3
    # consecutive uppercase chars). Checked BEFORE the fragment
    # opener so `12. HERAKLEITOS.` isn't misclassified as a
    # German-translation fragment.
    m = _CHAPTER_HEADING_RE.match(line)
    if m is not None:
        name = m.group(1).upper().rstrip(".")
        return "chapter", (None, name)

    # Strip an optional leading print-line-number prefix before
    # fragment-start detection. Without this, lines like
    # `25 1. [1—32. 52—57 Karst.] ...` (Parmenides B 1) hit the
    # apparatus regex and the actual fragment-start is dropped.
    candidate = _LINE_NUMBER_PREFIX_RE.sub("", line)

    m = _FRAG_OPENER_RE.match(candidate)
    if m is not None:
        body = m.group(2)
        first_num = int(m.group(1))
        # A leading `[<crossref>]` bracket is a reliable signal of a
        # Greek B-fragment opener (old-numbering reference: Bywater,
        # Karsten, Crusius, ...). German translation lines never open
        # with a bracket — they start with German prose directly. So
        # the bracket presence wins even when no Greek script is on
        # this particular text line (the Greek body may continue on
        # the next OCR line; the source citation that fills this line
        # is all-Latin).
        has_crossref = body.startswith("[")
        if _GREEK_CHAR_RE.search(body) or has_crossref:
            # Crammed-line detection: when OCR packs multiple Greek
            # fragments onto one text line, return them all as a list.
            # The parser loop emits each in source order.
            return "frag_greek", _split_crammed_greek(first_num, body)
        # No Greek script AND no crossref bracket — German translation
        # OR an unrecognized line. Require the body to start with a
        # Latin capital so we don't misclassify e.g. `1. p. 96` page
        # refs.
        body_stripped = _LEADING_CROSSREF_RE.sub("", body)
        if re.match(r"[A-ZÄÖÜ]", body_stripped):
            # Crammed-line detection for German too — multiple German
            # fragments can be packed onto one OCR line just like the
            # Greek side.
            return "frag_german", _split_crammed_german(first_num, body_stripped)

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
        self.mode: str = "outside"  # outside | pre_b | in_b
        self.block: str = "none"  # none | greek | german | apparatus | doubtful
        # Two separate "last fragment number" trackers, one per language.
        # The page layout interleaves apparatus + page-break running heads
        # between a fragment's Greek lines and its German translation;
        # routing continuations by the language they look like (Greek
        # script vs Latin/German) is more robust than tracking a single
        # cur_frag. See `_classify_line` + `_on_continuation`.
        self.last_greek_frag: int | None = None
        self.last_german_frag: int | None = None
        self.greek_buf: dict[int, list[str]] = {}
        self.german_buf: dict[int, list[str]] = {}
        # Apparatus, keyed by the Greek fragment it follows on the page.
        self.apparatus_buf: dict[int, list[str]] = {}
        # Whether a German opener has been seen since the last page
        # break: until one has, German at the top of a page is the last
        # German fragment carrying on.
        self.german_opened_on_page = False
        # Set when the OCR has put the page's fragment numbers in a
        # margin column (`19.` `20.` `21.` on lines of their own): the
        # German below them has lost its openers, so none of it may be
        # taken for the last fragment resuming. Cleared by a real opener.
        self.german_openers_lost = False

    def flush_chapter(self) -> Iterator[Chunk]:
        if self.current_phil is None:
            return
        yield from _emit_chapter_chunks(
            self.current_phil,
            self.greek_buf,
            self.german_buf,
            self.source_file,
            self.apparatus_buf,
        )
        self.greek_buf = {}
        self.german_buf = {}
        self.apparatus_buf = {}
        self.last_greek_frag = None
        self.last_german_frag = None

    def _reset_blocks(self) -> None:
        self.block = "none"
        self.last_greek_frag = None
        self.last_german_frag = None

    def feed(self, line: str) -> Iterator[Chunk]:
        kind, payload = _classify_line(line)

        if kind == "chapter":
            yield from self._on_chapter(payload)
            return
        if self.current_phil is None or self.mode == "outside":
            return
        if kind in ("a_marker", "b_marker", "c_marker", "doubtful"):
            yield from self._on_marker(kind)
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
        # Not a recognized philosopher — ignore.
        if entry is None:
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

    def _on_marker(self, kind: str) -> Iterator[Chunk]:
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
            # Exception: when `block == "doubtful"`, we've been
            # skipping the ZWEIFELHAFTE FRAGMENTE subsection. The
            # running B-marker that follows it signals we're back in
            # canonical B-fragments — clear the doubtful flag so
            # subsequent frag-openers fire.
            if self.mode != "in_b":
                self.mode = "in_b"
                self._reset_blocks()
            elif self.block == "doubtful":
                self.block = "none"
            else:
                self._on_page_break()
        elif kind == "c_marker":
            # C-fragments aren't canonical B; emit what we have and
            # stop collecting for this chapter.
            yield from self.flush_chapter()
            self.current_phil = None
            self.mode = "outside"
            self._reset_blocks()
        else:
            # ZWEIFELHAFTE FRAGMENTE — skip until next B-marker, C, or
            # chapter. Just enter a sentinel block; non-frag-start
            # lines are ignored anyway in `in_b` mode unless we
            # explicitly accumulate.
            self.block = "doubtful"

    def _on_frag_greek(self, frag_list: list[tuple[int, str]]) -> None:
        # Payload is a list of (num, body) pairs — one entry for a
        # normal single-fragment line, multiple when the OCR
        # crammed several fragments onto one text line.
        for frag_num, head_text in frag_list:
            self.greek_buf.setdefault(frag_num, []).append(head_text)
        # The "current" Greek fragment for continuation routing is
        # the LAST one in the crammed list — subsequent continuation
        # lines (page-break Greek tails) belong to that one.
        self.last_greek_frag = frag_list[-1][0]
        self.block = "greek"

    def _on_frag_german(self, frag_list: list[tuple[int, str]]) -> None:
        # Same shape as frag_greek to handle crammed-OCR
        # multi-fragment lines.
        for frag_num, head_text in frag_list:
            self.german_buf.setdefault(frag_num, []).append(head_text)
        self.last_german_frag = frag_list[-1][0]
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
        has_greek = bool(_GREEK_CHAR_RE.search(text_payload))
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
        for frag_num, head_text in _split_crammed_greek(int(first_split.group(1)), rest):
            self.greek_buf.setdefault(frag_num, []).append(head_text)
            self.last_greek_frag = frag_num
        self.block = "greek"
        return True

    def _split_crammed_german_continuation(self, text_payload: str) -> bool:
        # German continuation can ALSO contain crammed interior
        # `N. <CapitalizedWord>` markers (Heraclitus has many).
        # Split + route similarly to the Greek case.
        if self.block not in ("german", "none"):
            return False
        first_split = _CRAMMED_GERMAN_SPLIT_RE.search(text_payload)
        if first_split is None:
            return False
        prefix = text_payload[: first_split.start()]
        if prefix.strip() and self.last_german_frag is not None:
            self.german_buf[self.last_german_frag].append(prefix.strip())
        rest = text_payload[first_split.end() :]
        for frag_num, head_text in _split_crammed_german(int(first_split.group(1)), rest):
            self.german_buf.setdefault(frag_num, []).append(head_text)
            self.last_german_frag = frag_num
        self.block = "german"
        return True

    def _route_by_content(self, text_payload: str, has_greek: bool) -> None:
        # Route the continuation by its CONTENT (Greek vs. Latin)
        # rather than by the block-state machine. After the German
        # block + apparatus + page-break running heads, a Greek
        # poem can resume mid-fragment; routing by content lets us
        # pick that up without an explicit page-break marker.
        if has_greek and self.last_greek_frag is not None:
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
    greek_buf: dict[int, list[str]],
    german_buf: dict[int, list[str]],
    source_file: str,
    apparatus_buf: dict[int, list[str]],
) -> Iterator[Chunk]:
    _dk_old, dk_mod, _src_name, canonical = philosopher
    work_title = f"Fragments (DK {dk_mod})"

    # Emit fragments in numeric order so chunk ord (assigned downstream
    # by store.insert_chunks) reflects the canonical fragment sequence.
    frag_nums = sorted(set(greek_buf) | set(german_buf))
    for n in frag_nums:
        section = f"{dk_mod} B {n}"

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
