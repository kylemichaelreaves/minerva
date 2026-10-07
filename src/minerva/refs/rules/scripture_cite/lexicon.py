"""Scripture citation lexicons and shared cite-regex helpers."""

from __future__ import annotations

import re

# Latin → Vulgate book lexicon
# ──────────────────────────────────────────────────────────────────
#
# Maps a (prefix, abbrev) pair to (canonical_book, sbl_abbr, confidence_modifier).
# The prefix slot carries an ordinal ("I", "II", "III", "IV",
# "prima", "secunda", "tertia") OR the preposition "ad", OR None for
# bare abbreviations. confidence_modifier discounts ambiguous bare
# abbrevs (Cor without ordinal could be 1Cor or 2Cor).

# Canonical book name → SBL abbreviation (matches Vulgate
# chunks.section prefix). Mirror of locations.BCV_BOOK_ABBR but
# imported lazily to dodge a circular import.

# (prefix, abbrev) → canonical Vulgate work title.
# Lexicon was built from the survey of 4,116 Aquinas chunks
# (806 matches, 73 distinct pairs). Additional unsurveyed but
# anticipated forms are included so a chunk that DOES carry, say,
# "Iosue. 1-1" doesn't slip through.
_LEXICON: dict[tuple[str | None, str], str] = {
    # ── Gospels ───────────────────────────────────────────────────
    (None, "Matth"): "Matthew",
    (None, "Matt"): "Matthew",
    (None, "Mt"): "Matthew",
    (None, "Marc"): "Mark",
    (None, "Mc"): "Mark",
    (None, "Luc"): "Luke",
    (None, "Lc"): "Luke",
    (None, "Ioan"): "John",
    (None, "Ioann"): "John",
    (None, "Io"): "John",
    (None, "Jo"): "John",
    (None, "Joan"): "John",
    # ── Acts ──────────────────────────────────────────────────────
    (None, "Act"): "Acts",
    # ── Pauline epistles (ordinal-prefixed where applicable) ──────
    (None, "Rom"): "Romans",
    ("ad", "Rom"): "Romans",
    ("ad", "Romanos"): "Romans",
    (None, "Romanos"): "Romans",
    (None, "Cor"): "1 Corinthians",  # ambiguous; default 1 Cor
    ("ad", "Cor"): "1 Corinthians",  # ambiguous
    (None, "Corinth"): "1 Corinthians",  # ambiguous
    ("I", "Cor"): "1 Corinthians",
    ("I", "Corinth"): "1 Corinthians",
    ("II", "Cor"): "2 Corinthians",
    ("II", "Corinth"): "2 Corinthians",
    (None, "Galat"): "Galatians",
    (None, "Gal"): "Galatians",
    ("ad", "Galat"): "Galatians",
    ("ad", "Gal"): "Galatians",
    (None, "Ephes"): "Ephesians",
    ("ad", "Ephes"): "Ephesians",
    (None, "Eph"): "Ephesians",
    ("ad", "Eph"): "Ephesians",
    (None, "Philipp"): "Philippians",
    (None, "Philip"): "Philippians",
    (None, "Phil"): "Philippians",
    ("ad", "Philipp"): "Philippians",
    ("ad", "Phil"): "Philippians",
    (None, "Coloss"): "Colossians",
    ("ad", "Coloss"): "Colossians",
    (None, "Col"): "Colossians",
    ("ad", "Col"): "Colossians",
    (None, "Thess"): "1 Thessalonians",  # ambiguous; default 1
    ("ad", "Thess"): "1 Thessalonians",  # ambiguous
    ("I", "Thess"): "1 Thessalonians",
    ("II", "Thess"): "2 Thessalonians",
    (None, "Tim"): "1 Timothy",  # ambiguous; default 1
    (None, "Timoth"): "1 Timothy",  # ambiguous
    ("ad", "Tim"): "1 Timothy",  # ambiguous
    ("I", "Tim"): "1 Timothy",
    ("I", "Timoth"): "1 Timothy",
    ("II", "Tim"): "2 Timothy",
    ("II", "Timoth"): "2 Timothy",
    (None, "Tit"): "Titus",
    ("ad", "Tit"): "Titus",
    (None, "Phlm"): "Philemon",
    (None, "Hebr"): "Hebrews",
    (None, "Heb"): "Hebrews",
    ("ad", "Hebr"): "Hebrews",
    ("ad", "Heb"): "Hebrews",
    # ── Catholic epistles ─────────────────────────────────────────
    (None, "Iac"): "James",
    (None, "Iacob"): "James",
    (None, "Jac"): "James",
    (None, "Petr"): "1 Peter",  # ambiguous; default 1
    (None, "Pet"): "1 Peter",  # ambiguous
    (None, "Ptr"): "1 Peter",  # ambiguous
    ("I", "Petr"): "1 Peter",
    ("I", "Ptr"): "1 Peter",
    ("II", "Petr"): "2 Peter",
    ("II", "Ptr"): "2 Peter",
    # Molesworth abbreviates one letter shorter: "2 Pet. iii. 13".
    ("I", "Pet"): "1 Peter",
    ("II", "Pet"): "2 Peter",
    # John epistles: bare "Ioan" defaults to the Gospel (more frequent);
    # ordinal-prefixed forms route to the epistles.
    ("I", "Ioan"): "1 John",
    ("I", "Io"): "1 John",
    ("II", "Ioan"): "2 John",
    ("II", "Io"): "2 John",
    ("III", "Ioan"): "3 John",
    ("III", "Io"): "3 John",
    (None, "Iud"): "Jude",  # ambiguous with Iudic/Iudit; lexicon order matters
    (None, "Iudae"): "Jude",
    # ── Revelation ────────────────────────────────────────────────
    (None, "Apoc"): "Revelation",
    # ── Pentateuch ────────────────────────────────────────────────
    (None, "Gen"): "Genesis",
    (None, "Exod"): "Exodus",
    (None, "Ex"): "Exodus",
    (None, "Levit"): "Leviticus",
    (None, "Lev"): "Leviticus",
    (None, "Num"): "Numbers",
    (None, "Numer"): "Numbers",
    (None, "Deut"): "Deuteronomy",
    (None, "Deuteron"): "Deuteronomy",
    # ── Historical ────────────────────────────────────────────────
    (None, "Iosue"): "Joshua",
    (None, "Ios"): "Joshua",
    (None, "Iudic"): "Judges",
    (None, "Iudc"): "Judges",
    (None, "Ruth"): "Ruth",
    (None, "Reg"): "1 Samuel",  # ambiguous; I-IV Reg = 1Sam,2Sam,1Kgs,2Kgs
    ("I", "Reg"): "1 Samuel",
    ("II", "Reg"): "2 Samuel",
    ("III", "Reg"): "1 Kings",
    ("IV", "Reg"): "2 Kings",
    (None, "Paral"): "1 Chronicles",  # ambiguous; default 1
    (None, "Paralip"): "1 Chronicles",  # ambiguous
    ("I", "Paral"): "1 Chronicles",
    ("I", "Paralip"): "1 Chronicles",
    ("II", "Paral"): "2 Chronicles",
    ("II", "Paralip"): "2 Chronicles",
    (None, "Esdr"): "Ezra",
    (None, "Esd"): "Ezra",
    (None, "Neh"): "Nehemiah",
    (None, "Tob"): "Tobit",
    (None, "Iudith"): "Judith",
    (None, "Iudt"): "Judith",
    (None, "Esth"): "Esther",
    (None, "Esther"): "Esther",
    (None, "Macc"): "1 Maccabees",  # ambiguous; default 1
    (None, "Mach"): "1 Maccabees",  # ambiguous
    ("I", "Macc"): "1 Maccabees",
    ("I", "Mach"): "1 Maccabees",
    ("II", "Macc"): "2 Maccabees",
    ("II", "Mach"): "2 Maccabees",
    # ── Wisdom ────────────────────────────────────────────────────
    (None, "Iob"): "Job",
    (None, "Job"): "Job",
    (None, "Psalm"): "Psalms",
    (None, "Ps"): "Psalms",
    (None, "Prov"): "Proverbs",
    (None, "Proverb"): "Proverbs",
    (None, "Eccle"): "Ecclesiastes",  # NOT to be confused with Eccli below
    (None, "Cant"): "Song of Songs",
    (None, "Sap"): "Wisdom",
    (None, "Eccli"): "Sirach",  # Ecclesiasticus / Sirach
    (None, "Ecclus"): "Sirach",
    (None, "Sir"): "Sirach",
    # ── Major prophets ────────────────────────────────────────────
    (None, "Isai"): "Isaiah",
    (None, "Is"): "Isaiah",
    (None, "Ierem"): "Jeremiah",
    (None, "Ier"): "Jeremiah",
    (None, "Jer"): "Jeremiah",
    (None, "Lam"): "Lamentations",
    (None, "Thren"): "Lamentations",  # Threni (Vulgate alternate)
    (None, "Bar"): "Baruch",
    (None, "Ezech"): "Ezekiel",
    (None, "Ez"): "Ezekiel",
    (None, "Dan"): "Daniel",
    # ── Minor prophets ────────────────────────────────────────────
    (None, "Os"): "Hosea",  # Osee in Vulgate
    (None, "Osee"): "Hosea",
    (None, "Ioel"): "Joel",
    (None, "Joel"): "Joel",
    (None, "Am"): "Amos",
    (None, "Abd"): "Obadiah",  # Abdias
    (None, "Ion"): "Jonah",  # Ionas
    (None, "Iona"): "Jonah",
    (None, "Mich"): "Micah",  # Michaeas
    (None, "Nah"): "Nahum",
    (None, "Hab"): "Habakkuk",
    (None, "Habac"): "Habakkuk",
    (None, "Soph"): "Zephaniah",  # Sophonias
    (None, "Agg"): "Haggai",  # Aggaeus
    (None, "Zach"): "Zechariah",
    (None, "Mal"): "Malachi",
    (None, "Malach"): "Malachi",
    # ── Spelled-out Latin forms (genitive case dominant in Aquinas
    # prose: "Lectura super Evangelium Iohannis", "in libro
    # Isaiae"). Survey of Aquinas chunks surfaced these as cite-
    # shaped but unmatched in the abbreviation lexicon above. Most
    # are genitive declensions of the canonical Latin book name;
    # confidence stays at FULL because the spelled-out form is
    # rarely ambiguous (Aquinas writes "Iohannis" only of the
    # Gospel/epistles, never of a different person).
    (None, "Genesis"): "Genesis",
    (None, "Exodi"): "Exodus",
    (None, "Levitici"): "Leviticus",
    (None, "Numerorum"): "Numbers",
    (None, "Deuteronomii"): "Deuteronomy",
    (None, "Iudicum"): "Judges",
    (None, "Regum"): "1 Kings",  # ambiguous (I-IV Reg)
    (None, "Paralipomenon"): "1 Chronicles",  # ambiguous
    (None, "Psalmi"): "Psalms",
    (None, "Psalmus"): "Psalms",
    (None, "Psalmorum"): "Psalms",
    (None, "Proverbiorum"): "Proverbs",
    (None, "Proverbia"): "Proverbs",
    (None, "Ecclesiastae"): "Ecclesiastes",
    (None, "Canticorum"): "Song of Songs",
    (None, "Canticum"): "Song of Songs",
    (None, "Sapientiae"): "Wisdom",
    (None, "Ecclesiastici"): "Sirach",
    (None, "Isaiae"): "Isaiah",
    (None, "Hisaiae"): "Isaiah",  # OCR / alt-spelling variant
    (None, "Ieremiae"): "Jeremiah",
    (None, "Lamentationes"): "Lamentations",
    (None, "Ezechielis"): "Ezekiel",
    (None, "Danielis"): "Daniel",
    (None, "Oseae"): "Hosea",
    (None, "Ioelis"): "Joel",
    (None, "Amos"): "Amos",
    (None, "Abdiae"): "Obadiah",
    (None, "Ionae"): "Jonah",
    (None, "Michaeae"): "Micah",
    (None, "Nahum"): "Nahum",
    (None, "Habacuc"): "Habakkuk",
    (None, "Sophoniae"): "Zephaniah",
    (None, "Aggaei"): "Haggai",
    (None, "Zachariae"): "Zechariah",
    (None, "Malachiae"): "Malachi",
    (None, "Tobiae"): "Tobit",
    (None, "Machabaeorum"): "1 Maccabees",  # ambiguous (I/II Macc)
    # Gospels
    (None, "Matthaei"): "Matthew",
    (None, "Matthaeus"): "Matthew",
    (None, "Marci"): "Mark",
    (None, "Marcus"): "Mark",
    (None, "Lucae"): "Luke",
    (None, "Lucas"): "Luke",
    (None, "Iohannis"): "John",  # ambiguous (Gospel vs epistles)
    (None, "Iohannes"): "John",
    (None, "Ioannis"): "John",  # ambiguous
    # Acts
    (None, "Actuum"): "Acts",
    # Pauline epistles (spelled-out Latin accusative/genitive of "ad <X>")
    (None, "Romanorum"): "Romans",
    (None, "Corinthiorum"): "1 Corinthians",  # ambiguous
    (None, "Galatas"): "Galatians",
    (None, "Ephesios"): "Ephesians",
    (None, "Philippenses"): "Philippians",
    (None, "Colossenses"): "Colossians",
    (None, "Thessalonicenses"): "1 Thessalonians",  # ambiguous
    (None, "Timotheum"): "1 Timothy",  # ambiguous
    (None, "Titum"): "Titus",
    (None, "Philemonem"): "Philemon",
    ("ad", "Corinthios"): "1 Corinthians",
    ("ad", "Corinthiorum"): "1 Corinthians",
    ("ad", "Galatas"): "Galatians",
    ("ad", "Ephesios"): "Ephesians",
    ("ad", "Philippenses"): "Philippians",
    ("ad", "Colossenses"): "Colossians",
    ("ad", "Thessalonicenses"): "1 Thessalonians",
    ("ad", "Timotheum"): "1 Timothy",
    ("ad", "Titum"): "Titus",
    ("ad", "Philemonem"): "Philemon",
    ("ad", "Hebraeos"): "Hebrews",
    # Hebrews — already in lexicon as Hebr/Heb; add the full Latin form
    (None, "Hebraeos"): "Hebrews",
    (None, "Hebraeorum"): "Hebrews",
    # Catholic epistles
    (None, "Iacobi"): "James",
    (None, "Petri"): "1 Peter",  # ambiguous (1/2 Peter)
    ("I", "Petri"): "1 Peter",
    ("II", "Petri"): "2 Peter",
    ("I", "Iohannis"): "1 John",
    ("II", "Iohannis"): "2 John",
    ("III", "Iohannis"): "3 John",
    ("I", "Ioannis"): "1 John",
    ("II", "Ioannis"): "2 John",
    ("III", "Ioannis"): "3 John",
    # Ordinal-prefixed Pauline spelled-out variants
    ("I", "Corinthiorum"): "1 Corinthians",
    ("II", "Corinthiorum"): "2 Corinthians",
    ("I", "Thessalonicenses"): "1 Thessalonians",
    ("II", "Thessalonicenses"): "2 Thessalonians",
    ("I", "Timotheum"): "1 Timothy",
    ("II", "Timotheum"): "2 Timothy",
    # Ordinal-prefixed historical spelled-out variants
    ("I", "Regum"): "1 Kings",
    ("II", "Regum"): "2 Kings",
    ("III", "Regum"): "1 Kings",  # Vulgate III-IV Reg = modern 1-2 Kgs
    ("IV", "Regum"): "2 Kings",
    ("I", "Paralipomenon"): "1 Chronicles",
    ("II", "Paralipomenon"): "2 Chronicles",
    ("I", "Machabaeorum"): "1 Maccabees",
    ("II", "Machabaeorum"): "2 Maccabees",
    # Revelation
    (None, "Apocalypsis"): "Revelation",
    (None, "Apocalypsim"): "Revelation",
    # Psalms, abbreviated one letter shorter than "Psalm". Molesworth
    # uses both forms ("Psal. lxxxiv. 11" beside "Psalm. xxxvi. 30").
    (None, "Psal"): "Psalms",
}


# 19th-century editions number the books in Arabic — "1 Cor." where the
# older convention writes "I Cor." — so every ordinal-prefixed entry
# above needs an Arabic twin. Generated rather than typed out: a hand
# mirror of 30-odd keys drifts the first time a book is added to one
# list and not the other.
#
# These keys were once reachable only from `ScriptureCiteRuleLatRoman`:
# `_CITE_RE`'s prefix group was `I{1,3}V?|ad`, which cannot match a
# digit, so Aquinas's "2 Cor. 3-18" fell to the bare default and bound
# 1 Cor (#719). It now admits a spaced `[1-4]` too. A digit that pins no
# entry here — "art. 3 Matth. 5-3" — is dropped from the cite by
# `BaseScriptureCiteRule._resolve_book` rather than sinking it.
_ARABIC_FOR_ROMAN_ORDINAL = {"I": "1", "II": "2", "III": "3", "IV": "4"}
_LEXICON.update(
    {
        (_ARABIC_FOR_ROMAN_ORDINAL[prefix], abbr): book
        for (prefix, abbr), book in list(_LEXICON.items())
        if prefix in _ARABIC_FOR_ROMAN_ORDINAL
    }
)


# Aquinas writes the spelled-out genitive forms lowercase mid sentence
# ("sicut sapientiae 11-21 dicitur", "Et actuum 10, dicit Petrus"), and
# the cite regex's capital-initial anchor missed them entirely. The
# anchor itself has to stay — it is what keeps "patet ex 30 affectuum"
# from binding Exodus 30 (#508) — so the relaxation is bounded by
# length instead of dropped: `_MIN_LOWERCASE_ABBR` letters or more.
#
# The floor is measured, not chosen. Over all 67,728 `lat` chunks, 12
# lowercase-initial lexicon forms sit before a number. The two genuine
# cites are `sapientiae` (10) and `actuum` (6); all ten collision hits
# are `ex`, `io`, `is` and `tim` — 2 or 3 letters, every one. A blanket
# `re.IGNORECASE` would admit all ten (#511).
#
# The regex is only half the anchor. `BaseScriptureCiteRule.scan` looks
# the abbrev up verbatim in three tables — `_LEXICON`, `_AMBIGUOUS_BARE`
# and `_WORD_COLLISION` — all keyed on the capitalised form, so
# relaxing the pattern alone finds the spans and then drops them at the
# lexicon miss (measured: +0 candidates). Rather than mirror lowercase
# entries into all three, the Latin rule canonicalises the abbrev once
# after matching — see `ScriptureCiteRule.canonical_abbr`. That keeps
# one spelling per book and makes the other two tables correct by
# construction: a lowercase `corinthiorum` stays ambiguous because it
# is looked up as `Corinthiorum`.
_MIN_LOWERCASE_ABBR = 4


# Canonical book name → SBL abbreviation. Mirror of
# locations.BCV_BOOK_ABBR (imported lazily below to dodge circular).
def _sbl_abbr_for(book: str) -> str | None:
    from .... import locations  # local import: avoid module-load cycle

    return locations.BCV_BOOK_ABBR.get(book)


# ──────────────────────────────────────────────────────────────────
# Cite regex
# ──────────────────────────────────────────────────────────────────
#
# Pattern:
#   (optional prefix: ordinal "I"/"II"/"III"/"IV", "1"–"4", or preposition "ad")
#   word-boundary + capitalized book abbreviation + literal "."
#   whitespace
#   chapter digits
#   optional (separator "-" or ":" + verse digits)
#
# Word boundary on the abbrev keeps "Matth." matching but rejects
# accidental in-word substrings ("Apostolicam." → not a cite).

_CITE_RE = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-4]|ad)\s+)?"  # optional ordinal/prep
    # Book abbreviation. Length 1..15 to accommodate spelled-out Latin
    # genitive forms ("Lamentationes" 13, "Thessalonicenses" 16 —
    # the 16-char form is just past the cap and would need explicit
    # special-casing if it appears; survey didn't surface it).
    # Trailing period is optional so spelled-out forms ("Isaiae
    # capitulo 5" without "Isaiae.") still match — most Aquinas
    # spelled-out cites omit the period.
    # Second alternative: the same form with a lowercase initial, but
    # only from _MIN_LOWERCASE_ABBR letters up — see the note above
    # that constant for why the floor is measured rather than chosen.
    # The tail is one shorter than the floor because the initial is
    # matched separately, and is interpolated rather than written out
    # so the pattern cannot drift from the constant the comment and
    # the lexicon keys both cite.
    r"\b(?P<abbr>[A-Z][a-zëæoœ]{1,15}"
    rf"|[a-z][a-zëæoœ]{{{_MIN_LOWERCASE_ABBR - 1},15}})\.?"
    r"\s+"  # whitespace
    r"(?P<chap>\d{1,3})"  # chapter number
    r"(?:[-:]\s*(?P<verse>\d{1,3}))?"  # optional verse
)


# Ambiguous bare abbrevs whose canonical-default is one of multiple
# Vulgate books. Cited bare ("Cor. 13-4" not "I Cor. 13-4"), we
# emit at LOW confidence (`_CONF_AMBIGUOUS`) because the right
# resolution depends on context the rule can't see.
_AMBIGUOUS_BARE: frozenset[str] = frozenset(
    {
        "Cor",
        "Corinth",
        "Petr",
        "Pet",
        "Ptr",
        "Tim",
        "Timoth",
        "Thess",
        "Reg",
        "Paral",
        "Paralip",
        "Macc",
        "Mach",
        # Spelled-out Latin forms that share lemma across numbered
        # books — bare cites at low confidence.
        "Petri",
        "Iohannis",
        "Ioannis",
        "Corinthiorum",
        "Thessalonicenses",
        "Timotheum",
        "Regum",
        "Paralipomenon",
        "Machabaeorum",
    }
)

# Abbrevs that are also ordinary Latin words. The trailing period in
# `_CITE_RE` is optional, because the spelled-out genitive forms omit
# it ("Isaiae 54-13", "Sapientiae 11-21" — both live in the corpus).
# For a short abbrev that doubles as a word, that leniency plus
# sentence-initial capitalisation makes prose indistinguishable from a
# cite: "Ex 3 modis potest dici" is "it can be said in 3 ways", not
# Exodus 3. Emitted at `_CONF_AMBIGUOUS` when the period is absent,
# and left at full confidence when it is present (#508) — the period
# is the only evidence of citation intent available to the rule.
#
# Measured 2026-09-04 over all 67,728 `lat` chunks: 5 of the 174
# distinct abbrevs appear as a lowercase word before a number, and
# `ex` leads them (Spinoza's "patet ex 30 affectuum definitione",
# Descartes's "ex 5 uersus u"). Zero capitalised period-less
# occurrences exist today, so nothing in the current corpus is
# downgraded by this — it is latency, closed before the next Latin
# author lands.
#
# `Am`, `Act`, `Bar`, `Iud` and `Sap` are deliberately NOT here:
# #508's candidate list named some of them, but none is a Latin word
# (`amo` is the verb; the rest are abbreviations only), and every one
# of their live cite occurrences carries the period — `Act.` 25,
# `Sap.` 36, `Iud.` 2, `Bar.` 1, and `Am` neither form.
_WORD_COLLISION: frozenset[str] = frozenset(
    {
        "Ex",  # preposition "out of" — 5 lowercase prose occurrences
        "Is",  # pronoun "he / that one" — 1
        "Io",  # interjection "io!" — 2, both OCR page noise in Hobbes
        "Num",  # interrogative particle "num …?" — 0, but a function word
        "Os",  # noun "mouth / bone" — 0, but a common noun
    }
)

_CONF_FULL = 0.90  # book + chapter + verse, unambiguous
_CONF_AMBIGUOUS = 0.65  # ambiguous bare abbrev (Cor without I/II)
_CONF_CHAPTER_ONLY = 0.75  # book + chapter, no verse — chunk-level only
