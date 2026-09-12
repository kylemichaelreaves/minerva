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

import sys
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
                # deployment concern: `stanza.download('de')` fetches it.
                #
                # It lands in `stanza.resources.common.DEFAULT_MODEL_DIR`,
                # which is **scoped by the stanza release** —
                # `user_cache_dir('stanza', 'StanfordNLP', __resources_version__)
                # + '/resources'`, e.g. ~/Library/Caches/stanza/1.14.0/resources
                # on macOS. So a stanza version bump does not migrate the
                # model, it starts from an empty cache and this pipeline
                # raises `LanguageNotDownloadedError` until someone
                # re-downloads. That is what #530 is about; it is also why
                # `~/stanza_resources/` (stanza's pre-1.5 default, and only
                # honoured now via `STANZA_RESOURCES_DIR`) is the wrong place
                # to go looking.
                download_method=None,
            )
    return _PIPELINE


def warm_pipeline() -> bool:
    """Build the pipeline ahead of the first request. True if it is resident.

    The load is ~4.5 s, and until #340 it happened inside the corpus lock on
    whichever request touched syntax first — so the first reader to open a
    diagram waited 4,499 ms and everyone else queued behind them. Paying it
    at startup instead moves the cost to a moment nobody is watching.

    Best-effort by design. Returns False rather than raising when Stanza is
    absent (the ``[lemma]`` extra is optional and CI does not install it) or
    when the model is not on disk — `_pipeline()` is built with
    ``download_method=None``, so an un-downloaded model raises here rather
    than silently fetching. Either way the server must still start: the
    syntax endpoint degrades to the old lazy load, and every other route is
    unaffected.

    The failure is reported on stderr rather than swallowed (#530). It used
    to be discarded entirely — the caller drops the return value and nothing
    logged the exception — so a missing model stayed invisible until a reader
    opened the overlay and got a 500. Startup is where this is cheap to fix
    and where somebody is watching.
    """

    try:
        _pipeline()
    # Broad on purpose: startup must survive any parser fault, and the
    # failure modes here are open-ended (ImportError without the extra;
    # Stanza's `LanguageNotDownloadedError` when `resources.json` is cached
    # but the `de/` model directory is not; its `ResourcesFileNotFoundError`
    # when even `resources.json` is absent).
    except Exception as exc:
        print(
            f"syntax: parser unavailable, diagrams will fail — {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            f"syntax: the model cache is scoped by stanza release, so a version bump "
            f"starts from an empty cache. Fix with: "
            f"python -c \"import stanza; stanza.download('{_LANG}')\"",
            file=sys.stderr,
        )
        return False
    return True


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
