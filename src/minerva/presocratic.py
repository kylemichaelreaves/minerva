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
  footnote-style line reference. Skipped wholesale.
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

from .authors.presocratic_works import _PHASE_1, find_by_chapter_heading
from .tei import Chunk, _make_chunk_id, _norm_text

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
_RUNNING_HEAD_CHAPTER_RE = re.compile(
    r"^\s*\d+\s+\d{1,3}\.\s+[A-ZÄÖÜ]{3,}"
)

# `B. FRAGMENTE.` opens the canonical B-fragments block. We accept
# both the standalone form (Heraclitus, Anaximenes) and the running-
# head form (`B. FRAGMENTE. 1—4. 175`, used by Zeno / Empedocles
# where Diels skipped the standalone marker). The transition is
# idempotent — re-firing inside an already-in_b state is a no-op.
_B_FRAGMENTS_RE = re.compile(r"^\s*B\.\s+FRAGMENTE\b")

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
_CRAMMED_GERMAN_SPLIT_RE = re.compile(
    r"\s+(\d{1,3})[.,]\s+(?=[A-ZÄÖÜ][a-zäöüß])"
)


def _split_crammed_greek(
    first_num: int, body: str
) -> list[tuple[int, str]]:
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


def _split_crammed_german(
    first_num: int, body: str
) -> list[tuple[int, str]]:
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

    tokens_with_pos = [
        (m.group(0), m.start()) for m in re.finditer(r"\S+", raw)
    ]
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


def _classify_line(line: str) -> tuple[str, object]:
    """Classify one line. Returns (kind, payload) where kind is one of:
    'chapter', 'b_marker', 'a_marker', 'c_marker', 'doubtful',
    'frag_greek', 'frag_german', 'apparatus', 'running_head',
    'page_num', 'blank', 'continuation'.
    """

    stripped = line.strip()
    if not stripped:
        return "blank", None
    if stripped.isdigit():
        return "page_num", None
    if _RUNNING_HEAD_CHAPTER_RE.match(line):
        # `78 12. HERAKLEITOS.` — page-number running head, not a real
        # chapter transition.
        return "running_head", None

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
        return "apparatus", None

    return "continuation", line.strip()


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
    lines = text.split("\n")

    current_phil: tuple[int, int, str, str] | None = None
    mode: str = "outside"  # outside | pre_b | in_b
    block: str = "none"    # none | greek | german | apparatus | doubtful
    # Two separate "last fragment number" trackers, one per language.
    # The page layout interleaves apparatus + page-break running heads
    # between a fragment's Greek lines and its German translation;
    # routing continuations by the language they look like (Greek
    # script vs Latin/German) is more robust than tracking a single
    # cur_frag. See `_classify_line` + the `continuation` branch below.
    last_greek_frag: int | None = None
    last_german_frag: int | None = None
    greek_buf: dict[int, list[str]] = {}
    german_buf: dict[int, list[str]] = {}

    def flush_chapter() -> Iterator[Chunk]:
        nonlocal greek_buf, german_buf, last_greek_frag, last_german_frag
        if current_phil is None:
            return
        yield from _emit_chapter_chunks(
            current_phil, greek_buf, german_buf, path.name
        )
        greek_buf = {}
        german_buf = {}
        last_greek_frag = None
        last_german_frag = None

    def reset_blocks() -> None:
        nonlocal block, last_greek_frag, last_german_frag
        block = "none"
        last_greek_frag = None
        last_german_frag = None

    for line in lines:
        kind, payload = _classify_line(line)

        # Chapter heading: switch to new philosopher (and flush prior)
        # only when the captured name resolves to a Phase-1 entry.
        # A regex match that doesn't resolve is treated as noise (an
        # uppercase token that happens to follow `N. ` — e.g. a
        # quoted SEXT abbreviation in an A-fragment that we want to
        # ignore in pre_b mode).
        if kind == "chapter":
            chap_int, name = payload  # type: ignore[misc]
            entry = find_by_chapter_heading(chap_int, name)
            if entry is None:
                # Not a recognized philosopher — treat as continuation
                # in the current mode (drop in pre_b; accumulate in_b
                # if we're in a block, which is essentially never
                # because frag-start regexes match first).
                continue
            if entry == current_phil:
                # Same philosopher running-head — ignore.
                continue
            # New Phase-1 philosopher — flush prior chapter's chunks.
            yield from flush_chapter()
            current_phil = entry
            mode = "pre_b"
            reset_blocks()
            continue

        if current_phil is None or mode == "outside":
            continue

        if kind == "a_marker":
            mode = "pre_b"
            reset_blocks()
            continue
        if kind == "b_marker":
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
            if mode != "in_b":
                mode = "in_b"
                reset_blocks()
            elif block == "doubtful":
                block = "none"
            continue
        if kind == "c_marker":
            # C-fragments aren't canonical B; emit what we have and
            # stop collecting for this chapter.
            yield from flush_chapter()
            current_phil = None
            mode = "outside"
            reset_blocks()
            continue
        if kind == "doubtful":
            # ZWEIFELHAFTE FRAGMENTE — skip until next B-marker, C, or
            # chapter. Just enter a sentinel block; non-frag-start
            # lines are ignored anyway in `in_b` mode unless we
            # explicitly accumulate.
            block = "doubtful"
            continue
        if kind in ("running_head", "page_num", "blank"):
            # Page chrome — never opens or interrupts a fragment.
            continue

        # In pre-B mode (skipping testimonia + apparatus), only B-marker
        # transitions matter; everything else is dropped.
        if mode == "pre_b":
            continue

        # mode == "in_b" beyond this point.
        if kind == "apparatus":
            block = "apparatus"
            continue

        if kind == "frag_greek":
            # Payload is a list of (num, body) pairs — one entry for a
            # normal single-fragment line, multiple when the OCR
            # crammed several fragments onto one text line.
            frag_list = payload  # type: ignore[assignment]
            for frag_num, head_text in frag_list:  # type: ignore[misc]
                greek_buf.setdefault(frag_num, []).append(head_text)
            # The "current" Greek fragment for continuation routing is
            # the LAST one in the crammed list — subsequent continuation
            # lines (page-break Greek tails) belong to that one.
            last_greek_frag = frag_list[-1][0]  # type: ignore[index]
            block = "greek"
            continue

        if kind == "frag_german":
            # Payload is a list of (num, body) pairs — same shape as
            # frag_greek to handle crammed-OCR multi-fragment lines.
            frag_list = payload  # type: ignore[assignment]
            for frag_num, head_text in frag_list:  # type: ignore[misc]
                german_buf.setdefault(frag_num, []).append(head_text)
            last_german_frag = frag_list[-1][0]  # type: ignore[index]
            block = "german"
            continue

        if kind == "continuation":
            text_payload = payload  # type: ignore[assignment]
            assert isinstance(text_payload, str)
            has_greek = bool(_GREEK_CHAR_RE.search(text_payload))

            # Continuation lines can themselves contain interior
            # `N. [<crossref>]` markers when the OCR linearizes a
            # Greek poem followed by mid-line new fragments. Detect
            # and split: the prefix continues the prior Greek
            # fragment; each subsequent split begins a new one.
            if has_greek:
                first_split = _CRAMMED_FRAG_SPLIT_RE.search(text_payload)
                if first_split is not None:
                    prefix = text_payload[: first_split.start()]
                    if prefix.strip() and last_greek_frag is not None:
                        greek_buf[last_greek_frag].append(prefix.strip())
                    # The first inner fragment + any further crammed
                    # ones get split via the shared helper. Note
                    # `first_split.end() - 1` backs up to the `[`.
                    rest = text_payload[first_split.end() - 1 :]
                    for frag_num, head_text in _split_crammed_greek(
                        int(first_split.group(1)), rest
                    ):
                        greek_buf.setdefault(frag_num, []).append(head_text)
                        last_greek_frag = frag_num
                    block = "greek"
                    continue

            # German continuation can ALSO contain crammed interior
            # `N. <CapitalizedWord>` markers (Heraclitus has many).
            # Split + route similarly to the Greek case.
            if (
                not has_greek
                and block in ("german", "apparatus", "none")
            ):
                first_split = _CRAMMED_GERMAN_SPLIT_RE.search(text_payload)
                if first_split is not None:
                    prefix = text_payload[: first_split.start()]
                    if prefix.strip() and last_german_frag is not None:
                        german_buf[last_german_frag].append(prefix.strip())
                    rest = text_payload[first_split.end() :]
                    first_inner = int(first_split.group(1))
                    for frag_num, head_text in _split_crammed_german(
                        first_inner, rest
                    ):
                        german_buf.setdefault(frag_num, []).append(head_text)
                        last_german_frag = frag_num
                    block = "german"
                    continue

            # Route the continuation by its CONTENT (Greek vs. Latin)
            # rather than by the block-state machine. After the German
            # block + apparatus + page-break running heads, a Greek
            # poem can resume mid-fragment; routing by content lets us
            # pick that up without an explicit page-break marker.
            if has_greek and last_greek_frag is not None:
                greek_buf[last_greek_frag].append(text_payload)
                block = "greek"
            elif (
                not has_greek
                and last_german_frag is not None
                and block in ("german", "apparatus", "none")
            ):
                # Pure-Latin/German continuation. Avoid accidentally
                # picking up a Latin source citation from `block ==
                # "greek"` — Greek fragments can legitimately have
                # Latin trailing notes, but those should stay with
                # the Greek chunk, not jump to German.
                german_buf[last_german_frag].append(text_payload)
                block = "german"
            # else: dropped (no anchor fragment yet, or ambiguous).
            continue

    # Final flush for the last chapter in the file.
    yield from flush_chapter()


def _emit_chapter_chunks(
    philosopher: tuple[int, int, str, str],
    greek_buf: dict[int, list[str]],
    german_buf: dict[int, list[str]],
    source_file: str,
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
                        source_file, work_title, "grc", str(dk_mod), section,
                        "", text[:120],
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

        # ── German translation chunk ──────────────────────────────
        if n in german_buf:
            raw = " ".join(german_buf[n])
            text = unicodedata.normalize("NFC", _norm_text(_dehyphenate(raw)))
            if text:
                yield Chunk(
                    chunk_id=_make_chunk_id(
                        source_file, work_title, "deu", str(dk_mod), section,
                        "", text[:120],
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
