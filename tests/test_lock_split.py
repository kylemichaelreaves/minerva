"""Verifies that LLM calls in `_handle_chat` and `_handle_translate`
run with the per-resource locks released. Concrete regression guard
for the audit finding that a single global lock serialized every
DB operation across the lifetime of any network round-trip."""

from __future__ import annotations

from conftest import make_deps

from minerva import llm, server


class _LockProbingBackend(llm.LLMBackend):
    """Captures which locks (corpus / conv / trans) are held while
    `complete()` runs. The expectation is *none* of them — that's the
    whole point of the lock split.
    """

    def __init__(self, deps_holder: list, reply: str = "ok") -> None:
        self.name = "stub"
        self.reply = reply
        # `deps_holder` is a single-element list we'll mutate later with
        # the real `ServerDeps` so the backend can introspect the locks
        # at call time. Using a list because `complete()` runs after
        # `make_deps` is called and we don't want a chicken-and-egg
        # constructor argument problem.
        self._deps_holder = deps_holder
        self.held_during_complete: dict[str, bool] = {}

    def complete(self, messages, *, temperature: float = 0.2) -> str:
        deps = self._deps_holder[0]
        # `Lock.locked()` reports the current owner; if we ARE the
        # holder this would be True. To prove we're not holding,
        # acquire(blocking=False): success means nobody had it.
        self.held_during_complete = {
            "corpus_lock": not deps.corpus_lock.acquire(blocking=False),
            "conv_lock": not deps.conv_lock.acquire(blocking=False),
            "trans_lock": not deps.trans_lock.acquire(blocking=False),
        }
        # Release whatever we managed to grab.
        for name in ("corpus_lock", "conv_lock", "trans_lock"):
            if not self.held_during_complete[name]:
                getattr(deps, name).release()
        return self.reply


def test_chat_llm_call_holds_no_lock(populated_db):
    holder: list = [None]
    backend = _LockProbingBackend(holder, reply="ok [1].")
    deps = make_deps(populated_db, backend)
    holder[0] = deps
    server._handle_chat(deps, {"query": "divided line"})
    # None of the per-resource locks should be held while the LLM call
    # is in flight. (The audit's concern: holding the lock across the
    # network round-trip blocks every sibling request.)
    assert backend.held_during_complete == {
        "corpus_lock": False,
        "conv_lock": False,
        "trans_lock": False,
    }


def test_translate_llm_call_holds_no_lock(populated_db, translations_conn):
    holder: list = [None]
    backend = _LockProbingBackend(holder, reply="Sing, goddess")
    deps = make_deps(populated_db, backend, translations_conn=translations_conn)
    holder[0] = deps
    server._handle_translate(
        deps,
        {
            "source_text": "Μῆνιν ἄειδε θεὰ",
            "target_lang": "eng",
        },
    )
    assert backend.held_during_complete == {
        "corpus_lock": False,
        "conv_lock": False,
        "trans_lock": False,
    }


def test_translate_doesnt_touch_corpus_or_conv_locks(populated_db, translations_conn):
    """`_handle_translate` should only ever hold `trans_lock`. The
    audit's concern was that a slow translate would block sibling
    chat/conversation operations because all three resources shared
    one lock. With per-resource locks, holding `corpus_lock` from this
    test thread must NOT prevent the handler from running.
    """

    holder: list = [None]
    backend = _LockProbingBackend(holder, reply="Sing, goddess")
    deps = make_deps(populated_db, backend, translations_conn=translations_conn)
    holder[0] = deps

    # Synchronously hold corpus_lock and conv_lock. Translate should
    # still complete because it only needs trans_lock — and even that,
    # only briefly around the cache lookup / insert (not during the
    # LLM call itself).
    with deps.corpus_lock, deps.conv_lock:
        body = server._handle_translate(
            deps,
            {
                "source_text": "Μῆνιν ἄειδε θεὰ",
                "target_lang": "eng",
            },
        )
    assert body["translated_text"] == "Sing, goddess"
    # The probe sees `corpus_lock` and `conv_lock` as held — by the
    # test scope above. What matters is that `trans_lock` was free
    # while the LLM call was in flight (the handler released it
    # between the cache lookup and the network round-trip).
    assert backend.held_during_complete["trans_lock"] is False
