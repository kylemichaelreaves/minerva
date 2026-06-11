# Code-quality audit — 2026-06-10

Branch: `chore/code-quality-audit`. Scope: all of `src/minerva/` (227 Python files) and `web/src/` (194 TypeScript/SolidJS files), plus CLI, Makefile, tests, and repo hygiene. Five parallel review passes; every finding below was verified by reading the code (several by live repro).

Severity: **high** = real bug / data loss / security; **medium** = likely bug or significant maintainability cost; **low** = readability/hygiene.

> **Status (2026-06-11):** all high-severity findings were fixed in round 1
> (PR #9); the medium/low findings were fixed in round 2
> (`fix/audit-round-2`), with one deliberate deferral:
>
> * **Neighbor/window scoping standardization** (medium, "Inconsistent
>   neighbor/window scoping") — `fetch_chunk_context` scopes by
>   `(work, lang)` while `neighbor_ids` scopes by edition/translation id;
>   `reader.work_range` resolves works by title; `insert_chunks` keys
>   `ord` on `(work, lang)` without author. Standardizing on
>   `work_id` + edition scoping changes data semantics for same-language
>   multi-edition works and deserves its own focused change (likely with
>   a migration), not a slot in a batch round. Revisit before adding a
>   second same-language edition of any work.

---

## High-severity bugs

### Data pipeline

1. **`find_works` multi-work discovery is broken — 11 of 12 English Kant works were never ingested.**
   `src/minerva/corpus/pipeline.py:126-138` looks up the plural `find_works` via `find_work.__module__`, but every `find_work` built by `make_find_work` (`src/minerva/corpus_works.py:87`) is a closure whose `__module__` is `minerva.corpus_works`, which has no `find_works`. Verified live: `kant_works.find_works("practical_philosophy_gregor.pdf")` returns 12 works, yet `data/chunks.jsonl` contains chunks for exactly one of them ("Review of Schulz's…", 5 chunks). Groundwork, KpV, Metaphysics of Morals etc. are missing from the corpus. The existing test (`tests/test_corpus_parse.py:647`) covers `find_works` itself, not the discovery path.
   *Fix:* have `ingest/registry.py:_corpus_label` (line 64) pass `getattr(works, "find_works", None)` into `parse_dir` explicitly instead of `__module__` sniffing. Then re-ingest Kant.

2. **`specs/hegel.yaml` silently shadows the 31-rule `hegel.py` module — Hegel refs build runs with 4 rules.**
   `src/minerva/refs/rules/__init__.py:240-252` prefers a YAML spec when one exists; `specs/hegel.yaml` is a self-described proof-of-concept with only Plato + Aristotle mentions. Verified: `_rules_for_author("Hegel")` returns 4 rules while `hegel.py` defines 31. All Hegel→Kant/Spinoza/Descartes/etc. candidates are silently lost on rescan, and the YAML loader can't express `source_method`/`ignore_case`/strong rules.
   *Fix:* delete the PoC YAML (or make YAML-plus-module an error), then rescan Hegel.

3. **`validate_keywords()` is a no-op.** `src/minerva/corpus_registry.py:542-552` iterates `AUTHOR_KEYWORDS.items()`, but `build_author_keywords()` already collapsed duplicates by dict overwrite, so the collision check can never fire (verified with a synthetic collision). Validation must iterate `CORPORA` entries.

### Server

4. **SSE chat stream writes a second HTTP response into an in-flight stream when validation fails.**
   `src/minerva/http/serve.py:174-175` + `src/minerva/http/handlers/chat.py:66-88`. `_handle_chat_stream` is a generator, so `prepare_chat_turn` (which raises for missing query, bad `conversation_id`, >50 pinned ids) doesn't run until the first `next()` — after `_send_sse` already wrote `200 OK` + SSE headers. The exception escapes into `do_POST`'s handler, which calls `_send_error_json` → a second status line is written into the body of the SSE response.
   *Fix:* run `prepare_chat_turn` eagerly before sending SSE headers, or catch `MinervaError` pre-first-yield and emit an `error` SSE event.

5. **Translate request-coalescing can steal the leader slot and busy-wait.**
   `src/minerva/http/handlers/translate.py:79-97,137-138` + `src/minerva/translate/coalesce.py`. A follower whose second wait misses the cache falls through to the LLM call without being the registered leader; its `finally: finish_inflight(cache_key)` pops the real leader's Event, releasing followers prematurely and permitting duplicate LLM calls. Separately, `_wait_for_leader` holds the old already-set Event after a leader change, so the loop hot-spins (DB lookup per iteration) for up to 240 s.
   *Fix:* track leadership explicitly (only the request whose `begin_inflight` returned `None` may call `finish_inflight`); re-fetch the fresh Event when re-following.

6. **A single LLM refusal permanently poisons the translation cache.**
   `src/minerva/http/handlers/translate.py:106-121` caches `translated_text=""` on `looks_like_refusal`, and `translations.lookup` (`src/minerva/translations.py:78-79`) treats empty string as a valid hit — every future request returns `cached: true` with an empty translation, no TTL/retry path short of `delete_all`.

### CLI / ops

7. **`minerva index` (no `--reset`) crashes on a DB with lemmas/embeddings but zero `cross_references`.**
   `src/minerva/cli/index_cmd.py:205` — the restore guard checks only `COUNT(*) FROM cross_references`; when 0 but the snapshot has lemmas, the restore runs against a live populated DB. Repro'd: second non-reset run dies with `database snap is locked`. The production DB is shielded only because it happens to have 21k xrefs. No test covers the non-reset-with-lemmas path.
   *Fix:* also check `chunk_lemmas`/`embeddings` counts, or restore only on reset/incremental-wipe paths.

8. **`refs build --strategy llm-verify --llm-base-url` bypasses the credential-leak guard.**
   `src/minerva/cli/refs/build.py:265` calls `llm.make_backend(...)` directly; `_shared.validate_base_url` (which ask/chat/serve all route through) is never applied — the API key can be sent to an arbitrary host, the exact attack the docstring warns about.

### Frontend (SolidJS)

9. **Selection-toolbar keydown listeners leak with stale closures.**
   `web/src/Reader/useSelectionToolbar.tsx:254-276` returns a cleanup function from `createEffect` — React idiom; Solid never calls it. Every toolbar open adds another permanent `keydown` listener, each capturing its own stale toolbar state, so a later `t`/`T` press fires `commitTranslate` once per past selection (duplicate translate requests, resurrected highlights).
   *Fix:* `onCleanup(() => document.removeEventListener("keydown", onKey))` inside the effect.

10. **`AppRoutes.tsx` `ctx` object freezes reactive props — topbar scrolled-state and the sidebar-reopen button are permanently dead.**
    `web/src/AppRoutes.tsx:55-71` builds `ctx` once with `scrolled: props.scrolled` / `sidebarCollapsed: props.sidebarCollapsed` (read once, `false` forever). So `Topbar` never gets its scrolled class, and the "Show sidebar" button never appears after collapsing the sidebar. `routes/ReaderRoute.tsx:5-26` contains a comment documenting this exact pitfall.
    *Fix:* make them accessors (`scrolled: () => props.scrolled`).

11. **Back-button trap in `routing.ts`.**
    `web/src/routing.ts:349-354` — effect-driven `pushState`: on first load `location.hash` (`""`) ≠ canonical `"#/"`, so an extra entry is pushed; pressing Back re-triggers the effect, which pushes again — the user cannot leave the app via Back. The string-identity guard also re-pushes on equivalent-but-non-canonical hashes (`%20` vs `+`, param order, Firefox's decoded `location.hash` — every Greek-lemma URL fails comparison on popstate).
    *Fix:* never write history from the effect; `pushState` only inside `navigate()`, `replaceState` for canonicalization.

12. **Unguarded `decodeURIComponent` crashes the app on a malformed URL.**
    `web/src/routing.ts:131-200` — `#/c/100%` or `#/r/%zz` throws `URIError` inside `readRoute()` at init (blank screen) and in the popstate handler.

### Hygiene

13. **`web/coverage/` is committed — 68 tracked generated files churning on every test run** (it's most of the noise in the current `git status`). `web/.gitignore` says `coverage` but gitignore doesn't untrack committed files.
    *Fix:* `git rm -r --cached web/coverage` + add `web/coverage/` and root `coverage.xml` to `.gitignore`.

---

## Medium severity

### Backend performance & correctness

- **Filtered vector search does a full `chunks_full` scan in Python per request, under `corpus_lock`** — `src/minerva/retrieve.py:252-285` (~300k rows through view joins per chat request). Push filters into SQL or memoize metadata alongside the embedding cache.
- **`_reserved_term_ids` runs one corpus-wide FTS MATCH per ≥4-char query token, serially, under the lock** — `src/minerva/retrieve.py:205-215`.
- **Inconsistent neighbor/window scoping** — `store/chunks.py:512-553` scopes context by `(work, lang)` while `neighbor_ids` scopes by edition/translation id; `reader/queries.py:105-153` resolves works by title string; `insert_chunks` keys `ord` on `(work, lang)` without author. Two same-language editions, or two authors sharing a title, interleave/bleed. Standardize on `work_id` + edition scoping.
- **`prepare_chat_turn` is a ~200-line god function** — `src/minerva/chat_service.py:159-357`; cache logic nested five deep. Extract payload parsing and concept-expansion.
- **`aggregate.build` claims transactional rebuild but commits piecemeal** — `src/minerva/concordance/aggregate.py:36-41` vs `_bulk_insert`'s per-scope `conn.commit()` (line 210); a crash leaves a half-built `lemma_counts` served as truth.
- **`looks_like_betacode` false-positives on ordinary punctuation** — `src/minerva/transliterate.py:133-144` triggers on any of `*()/\=|+`; already-Unicode Greek chunks containing `(` or `/` get all ASCII letters converted to Greek at display time (`reader/queries.py:187`); same guard at ingest (`tei.py:256`). Require a real beta-code letter+diacritic sequence or check for precomposed Greek codepoints.
- **`_chunk_rows` blows SQLite's 999-variable cap on works >999 chunks** — `src/minerva/glossary_import.py:481-496` (Psalms ≈ 2,500 chunks). Batch ids.
- **Per-file/per-source failures only `print()` and continue** — `src/minerva/corpus/pipeline.py:155-157`, `ingest/parallel.py:186-191,205-211`: a failed source is silently excluded and a full parallel ingest overwrites `chunks.jsonl` without that corpus. Return failure counts; non-zero exit.
- **`dominant_code` collisions, no validation** — `corpus_registry.py`: hume/cicero `'I'`, hobbes/boulainvilliers `'B'`, rousseau/renan `'R'`, aquinas/theognis `'T'` (comment at line 398 wrongly claims T unused), septuagint/gobineau `'G'`. The glyph renders in the UI margin; collisions make it ambiguous.
- **`index --reset` silently destroys embeddings on an embeddings-only DB** — `cli/index_cmd.py:139` snapshots only when xrefs or lemmas are non-empty, but the restore path explicitly promises embeddings survive.
- **`minerva embed --lang` choices are `(eng, grc, any)` defaulting to `eng`** — `cli/embed_cmd.py:144-149` — can't target deu/lat/fra/heb; repeats the documented "silent English-only" bug class. Drive from `RETRIEVAL_LANG_CHOICES`, default `any`.
- **`make reingest`/`reindex`/`reingest-only` skip the mandatory snapshot convention** — `Makefile:174-199`; `chunks.jsonl` is overwritten before any snapshot exists. Prefix targets with `scripts/snapshot-db.sh`.
- **`LANG := any` is exported into every recipe's environment** — `Makefile:24`; subprocesses run with invalid locale `LANG=any`. Rename to `MINERVA_LANG` or `unexport LANG`.
- **~55-line retry loop duplicated byte-for-byte** between `AnthropicBackend.complete` and `stream_complete` — `src/minerva/llm.py:314-354` vs `385-421`. Extract `_urlopen_with_retry`.

### Frontend

- **Three `ResizeObserver`s never disconnected, copy-pasted verbatim** — `Network/components/ArcPanel.tsx:87-99`, `HeatmapPanel.tsx:12-22`, `MatrixPanel.tsx:14-24`. Extract a `useElementSize` hook with `onCleanup`.
- **Streaming turn does full DOM teardown per SSE delta** — `web/src/Thread/index.tsx:36-46`: ternary on `msg().role` inside the `Index` row recreates `MinervaTurnView` on every delta and wipes citation-expand state on finalize. Use `<Show>` with lazy props.
- **Refs review pagination skips pending rows** — `Refs/components/Review.tsx:122-150` + `hooks/usePaginatedAppend.tsx:55`: offset is computed against a queue the curator is shrinking; page 2 skips as many rows as were decided on page 1, and `meta.offset` is never advanced.
- **Concordance filter bar refetches per keystroke / per pixel of slider drag** — `Concordance/components/FilterBar.tsx:144-172,247-258`. Debounce text; commit slider on release.
- **Global keydown handler hijacks Arrow/Enter/Escape app-wide while LemmaDetail is mounted** — `Concordance/components/LemmaDetail.tsx:389-427`; guards only input/textarea, and duplicates the queue-nav that `Refs/components/Review.tsx:198-216` implements separately. Extract a shared `useListKeyboardNav`.
- **Three different async-fetch idioms** for the same load/error/retry problem: `useAbortableFetch` (Refs/Network), raw `createResource` + `_retry` hack (Concordance), hand-rolled AbortController (Reader hooks, MinervaTurnView). Converge on the `Refs/` pattern where pagination doesn't demand custom code.
- **`FilterBar`/`FilterRail` mounted twice per page with 10–15 duplicated props** — `Concordance/components/IndexPage.tsx:177-191` vs `:239-252`; `LemmaDetail.tsx:192-221` vs `:274-300`. Use the `const filterRail = () => <FilterRail …/>` closure pattern `Refs/index.tsx:113` already uses.
- **`api/client.ts` errors lose the status code** — `client.ts:21`; `conversationsCtrl.ts:144-150` then treats any failure (500, network blip) as "conversation no longer available" and navigates the user away. Add a typed `ApiError { status }`.
- **SSE `meta`/`done` payloads double-cast with zero validation** — `api/chatApi.ts:208,214`; a malformed `done` event crashes the stream handler instead of reaching `onError`. Also the non-streaming `chat()` (`chatApi.ts:82-134`) is dead production code that has already drifted from the streaming path.
- **`Reader/components/Rail.tsx:70-78`** — `activeTab` memo is a no-op and the documented "auto-flip to Lemma tab on word lookup" is unimplemented; the comment lies.
- **`tsconfig`: `noUncheckedIndexedAccess` off** — the codebase pays with 11+ `eslint-disable no-unnecessary-condition` comments that the flag would delete.
- **Scripture-cite rules quadruplicated** — `refs/rules/scripture_cite/{de,en,fr,lat}.py` are ~180-line near-verbatim copies differing only in lexicon/regex/target (plus a dead `_key` field cargo-culted into each). One parametrized `ScriptureCiteRule` removes ~500 lines and a 4× drift surface.
- **`_roman_to_int` triplicated with divergent semantics** — `sources/hobbes_la.py:102`, `sources/marx_de.py:172`, `sources/ica_parse.py:66` (the last returns wrong values for garbage instead of `None`).

---

## Low severity (selected)

- `conn.row_factory` mutated as a side effect at ~25 call sites across `store/`, `reader/`, `refs/`, `concordance/`, `glossary_import.py` — set once at `open_db`.
- `OpenAIBackend.stream_complete` crashes on a chunk with empty `choices` — `llm.py:192`; guard with `(chunk.get("choices") or [{}])[0]`.
- Embedding cache keyed on `id(conn)` + row-count freshness — `store/embeddings.py:150-184`; id reuse / same-count re-embed serves stale vectors. Use a generation counter in `meta`.
- `_RateLimiter` buckets never pruned — `http/server_core.py:45-66`; unbounded on a public bind.
- Apostrophe-final and longer alternates in refs `forms` are unreachable — `refs/rules/__init__.py:134-140` (`\b` after `'` can't match; shorter forms shadow longer). Affects most rule modules' span coverage.
- `_PATTERN_CACHE` keyed only on rule name — `refs/rules/__init__.py:166-179`; two rules sharing a name silently share a pattern.
- Dead filter-building code in `lemma_index` — `concordance/index_queries.py:124-139`; WHERE-builder also duplicated between main and totals queries (196-224 vs 332-352).
- `retrieve.search` queries `neighbor_ids` twice per hit (`retrieve.py:372-390`); `expanded_passage` is dead code (`retrieve.py:406-418`).
- SQL interpolation in `ATTACH` — `cli/index_cmd.py:251`; breaks on paths containing `'`.
- `refs load-spec --dry-run` reports `inserted=0` always and `ensure_target` still writes rows in dry-run — `cli/refs/load_spec_cmd.py:151-152`.
- Stale docstrings: `cli/refs/build.py:19` ("llm-verify … not yet wired" — it is), `cli/refs/__init__.py:12,182`; `translations.insert` docstring wrong about return value (`translations.py:98-102`).
- `ingest/__init__.py:21-62` legacy `DEFAULT_*` shim already omits the 8 newest sources — deprecate or derive mechanically.
- Test temp-file leak — `tests/conftest.py:193,201`: `NamedTemporaryFile(delete=False)` per `make_deps()` call, never removed.
- `web/src/routing.ts:156-161` multi-select params serialize as unescaped CSV — commas in values corrupt round-trips.
- `chatApi.ts:25` `KNOWN_DOMINANT` magic set hand-synced with backend (suspicious lowercase `"c"`); unknown authors render as Plato.
- `parseSseBuffer` splits only on `"\n\n"` — a CRLF-emitting proxy buffers forever (`chatApi.ts:141`).
- `Landing/index.tsx:129-136` dead `<Show when={false}>` block; `ArcPanel.tsx:515-517` orphaned section banner; `Select.tsx:83,403` dead `panelRef`.
- `data.ts` is a 44-line vestige (one-key `ACCENTS` record, dead `AccentKey` abstraction) — fold into `theme.ts`/`Landing/`.
- `AppRoutes.tsx:74-91` four-level `<Show fallback>` pyramid — use `<Switch>/<Match>`.
- Three query-string idioms across api modules — one shared `qs()` in `client.ts` deletes ~60 lines; `apiGet`'s jsdom guard missing from `apiPost`/`apiPatch`.
- Makefile `.PHONY` gaps (`coverage`, `check-api-types`, `ingest-only`, `reingest-only`); untracked `scripts/clean-hegel-lectures-glossary.py`.
- `db_cmd.py:27` unreachable branch with inconsistent exit style; duplicate `add_common_db_arg` (`cli/_shared.py:78` vs `cli/terms/_io.py:76`).
- Concordance `_DEFAULT_CONTENT_POS` omits ADV while the `lemma_index` docstring promises it (`concordance/_scope.py:20` vs `index_queries.py:38`).
- `corpus_registry.CORPORA` codegen sentinel block duplicated (lines 22-32); adding an author touches 3–4 registries with nothing cross-validating them.

---

## Cross-cutting themes

1. **Registry sync burden.** Adding an author touches `corpus_registry.CORPORA`, `ingest/registry`, `authors/<x>_works.py`, refs rules, and `dominant_code` — and the two validators that exist (`validate_keywords`, dominant-code uniqueness) are respectively broken and absent. A startup cross-validation pass would catch findings #1–#3 class bugs structurally.
2. **Copy-paste growth in per-author/per-lang modules.** scripture_cite ×4, `_roman_to_int` ×3, `parse_dir` walkers ×7, ResizeObserver ×3, retry loop ×2, WHERE-builder ×2, filter UI ×2. Each is a drift surface; several have already drifted.
3. **Solid reactivity footguns recur** in exactly the shapes the repo has already documented elsewhere (captured props/`i()` in row bodies, React-style effect cleanup, plain ternaries where `<Show>` belongs). Worth an ESLint rule audit (`eslint-plugin-solid` catches some of these) and a short CONTRIBUTING note.
4. **Silent failure as a policy.** Pipeline per-file excepts, parallel-ingest source drops, refusal-cached translations, YAML-shadowed rules — all fail by shrinking output rather than erroring. Prefer loud failure + counts in anything that feeds the corpus.
5. **Connection-state side effects.** `row_factory` mutation everywhere; embedding cache keyed on `id(conn)`.

## Verified-clean areas (worth knowing)

- No SQL injection found anywhere (parameterized throughout; the f-string SQL sites interpolate internal constants only).
- `refs/schema.py` is a clean single write path; `textnorm.py` is a good shared-core example.
- Test suite quality is strong: registry-driven CLI arg tests, synthetic fixtures, no assert-nothing tests.
- Frontend infra better than expected: shared `api/client.ts`, abort-signal plumbing complete with correct stale-response guards, guarded localStorage parsing, `Select.tsx` is a competent WAI-ARIA combobox (its 456 lines are justified), strict tsconfig + typed ESLint with individually justified relaxations.
- OCR parsers (presocratic, hobbes_la, marx_de) are unusually well-documented.

## Suggested fix order

1. Corpus-data integrity (re-ingest required after): find_works discovery (#1), hegel.yaml shadow (#2), betacode false-positive (medium).
2. Security/ops: llm-verify base-url guard (#8), index restore guard (#7), snapshot-in-Makefile, embed `--lang any` default.
3. User-facing server bugs: SSE double-response (#4), translate coalescing (#5), refusal cache poisoning (#6).
4. User-facing frontend bugs: keydown leak (#9), frozen ctx props (#10), back-button trap (#11), decodeURIComponent guard (#12), review pagination, streaming-turn teardown.
5. Hygiene: `git rm -r --cached web/coverage`.
6. Consolidation passes (mechanical, low-risk): scripture_cite, retry loop, ResizeObserver hook, fetch-idiom convergence, row_factory.
