"""Tests for the CLI argument parser surface — choices, defaults, and the
LLM base-url safety check."""

from __future__ import annotations

import pytest

from minerva.cli import _validate_base_url, build_parser


@pytest.fixture
def parser():
    return build_parser()


# ---------- --corpus / --lang choices ----------


def test_chat_corpus_accepts_every_ingested_slug(parser):
    """``--corpus`` is driven by ``_ORIGINAL_LANG_BY_CORPUS`` so every
    ingested author / corpus lights up automatically. The earlier
    8-author tuple was the bug behind the multilingual-chat-retrieval
    fix — nietzsche/marx/cicero/hebrew_mt were silently rejected."""
    for corpus in (
        "plato", "aristotle", "hegel", "kant",
        "nietzsche", "marx", "cicero", "lucretius",
        "hobbes", "hume", "locke", "rousseau", "pascal",
        "epictetus", "marcus_aurelius",
        "septuagint", "new_testament", "vulgate",
        "hebrew_mt", "presocratic",
        "any",
    ):
        args = parser.parse_args(["chat", "--corpus", corpus])
        assert args.corpus == corpus, f"{corpus} not accepted"


def test_chat_lang_accepts_every_indexed_code(parser):
    for lang in ("any", "eng", "grc", "deu", "lat", "fra", "heb", "ara"):
        args = parser.parse_args(["chat", "--lang", lang])
        assert args.lang == lang, f"{lang} not accepted"


def test_chat_rejects_genuinely_unknown_corpus(parser):
    """Truly-not-a-corpus slugs must still SystemExit. ``nietzsche``
    USED to be on this list (the bug); now only entries absent from
    ``_ORIGINAL_LANG_BY_CORPUS`` should reject."""
    with pytest.raises(SystemExit):
        parser.parse_args(["chat", "--corpus", "kafka"])


def test_chat_lang_default_is_any(parser):
    """The default WAS ``eng`` for a long time and silently excluded
    every German / Latin / Hebrew / Greek primary text from chat
    retrieval — see ``docs/INGESTION.md`` §14 / §15."""
    args = parser.parse_args(["chat"])
    assert args.lang == "any"
    args = parser.parse_args(["ask", "anything"])
    assert args.lang == "any"
    args = parser.parse_args(["serve"])
    assert args.lang == "any"


def test_serve_corpus_accepts_kant(parser):
    args = parser.parse_args(["serve", "--corpus", "kant"])
    assert args.corpus == "kant"


def test_ask_lang_accepts_deu(parser):
    args = parser.parse_args(["ask", "--lang", "deu", "Was ist Sittlichkeit?"])
    assert args.lang == "deu"


def test_chat_reply_lang_default_is_auto(parser):
    args = parser.parse_args(["chat"])
    assert args.reply_lang == "auto"


def test_ask_reply_lang_accepts_fra(parser):
    args = parser.parse_args(["ask", "--reply-lang", "fra", "Qu'est-ce que la justice?"])
    assert args.reply_lang == "fra"


# ---------- _validate_base_url footgun ----------


def _ns(**overrides):
    """Build a namespace matching `_validate_base_url`'s expectations."""
    import argparse

    defaults = {
        "llm": "openai",
        "llm_base_url": None,
        "unsafe_llm_base_url_host": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_validate_base_url_none_is_fine():
    _validate_base_url(_ns(llm_base_url=None))


def test_validate_base_url_localhost_is_fine():
    _validate_base_url(_ns(llm_base_url="http://localhost:11434"))
    _validate_base_url(_ns(llm_base_url="http://127.0.0.1:9090/v1"))


def test_validate_base_url_default_openai_host_is_fine():
    _validate_base_url(_ns(llm="openai", llm_base_url="https://api.openai.com/v1"))


def test_validate_base_url_default_anthropic_host_is_fine():
    _validate_base_url(_ns(llm="anthropic", llm_base_url="https://api.anthropic.com/v1"))


def test_validate_base_url_refuses_unknown_host_for_openai():
    with pytest.raises(SystemExit) as info:
        _validate_base_url(_ns(llm="openai", llm_base_url="https://attacker.example/v1"))
    assert info.value.code == 2


def test_validate_base_url_refuses_unknown_host_for_anthropic():
    with pytest.raises(SystemExit) as info:
        _validate_base_url(_ns(llm="anthropic", llm_base_url="https://attacker.example/v1"))
    assert info.value.code == 2


def test_validate_base_url_unsafe_flag_allows_override(capsys):
    # User opted in explicitly — pass with a warning.
    _validate_base_url(
        _ns(
            llm="openai",
            llm_base_url="https://my-proxy.example.com/v1",
            unsafe_llm_base_url_host=True,
        )
    )
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "my-proxy.example.com" in err


# ---------- --allow-origin ----------


def test_serve_allow_origin_collects_multiple(parser):
    args = parser.parse_args(
        [
            "serve",
            "--allow-origin",
            "https://a.example",
            "--allow-origin",
            "https://b.example",
        ]
    )
    assert args.allow_origin == ["https://a.example", "https://b.example"]


def test_serve_allow_origin_defaults_to_empty(parser):
    args = parser.parse_args(["serve"])
    assert args.allow_origin == []
