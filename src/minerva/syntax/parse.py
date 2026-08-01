"""Stanza German dependency parsing.

Why Stanza and not the spaCy model already installed: `de_core_news_sm` emits
TIGER labels and an inverted verbal complex — for *Der Geist hat sich in der
Geschichte entwickelt* it makes `hat` the ROOT with `entwickelt` as an `oc`
dependent, where UD makes `entwickelt` the root with `hat` as its `aux`. That
inversion breaks the relation inventory, the fixtures, and the topological-field
heuristic, which depends specifically on the UD direction. Stanza's German
models are UD-trained and produce what the rest of this feature assumes.

Everything Stanza-shaped is confined to `_pipeline()` and `parse_text()`.
The conversion in `doc_to_tokens()` is pure and takes duck-typed input, so it
is testable without the `[lemma]` extra — which CI does not install.
"""

from __future__ import annotations

import threading
from typing import Any

from .queries import SyntaxToken

# Stanza's German pipeline. Loading costs ~4s, so it is built once per process
# and reused. Guarded because the HTTP server dispatches on many threads and
# two concurrent first-requests would otherwise each pay the load.
_PIPELINE: Any = None
_PIPELINE_LOCK = threading.Lock()

_PROCESSORS = "tokenize,pos,lemma,depparse"
_LANG = "de"


def _stanza_version() -> str:
    import stanza

    return str(stanza.__version__)


def parser_id() -> str:
    """Identifier stored in ``chunk_syntax_state.parser``.

    Records which model produced a tree so a future re-parse can tell what is
    stale — the trees themselves carry no other provenance.
    """

    return f"stanza-{_LANG}-{_stanza_version()}"


def _pipeline() -> Any:
    """The lazily-built German pipeline.

    Imported inside the function: `stanza` lives in the optional ``[lemma]``
    extra, and importing this module must not require it. Everything except
    an actual parse works without Stanza installed.
    """

    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE
    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            import stanza

            _PIPELINE = stanza.Pipeline(
                _LANG,
                processors=_PROCESSORS,
                verbose=False,
                # Never reach for the network mid-request. The model is a
                # deployment concern: `minerva syntax parse --download` or
                # `stanza.download('de')` puts it in ~/stanza_resources/.
                download_method=None,
            )
    return _PIPELINE


def doc_to_tokens(doc: Any) -> list[SyntaxToken]:
    """Flatten a parsed document into storable tokens.

    Character offsets come from the *token*, not the word. A multiword token
    (`zum` = `zu` + `dem`) is one surface string covering two syntactic words;
    neither word has a narrower span, and the Reader aligns to the text by
    offset, so both carry the token's.

    Token ids restart at 1 in each sentence — that is the CoNLL-U convention,
    and `(sent_ord, tok_id)` is the identity a correction addresses. Flattening
    to a chunk-wide index would make every correction in a multi-sentence chunk
    point at the wrong word.
    """

    out: list[SyntaxToken] = []
    for sent_ord, sent in enumerate(doc.sentences):
        for token in sent.tokens:
            for word in token.words:
                out.append(
                    SyntaxToken(
                        sent_ord=sent_ord,
                        tok_id=int(word.id),
                        form=word.text,
                        lemma=word.lemma,
                        upos=word.upos,
                        xpos=word.xpos,
                        feats=word.feats,
                        misc=None,
                        head=int(word.head),
                        deprel=word.deprel,
                        surface_start=int(token.start_char),
                        surface_end=int(token.end_char),
                    )
                )
    return out


def parse_text(text: str) -> list[SyntaxToken]:
    """Parse *text* into tokens with sentence ordinals and character offsets.

    Offsets are relative to *text*, so callers pass a chunk's body verbatim
    and the results index straight back into ``chunks.text``.
    """

    if not text.strip():
        # Skip the ~4s pipeline load entirely for an empty chunk.
        return []
    return doc_to_tokens(_pipeline()(text))
