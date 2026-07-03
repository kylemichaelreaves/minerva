# Code audit — 2026-07-03

Full-stack audit (frontend, backend/API, data layer/CLI, ingestion pipeline, cross-cutting seams).
Five parallel review passes; every finding below was verified against the actual code at the cited
location. Status: **Phase 2 largely complete** on `remediation/phase-2-critical-ux` (commits
`3cbfd1a`, `a84ba82`). Fix-first shortlist items 1, 6, 8 done; items 2–5 & 7 done in phase 1
(`43f62df`). Frontend §2 high/medium/low items addressed except dead-code cleanup.

Severity legend: 🔴 critical · 🟠 high · 🟡 medium · ⚪ low

---

## 1. Fix-first shortlist

The eight items most worth fixing before anything else, across all layers:

1. 🔴 **Reader infinite scroll is dead.** `web/src/Reader/index.tsx:96-119` — the effect's only
   reactive read (`hasMore()`) sits after an early `return` that always fires on first run (the
   sentinel is inside `<Show when={range()}>` and doesn't exist yet), so the effect ends with zero
   tracked dependencies and never re-runs; the IntersectionObserver is never attached. Any work
   longer than the first 80-chunk page cannot be scrolled past page 1. Fix: use the existing
   `hooks/useInfiniteScrollSentinel` (add a `root` option) or read the signals before the guards.

2. 🔴 **`.sql` migrations are not transactional despite the runner's docstring.**
   `src/minerva/migrations/__init__.py:22-24,79-80` — `conn.executescript` autocommits per
   statement. A mid-script failure (e.g. `0008`'s two consecutive `ALTER TABLE ADD COLUMN`) leaves
   the first statement committed with the version unrecorded → re-apply → "duplicate column" →
   permanently wedged DB. Same trap inside `.py` migrations 0003/0009/0013/0016, where interleaved
   `executescript` calls commit pending DML mid-migration (`0013:107,114`). The repo already knows
   this (0021/0022 explicitly avoid `executescript`) but the runner still relies on the false
   guarantee. Fix: no `executescript` in migrations; runner wraps `.sql` files in explicit
   BEGIN/COMMIT via split `execute` calls.

3. 🔴 **Both DB snapshot mechanisms are WAL-blind on a WAL-mode DB.** `scripts/snapshot-db.sh:64-70`
   and `src/minerva/cli/index_cmd.py:143-144` copy `index.sqlite` alone; unchekpointed WAL frames
   (the newest commits — including LLM-verified xrefs, the exact asset snapshots exist to protect)
   are silently absent, and a copy concurrent with a checkpoint can be torn. Fix: `sqlite3 "$db"
   ".backup"` in the script, `Connection.backup()` / `VACUUM INTO` in Python. (Related: `reset_db`
   and `--reset` unlink only the main file, leaving stale `-wal`/`-shm` behind — a documented
   SQLite corruption vector. `store/schema.py:112-114`, `index_cmd.py:67-68`.)

4. 🔴 **`chunks.jsonl` is overwritten non-atomically while consuming lazy parser iterators.**
   `src/minerva/ingest/__init__.py:47` (`write_jsonl`) and `ingest/parallel.py:248`
   (`concat_shards`) open the canonical file with `"w"` directly; any mid-ingest exception, Ctrl-C,
   or disk-full truncates it, and the next `index --reset` mass-deletes chunks.
   `_merge_dicts_to_jsonl` (`:120-135`) already does temp-file + rename — mirror it.

5. 🟠 **A full ingest silently skips any source whose raw path is missing.**
   `src/minerva/ingest/registry.py:546-548` + `parallel.py:77-84` — no stderr, not in failures,
   exit 0; `chunks.jsonl` is rewritten without that corpus and the next reset wipes it from the DB.
   This is the English-Hobbes silent-wipe class with zero detection. Fix: loud per-source SKIPPED
   line and non-zero exit (or opt-out flag). Related: full parallel ingest concats shards into
   `chunks.jsonl` *before* the failure check (`cli/ingest_cmd.py:232-235`), so a failed source's
   corpus is already dropped from the file by the time it exits 1.

6. 🟠 **Reader work identity keys on `(title, lang)`, not `work_id`.**
   `src/minerva/reader/queries.py:139-152` — 72 (title, lang) pairs in the live DB map to two
   `work_id`s (Luther 1912 vs 1545 share every book title). Verified: paging `1 Corinthians`/deu
   past ordinal 437 silently walks into the other translation; `around=` mode returns the wrong
   work's metadata. Same class in `store/chunks.py:544-569` (`fetch_chunk_context` scopes neighbors
   by `(work, lang)`, unlike `neighbor_ids` which correctly uses edition/translation id). Fix:
   resolve and filter by `works.id` in the meta, range, and context queries.

7. 🟠 **The pre-index restore error path masks the real exception and re-triggers the
   PRAGMA-in-transaction trap.** `src/minerva/cli/index_cmd.py:258-338` — a failure in the
   ATTACH-restore DML (realistic: positional `INSERT ... SELECT *` at :275/:287/:302 breaks on any
   schema drift between snapshot and live) reaches a `finally` that runs `DETACH` inside the open
   transaction (raises, hiding the original error), never rolls back, then runs `PRAGMA
   foreign_keys` as a documented no-op inside the still-open transaction. Fix: rollback-and-reraise
   before DETACH; explicit column lists in the restore INSERTs.

8. 🟠 **`refs verify --strategy llm-verify --resume` permanently skips errored batches.**
   `src/minerva/refs/llm_verify.py:483-503,583` — an errored batch `continue`s without
   checkpointing, but a later success writes `_write_checkpoint(batch[-1].id)`, advancing past the
   failed rows; resume (`xr.id > resume_from_id`) never revisits them. Silent under-verification.
   Fix: never advance the checkpoint past the lowest unprocessed row id.

---

## 2. Frontend (web/src)

### High
- 🟠 `hooks/usePaginatedAppend.tsx:29-38,61-65` — generation bump on filter change never resets
  `appending`; a filter change mid-flight leaves `appending()` stuck true and `loadMore`
  early-returns forever (Refs list + Review queue pagination dead until remount). The existing test
  covers the path but never asserts `appending()`. Fix: reset in `finally` unconditionally.
- 🟠 `Reader/useTermCard.tsx:73-81` — URL-resume effect tracks both `props.openTermId()` and
  `openCard()`; Esc/outside-click on a click-opened card re-opens it at the sentinel anchor before
  the URL clears. Fix: `untrack` the `openCard()` read.
- 🟠 `hooks/usePopoverPosition.tsx:8-10` — position computed once at setup; clicking a second
  marked word while a card is open renders new content anchored at the old word (Reader mounts
  cards in non-keyed `<Show>`, `Reader/index.tsx:328-346`). Fix: effect over `anchor()` or key the
  Show.

### Medium
- 🟡 `api/chatApi.ts:213-217` — a stream that ends after `meta` but without `done`/`error` returns
  silently; the placeholder turn stays `streaming: true` forever (stuck cursor, partial text
  dropped). Fix: treat meta-without-done as `onError("Stream ended early.")`.
- 🟡 `Refs/components/Review.tsx:136,205,210-268` — cursor increments unboundedly past queue end;
  `goNext`/`goPrev` not gated on `acting()` (wheel flick during in-flight PATCH silently skips a
  row past review); `actionError` banner never cleared on later success.
- 🟡 `Reader/useWordLookup.tsx:122-148` — "Show more samples" passes no AbortSignal (comment
  claiming propagation is false) and the post-await guard doesn't check same-word identity; word
  A's page can merge into word B's panel. Also lacks `onCleanup` abort (sibling
  `useTranslateRail.tsx:88` has it).
- 🟡 `Concordance/components/IndexPage.tsx:262` — language switch clears `letter` but not
  `scopeAuthors`/`scopeWorks` → permanent "No lemmas in this scope" with a stale invisible filter.
- 🟡 `Concordance/components/FilterBar.tsx:83-116` — Dropdown has no outside-click/Escape close
  despite `useClickOutside` existing.
- 🟡 `AppRoutes.tsx:40-50` — auto-scroll forces bottom on every SSE delta with no "user scrolled
  up" guard; can't re-read earlier turns while streaming.
- 🟡 A11y, systemic: `components/MobileSheet.tsx:21` and `components/PopoverCard.tsx:37-48` —
  `role="dialog"`/`aria-modal` with no focus-in, no trap, no restore. `ThemeToggle.tsx:12-13` —
  `aria-label` frozen at setup.

### Low (selected)
- ⚪ `MobileSheet.tsx:13-15` — `useEscape` registered without the `active` gate; a closed sheet
  still `preventDefault()`s every Esc on refs/network pages.
- ⚪ `Network/index.tsx:58-70` — `?source=` deep link leaves the author dropdown filtered;
  `Body.tsx:76` mobile "More views →" wired to a defaulted no-op.
- ⚪ `Concordance/components/FilterRail.tsx:241` — `"v" + (p.italic ? "" : "")` italic flag dead in
  both branches. `FilterBar.tsx:150-151` — `NaN%` slider when ceil()===1. `IndexPage.tsx:167` —
  freqCeil ratchet wrong on `sort=alpha|pos` deep links.
- ⚪ `Reader/useWordHoverTranslations.tsx:40-56` — hover-translation cache grows unboundedly for the
  Reader's lifetime.
- ⚪ `utils/popoverPosition.ts:15-19` — RTL placement branch unreachable (no caller passes
  `direction`); Hebrew/Arabic word-cards always get LTR placement.

### Dead code (grep-verified zero importers) — **removed** (`a84ba82` follow-up)
Whole files removed: `utils/citations.ts` (+ test), drifted `api/types/concordance.ts` (fixture
now points at `concordanceApi.ts`), `api/types/terms.ts` (no frontend caller), `SortBtn.tsx`,
`src/minerva/parsers/`, `src/minerva/works/`. Smaller: `ScopePillDetail`, `CASE_LABEL`/`NUMBER_LABEL`
exports, `Refs/index` refsList re-export block, `usePopoverPosition` `flipUp` return,
`STARTER_PROMPTS` export. `retryKey` retained — used by concordance refetch.

### Duplication
`turnId` in `Thread/index.tsx:22` vs `ThreadSearchSheet.tsx:14` (must stay in sync or search-scroll
breaks); `confLabel` (Network `Header.tsx:25-28` vs `NetworkFiltersBar.tsx:61-64`); `lockedGender`
0.95 heuristic (`FilterRail.tsx:65-72` ≡ `LemmaIdentityCard.tsx:29-36`); `targetAuthors` memo
clones `useRefsSourceAuthors`; Reader's inline IntersectionObserver duplicates
`useInfiniteScrollSentinel`.

---

## 3. Backend / API

- 🟡 `concordance/index_queries.py:190,264` — merge_case pagination fetches ≤ max(limit·10, 2000)
  raw rows from offset 0, merges in Python, slices; deep pages are silently short/empty while
  `total_lemmas` advertises more. Fix: page in SQL over a materialized `lemma_fold`.
- 🟡 `http/serve.py:96-98` + `server_core.py:118` — loopback binds send `Access-Control-Allow-Origin: *`;
  any web page the operator visits can read `/api/conversations` and drive billable
  `/api/chat`/`/api/translate` from drive-by JS. Fix: allow only explicit origins even on loopback.
- 🟡 `http/serve.py:105,72` — no socket timeout on the handler; a stalled `Content-Length` body
  pins a ThreadingHTTPServer thread forever (slow-loris on non-loopback binds). Fix: `timeout = 60`.
- 🟡 `chat_service.py:54-65,173-215` — no cap on `query` length or `history` size below the global
  1 MiB body cap; each of 30 req/min can carry ~1 MiB into the LLM prompt. translate already caps
  at 8 KiB (`translate.py:71`) — mirror it.
- 🟡 `http/handlers/translate.py:93-113` — `begin_inflight` acquired at :93 but `finish_inflight`
  lives in a `finally` whose `try` starts at :113; an exception in the gap leaks the inflight entry
  permanently (every later request for that pair waits 240 s and 502s until restart).
- ⚪ `http/handlers/chat.py:150-162` + `serve.py:150-153` — client disconnect mid-SSE raises
  `GeneratorExit` (uncaught by `except Exception`) → the fully generated, billed answer *and* the
  user's message are rolled back.
- ⚪ `llm.py:236,350,375` — `AnthropicBackend.last_usage` is shared mutable state across request
  threads; concurrent calls mis-attribute usage (observability only).
- ⚪ `http/server_core.py:49-66` — rate-limiter buckets never evict drained `(route, ip)` keys;
  unbounded growth on public binds.
- ⚪ `concordance/kwic_queries.py:254-328` — `_lemma_breakdowns` fetches every occurrence row of a
  lemma into Python with no LIMIT, under `deps.corpus_lock`, stalling all corpus endpoints.
- ⚪ Duplication: `reader/queries.py:314-358` vs `kwic_queries.py:331-373` — near-duplicate KWIC
  builders with already-drifted punctuation constants (reader's lacks `»`). Integer query-param
  parsing hand-rolled at 6+ sites with inconsistent clamp-vs-400 semantics — one
  `parse_int_param(query, name, default, lo, hi)` unifies. `terms_list`/`lemma_detail` LIKE filters
  don't escape `%`/`_` (wildcard smuggling; `_counts_where` does escape); `terms_list` has no LIMIT.
- ⚪ `serve.py:161-275` — do_POST/GET/PATCH/DELETE each hand-roll dispatch with drift (only do_POST
  maps LLMError→502; three coexisting domain-error-mapping layers).

Verified clean: SQL consistently parameterized; static-file traversal guard sound; translate
leader/follower coalescing and chat lock/LLM-release choreography well designed.

---

## 4. Data layer / CLI / migrations

(Items 2, 3, 7 in the shortlist above, plus:)

- 🟡 `store/chunks.py:184-187,221-222,349-350` — incremental xref rebind/orphan-sweep is documented
  as corpus-scoped but is actually global; `deleted_chunk_ids` is captured and never used. O(all
  xrefs) per incremental index, and any pre-existing dangling row anywhere is deleted during an
  unrelated single-corpus reindex. Fix code or docstring.
- 🟡 `cli/index_cmd.py:67-69` + `serve_cmd.py:32` — `index --reset` unlinks the DB out from under a
  running server (long-lived connection keeps the deleted inode; API xref-curation writes lost on
  close). Needs at least a "stop the server" probe.
- 🟡 `store/chunks.py:121-132,252` — incremental delete-scope derives author labels from the *new*
  JSONL only; a parser author-label rename leaves stale chunks beside replacements (same dup class
  the slug/label fix addressed, one step removed).
- ⚪ `cli/ingest_cmd.py:178-181` — `meta.ingest.only` never cleared by a full ingest; a later
  `--from-ingest-only` silently scopes to a stale corpus set.
- ⚪ `cli/embed_cmd.py:64-67` — `--all --lang X` with zero chunks of that lang exits 2 with "No
  chunks present. Run `minerva index` first." in a populated DB.
- ⚪ Snapshot cost: `_maybe_snapshot_pre_index` does a full byte copy of the ~8 GB DB on *every*
  index run, including 1.5 s incremental ones.

### Choreography duplication (the root-cause pattern)
- FK save/toggle/restore boilerplate ×12 (`store/chunks.py:380,385`, `index_cmd.py:338`, 9
  migrations); table-exists probes ×7; three orphan-cleanup implementations; `chunks_full` view +
  FTS trigger DDL duplicated in 4 places (`store/schema.py:70-87`, migrations 0003/0021/0022).
  Fix: `sqlite_util.foreign_keys_disabled(conn)` context manager (asserting no open transaction —
  closes the PRAGMA-no-op trap class for good), `sqlite_util.table_exists`, one orphan-sweep
  helper, a shared DDL constants module.
- The snapshot→reset→restore→insert→rebind→sweep invariant lives in call-order comments across two
  layers; should be one context manager (`with preserved_state(db_path, tables=...)`).

### Test gaps (worst first)
1. **No end-to-end test for xref survival across `index --reset`** — the headline recovery path
   (historically lost 21,751 xrefs). Lemma/embedding preservation is tested; xrefs are not.
   `--from-ingest-only` never exercised.
2. **`store/chunks._resolve_work_refs`** — docstring cites `test_store_resolve_work_refs.py`,
   *which does not exist*. This is the edition-vs-translation classifier whose drift vs migration
   0003 corrupts on re-ingest.
3. Migrations: no legacy-shape (pre-0003) application test, no mid-migration-failure re-entrancy
   test (would have caught the executescript findings).
4. `cli/refs/review.py` (240 lines, writes curated verdicts) — zero tests.
5. `store/stats.py` / `cli/db_cmd.py` — zero test references.

---

## 5. Ingestion pipeline

(Items 4, 5, 8 in the shortlist above, plus:)

### Text-corruption bugs (live, in the DB now)
- 🟠 `sources/tei_drama.py:66-79` — `_text_of` claims to skip `<speaker>`/`<stage>` but
  `elem.iter()` still yields their descendants and drops the skipped node's tail: stage-direction
  names leak into Greek line text/lemmas/embeddings; prose after inline stage directions is lost.
- 🟡 `sources/tei_p5.py:47-51` — `_text_of` uses `itertext()` without excluding `<note>` (every
  sibling parser excludes it): critical-apparatus prose folds into Aristotle/Origen chunks.
- Root cause: **five** implementations of "text excluding `<note>`" — three byte-identical
  (`tei.py:129-141` ≡ `hebrew_mt.py:67-78` ≡ `tei_lxx.py:53-64`), one divergent (`osis_bible.py`),
  one broken (`tei_drama`). Hoist one `text_excluding(el, skip_tags)` into `tei.py`.

### Silent-failure gaps
- 🟠 `corpus/pipeline.py:88-135` vs guard at `:154-166` — the zero-chunk warning covers only
  `_SPLITTERS`-dispatched locators; all 8 direct `yield from` branches (hegel_pr ×2,
  spinoza_ethica, descartes_objections, kapital_mew, zeno_pages, ekgwb, stephanus_de) bypass it.
  Markup drift drops a whole work with exit 0.
- 🟠 `tei.py:527-529` — `tei.parse_dir` has no per-file error capture (unlike
  `corpus/pipeline.py:209-216`); one malformed XML aborts the whole sequential ingest mid-write.
- 🟠 Chunk-count validation still missing: neither `scripts/check_author_ingest.py` nor
  `scripts/corpus-quality-audit.py` validates counts against expected work size; the Theognis
  failure (2,237 junk chunks) would pass both today (`theognis` is even in SKIP_RULES). Add
  manifest-declared expected ranges.
- 🟡 Root-element `find()` misses are silent empty iterators in 4 parsers (`tei_lxx.py:145-147`,
  `tei_p5.py:193-198`, `tei_drama.py:180-182`, `tei.py:147-149`).

### Refs rules gaps
- 🟠 `refs/embed_verify.py:232-239` — work-level target matrix joins editions only; translation-only
  target works never resolve (known issue, confirmed still unfixed).
- 🟡 No `refs/rules/new_testament.py` — NT→OT citations (Matthew→Isaiah/Psalms) never auto-detected.
- 🟡 `hobbes.py` targets Descartes but `descartes.py` has no Hobbes rule (bidirectional-audit class,
  despite its own docstring citing the Third Objections exchange).
- 🟡 `scripture_cite/lexicon.py:342` — Latin bare-abbrev regex over-matches (`ex 3 modis` → Exodus 3).
- 🟡 Rule targets are free-text title literals (`aquinas.py:41-46`, `hegel.py:42-48`, `renan.py`,
  `nietzsche.py`) — a title rename on re-ingest silently orphans edges. Resolve via slugs/IDs.
- ⚪ `kant.py:113` "Berkleyan" typo never matches; `scripture_cite/de.py:176` lone "V. Mose"
  unreachable; `lexicon.py:345` "Matth. 5-7" parsed as 5:7.
- ⚪ `refs/rules/__init__.py:475-518` — scan-state marks chunks scanned even on zero matches; fixed
  rules don't retroactively apply without `--rescan-all`.

### Download/extract scripts
- 🟠 `perseus/download_first1kgreek_lxx.py:79`, `download_first1kgreek_aristotle.py:95,105`,
  `download_marcus_aurelius.py:103` — `except urllib.error.HTTPError` with **no `import
  urllib.error`**: the expected-404 path raises NameError and aborts the batch.
- 🟠 `perseus/_download.py:73` — retry helper never validates body/size/content-type; the
  mlwerke-parking-page trap generalizes to every fetch. Add a validate/min-size gate.
- 🟡 Five byte-identical zeno crawlers (hegel/kant/marx/nietzsche/schiller); four swallow
  exceptions inside BFS, silently truncating whole chapter subtrees. Extract `perseus/_zeno.py`.
- 🟡 `_gutenberg.py:52-57` — missing `Language:` header bypasses the wrong-ID guard built after the
  Pascal/Rousseau incident.
- 🟡 Absolute line offsets sliced into live archive.org OCR (`extract_descartes_principes.py:50`,
  `download_boulainvilliers.py:64`) — regenerated OCR silently shifts the cut.

### Splitter fragility/duplication
- 🟡 ~11 copies of the `_make_chunk_id + Chunk(...)` emit recipe across splitters, plus 6 BCV
  parsers hand-constructing the identical verse-chunk block. One shared emit helper + one
  `make_verse_chunk` factory. Byte-identical `_chunk` in `split_hegel_pr_de.py:86-117` ≡
  `split_hegel_pr_epub.py:94-125`.
- 🟡 `corpus_works.py:36-37` — `CorpusWork` defaults `corpus="hegel", author="Hegel"`; a forgotten
  override silently files a new author under Hegel. Also `filename_index` (:83-90) last-wins on
  duplicate filenames (the Kapital Band-II collision class) — raise instead.
- 🟡 `corpus_registry.py:538,543` — unknown corpus id silently returns `"paragraph"`/`"eng"`.
- 🟡 `split_kant.py:30-33` — A/B page-marker regex matches words like "Bild"; `split_hegel_pr_de.py:63`
  — de-hyphenation `re.sub(r"-\s+", "")` fuses "Recht - Moralität" → "RechtMoralität" (safe variant
  exists at `split_stephanus_de.py:114`); `split_spinoza_ethica.py:95-98` — broad except falls back
  to the parser the docstring says loses 65/73 propositions; `split_descartes.py:119-123` — TOC
  captured as body (first-occurrence slicing).
- 🟡 `embed.py:17,35` — HF model loaded with no `revision=` pin; an upstream update silently changes
  the embedding space under stored vectors and cosine thresholds (same for spaCy/Stanza loads).
- 🟡 `ingest/registry.py:474-493` — hand-maintained `INGEST_ID_TO_CORPUS` currently consistent
  (verified) but unenforced; add a sync test.
- 🟡 No `make post-ingest` target: embed → lemmatize → refs build → embed-verify → llm-verify
  remains tribal knowledge (the exact gap that left 9 authors / 6k xrefs unverified).

---

## 6. Cross-cutting seams

### Live drift (only two channels found — both closable)
- 🟡 `web/src/utils/dominantPhil.ts:6-46` — hand-maintained `PHIL_DOMINANT_GLYPH` is missing
  Schiller's dominant code `'l'`; renders the raw letter as a glyph. Fold into the manifest codegen
  (the one place codegen discipline wasn't applied; `citations.ts:23-27` already set the precedent
  by deleting its hand copy).
- 🟡 `.github/workflows/check.yml` claims to mirror `make check` but omits `check-api-types` (the
  TS-side contract gate), `check-author-imports`, and `check_author_ingest --all` — TS wire-type
  drift can merge green.

### Codegen script defects
- 🟡 `scripts/generate_author_artifacts.py:320-324,348-357,373-395` — dead identical-branch
  conditional; `_replace_region` passes generated code as an `re.sub` replacement string (backslash
  escape-processing → corruption); three artifact files written with no all-or-nothing; and the
  `# BEGIN CORPORA` sentinel is already duplicated in `corpus_registry.py` because
  `_comments_from_corpus_registry` scoops the module header into Plato's comment.

### Dead surface
- Five GET routes with zero frontend callers: `/api/chunks/:id/references`, `/api/terms/by_chunk/:id`,
  `/api/works/:id/term_occurrences`, `/api/translations/:id/renderings`, `/api/terms` (list)
  (`http/router.py:104,124,129,144,148`) — plus their fixtures and `api/types/terms.ts`.
- `src/minerva/parsers/` and `src/minerva/works/` — migration shims with zero importers; delete.
- `src/minerva/server.py` — 65-line re-export shim of ~50 underscore names; tests split 5/5 between
  the two import paths. Migrate tests to `minerva.http.*`, delete.
- ~12 one-off remediation scripts in `scripts/` → archive under `scripts/oneoff/`; `SCRIPTS.md`
  documents 4 of ~26 scripts.

### Docs
- `FRONTEND.md` references non-existent `web/src/lib/` six times (actual: `utils/`, `hooks/`).
- `block-structure-remediation-plan.md:3` says IN PROGRESS; tracker shows all 8 items ✅ → flip to
  DONE. Archivable: `CODE_AUDIT_2026-06-10.md`, `orthography-normalization-plan.md`,
  `aquinas_cite_survey.md`, stale `corpus-quality-audit.md` + `dashboard_aggregates.json`.
- `ARCHITECTURE.md:70` still calls `server.py` the stdlib server.
- `pyproject.toml` — `pyyaml` required at runtime by `refs/rules/loader.py` but only in
  `[lemma]`/`[dev]` extras.
- `Makefile` — `make test` is frontend-only (python is `test-py`) — naming trap.

---

## 7. What's healthy (verified, keep doing)

- SQL is consistently parameterized end to end; static-file traversal guard sound.
- The error seam is genuinely consistent: `errors.py` hierarchy → HTTP status map → `{"error"}`
  envelope → typed `ApiError` in the client.
- manifest.yaml → codegen (corpus_registry, author_ordering, atlasData) with CI-enforced sync;
  `_ORIGINAL_LANG_BY_CORPUS` now derived, structurally fixing the missing-entry argparse class.
- Frontend API client layer (shared error/qs/abort plumbing, AbortSignal on every endpoint),
  routing, and the chat send/hydrate/delete flow are solid; the shared hook layer covers most
  repeated patterns (the defects are where hand-rolled code bypassed it).
- `locations._BCV_BOOKS` clean (85 rows, no dup names/ordinals/abbrevs); registry 3-way consistent
  across manifest/corpus_registry/stamped slugs; `--only` sibling-wipe guard works as designed;
  chat/translate concurrency choreography carefully built.

## 8. Systemic themes

1. **Silence is the pipeline's failure mode.** Missing source dirs, zero-chunk parses, root-element
   misses, dropped BFS subtrees, skipped LLM batches — all exit 0. Every fix in §5 is a variant of
   "make it loud."
2. **Choreography duplicated instead of centralized.** FK toggling ×12, note-excluding extractor
   ×5, chunk-emit ×11, zeno crawler ×5, KWIC builder ×2, DDL ×4. Both live text-corruption bugs and
   the drifted punctuation constants exist because copies diverged. One consolidation pass
   eliminates roughly half the findings.
3. **The safety net has holes exactly where tests are thinnest**: destructive/recovery paths (xref
   restore, legacy migrations, `_resolve_work_refs`) — where the next silent data loss will occur.
4. **Codegen discipline works** — the only two live drift channels are the two places it wasn't
   applied (glyph map, CI gate).
