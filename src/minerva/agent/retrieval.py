"""Retrieval, concept expansion, and answer datatypes."""

from __future__ import annotations

import dataclasses
import sqlite3

from .. import llm, retrieve
from .language import resolve_reply_lang
from .prompts_constants import _ABSTAIN_TEMPLATES, LANG_DISPLAY_NAMES, REWRITE_PROMPT


@dataclasses.dataclass
class Answer:
    query: str
    response: str
    hits: list[retrieve.Hit]
    abstained: bool
    backend: str
    pinned: list[retrieve.Hit] = dataclasses.field(default_factory=list)


# Display-only default: short enough to scroll through in a CLI dump.
# The LLM path uses a higher cap (`_LLM_PASSAGE_CHARS`) so a relevant
# clause buried in the second half of a long passage doesn't get
# silently truncated before the model sees it.
_LLM_PASSAGE_CHARS = 4000


def _format_passages(
    hits: list[retrieve.Hit],
    *,
    max_chars_per_passage: int = 1200,
    label_prefix: str = "",
) -> str:
    blocks: list[str] = []
    for i, h in enumerate(hits, 1):
        loc = retrieve.format_locator(h.meta)
        text = h.meta["text"]
        if len(text) > max_chars_per_passage:
            text = text[:max_chars_per_passage].rstrip() + " […]"
        blocks.append(f"[{label_prefix}{i}] ({loc})\n{text}")
    return "\n\n".join(blocks)


_CONCEPT_EXPAND_PROMPT = """You are a retrieval helper. Given a question \
about a closed corpus by ONE author, your job is to suggest 2–4 KEY TERMS \
in {target_lang_name} that would likely appear in passages answering the \
question.

Constraints:
- Output STRICTLY a JSON object: {{"terms": ["term1", "term2", ...]}}
- 2 to 4 terms maximum.
- Prefer the author's own technical vocabulary (Nietzsche → ``Mißratenen`` \
not ``Versager``; Aristotle → ``οὐσία`` not ``οντότητα``; Aquinas → \
``substantia`` not ``ouvrage``).
- Include morphological variants ONLY when they're orthographically \
distinct (Greek and Latin declensions, German -e/-en plurals).
- If the question is too vague to expand meaningfully, return \
``{{"terms": []}}``.
- Do not translate the whole question, just the key concept words.
- No prose, no commentary, no markdown — just the JSON object.

The corpus is {corpus_name}. The question is in {source_lang_name} \
and the corpus passages are in {target_lang_name}.
"""


def concept_expand(
    backend: llm.LLMBackend,
    query: str,
    *,
    corpus: str,
    target_lang: str,
    source_lang: str = "English",
    temperature: float = 0.0,
    max_terms: int = 4,
) -> list[str]:
    """Ask the LLM for 2–4 target-language terms that would appear in
    passages answering ``query`` within ``corpus``.

    Used as a retrieval pre-pass when the query is in one language
    (typically English) but the corpus original is in another. The
    multilingual embedding model isn't strong enough to bridge
    English "failures" → German *Mißratenen* on its own; surfacing
    the German technical term explicitly in the retrieval query
    fixes that. Same logic for Greek "ousia", Latin "substantia",
    Hebrew "dabar", Arabic "kitab", etc.

    Returns ``[]`` on backend=none, LLM error, malformed JSON, or
    when the LLM judges the question too vague to expand. Callers
    fall back to the unexpanded query — empty expansion is never
    harmful.
    """

    if backend.name == "none":
        return []

    target_lang_name = LANG_DISPLAY_NAMES.get(target_lang, target_lang)
    system_msg = _CONCEPT_EXPAND_PROMPT.format(
        target_lang_name=target_lang_name,
        source_lang_name=source_lang,
        corpus_name=corpus,
    )
    messages = [
        llm.Message(role="system", content=system_msg),
        llm.Message(role="user", content=query),
    ]
    try:
        raw = backend.complete(messages, temperature=temperature)
    except llm.LLMError:
        return []

    # Sniff the JSON. LLM responses sometimes wrap JSON in ```json
    # fences or include preamble despite the prompt; trim defensively.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
        raw = raw.rstrip("`").strip()
    # Sometimes the model emits prose-then-JSON; grab the first {…}.
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
        return []
    raw = raw[first_brace : last_brace + 1]

    import json as _json

    try:
        obj = _json.loads(raw)
    except _json.JSONDecodeError:
        return []
    terms = obj.get("terms") if isinstance(obj, dict) else None
    if not isinstance(terms, list):
        return []
    out: list[str] = []
    for t in terms:
        if isinstance(t, str):
            t = t.strip()
            if t and t not in out:
                out.append(t)
        if len(out) >= max_terms:
            break
    return out


def rewrite_query(
    backend: llm.LLMBackend,
    history: list[llm.Message],
    query: str,
    *,
    temperature: float = 0.0,
) -> str | None:
    """Ask the LLM to compress prior turns + the new question into a
    standalone retrieval query. Returns the trimmed text, or None on any
    failure (caller falls back to naive concatenation).
    """

    if backend.name == "none":
        return None
    messages = [
        llm.Message(role="system", content=REWRITE_PROMPT),
        *history,
        llm.Message(role="user", content=query),
    ]
    try:
        text = backend.complete(messages, temperature=temperature)
    except llm.LLMError:
        return None
    text = text.strip().strip('"').strip("'").strip()
    return text or None


def _abstain_message(query: str, *, reply_lang: str | None = None) -> str:
    code = reply_lang or resolve_reply_lang(query)
    template = _ABSTAIN_TEMPLATES.get(code, _ABSTAIN_TEMPLATES["eng"])
    return template.format(query=query)


@dataclasses.dataclass
class RetrievalResult:
    """Output of `retrieve_passages` — the hits + a flag indicating
    whether retrieval was strong enough to bother with the LLM call.
    The server holds `corpus_lock` only for the retrieve step, then
    releases it before calling the LLM (see `_handle_chat`).
    """

    hits: list[retrieve.Hit]
    pinned: list[retrieve.Hit]
    abstain: bool


def retrieve_passages(
    *,
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 6,
    lang: str | None = "eng",
    corpus: str | None = None,
    embedder=None,
    bm25_floor: float = 0.5,
    cosine_floor: float = 0.25,
    retrieval_query: str | None = None,
    pinned: list[retrieve.Hit] | None = None,
    speaker: str | None = None,
    fold_lang: str | None = None,
    work_id: int | None = None,
) -> RetrievalResult:
    """Run BM25 + vector retrieval and decide whether the result is
    strong enough to send to the LLM. No network calls; safe to run
    under the corpus lock.

    ``fold_lang`` enables orthographic spelling-variant expansion in the
    BM25 query for that language (e.g. ``deu`` folds the historical
    ``Mißrathenen`` to the modernized ``Mißratenen`` the index stores).
    """

    hits = retrieve.search(
        conn,
        retrieval_query if retrieval_query is not None else query,
        top_k=top_k,
        lang=lang,
        corpus=corpus,
        speaker=speaker,
        embedder=embedder,
        fold_lang=fold_lang,
        work_id=work_id,
    )

    pinned = pinned or []
    pinned_ids = {p.chunk_id for p in pinned}
    # Drop hits already present as pins so they don't render twice.
    hits = [h for h in hits if h.chunk_id not in pinned_ids]

    # `Hit.score` is min-max normalized so the top hit is always 1.0; threshold
    # on the raw signals instead. A strong vector match can rescue a weak BM25
    # (synonyms, cross-language), so abstain only when both are below floor.
    if not hits:
        retrieval_weak = True
    else:
        top = hits[0]
        retrieval_weak = top.bm25 < bm25_floor and top.cosine < cosine_floor
    # Pins keep us in scope even when fresh retrieval is empty.
    abstain = retrieval_weak and not pinned
    return RetrievalResult(hits=hits, pinned=pinned, abstain=abstain)


