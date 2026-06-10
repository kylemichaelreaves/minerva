"""Tests for `minerva.agent` — prompt assembly, abstention, pinning, citation styles."""

from __future__ import annotations

from conftest import StubBackend, make_hit

from minerva import agent, llm

# ---------- reply-language directive stripping ----------


def test_strip_reply_directive_removes_trailing_answer_directive():
    out = agent.strip_reply_directive(
        "What is the difference between Vorstellung and Darstellung for Hegel? "
        "Answer in English"
    )
    assert out == "What is the difference between Vorstellung and Darstellung for Hegel?"
    assert "English" not in out


def test_strip_reply_directive_removes_leading_directive():
    assert agent.strip_reply_directive("In French, qu'est-ce que la volonté") == (
        "qu'est-ce que la volonté"
    )
    assert agent.strip_reply_directive("Please respond in German: was ist Geist") == (
        "was ist Geist"
    )


def test_strip_reply_directive_preserves_substantive_in_clauses():
    # "explain" is not a directive verb, and a content word between the
    # verb and "in" is not whitelisted filler — so the topic survives.
    assert (
        agent.strip_reply_directive("explain Hegel in English please")
        == "explain Hegel in English please"
    )
    # A genuine reference to a language as subject matter is untouched.
    assert (
        agent.strip_reply_directive("passages about the English language")
        == "passages about the English language"
    )


def test_strip_reply_directive_noop_when_absent():
    q = "What is Geist for Hegel?"
    assert agent.strip_reply_directive(q) == q


def test_build_retrieval_query_strips_directive_and_keeps_history():
    out = agent.build_retrieval_query(
        "Answer in English what is Geist", ["earlier turn about Kant"]
    )
    assert "English" not in out
    assert "Geist" in out and "Kant" in out


# ---------- system prompt ----------


def test_system_prompt_locator_style_default():
    p = agent._system_prompt("locator")
    assert "[Author, Work Section]" in p
    assert "[N]" not in p


def test_system_prompt_numeric_style():
    p = agent._system_prompt("numeric")
    assert "[N]" in p
    assert "[Author, Work Section]" not in p


def test_system_prompt_includes_multilingual_reply_rules():
    p = agent._system_prompt("numeric")
    assert "language of <QUESTION>" in p
    assert "exactly as given" in p


def test_system_prompt_explicit_reply_lang_clause():
    p = agent._system_prompt("numeric", reply_lang="fra")
    assert "replies in French" in p


def test_module_level_system_prompt_is_locator_style():
    # Existing CLI behavior must be preserved.
    assert "[Author, Work Section]" in agent.SYSTEM_PROMPT


# ---------- rewrite_query ----------


def test_rewrite_query_strips_quotes_and_whitespace():
    backend = StubBackend(reply='  "the divided line in Republic"  ')
    out = agent.rewrite_query(backend, history=[], query="and what comes next?")
    assert out == "the divided line in Republic"


def test_rewrite_query_returns_none_for_empty_reply():
    backend = StubBackend(reply="   ")
    assert agent.rewrite_query(backend, history=[], query="x") is None


def test_rewrite_query_returns_none_on_llm_error():
    backend = StubBackend(reply=llm.LLMError("boom"))
    assert agent.rewrite_query(backend, history=[], query="x") is None


def test_rewrite_query_skips_null_backend_without_calling():
    null = llm.NullBackend()
    # NullBackend.complete returns "" — but rewrite_query should bail before calling.
    # We verify by giving NullBackend a sentinel that would explode if called.
    null.complete = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call"))  # type: ignore
    assert agent.rewrite_query(null, history=[], query="x") is None


# ---------- concept_expand ----------


def test_concept_expand_parses_clean_json():
    backend = StubBackend(reply='{"terms": ["Mißratenen", "die Gescheiterten"]}')
    out = agent.concept_expand(backend, "Who are the failures?", corpus="nietzsche", target_lang="deu")
    assert out == ["Mißratenen", "die Gescheiterten"]


def test_concept_expand_strips_markdown_fences():
    backend = StubBackend(reply='```json\n{"terms": ["οὐσία", "ousia"]}\n```')
    out = agent.concept_expand(backend, "What is substance?", corpus="aristotle", target_lang="grc")
    assert out == ["οὐσία", "ousia"]


def test_concept_expand_tolerates_prose_around_json():
    backend = StubBackend(reply='Sure! Here are the terms: {"terms": ["substantia"]} Hope that helps.')
    out = agent.concept_expand(backend, "What is substance?", corpus="aquinas", target_lang="lat")
    assert out == ["substantia"]


def test_concept_expand_caps_at_max_terms():
    backend = StubBackend(reply='{"terms": ["a", "b", "c", "d", "e", "f"]}')
    out = agent.concept_expand(backend, "q", corpus="aristotle", target_lang="grc", max_terms=3)
    assert out == ["a", "b", "c"]


def test_concept_expand_drops_duplicates():
    backend = StubBackend(reply='{"terms": ["λόγος", "λόγος", " λόγος "]}')
    out = agent.concept_expand(backend, "q", corpus="aristotle", target_lang="grc")
    assert out == ["λόγος"]


def test_concept_expand_empty_terms_returns_empty():
    backend = StubBackend(reply='{"terms": []}')
    out = agent.concept_expand(backend, "vague question", corpus="aristotle", target_lang="grc")
    assert out == []


def test_concept_expand_malformed_json_returns_empty():
    backend = StubBackend(reply='this is not json at all')
    out = agent.concept_expand(backend, "q", corpus="aristotle", target_lang="grc")
    assert out == []


def test_concept_expand_llm_error_returns_empty():
    backend = StubBackend(reply=llm.LLMError("rate limited"))
    out = agent.concept_expand(backend, "q", corpus="aristotle", target_lang="grc")
    assert out == []


def test_concept_expand_null_backend_returns_empty():
    null = llm.NullBackend()
    null.complete = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call"))  # type: ignore
    out = agent.concept_expand(null, "q", corpus="aristotle", target_lang="grc")
    assert out == []


def test_concept_expand_ignores_non_string_term_entries():
    backend = StubBackend(reply='{"terms": ["good", 42, null, "also good"]}')
    out = agent.concept_expand(backend, "q", corpus="aristotle", target_lang="grc")
    assert out == ["good", "also good"]


# ---------- agent.answer with stub backend ----------


def test_answer_with_no_llm_returns_formatted_passages(populated_db):
    backend = llm.NullBackend()
    ans = agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=3,
        lang="eng",
    )
    assert ans.backend == "none"
    assert ans.abstained is False
    # Bare passage list, no <PASSAGES> wrapper
    assert "<PASSAGES>" not in ans.response
    assert "[1]" in ans.response


def test_answer_uses_retrieval_query_for_search(populated_db):
    backend = StubBackend()
    ans = agent.answer(
        conn=populated_db,
        query="meaningless prose to the user",
        backend=backend,
        top_k=3,
        lang="eng",
        retrieval_query="divided line",
    )
    assert not ans.abstained
    assert any("Republic" in h.meta["work"] for h in ans.hits)
    # The user-visible query is preserved in the prompt regardless.
    assert "meaningless prose to the user" in backend.last_user_block()


def test_answer_threads_history_between_system_and_user(populated_db):
    backend = StubBackend()
    history = [
        llm.Message(role="user", content="Tell me about justice."),
        llm.Message(role="assistant", content="Republic II..."),
    ]
    agent.answer(
        conn=populated_db,
        query="and the divided line?",
        backend=backend,
        top_k=2,
        lang="eng",
        history=history,
    )
    msgs = backend.captured[-1][0]
    assert msgs[0].role == "system"
    assert msgs[1] is history[0]
    assert msgs[2] is history[1]
    assert msgs[3].role == "user"


def test_answer_with_cite_style_numeric_uses_numeric_system_prompt(populated_db):
    backend = StubBackend()
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=2,
        lang="eng",
        cite_style="numeric",
    )
    assert "[N]" in backend.last_system()
    assert "[Author, Work Section]" not in backend.last_system()


def test_answer_with_pinned_renders_a_pinned_block_before_passages(populated_db):
    backend = StubBackend()
    pin = make_hit(chunk_id="rep-510a", section="510a", text="visible vs intelligible")
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=3,
        lang="eng",
        pinned=[pin],
    )
    block = backend.last_user_block()
    assert "<PINNED>" in block
    assert "<PASSAGES>" in block
    assert block.index("<PINNED>") < block.index("<PASSAGES>")
    assert "[P1]" in block


def test_answer_with_pinned_numeric_uses_continuous_numbering(populated_db):
    backend = StubBackend()
    pin = make_hit(chunk_id="rep-510a", section="510a", text="visible vs intelligible")
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=3,
        lang="eng",
        pinned=[pin],
        cite_style="numeric",
    )
    block = backend.last_user_block()
    assert "[1]" in block
    assert "[P1]" not in block
    assert "[2]" in block


def test_answer_dedupes_pinned_chunks_from_retrieval_results(populated_db):
    backend = StubBackend()
    # Pin a chunk that retrieval would also surface for "divided line".
    pin = make_hit(chunk_id="rep-509d")
    ans = agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=3,
        lang="eng",
        pinned=[pin],
    )
    assert all(h.chunk_id != "rep-509d" for h in ans.hits)
    assert any(p.chunk_id == "rep-509d" for p in ans.pinned)


def test_answer_abstains_when_retrieval_is_weak_and_no_pins(populated_db):
    backend = StubBackend()
    ans = agent.answer(
        conn=populated_db,
        query="zxqv asdfgh poiuy",
        backend=backend,
        top_k=3,
        lang="eng",
    )
    assert ans.abstained is True
    assert "could not find enough evidence" in ans.response.lower()
    # Backend was never called on the abstain path.
    assert backend.captured == []


def test_abstains_when_no_hit_has_any_lexical_match(populated_db, monkeypatch):
    # Gibberish queries get no FTS match anywhere but still embed at
    # 0.39-0.58 cosine against letter-sequence/genealogy chunks — inside
    # the range real conceptual queries occupy, so the cosine floor can't
    # catch them. An all-vector result set (every hit bm25=0) must abstain
    # on the lexical signal alone, however high the cosines are.
    vector_only = [
        make_hit(chunk_id="rep-509d", bm25=0.0, cosine=0.58),
        make_hit(chunk_id="rep-510a", section="510a", bm25=0.0, cosine=0.44),
    ]
    monkeypatch.setattr(agent.retrieval.retrieve, "search", lambda *a, **k: vector_only)
    result = agent.retrieve_passages(conn=populated_db, query="zxqv asdf qwer")
    assert result.abstain is True


def test_no_abstain_when_some_hit_has_a_lexical_match(populated_db, monkeypatch):
    # Same cosines, but one hit carries a BM25 score: the query shares
    # vocabulary with the corpus, so the ordinary floors apply.
    mixed = [
        make_hit(chunk_id="rep-509d", bm25=12.0, cosine=0.58),
        make_hit(chunk_id="rep-510a", section="510a", bm25=0.0, cosine=0.44),
    ]
    monkeypatch.setattr(agent.retrieval.retrieve, "search", lambda *a, **k: mixed)
    result = agent.retrieve_passages(conn=populated_db, query="the divided line")
    assert result.abstain is False


def test_pinned_passages_rescue_abstention_on_weak_retrieval(populated_db):
    backend = StubBackend()
    pin = make_hit(chunk_id="rep-509d", text="anchored passage")
    ans = agent.answer(
        conn=populated_db,
        query="zxqv asdfgh poiuy",
        backend=backend,
        top_k=3,
        lang="eng",
        pinned=[pin],
    )
    assert ans.abstained is False
    # Backend was called.
    assert len(backend.captured) == 1


def test_answer_returns_pinned_in_the_answer_object(populated_db):
    backend = StubBackend()
    pin = make_hit(chunk_id="rep-510a")
    ans = agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=2,
        lang="eng",
        pinned=[pin],
    )
    assert [p.chunk_id for p in ans.pinned] == ["rep-510a"]


def test_answer_response_text_is_what_backend_returned(populated_db):
    backend = StubBackend(reply="The divided line is at Republic 509d [1].")
    ans = agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=2,
        lang="eng",
    )
    assert ans.response == "The divided line is at Republic 509d [1]."


def test_llm_path_uses_higher_passage_cap_than_display(populated_db):
    """The LLM sees up to `_LLM_PASSAGE_CHARS` per passage; the no-LLM
    display path still truncates at the original 1200 to keep CLI dumps
    readable. Regression guard: a passage in the 1500-char range must
    survive the truncation in the LLM prompt."""
    backend = StubBackend()
    # Inject a synthetic chunk via pinning so we control the exact text length.
    long_text = "abcdef ghijkl " * 200  # ~2800 chars, comfortably > 1200
    pin = make_hit(chunk_id="long", text=long_text)
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=1,
        lang="eng",
        pinned=[pin],
    )
    user_block = backend.last_user_block()
    # Pin appears in <PINNED>; the long text should fit at ≥ 2000 chars
    # (LLM cap is 4000; the synthetic body is ~2800).
    assert long_text[:2000] in user_block


# ---------- cite_style consistency in user block tail ----------


def test_user_block_tail_matches_cite_style_numeric(populated_db):
    """Regression guard: the closing instruction in the user block must
    agree with the system prompt's citation rule. Numeric mode must NOT
    tell the model to 'Use locators exactly as shown in parentheses' —
    that was a real bug producing contradictory signals."""
    backend = StubBackend()
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=1,
        lang="eng",
        cite_style="numeric",
    )
    user_block = backend.last_user_block()
    # The numeric instruction is present...
    assert "[N]" in user_block or "bracketed index" in user_block.lower()
    # ...and the locator-style instruction is absent.
    assert "locators exactly as" not in user_block.lower()


def test_user_block_tail_matches_cite_style_locator(populated_db):
    backend = StubBackend()
    agent.answer(
        conn=populated_db,
        query="divided line",
        backend=backend,
        top_k=1,
        lang="eng",
        cite_style="locator",
    )
    user_block = backend.last_user_block()
    assert "locators exactly as" in user_block.lower()


# ---------- shared build_retrieval_query ----------


def test_build_retrieval_query_uses_last_two_user_turns():
    out = agent.build_retrieval_query(
        "now",
        ["first", "second", "third"],  # three prior queries; only last 2 used
    )
    assert out == "second third now"


def test_build_retrieval_query_with_empty_history():
    assert agent.build_retrieval_query("hello", []) == "hello"


def test_build_retrieval_query_with_single_prior():
    assert agent.build_retrieval_query("now", ["first"]) == "first now"


# ---------- detect_corpus ----------


def test_detect_corpus_finds_single_author_by_name():
    assert agent.detect_corpus("What does Hegel say about the state?") == "hegel"
    assert agent.detect_corpus("Aristotle on virtue") == "aristotle"
    assert agent.detect_corpus("Kant's categorical imperative") == "kant"
    assert agent.detect_corpus("Plato on the forms") == "plato"
    assert agent.detect_corpus("Nietzsche on ressentiment") == "nietzsche"
    assert agent.detect_corpus("Marx on alienation") == "marx"
    assert agent.detect_corpus("Cicero on the republic") == "cicero"


def test_detect_corpus_case_insensitive():
    assert agent.detect_corpus("HEGEL on freedom") == "hegel"
    assert agent.detect_corpus("aristotle and the mean") == "aristotle"


def test_detect_corpus_matches_adjective_forms():
    assert agent.detect_corpus("the Kantian view") == "kant"
    assert agent.detect_corpus("Aristotelian ethics") == "aristotle"
    assert agent.detect_corpus("Hegelian dialectic") == "hegel"
    assert agent.detect_corpus("the Platonic forms") == "plato"


def test_detect_corpus_returns_none_for_multi_author_query():
    """Comparative questions touch two corpora; routing to one would
    silently drop half the question."""

    assert agent.detect_corpus("Compare Plato and Aristotle on virtue") is None
    assert agent.detect_corpus("Hegel vs. Kant on freedom") is None


def test_detect_corpus_returns_none_for_corpus_free_query():
    assert agent.detect_corpus("What is justice?") is None
    assert agent.detect_corpus("") is None


def test_detect_corpus_does_not_match_substring():
    """Word-boundary match — `aristocracy` must not route to Aristotle."""

    assert agent.detect_corpus("the rule of aristocracy") is None
    assert agent.detect_corpus("Cantor's diagonal") is None  # not "Kant"


# ---------- reply language inference ----------


def test_infer_reply_language_french():
    assert agent.infer_reply_language("Qu'est-ce que la justice pour Platon?") == "fra"
    assert agent.infer_reply_language("le bien et le mal") == "fra"


def test_infer_reply_language_german():
    assert agent.infer_reply_language("Was ist Sittlichkeit bei Hegel?") == "deu"
    assert agent.infer_reply_language("über die Moralität") == "deu"


def test_infer_reply_language_english_ascii():
    assert agent.infer_reply_language("What is justice?") == "eng"


def test_infer_reply_language_greek_script():
    assert agent.infer_reply_language("τί ἐστι δικαιοσύνη;") == "grc"


def test_resolve_reply_lang_explicit_override():
    assert agent.resolve_reply_lang("bonjour", reply_lang="deu") == "deu"


def test_abstain_message_french():
    msg = agent._abstain_message("justice pour tous", reply_lang="fra")
    assert "corpus indexé" in msg
    assert "could not find" not in msg.lower()


def test_abstain_message_defaults_to_english():
    msg = agent._abstain_message("zxqv nonsense query")
    assert "could not find enough evidence" in msg.lower()


def test_compose_messages_preserves_greek_passage_text(populated_db):
    backend = StubBackend()
    greek = "ἡ ψυχὴ ἀθάνατος"
    pin = make_hit(chunk_id="grc-pin", text=greek, lang="grc")
    agent.answer(
        conn=populated_db,
        query="Qu'est-ce que l'âme?",
        backend=backend,
        top_k=2,
        lang="any",
        pinned=[pin],
        reply_lang="fra",
    )
    block = backend.last_user_block()
    assert greek in block
    assert "language of <QUESTION>" in backend.last_system()
