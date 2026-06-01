"""Language-routed lemmatizer for the glossary importer.

Used by ``minerva terms lemmatize`` (and `glossary_import`) to convert
a chunk of text into ``(surface, start, end, lemma)`` tuples that the
importer joins against ``terms.lemma`` to find term occurrences
mechanically.

Routing
-------

* ``deu`` → spaCy ``de_core_news_sm``. Stable, ~95 % accuracy on
  modern German; still acceptable on Hegel/Kant German.
* ``grc`` → spaCy ``grc_dep_web_sm`` (LatinCy / Patrick Burns), with
  Stanza ``grc`` as fallback if the model isn't installed. LatinCy
  was trained on AGLDT+PROIEL+Perseus and scores 97.4% lemma accuracy
  on UD grc-PROIEL dev (Stanza: 89.8%), while running ~5× faster.
* ``lat`` → spaCy ``la_core_web_sm`` (LatinCy), with Stanza ``la`` as
  fallback. LatinCy scores 88.1% on UD lat-PROIEL dev (Stanza:
  84.9%), again ~5× faster.

Both LatinCy models are HuggingFace-hosted spaCy wheels — install with::

    uv pip install \\
      https://huggingface.co/latincy/grc_dep_web_sm/resolve/main/grc_dep_web_sm-3.8.1-py3-none-any.whl \\
      https://huggingface.co/latincy/la_core_web_sm/resolve/main/la_core_web_sm-3.9.0-py3-none-any.whl

See lemmatize-perf-plan memory for the full eval methodology + numbers.

Both backends are wrapped in this module so the importer doesn't
care which engine produced a token — it just consumes
:class:`Token`. Framework imports are deferred to ``__init__`` so
importing the module on a plain (no-``[lemma]``-extras) install
doesn't hard-fail; only constructing a :class:`Lemmatizer` actually
touches the heavy deps.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


class UnsupportedLanguageError(RuntimeError):
    """Raised when the lemmatizer can't service a given language code.

    Callers (the glossary importer) treat this as a signal to fall
    back to surface-form regex matching rather than an error to halt
    on.
    """


# How many Stanza Documents to pass to `bulk_process` at once. 256 is
# a sweet spot: big enough to amortize Stanza's per-call overhead (the
# 2.7× speedup over per-text calls measured on grc), small enough that
# the working set stays bounded for typical philosophical chunks
# (~500-2000 chars each). Tune if you see memory pressure or want
# more parallelism — Stanza's own intra-document batching is
# orthogonal and already at sane defaults.
_STANZA_BULK_SIZE = 256


_LEMMA_ALLOWED_PUNCT = frozenset(
    (
        "-",   # mid-word hyphen — "black-box", "Sturm-und-Drang"
        "'",   # ASCII apostrophe — "O'Connor", elided forms
        "ʼ",   # MODIFIER LETTER APOSTROPHE (U+02BC) — Stanza Greek crasis
        "'",  # RIGHT SINGLE QUOTATION MARK (U+2019) — typeset apostrophe
        "·",   # MIDDLE DOT (U+00B7) — Greek "ano teleia" appears in some lemmas
    )
)


def is_valid_lemma(lemma: str) -> bool:
    """Reject lemmas that aren't real words.

    spaCy and Stanza both emit tokens for punctuation, numbers, and
    line-break artifacts from scanned/OCR'd source text. Those clutter
    the concordance — the user clicks ``All German`` sorted A→Z and
    sees ``$``, ``--`` (1,497 occurrences as PROPN), ``+20``,
    ``A.smith``, ``A=25``. None of these belong in a lemma index of a
    philosophical corpus.

    The rule: a valid lemma's first character is a Unicode Letter, and
    every other character is either a Letter, a Mark (combining
    diacritic), or one of a small whitelist of mid-word punctuation
    (hyphen + apostrophe variants). This:

    * Drops ``-``-prefixed line-break fragments (`-begriff`, `-instinkt`)
    * Drops punctuation-only tokens (``--``, ``$``, ``(=``, ``-^``)
    * Drops numeric-only tokens (``+20``, ``-3``)
    * Drops English contraction tails spaCy emits as standalone (``'s``)
    * Drops scan/OCR junk that starts with a letter but contains
      symbols or digits (``A.smith``, ``A=25``, ``A11``, ``A.``)
    * Preserves single-letter words (Greek ὁ / ἡ / ᾧ, Latin a / e)
    * Preserves Umlaut-leading German nouns (Über, Äußerung)
    * Preserves hyphenated compounds and possessives
      (``black-box``, ``O'Connor``)
    * Preserves any non-Latin script's words

    Linguistic-mention edge cases (Hegel discussing the German suffix
    ``-keit`` as a standalone term) are collateral damage — rarer than
    the genuine noise and outside the concordance's primary use case.

    Empty string also fails — defensive.
    """

    if not lemma:
        return False
    if not unicodedata.category(lemma[0]).startswith("L"):
        return False
    for ch in lemma:
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "M")):
            continue
        if ch in _LEMMA_ALLOWED_PUNCT:
            continue
        return False
    return True


@dataclass(frozen=True)
class Token:
    """One token of a lemmatised chunk.

    ``surface``, ``start``, ``end`` index into the original chunk
    text exactly as it was passed to :meth:`Lemmatizer.tokens`.
    ``lemma`` is NFC-normalised so equality comparisons against
    ``terms.lemma`` (also NFC at write time) are exact.

    ``pos`` is the Universal Dependencies coarse part-of-speech
    (NOUN, VERB, ADJ, …), and ``feats`` is the UD morph-features
    string (e.g. ``"Case=Acc|Gender=Fem|Number=Sing"``). Both are
    optional because not every backend tags every token, and
    pre-backfill rows in ``chunk_lemmas`` carry NULL for these fields.
    """

    surface: str
    start: int
    end: int
    lemma: str
    pos: str | None = None
    feats: str | None = None


class Lemmatizer:
    """Lemmatizer for one language. Constructed once and reused — the
    underlying spaCy model loads its weights at ``__init__`` time and
    keeps them resident for the lifetime of the instance."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self._backend: str | None = None
        self._nlp: Any | None = None
        if lang == "deu":
            self._init_spacy_de()
        elif lang == "fra":
            self._init_spacy_fr()
        elif lang == "eng":
            self._init_spacy_en()
        elif lang == "grc":
            # Prefer LatinCy spaCy model (faster + higher lemma
            # accuracy on UD-PROIEL gold); fall back to Stanza if the
            # spaCy model isn't installed so existing setups don't
            # break.
            if not self._try_init_spacy_grc():
                self._init_stanza_grc()
        elif lang == "lat":
            if not self._try_init_spacy_lat():
                self._init_stanza_lat()
        elif lang in ("heb", "ara"):
            self._init_stanza_generic(lang)
        else:
            raise UnsupportedLanguageError(
                f"no lemmatizer registered for language {lang!r}"
            )

    @property
    def backend(self) -> str:
        """``spacy`` or ``stanza`` — which engine backs this instance."""

        return self._backend or "unknown"

    @property
    def model(self) -> str:
        """Installed spaCy model name, or ISO 639-3 code for Stanza."""

        if self._backend == "spacy" and self._nlp is not None:
            return str(self._nlp.meta.get("name", "?"))
        if self._backend == "stanza":
            return self.lang
        return "?"

    def _init_spacy_de(self) -> None:
        try:
            import spacy
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "spaCy not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        try:
            # Drop `parser` and `ner` — downstream consumers only read
            # tagger/morphologizer/lemmatizer output, so leaving the
            # parse tree and entity recognition enabled was pure
            # overhead (~2-3× per-chunk cost). See lemmatize-perf-plan
            # memory for the full optimization ranking.
            self._nlp = spacy.load(
                "de_core_news_sm", disable=["parser", "ner"]
            )
        except OSError as exc:
            raise UnsupportedLanguageError(
                "spaCy model `de_core_news_sm` not installed; "
                "the lemma extras should pull it in automatically — "
                "rerun `uv pip install -e '.[lemma]'`"
            ) from exc
        self._backend = "spacy"

    def _init_spacy_fr(self) -> None:
        try:
            import spacy
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "spaCy not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        try:
            self._nlp = spacy.load(
                "fr_core_news_sm", disable=["parser", "ner"]
            )
        except OSError as exc:
            raise UnsupportedLanguageError(
                "spaCy model `fr_core_news_sm` not installed; "
                "the lemma extras should pull it in automatically — "
                "rerun `uv pip install -e '.[lemma]'`"
            ) from exc
        self._backend = "spacy"

    def _init_spacy_en(self) -> None:
        """spaCy ``en_core_web_sm`` lemmatizer. Standard English UD
        pipeline; ~98% accuracy on EWT gold. Same shape as the deu
        / fra init paths — disable ``parser`` and ``ner`` since we
        only consume the tagger + lemmatizer output.

        Wheel install path (model isn't on PyPI by name):
            uv pip install "en_core_web_sm @ \\
              https://github.com/explosion/spacy-models/releases/\\
              download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
        """

        try:
            import spacy
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "spaCy not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        try:
            self._nlp = spacy.load(
                "en_core_web_sm", disable=["parser", "ner"]
            )
        except OSError as exc:
            raise UnsupportedLanguageError(
                "spaCy model `en_core_web_sm` not installed; install via "
                "`uv pip install 'en_core_web_sm @ https://github.com/"
                "explosion/spacy-models/releases/download/en_core_web_sm"
                "-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'`"
            ) from exc
        self._backend = "spacy"

    def _init_stanza_generic(self, lang: str) -> None:
        """Stanza pipeline for languages without a spaCy model in our
        install set — currently Hebrew (``heb``) and Arabic (``ara``).
        Same shape as ``_init_stanza_grc`` but maps ISO 639-3 →
        Stanza's two-letter codes (``he`` / ``ar``)."""

        try:
            import stanza
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "Stanza not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        # ISO 639-3 → Stanza's two-letter codes. Add more entries here
        # when extending to other Stanza-only languages.
        stanza_lang = {"heb": "he", "ara": "ar"}.get(lang)
        if stanza_lang is None:
            raise UnsupportedLanguageError(
                f"_init_stanza_generic: no Stanza code mapping for {lang!r}"
            )
        try:
            self._nlp = stanza.Pipeline(
                lang=stanza_lang,
                processors="tokenize,pos,lemma",
                download_method="reuse_resources",
                verbose=False,
            )
        except FileNotFoundError:
            stanza.download(stanza_lang, verbose=False)
            self._nlp = stanza.Pipeline(
                lang=stanza_lang,
                processors="tokenize,pos,lemma",
                download_method="reuse_resources",
                verbose=False,
            )
        self._backend = "stanza"

    def _try_init_spacy_grc(self) -> bool:
        """Try to load LatinCy's grc_dep_web_sm. Returns True on
        success; False (with the spaCy backend NOT set) when the
        model wheel isn't installed — caller then falls back to
        Stanza so old setups still work."""

        try:
            import spacy
        except ImportError:
            return False
        try:
            # Disable `parser` (we don't use the dep tree) and
            # `senter` (we never split by sentence — chunks are the
            # unit). Keep tagger/morphologizer/lemmatizer.
            self._nlp = spacy.load(
                "grc_dep_web_sm", disable=["parser", "senter"]
            )
        except OSError:
            return False
        self._backend = "spacy"
        return True

    def _try_init_spacy_lat(self) -> bool:
        """Try to load LatinCy's la_core_web_sm. Same fallback shape
        as ``_try_init_spacy_grc``."""

        try:
            import spacy
        except ImportError:
            return False
        try:
            # The LatinCy lat pipeline includes
            # ``normer, harmonizer, uv_normalizer, remorpher`` — kept
            # on; they're tuned by the model author and improve lemma
            # quality on the Latin orthographic conventions our corpus
            # uses (u/v, j/i, classical/medieval spellings). Only
            # disable the parser (unused) and ner (we don't index
            # entities).
            self._nlp = spacy.load(
                "la_core_web_sm", disable=["parser", "ner"]
            )
        except OSError:
            return False
        self._backend = "spacy"
        return True

    def _init_stanza_grc(self) -> None:
        try:
            import stanza
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "Stanza not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        # First-run: stanza.download fetches the model into
        # ~/stanza_resources/. The download_method=DownloadMethod
        # .REUSE_RESOURCES (default since 1.5) skips when present, so
        # this is a one-time cost we pay implicitly.
        try:
            self._nlp = stanza.Pipeline(
                lang="grc",
                processors="tokenize,pos,lemma",
                # Stanza's Pipeline blocks the first run on a model
                # download. download_method=None forces an explicit
                # download() up-front; we do that in a guarded try so
                # the user gets a clean error rather than a half-
                # initialised pipeline.
                download_method="reuse_resources",
                verbose=False,
            )
        except FileNotFoundError:
            stanza.download("grc", verbose=False)
            self._nlp = stanza.Pipeline(
                lang="grc",
                processors="tokenize,pos,lemma",
                download_method="reuse_resources",
                verbose=False,
            )
        self._backend = "stanza"

    def _init_stanza_lat(self) -> None:
        try:
            import stanza
        except ImportError as exc:
            raise UnsupportedLanguageError(
                "Stanza not installed; install the lemma extras: "
                "uv pip install -e '.[lemma]'"
            ) from exc
        try:
            self._nlp = stanza.Pipeline(
                lang="la",
                processors="tokenize,pos,lemma",
                download_method="reuse_resources",
                verbose=False,
            )
        except FileNotFoundError:
            stanza.download("la", verbose=False)
            self._nlp = stanza.Pipeline(
                lang="la",
                processors="tokenize,pos,lemma",
                download_method="reuse_resources",
                verbose=False,
            )
        self._backend = "stanza"

    def tokens(self, text: str) -> Iterable[Token]:
        """Yield one :class:`Token` per word in ``text``. Whitespace
        and punctuation tokens are skipped — the importer only cares
        about content words that can plausibly carry a lemma match."""

        if self._backend == "spacy":
            yield from self._tokens_spacy(text)
        elif self._backend == "stanza":
            yield from self._tokens_stanza(text)
        else:  # pragma: no cover — guarded by __init__
            raise UnsupportedLanguageError(self.lang)

    def batch_pipe(
        self,
        items: Iterable[tuple[str, object]],
        *,
        batch_size: int = 64,
        n_process: int = 1,
    ) -> Iterable[tuple[list[Token], object]]:
        """Stream-process ``(text, context)`` pairs and yield
        ``(tokens, context)`` pairs in input order.

        For the spaCy backends (deu, fra) this delegates to
        ``nlp.pipe(..., as_tuples=True, batch_size=N, n_process=N)``,
        which is dramatically faster than per-text ``nlp(text)``
        calls — pipeline state is reused across texts and ``n_process
        > 1`` splits the work across worker processes, each holding
        its own model copy (~80 MB for de_core_news_sm).

        For Stanza backends batching offers fewer wins via this API,
        so we fall back to per-text calls. (Future work: switch grc
        to spaCy if accuracy is acceptable — see the
        lemmatize-perf-plan memory.)
        """

        if self._backend == "spacy":
            for doc, context in self._nlp.pipe(
                items, batch_size=batch_size, n_process=n_process, as_tuples=True
            ):
                yield list(self._tokens_from_spacy_doc(doc)), context
        elif self._backend == "stanza":
            # Stanza's `Pipeline.bulk_process` accepts a list of
            # Documents and processes them in one go, amortizing the
            # per-call overhead that dominates per-chunk usage.
            # Measured 2.7× on grc against per-text `nlp(text)` calls
            # (see lemmatize-perf-plan memory). The intra-batch
            # tokenize/pos/lemma batch sizes are already tuned by
            # Stanza defaults — raising them further had no effect.
            import stanza

            items_iter = iter(items)
            bulk = _STANZA_BULK_SIZE
            while True:
                batch = []
                contexts = []
                for _ in range(bulk):
                    nxt = next(items_iter, None)
                    if nxt is None:
                        break
                    text, ctx = nxt
                    batch.append(stanza.Document([], text=text))
                    contexts.append(ctx)
                if not batch:
                    break
                for doc, ctx in zip(
                    self._nlp.bulk_process(batch), contexts, strict=True
                ):
                    yield list(self._tokens_from_stanza_doc(doc)), ctx
        else:  # pragma: no cover — guarded by __init__
            raise UnsupportedLanguageError(self.lang)

    def _tokens_spacy(self, text: str) -> Iterable[Token]:
        yield from self._tokens_from_spacy_doc(self._nlp(text))

    def _tokens_from_spacy_doc(self, doc) -> Iterable[Token]:
        for t in doc:
            if t.is_space or t.is_punct:
                continue
            start = t.idx
            end = start + len(t.text)
            # NFC-normalise so equality with `terms.lemma` (also NFC
            # at write time) is exact. Do NOT lowercase — German
            # capitalises nouns and the lemmatizer's case carries
            # that signal (`Geist` vs `geist`).
            lemma = unicodedata.normalize("NFC", t.lemma_ or t.text)
            # spaCy returns morph as a special MorphAnalysis object
            # whose str() round-trips to the UD `Key=Val|...` shape
            # Stanza emits natively. None when empty.
            morph_str = str(t.morph) if str(t.morph) else None
            yield Token(
                surface=t.text,
                start=start,
                end=end,
                lemma=lemma,
                pos=t.pos_ or None,
                feats=morph_str,
            )

    def _tokens_stanza(self, text: str) -> Iterable[Token]:
        yield from self._tokens_from_stanza_doc(self._nlp(text))

    def _tokens_from_stanza_doc(self, doc) -> Iterable[Token]:
        for sent in doc.sentences:
            for w in sent.words:
                # Stanza emits a punctuation upos for `.` `,` `;` etc.
                # and a synthetic SYM upos for non-alphabetic markers.
                if w.upos in {"PUNCT", "SYM"}:
                    continue
                # Greek lemmas are conventionally lowercase, but
                # Stanza preserves the case of the surface — use the
                # lemma as-is after NFC.
                lemma = unicodedata.normalize("NFC", w.lemma or w.text)
                # `w.feats` is the UD-formatted morph string when
                # Stanza tagged any features; an empty string or
                # `_` when there's nothing to report. Coerce both
                # to None so the column is honest about gaps.
                feats = w.feats if w.feats and w.feats != "_" else None
                # Multi-Word Token handling (Arabic clitic expansion,
                # German contraction splits, etc.): when Stanza splits
                # an input token like ``والكتاب`` into multiple words,
                # the expanded ``w.start_char`` / ``w.end_char`` are
                # None because there's no clean character span for the
                # sub-word in the original text. Fall back to the
                # parent token's span — every clitic in the same input
                # token shares it, which means multiple ``chunk_lemmas``
                # rows can have the same (surface_start, surface_end),
                # but token_index disambiguates them at PK level.
                start = w.start_char
                end = w.end_char
                if start is None or end is None:
                    parent = getattr(w, "parent", None)
                    if parent is not None:
                        start = parent.start_char
                        end = parent.end_char
                # If even the parent has no span (rare — Stanza
                # sometimes emits synthetic tokens for empty heads),
                # skip rather than violate the NOT NULL constraint.
                if start is None or end is None or end <= start:
                    continue
                yield Token(
                    surface=w.text,
                    start=start,
                    end=end,
                    lemma=lemma,
                    pos=w.upos or None,
                    feats=feats,
                )


# Languages we know how to lemmatize. Importers check this before
# attempting `Lemmatizer(lang)` so they can pick the surface-form
# fallback eagerly instead of catching exceptions per call site.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {
        "deu",  # spaCy de_core_news_sm
        "fra",  # spaCy fr_core_news_sm
        "eng",  # spaCy en_core_web_sm (added 2026-05-29)
        "grc",  # LatinCy grc_dep_web_sm → Stanza fallback
        "lat",  # LatinCy la_core_web_sm → Stanza fallback
        "heb",  # Stanza (he); model downloads on first run
        "ara",  # Stanza (ar); model downloads on first run
    }
)


def is_supported(lang: str) -> bool:
    """``True`` if :class:`Lemmatizer` can be constructed for ``lang``
    without raising. Cheap — does no model loading."""

    return lang in SUPPORTED_LANGUAGES
