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
