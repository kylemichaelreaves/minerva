"""Unit tests for llm_verify pure helpers (no live LLM)."""

from __future__ import annotations

from minerva.refs import llm_verify


def test_truncate_short_text_unchanged():
    assert llm_verify._truncate("hello", 10) == "hello"


def test_truncate_long_text_word_boundary():
    text = "one two three four five six seven eight nine ten"
    out = llm_verify._truncate(text, 20)
    assert len(out) <= 20
    assert out.endswith("…")


def test_parse_verdicts_plain_json_array():
    raw = '[{"id": 1, "references": true, "type": "cites", "confidence": 0.9, "notes": "ok"}]'
    verdicts = llm_verify._parse_verdicts(raw)
    assert verdicts is not None
    assert verdicts[0]["id"] == 1


def test_parse_verdicts_strips_json_fence():
    raw = """```json
[{"id": 2, "references": false, "type": "quotes", "confidence": 0.1, "notes": "no"}]
```"""
    verdicts = llm_verify._parse_verdicts(raw)
    assert verdicts is not None
    assert len(verdicts) == 1


def test_parse_verdicts_returns_none_on_garbage():
    assert llm_verify._parse_verdicts("not json at all") is None


def test_build_user_message_includes_truncated_fields():
    rows = [
        {
            "id": 7,
            "source_author": "Aquinas",
            "source_work": "ST",
            "source_section": "Ia q.1",
            "source_text": "x" * 500,
            "source_form_snapshot": "Philosophus",
            "target_author": "Aristotle",
            "target_work": "Metaphysics",
            "target_locator": "Met 1:1",
            "reference_type": "comments_on",
            "source_method": "rule_strong",
            "confidence": 0.9,
            "target_text": "y" * 400,
            "quoted_phrase": "ens",
        }
    ]
    payload = llm_verify._build_user_message(rows)
    data = __import__("json").loads(payload)
    assert data[0]["id"] == 7
    assert len(data[0]["source_text"]) < 500
    assert data[0]["target_in_corpus"] is True


def test_format_eta_seconds_minutes_hours():
    assert llm_verify._format_eta(30) == "30s"
    assert "m" in llm_verify._format_eta(120)
    assert "h" in llm_verify._format_eta(7200)


def test_excerpt_without_a_span_is_the_head():
    text = "word " * 200
    assert llm_verify._excerpt(text, None, None, 400) == llm_verify._truncate(text, 400)


def test_excerpt_with_a_span_inside_the_head_is_the_head():
    text = "word " * 200
    assert llm_verify._excerpt(text, 10, 20, 400) == llm_verify._truncate(text, 400)


def test_excerpt_centres_on_a_span_past_the_head():
    text = ("a " * 600) + "CITE" + (" b" * 600)
    start = text.index("CITE")
    out = llm_verify._excerpt(text, start, start + 4, 400)
    assert "CITE" in out
    assert out.startswith("…") and out.endswith("…")
    assert len(out) <= 402
    # Roughly centred: context on both sides.
    before, after = out.split("CITE")
    assert len(before) > 150 and len(after) > 150


def test_excerpt_near_the_end_has_no_trailing_ellipsis():
    text = ("a " * 600) + "CITE."
    start = text.index("CITE")
    out = llm_verify._excerpt(text, start, start + 4, 400)
    assert out.startswith("…")
    assert out.endswith("CITE.")


def test_excerpt_keeps_a_span_longer_than_the_budget_whole():
    quote = "q" * 500
    text = ("a " * 300) + quote + (" b" * 300)
    start = text.index(quote)
    out = llm_verify._excerpt(text, start, start + len(quote), 400)
    assert quote in out


def test_excerpt_with_a_span_the_head_trim_would_cut_is_windowed():
    # The head is cut back to a word boundary, so a cite ending just
    # under char 400 falls off it — 7 live rows, e.g. "Plato" at 395–400.
    text = ("a " * 197) + " Plato said" + (" b" * 100)
    start = text.index("Plato")
    assert start + 5 <= 400
    assert "Plato" not in llm_verify._truncate(text, 400)
    assert "Plato" in llm_verify._excerpt(text, start, start + 5, 400)
