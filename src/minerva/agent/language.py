"""Reply language inference and retrieval query building."""

from __future__ import annotations

import re

from .detect import _WORD_RE
from .prompts_constants import (
    _LOCATOR_CITATION_RULE,
    _NUMERIC_CITATION_RULE,
    _SYSTEM_PROMPT_TEMPLATE,
    LANG_DISPLAY_NAMES,
)

_RETRIEVAL_HISTORY_WINDOW = 2

_GREEK_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_FRENCH_CHARS_RE = re.compile(r"[àâäçéèêëïîôùûüÿœæ]", re.IGNORECASE)
_GERMAN_CHARS_RE = re.compile(r"[äöüß]", re.IGNORECASE)

_FRENCH_WORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "des",
        "une",
        "est",
        "que",
        "pour",
        "dans",
        "avec",
        "sur",
        "pas",
        "comment",
        "quoi",
        "pourquoi",
        "et",
        "bien",
    }
)
_GERMAN_WORDS = frozenset(
    {"der", "die", "das", "und", "ist", "nicht", "was", "wie", "auch", "sich", "über", "für"}
)
_LATIN_WORDS = frozenset({"quid", "quae", "quod", "autem", "igitur", "enim", "ergo"})

# Reply-language directives the user types inline ("… Answer in English",
# "Please respond in German", "In French: …"). These belong to the
# *answer* (handled separately via reply_lang) and must NOT reach the
# retrieval query — left in, the bare language name matches translator
# prefaces and front-matter ("The English reader is desired to…"),
# which is exactly how Aesop/Cicero/Theognis intro pages polluted a
# Hegel question. The verb list is deliberately tight (no "explain"/
# "translate") and the filler between verb and "in" is whitelisted, so
# "explain Hegel in English" keeps "Hegel" — only the directive clause
# is removed.
_REPLY_LANG_NAMES = (
    r"english|german|deutsch|french|fran[cç]ais|latin|greek|ancient\s+greek|hebrew|arabic"
)
_REPLY_DIRECTIVE_RE = re.compile(
    r"\b(?:please\s+)?(?:answer|respond|reply|write)"
    r"(?:\s+(?:me|us|this|it|that|back|your\s+answer))?"
    rf"\s+in\s+(?:{_REPLY_LANG_NAMES})\b\.?",
    re.IGNORECASE,
)
_LEADING_LANG_RE = re.compile(
    rf"^\s*in\s+(?:{_REPLY_LANG_NAMES})\s*[,:]\s*",
    re.IGNORECASE,
)


def strip_reply_directive(text: str) -> str:
    """Remove an inline answer-language directive from retrieval text.

    Returns ``text`` unchanged when no directive is present. Only the
    directive clause is stripped; the substantive question survives.
    """

    out = _REPLY_DIRECTIVE_RE.sub(" ", text)
    out = _LEADING_LANG_RE.sub("", out)
    return re.sub(r"\s{2,}", " ", out).strip(" .,:;")


def _system_prompt(cite_style: str, *, reply_lang: str | None = None) -> str:
    rule = _NUMERIC_CITATION_RULE if cite_style == "numeric" else _LOCATOR_CITATION_RULE
    clause = ""
    if reply_lang:
        name = LANG_DISPLAY_NAMES.get(reply_lang, reply_lang)
        clause = f" The user requested replies in {name}."
    return _SYSTEM_PROMPT_TEMPLATE.format(citation_rule=rule, reply_lang_clause=clause)


def build_retrieval_query(query: str, prior_user_turns: list[str]) -> str:
    recent = prior_user_turns[-_RETRIEVAL_HISTORY_WINDOW:]
    return strip_reply_directive(" ".join([*recent, query]))


def infer_reply_language(query: str) -> str | None:
    if not query.strip():
        return None
    if _HEBREW_RE.search(query):
        return "heb"
    if _ARABIC_RE.search(query):
        return "ara"
    if _GREEK_RE.search(query):
        return "grc"
    lower = query.lower()
    tokens = _WORD_RE.findall(lower)
    words = set(tokens)
    french_hits = sum(1 for t in tokens if t in _FRENCH_WORDS)
    german_hits = sum(1 for t in tokens if t in _GERMAN_WORDS)
    if _GERMAN_CHARS_RE.search(query) or german_hits >= 2:
        return "deu"
    if _FRENCH_CHARS_RE.search(query) or french_hits >= 2:
        return "fra"
    if len(words & _LATIN_WORDS) >= 2 and not words & {"the", "and", "what", "how"}:
        return "lat"
    if query.isascii():
        return "eng"
    return None


def resolve_reply_lang(query: str, reply_lang: str | None = None) -> str:
    if reply_lang and reply_lang not in ("auto",):
        return reply_lang
    return infer_reply_language(query) or "eng"
