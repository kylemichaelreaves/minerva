# Code audit — 2026-07-03

Full-stack audit (frontend, backend/API, data layer/CLI, ingestion pipeline, cross-cutting seams).
Five parallel review passes; every finding below was verified against the actual code at the cited
location. Status: **Phase 2 largely complete** on `remediation/phase-2-critical-ux` (commits
`3cbfd1a`, `a84ba82`). Fix-first shortlist items 1, 6, 8 done; items 2–5 & 7 done in phase 1
(`43f62df`). Frontend §2 high/medium/low items addressed except dead-code cleanup.

Severity legend: 🔴 critical · 🟠 high · 🟡 medium · ⚪ low

---

## Triage status — re-run 2026-09-03 (#481), amended 2026-09-03 (#507)

Every finding in §§1, 2, 5 and 6 was re-run against `main` at `ff6bf9c` and
carries an inline `>` verdict naming the check that produced it. Each is either
struck/marked fixed with that check, or annotated `**Live** → #NNN`. §7 (what's
healthy) and §8 (themes) are not findings and were not triaged.

**§§3 and 4 were not re-run.** All 22 of their findings were already struck when
the pass began, and they were carried forward on the strength of those strikes —
which is why they alone carry no `>` verdict. This paragraph used to say all six
sections were re-run; it was wrong, and the table's `already struck` column was
the honest half of the same page. Two spot-checks (`ChatHandler.timeout = 60` at
`http/serve.py:205`, `serve_lock` at `cli/index_cmd.py:74`) do hold, so the
strikes are not under suspicion — but *already struck* and *verified struck* are
different claims, and only one of them was made.

| section | findings | already struck | fixed but unstruck | live |
|---|---:|---:|---:|---:|
| §1 fix-first shortlist | 8 | 1 | **7** | 0 |
| §2 frontend | 15 | 0 | **15** | 0 |
| §3 backend / API | 11 | 11 | 0 | 0 |
| §4 data layer / CLI | 11 | 11 | 0 | 0 |
| §5 ingestion | 26 | 9 | 3 | **14** |
| §6 cross-cutting | 12 | 3 | 2 | **7** |
| **total** | **83** | **35** | **27** | **21** |

The `findings` column counts `-` and numbered **bullets**, which is what the
pass keyed on. §2 carries five further findings as a prose paragraph under
"Duplication" — they were therefore neither counted nor annotated, and sat
untracked through a triage whose whole point was that nothing here should. They
are triaged inline now: three fixed, two live → #507.

The 21 live bullet findings are tracked in #492–#505 (fourteen issues, grouped
by audit bullet); the two live prose findings are #507. **23 live in all, across
sixteen issues** — a total no row of the table above carries, because the table
counts bullets. Three of this document's own claims did not survive the re-run and are
corrected inline: `kant.py`'s "Berkleyan" typo and `scripture_cite/de.py`'s lone
"V. Mose" are fixed outright, and the Latin `ex 3 modis` over-match is fixed for
the lowercase form this document cites but not for its class (#508). A fourth —
the `Recht - Moralität` de-hyphenation example — does not reproduce as
described, and the fix this document recommends for it does not fix the real
defect (#496).

**Amended 2026-09-04, working the first of those issues: 22 live, not 23, and
a fifth of this document's claims is wrong.** #494 — §5's `Matth. 5-7` parsed
as 5:7 — does not reproduce as a defect at all; the hyphen is this corpus's
chapter–verse separator, 846 of 853 live hyphen cites resolve to verses that
exist, and the cited form occurs zero times. §5's live count is therefore 13
rather than 14 and the bullet total 20 rather than 21, and the table above is
left as it was written on 2026-09-03 rather than silently re-totalled — a
snapshot that gets edited in place stops being evidence of anything. The
correction is on #494 with its commands, and the annotation at the bullet
itself carries the measurement. **This is the second time a fix this document
recommends would have caused harm** (#496 was the first): implementing #494 as
filed would have unbound 846 correct verse references.

**Do not read a count off this table without re-running it.** It was true on
2026-09-03 and every row is a snapshot; the point of the `> ` annotations is
that each one names the check that produced it.

---

---

## 1. Fix-first shortlist

The eight items most worth fixing before anything else, across all layers:

1. 🔴 **Reader infinite scroll is dead.** `web/src/Reader/index.tsx:96-119` — the effect's only
   reactive read (`hasMore()`) sits after an early `return` that always fires on first run (the
   sentinel is inside `<Show when={range()}>` and doesn't exist yet), so the effect ends with zero
   tracked dependencies and never re-runs; the IntersectionObserver is never attached. Any work
   longer than the first 80-chunk page cannot be scrolled past page 1. Fix: use the existing
   `hooks/useInfiniteScrollSentinel` (add a `root` option) or read the signals before the guards.

  > **Fixed** (#481, 2026-09-03): `Reader/index.tsx:27,129` imports and calls `useInfiniteScrollSentinel`; the hand-rolled observer is gone.

2. 🔴 **`.sql` migrations are not transactional despite the runner's docstring.**
   `src/minerva/migrations/__init__.py:22-24,79-80` — `conn.executescript` autocommits per
   statement. A mid-script failure (e.g. `0008`'s two consecutive `ALTER TABLE ADD COLUMN`) leaves
   the first statement committed with the version unrecorded → re-apply → "duplicate column" →
   permanently wedged DB. Same trap inside `.py` migrations 0003/0009/0013/0016, where interleaved
   `executescript` calls commit pending DML mid-migration (`0013:107,114`). The repo already knows
   this (0021/0022 explicitly avoid `executescript`) but the runner still relies on the false
   guarantee. Fix: no `executescript` in migrations; runner wraps `.sql` files in explicit
   BEGIN/COMMIT via split `execute` calls.

  > **Fixed** (#481, 2026-09-03): `migrations/__init__.py:58,97` routes `.sql` files through `sqlite_util.execute_script_statements`; `:152,158,160` wrap them in an explicit `BEGIN`/`commit`/`rollback`. No migration calls `executescript`.

3. 🔴 **Both DB snapshot mechanisms are WAL-blind on a WAL-mode DB.** `scripts/snapshot-db.sh:64-70`
   and `src/minerva/cli/index_cmd.py:143-144` copy `index.sqlite` alone; unchekpointed WAL frames
   (the newest commits — including LLM-verified xrefs, the exact asset snapshots exist to protect)
   are silently absent, and a copy concurrent with a checkpoint can be torn. Fix: `sqlite3 "$db"
   ".backup"` in the script, `Connection.backup()` / `VACUUM INTO` in Python. (Related: `reset_db`
   and `--reset` unlink only the main file, leaving stale `-wal`/`-shm` behind — a documented
   SQLite corruption vector. `store/schema.py:112-114`, `index_cmd.py:67-68`.)

  > **Fixed** (#481, 2026-09-03): `scripts/snapshot-db.sh` runs `sqlite3 "$db" ".backup ..."`; `store/preserved_state.py:48-53` documents the backup-API choice for the pre-index snapshot; `store/schema.py:106-108` unlinks `-wal`/`-shm` alongside the main file.

4. 🔴 **`chunks.jsonl` is overwritten non-atomically while consuming lazy parser iterators.**
   `src/minerva/ingest/__init__.py:47` (`write_jsonl`) and `ingest/parallel.py:248`
   (`concat_shards`) open the canonical file with `"w"` directly; any mid-ingest exception, Ctrl-C,
   or disk-full truncates it, and the next `index --reset` mass-deletes chunks.
   `_merge_dicts_to_jsonl` (`:120-135`) already does temp-file + rename — mirror it.

  > **Fixed** (#481, 2026-09-03): both `ingest/__init__.py:49` (`write_jsonl`) and `ingest/parallel.py:252` (`concat_shards`) write to a `.tmp` sibling and atomically rename.

5. 🟠 ~~**A full ingest silently skips any source whose raw path is missing.**~~
   **Fixed** (`remediation/phase-5-ingestion`): `missing_registered_sources` +
   `iter_registered_chunks(..., allow_missing_sources=)` print loud per-source
   ``SKIPPED`` lines and raise :class:`~minerva.ingest.registry.MissingIngestSourcesError`
   before yielding; ``cmd_ingest`` exits 2 unless ``--allow-missing-sources``.
   Related full parallel concat-before-failure check unchanged in ``cli/ingest_cmd.py``.

6. 🟠 **Reader work identity keys on `(title, lang)`, not `work_id`.**
   `src/minerva/reader/queries.py:139-152` — 72 (title, lang) pairs in the live DB map to two
   `work_id`s (Luther 1912 vs 1545 share every book title). Verified: paging `1 Corinthians`/deu
   past ordinal 437 silently walks into the other translation; `around=` mode returns the wrong
   work's metadata. Same class in `store/chunks.py:544-569` (`fetch_chunk_context` scopes neighbors
   by `(work, lang)`, unlike `neighbor_ids` which correctly uses edition/translation id). Fix:
   resolve and filter by `works.id` in the meta, range, and context queries.

  > **Fixed** (#481, 2026-09-03): `reader/queries.py` resolves `work_id` and scopes the range by `_edition_selector` (#50); `store/chunks.py:817-838` scopes `fetch_chunk_context`'s neighbours by the focus chunk's `edition_id`/`translation_id`.

7. 🟠 **The pre-index restore error path masks the real exception and re-triggers the
   PRAGMA-in-transaction trap.** `src/minerva/cli/index_cmd.py:258-338` — a failure in the
   ATTACH-restore DML (realistic: positional `INSERT ... SELECT *` at :275/:287/:302 breaks on any
   schema drift between snapshot and live) reaches a `finally` that runs `DETACH` inside the open
   transaction (raises, hiding the original error), never rolls back, then runs `PRAGMA
   foreign_keys` as a documented no-op inside the still-open transaction. Fix: rollback-and-reraise
   before DETACH; explicit column lists in the restore INSERTs.

  > **Fixed** (#481, 2026-09-03): `store/preserved_state.py:251-253` rolls back and re-raises *before* the `finally` DETACH at `:291-292`; `:557-560` builds an explicit live∩snapshot column list instead of `SELECT *`.

8. 🟠 **`refs verify --strategy llm-verify --resume` permanently skips errored batches.**
   `src/minerva/refs/llm_verify.py:483-503,583` — an errored batch `continue`s without
   checkpointing, but a later success writes `_write_checkpoint(batch[-1].id)`, advancing past the
   failed rows; resume (`xr.id > resume_from_id`) never revisits them. Silent under-verification.
   Fix: never advance the checkpoint past the lowest unprocessed row id.

  > **Fixed** (#481, 2026-09-03): `refs/llm_verify.py:738-741` gates `_write_checkpoint` on `first_failed_id is None or batch[-1]["id"] < first_failed_id`, so the checkpoint can never pass a row an earlier failure left unexamined.

---

## 2. Frontend (web/src)

### High
- 🟠 `hooks/usePaginatedAppend.tsx:29-38,61-65` — generation bump on filter change never resets
  `appending`; a filter change mid-flight leaves `appending()` stuck true and `loadMore`
  early-returns forever (Refs list + Review queue pagination dead until remount). The existing test
  covers the path but never asserts `appending()`. Fix: reset in `finally` unconditionally.

  > **Fixed** (#481): `usePaginatedAppend.tsx:72-79` resets `appending` in an unconditional `finally`.
- 🟠 `Reader/useTermCard.tsx:73-81` — URL-resume effect tracks both `props.openTermId()` and
  `openCard()`; Esc/outside-click on a click-opened card re-opens it at the sentinel anchor before
  the URL clears. Fix: `untrack` the `openCard()` read.

  > **Fixed** (#481): `useTermCard.tsx:80` reads `untrack(openCard)`.
- 🟠 `hooks/usePopoverPosition.tsx:8-10` — position computed once at setup; clicking a second
  marked word while a card is open renders new content anchored at the old word (Reader mounts
  cards in non-keyed `<Show>`, `Reader/index.tsx:328-346`). Fix: effect over `anchor()` or key the
  Show.

  > **Fixed** (#481): `usePopoverPosition.tsx:22-30` recomputes in a `createEffect` over `anchor()`.

### Medium
- 🟡 `api/chatApi.ts:213-217` — a stream that ends after `meta` but without `done`/`error` returns
  silently; the placeholder turn stays `streaming: true` forever (stuck cursor, partial text
  dropped). Fix: treat meta-without-done as `onError("Stream ended early.")`.

  > **Fixed** (#481): `chatApi.ts:215-223` — no meta → "Stream ended before any data arrived", meta-without-done → "Stream ended early — the answer was cut off."
- 🟡 `Refs/components/Review.tsx:136,205,210-268` — cursor increments unboundedly past queue end;
  `goNext`/`goPrev` not gated on `acting()` (wheel flick during in-flight PATCH silently skips a
  row past review); `actionError` banner never cleared on later success.

  > **Fixed** (#481): `features/Refs/components/Review.tsx:206,217-226` gates `goPrev`/`goNext` on `acting()`; `goPrev` bounds at `c <= 0` and `goNext` routes through `advanceAfterWrite`; `:148,178,186` clear `actionError`.
- 🟡 `Reader/useWordLookup.tsx:122-148` — "Show more samples" passes no AbortSignal (comment
  claiming propagation is false) and the post-await guard doesn't check same-word identity; word
  A's page can merge into word B's panel. Also lacks `onCleanup` abort (sibling
  `useTranslateRail.tsx:88` has it).

  > **Fixed** (#481): `useWordLookup.tsx:93` guards on `wordInfoController === controller && !aborted`; `:171-172` aborts both controllers in `onCleanup`.
- 🟡 `Concordance/components/IndexPage.tsx:262` — language switch clears `letter` but not
  `scopeAuthors`/`scopeWorks` → permanent "No lemmas in this scope" with a stale invisible filter.

  > **Fixed** (#481): `Concordance/components/IndexPage.tsx:268-274` — `onSetLang` clears `letter`, `scopeAuthors` and `scopeWorks`.
- 🟡 `Concordance/components/FilterBar.tsx:83-116` — Dropdown has no outside-click/Escape close
  despite `useClickOutside` existing.

  > **Fixed** (#481): the local `Dropdown` was replaced by the shared keyboard-operable `Select` (#364), `Concordance/components/FilterBar.tsx:79-112`.
- 🟡 `AppRoutes.tsx:40-50` — auto-scroll forces bottom on every SSE delta with no "user scrolled
  up" guard; can't re-read earlier turns while streaming.

  > **Fixed** (#481): `AppRoutes.tsx:43,57,65-72` — a `stickToBottom` signal, cleared by a scroll listener, gates the auto-scroll.
- 🟡 A11y, systemic: `components/MobileSheet.tsx:21` and `components/PopoverCard.tsx:37-48` —
  `role="dialog"`/`aria-modal` with no focus-in, no trap, no restore. `ThemeToggle.tsx:12-13` —
  `aria-label` frozen at setup.

  > **Fixed** (#481): `components/shell/MobileSheet.tsx:3,22` and `components/primitives/PopoverCard.tsx:5,44` both use `useDialogFocus`; `ThemeToggle.tsx:12` computes `aria-label` in an accessor.

### Low (selected)
- ⚪ `MobileSheet.tsx:13-15` — `useEscape` registered without the `active` gate; a closed sheet
  still `preventDefault()`s every Esc on refs/network pages.

  > **Fixed** (#481): `MobileSheet.tsx:16-21` passes `() => props.open` as `useEscape`'s active gate.
- ⚪ `Network/index.tsx:58-70` — `?source=` deep link leaves the author dropdown filtered;
  `Body.tsx:76` mobile "More views →" wired to a defaulted no-op.

  > **Fixed** (#481): `Network/index.tsx:74-80` seeds the unfiltered author list behind a `?source=` deep link; `:153` wires `onOpenMore` to `shell.setFiltersSheetOpen(true)`.
- ⚪ `Concordance/components/FilterRail.tsx:241` — `"v" + (p.italic ? "" : "")` italic flag dead in
  both branches. `FilterBar.tsx:150-151` — `NaN%` slider when ceil()===1. `IndexPage.tsx:167` —
  freqCeil ratchet wrong on `sort=alpha|pos` deep links.

  > **Fixed** (#481): `FilterRail.tsx:224` emits `" italic"`; `FilterBar.tsx:154` returns `0` when `ceil() <= 1`; `IndexPage.tsx:181` gates the freqCeil ratchet on `sort() === "freq"`.
- ⚪ `Reader/useWordHoverTranslations.tsx:40-56` — hover-translation cache grows unboundedly for the
  Reader's lifetime.

  > **Fixed** (#481): `useWordHoverTranslations.tsx:38` caps the cache at `HOVER_TRANSLATION_CACHE_MAX = 500` and evicts oldest-first.
- ⚪ `utils/popoverPosition.ts:15-19` — RTL placement branch unreachable (no caller passes
  `direction`); Hebrew/Arabic word-cards always get LTR placement.

  > **Fixed** (#481): `detectAnchorDirection` reaches `computePopoverPosition` via `Reader/components/WordRun.tsx:203` → `Reader/index.tsx:447` → `TermCard.tsx:71` → `PopoverCard.tsx:36-38`.

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

  > **Three fixed, two live** (#507, 2026-09-03). These five are the prose findings the
  > #481 pass skipped — see the amended triage note at the top of this file. Fixed:
  > `turnId` is extracted to `Thread/turnId.ts:7` and imported by both call sites
  > (`Thread/index.tsx:7`, `Thread/components/ThreadSearchSheet.tsx:4`); `targetAuthors`
  > is now `useRefsTargetAuthors` in `features/Refs/components/refsList.tsx`, called at
  > `features/Refs/index.tsx:97` beside its `useRefsSourceAuthors` sibling; the Reader
  > observer is gone (§1.1's verdict). **Live** → #507: `confLabel` is byte-identical in
  > `Network/components/Header.tsx:25-28` and `NetworkFiltersBar.tsx:61-64`, and the
  > `lockedGender` 0.95 heuristic is duplicated in
  > `Concordance/components/FilterRail.tsx:65-72` and `LemmaIdentityCard.tsx:29-36`.
  >
  > **Fixed 2026-09-04 (PR #514), and the `lockedGender` half was not the duplication it
  > looked like.** `confLabel` was a straight hoist into `Network/constants.ts`. The two
  > `lockedGender` copies, however, computed *different things*: the card read the API's
  > count-descending buckets and so took the true maximum, while the rail read them
  > re-sorted into canonical Masc/Fem/Neut order and scored whichever gender came
  > **first** against the 95% threshold. Both components are handed the same `data()`
  > object, so they contradicted each other in one view — `ratio` (lat) is Fem 17,619 /
  > Masc 50, which the card locked as "Fem" while the rail showed a multi-gender chooser.
  > Measured over the whole corpus: 3,653 lemma×lang pairs are locked by max-count and
  > **1,833 of them (50.2%) disagreed** (deu 605, lat 579, grc 386, fra 262, ara 1). So
  > this bullet's "duplication" was hiding a live defect, and the extraction had to pick a
  > semantic rather than preserve behaviour. The shared helper takes the maximum by count,
  > order-independently, and both surfaces now report the measured share instead of
  > claiming "single attested" / "only attested gender" — wording that overstated the
  > >95% case, which is most of them.

---

## 3. Backend / API

- 🟡 ~~`concordance/index_queries.py`~~ — **fixed**: merge_case / multi-work pages use SQL
  `GROUP BY` + `LIMIT`/`OFFSET` instead of scanning 2000 rows from offset 0.
- 🟡 ~~`http/serve.py` + `server_core.py`~~ — **fixed**: loopback CORS uses explicit dev
  origins (API port + Vite :5173/:4173), never `*`; unmatched origins get no ACAO header.
- 🟡 ~~`http/serve.py`~~ — **fixed**: `ChatHandler.timeout = 60` slow-loris guard.
- 🟡 ~~`chat_service.py`~~ — **fixed**: 8 KiB query cap + history turn/char caps (mirror translate).
- 🟡 ~~`http/handlers/translate.py`~~ — **fixed**: leader translate path wraps LLM work in
  `try`/`finally` so `finish_inflight` always runs.
- ⚪ ~~`http/handlers/chat.py:150-162` + `serve.py:150-153`~~ — **fixed**: assistant turn
  persisted before the ``done`` SSE event; rollback skipped once ``persisted`` is set so client
  disconnect no longer deletes a billed answer.
- ⚪ ~~`llm.py:236,350,375`~~ — **fixed**: ``AnthropicBackend.last_usage`` stored per-thread via
  ``threading.local``.
- ⚪ ~~`http/server_core.py:49-66`~~ — **fixed**: drained rate-limiter buckets evict their
  ``(route, ip)`` key.
- ⚪ ~~`concordance/kwic_queries.py:254-328`~~ — **fixed**: ``_lemma_breakdowns`` aggregates
  pos/surface/feats/work in SQL instead of fetching every occurrence row.
- ⚪ ~~Duplication~~ — **fixed**: shared ``text/snippet.py`` KWIC/mark builders (incl. ``»``);
  ``query_params.parse_int_param`` + ``escape_like_substring``; ``terms_list`` LIKE escape +
  LIMIT/OFFSET.
- ⚪ ~~`serve.py:161-275`~~ — **fixed**: ``_translate_route_exception`` shared across
  POST/GET/PATCH/DELETE; LLMError→502 on all verbs.

Verified clean: SQL consistently parameterized; static-file traversal guard sound; translate
leader/follower coalescing and chat lock/LLM-release choreography well designed.

---

## 4. Data layer / CLI / migrations

(Items 2, 3, 7 in the shortlist above, plus:)

- 🟡 ~~`store/chunks.py:184-187,221-222,349-350`~~ — **fixed**: incremental xref
  rebind/orphan sweep scoped to ``deleted_chunk_ids``; DB-side author labels included in
  delete scope for parser renames.
- 🟡 ~~`cli/index_cmd.py:67-69` + `serve_cmd.py:32`~~ — **fixed**: ``serve_lock`` pid file
  blocks ``index --reset`` while ``minerva serve`` holds the DB open.
- ⚪ ~~`cli/ingest_cmd.py:178-181`~~ — **fixed**: full ingests clear
  ``meta.ingest.only`` so ``--from-ingest-only`` cannot rescope to a stale set.
- ⚪ ~~`cli/embed_cmd.py:64-67`~~ — **fixed**: ``--all --lang X`` with zero
  matching chunks reports how many chunks of other languages are present.
- ⚪ ~~Snapshot cost~~ — **fixed**: incremental index runs skip
  ``_maybe_snapshot_pre_index`` (full-byte copy only before destructive
  non-incremental re-indexes).

### Choreography duplication (the root-cause pattern)
- ~~Partially addressed~~ — **fixed**: ``sqlite_util.sweep_orphan_chunk_ids``
  centralises chunk-id orphan sweeps; ``store/chunks`` uses ``table_exists``
  helper; ``foreign_keys_off_for_transaction`` replaces hand-rolled FK
  toggle in ``insert_chunks``; shared ``store/ddl.py`` for ``chunks_full``
  view + FTS trigger DDL (schema + migrations 0021/0022); snapshot/restore
  extracted to ``store/preserved_state.py``.

### Test gaps (worst first)
1. ~~**No end-to-end test for xref survival across `index --reset`**~~ — covered by
   ``test_index_xref_preservation.py``; ``--from-ingest-only`` exercised there too.
2. ~~**`store/chunks._resolve_work_refs`**~~ — **fixed**: ``test_store_resolve_work_refs.py``.
3. ~~Migrations: legacy-shape + mid-migration-failure re-entrancy~~ — **fixed**:
   ``test_migrations_legacy_shape.py``, ``test_migration_failure_semantics.py``.
4. ~~``cli/refs/review.py``~~ — **fixed**: ``test_refs_review.py``.
5. ~~``store/stats.py`` / ``cli/db_cmd.py``~~ — **fixed**: ``test_store_stats.py``.

---

## 5. Ingestion pipeline

(Items 4, 5, 8 in the shortlist above, plus:). **Phase 5 started**
(`remediation/phase-5-ingestion`): shared ``text_excluding`` + missing-path loud failure.

Note: shortlist #5 now enforced at the registry layer too —
``missing_registered_sources`` + ``iter_registered_chunks`` raise
:class:`~minerva.ingest.registry.MissingIngestSourcesError` with loud
``SKIPPED`` stderr; ``cmd_ingest`` still exits 2 unless
``--allow-missing-sources``.

### Text-corruption bugs (live, in the DB now)
- 🟠 ~~`sources/tei_drama.py:66-79`~~ — **fixed**: shared
  ``tei.text_excluding`` child-walk skips ``speaker``/``stage`` subtrees
  without dropping following ``tail`` text.
- 🟡 ~~`sources/tei_p5.py:47-51`~~ — **fixed**: ``_text_of`` uses
  ``text_excluding`` to drop namespaced ``<note>`` apparatus.
- Root cause: ~~five implementations~~ — **fixed**:
  ``tei.text_excluding(el, skip_tags)`` hoisted into ``tei.py``; drama,
  P5, ``hebrew_mt``, ``tei_lxx``, and ``osis_bible`` parsers migrated.

### Silent-failure gaps
- 🟡 ~~`corpus/pipeline.py:88-135` vs guard at `:154-166`~~ — **fixed**:
  all 8 direct ``yield from`` structured-parser branches route through
  ``_yield_structured``, which warns on zero output (no chapter fallback).
- 🟡 ~~`tei.py:527-529`~~ — **fixed**: ``tei.parse_dir`` catches per-file
  errors via shared ``record_parse_failure`` (same log as ``corpus/pipeline``).
- 🟠 ~~Chunk-count validation still missing: neither `scripts/check_author_ingest.py` nor
  `scripts/corpus-quality-audit.py` validates counts against expected work size; the Theognis
  failure (2,237 junk chunks) would pass both today (`theognis` is even in SKIP_RULES). Add
  manifest-declared expected ranges.~~ — **fixed**: top-level `expected_chunks` in
  `manifest.yaml`; shared `scripts/chunk_count_validation.py`; wired into
  `check_author_ingest --db` and `corpus-quality-audit.py` (non-zero exit on violation).
- 🟡 ~~Root-element `find()` misses are silent empty iterators in 4 parsers~~ —
  **fixed**: ``tei.py``, ``tei_lxx.py``, ``tei_p5.py``, ``tei_drama.py`` now warn on
  stderr when expected root elements are absent.

### Refs rules gaps
- 🟠 `refs/embed_verify.py:232-239` — work-level target matrix joins editions only; translation-only
  target works never resolve (known issue, confirmed still unfixed).

  > **Live** (#481, 2026-09-03) → #492. Now *documented* as deliberate at `refs/embed_verify.py:239-247`; what the docstring does not settle is the translation-only case.
- 🟡 No `refs/rules/new_testament.py` — NT→OT citations (Matthew→Isaiah/Psalms) never auto-detected.

  > **Live** (#481) → #493.
- 🟡 `hobbes.py` targets Descartes but `descartes.py` has no Hobbes rule (bidirectional-audit class,
  despite its own docstring citing the Third Objections exchange).

  > **Live** (#481) → #493. `grep -i hobbes src/minerva/refs/rules/descartes.py` finds only a docstring mention at `:25`.
- 🟡 `scripture_cite/lexicon.py:342` — Latin bare-abbrev regex over-matches (`ex 3 modis` → Exodus 3).

  > **Fixed for the cited form; the class is live** (#481, 2026-09-03) → #508. `_CITE_RE.finditer("ex 3 modis")` → `[]`, because the regex now requires a capital initial. Sentence-initial capitalisation reopens it: `ScriptureCiteRule().scan()` on `"Ex 3 modis potest dici."` returns `[('Exod 3', 0.75)]`, undowngraded because `Ex` is not in `_AMBIGUOUS_BARE`. Latent, not live in the data — across all 67,728 `lat` chunks every word-collision match (`Act.`, `Num.`, `Sap.`, `Bar.`, `Iud.`) carries the citation period, and `Ex <n>` does not occur at all.
- 🟡 Rule targets are free-text title literals (`aquinas.py:41-46`, `hegel.py:42-48`, `renan.py`,
  `nietzsche.py`) — a title rename on re-ingest silently orphans edges. Resolve via slugs/IDs.

  > **Live** (#481) → #493.
- ⚪ `kant.py:113` "Berkleyan" typo never matches; `scripture_cite/de.py:176` lone "V. Mose"
  unreachable; `lexicon.py:345` "Matth. 5-7" parsed as 5:7.

  > **All three closed** (#481, 2026-09-03; third corrected 2026-09-04): `kant.py:110` spells `Berkeleyan`, and `scripture_cite/de.py:21` carries `("V", "Mose"): "Deuteronomy"`. The third claim is **wrong, and was carried into #494 before it was re-run**: `Matth. 5-7` → `Matt 5:7` is the rule working as designed, because the hyphen is the Corpus Thomisticum chapter–verse separator (`scripture_cite/lat.py:43`, `_base.py:62-65`, and the original per-author survey: `Matth. 5-48`, `Ioan. 17-3`, `I Cor. 13-4`). Measured over all 67,728 `lat` chunks, 846 of the 853 hyphen-form cites resolve to verses that exist in the target book, and `Matth. 5-7` occurs **0 times** — of the 41 distinct `Matth. <c>-<v>` forms the corpus does carry, `Matth. 11-27` (8×) and `Matth. 25-41` are verse cites, and the latter cannot be a chapter range in a 28-chapter gospel. Had this been implemented as written, removing `-` from the verse-separator class would have turned all 846 bound verse references into unbindable chapter-only rows.
- ⚪ `refs/rules/__init__.py:475-518` — scan-state marks chunks scanned even on zero matches; fixed
  rules don't retroactively apply without `--rescan-all`.

  > **Fixed** (#481, 2026-09-03): `refs/rules/__init__.py:477-495` — the skip predicate now also compares the author's rule-set fingerprint, so editing a rules file re-scans that author (#287, #304).

### Download/extract scripts
- 🟠 ~~`perseus/download_first1kgreek_lxx.py:79`, `download_first1kgreek_aristotle.py:95,105`,
  `download_marcus_aurelius.py:103` — `except urllib.error.HTTPError` with **no `import
  urllib.error`**: the expected-404 path raises NameError and aborts the batch.~~ — **fixed**:
  added missing imports.
- 🟠 ~~`perseus/_download.py:73` — retry helper never validates body/size/content-type; the
  mlwerke-parking-page trap generalizes to every fetch. Add a validate/min-size gate.~~ —
  **fixed**: `fetch_bytes_with_retry` accepts `min_bytes` and `reject_markers` (parking-page
  substring guard).
- 🟡 Five byte-identical zeno crawlers (hegel/kant/marx/nietzsche/schiller); four swallow
  exceptions inside BFS, silently truncating whole chapter subtrees. Extract `perseus/_zeno.py`.

  > **Live** (#481) → #501. All five crawlers carry a broad `except Exception`; no shared `perseus/_zeno.py` exists.
- 🟡 `_gutenberg.py:52-57` — missing `Language:` header bypasses the wrong-ID guard built after the
  Pascal/Rousseau incident.

  > **Live** (#481) → #499. `_gutenberg.py:53-55` is `if m and ...` — a missing header still passes.
- 🟡 Absolute line offsets sliced into live archive.org OCR (`extract_descartes_principes.py:50`,
  `download_boulainvilliers.py:64`) — regenerated OCR silently shifts the cut.

  > **Live** (#481) → #499. `extract_descartes_principes.py:100` still slices `lines[PART_II_START - 1 : TABLE_START - 1]`.

### Splitter fragility/duplication
- 🟡 ~11 copies of the `_make_chunk_id + Chunk(...)` emit recipe across splitters, plus 6 BCV
  parsers hand-constructing the identical verse-chunk block. One shared emit helper + one
  `make_verse_chunk` factory. Byte-identical `_chunk` in `split_hegel_pr_de.py:86-117` ≡
  `split_hegel_pr_epub.py:94-125`.

  > **Live** (#481) → #501. `_make_chunk_id` *is* shared (`tei.py:136`, 13 importers); the call recipe and the BCV verse block are not, and no `make_verse_chunk` factory exists.
- 🟡 `corpus_works.py:36-37` — `CorpusWork` defaults `corpus="hegel", author="Hegel"`; a forgotten
  override silently files a new author under Hegel. Also `filename_index` (:83-90) last-wins on
  duplicate filenames (the Kapital Band-II collision class) — raise instead.

  > **Live** (#481) → #498. Now at `src/minerva/corpus_works.py:60-61` and `:107-113`.
- 🟡 `corpus_registry.py:538,543` — unknown corpus id silently returns `"paragraph"`/`"eng"`.

  > **Live** (#481) → #498. Now at `corpus_registry.py:611,616`.
- 🟡 `split_kant.py:30-33` — A/B page-marker regex matches words like "Bild"; `split_hegel_pr_de.py:63`
  — de-hyphenation `re.sub(r"-\s+", "")` fuses "Recht - Moralität" → "RechtMoralität" (safe variant
  exists at `split_stephanus_de.py:114`); `split_spinoza_ethica.py:95-98` — broad except falls back
  to the parser the docstring says loses 65/73 propositions; `split_descartes.py:119-123` — TOC
  captured as body (first-occurrence slicing).

  > **Split** (#481, 2026-09-03): `split_kant`'s `Bild` match → #495 (demonstrated); the de-hyphenation fusion → #496 (demonstrated — and the `split_stephanus_de.py:114` variant recommended here does **not** fix it); Spinoza's broad `except` and Descartes' TOC slicing → #497.
- 🟡 `embed.py:17,35` — HF model loaded with no `revision=` pin; an upstream update silently changes
  the embedding space under stored vectors and cosine thresholds (same for spaCy/Stanza loads).

  > **Live** (#481) → #500.
- 🟡 `ingest/registry.py:474-493` — hand-maintained `INGEST_ID_TO_CORPUS` currently consistent
  (verified) but unenforced; add a sync test.

  > **Live** (#481) → #502. `tests/test_ingest_registry.py` asserts three sentinel keys, not completeness.
- 🟡 No `make post-ingest` target: embed → lemmatize → refs build → embed-verify → llm-verify
  remains tribal knowledge (the exact gap that left 9 authors / 6k xrefs unverified).

  > **Live** (#481) → #502.

---

## 6. Cross-cutting seams

### Live drift (only two channels found — both closable)
- 🟡 ~~`web/src/utils/dominantPhil.ts`~~ — **fixed**: `PHIL_DOMINANT_GLYPH` now codegen'd from
  `manifest.yaml` (includes Schiller `'l'`); hand-maintained copy removed.
- 🟡 ~~`.github/workflows/check.yml` claims to mirror `make check` but omits `check-api-types` (the
  TS-side contract gate), `check-author-imports`, and `check_author_ingest --all`~~ — **fixed** in PR
  #38: python job now runs all three contract scripts.

### Codegen script defects
- 🟡 `scripts/generate_author_artifacts.py:320-324,348-357,373-395` — dead identical-branch
  conditional; `_replace_region` passes generated code as an `re.sub` replacement string (backslash
  escape-processing → corruption); three artifact files written with no all-or-nothing; and the
  `# BEGIN CORPORA` sentinel is already duplicated in `corpus_registry.py` because
  `_comments_from_corpus_registry` scoops the module header into Plato's comment.

  > **All four closed** (#481, 2026-09-03; last two fixed 2026-09-04, PR #513): the duplicated `BEGIN CORPORA` sentinel is guarded at `:394-399` (#69), the dead identical-branch conditional is gone, and the `re.sub`-replacement defect and the non-atomic write are fixed under #503.
  >
  > **Two corrections to this bullet and to the 2026-09-03 annotation that replaced it.** (a) It is **four** generated artifacts, not three — `corpus_registry.py`, `author_ordering.py`, `atlasData.ts`, `dominantPhil.ts`. (b) The 2026-09-03 annotation said "the backslash case *raises* rather than corrupting silently", which is half the truth and was carried into #503's own framing: measured across the four escape shapes, `\d` and `\1` raise, while `\\` collapses to a single backslash **and `\g<0>` re-injects this region's entire previous text into the file being rewritten**. So the audit's original "escape-processing → corruption" was right about the kind and the annotation was right about the reach, and neither was right on its own. The fix (a function replacement) closes all four shapes.

### Dead surface
- Five GET routes with zero frontend callers: `/api/chunks/:id/references`, `/api/terms/by_chunk/:id`,
  `/api/works/:id/term_occurrences`, `/api/translations/:id/renderings`, `/api/terms` (list)
  (`http/router.py:104,124,129,144,148`) — plus their fixtures and `api/types/terms.ts`.

  > **Live** (#481) → #504. Re-verified 2026-09-03: zero frontend callers for all five.
- `src/minerva/parsers/` and `src/minerva/works/` — migration shims with zero importers; delete.

  > **Fixed** (#481, 2026-09-03): `ls src/minerva/parsers src/minerva/works` → `No such file or directory` for both.
- `src/minerva/server.py` — 65-line re-export shim of ~50 underscore names; tests split 5/5 between
  the two import paths. Migrate tests to `minerva.http.*`, delete.

  > **Live** (#481) → #504. `wc -l` → 67; `grep -rn 'minerva\.server' tests/ src/` → 9 references.
- ~12 one-off remediation scripts in `scripts/` → archive under `scripts/oneoff/`; `SCRIPTS.md`
  documents 4 of ~26 scripts.

  > **Live** (#481) → #505. Re-measured 2026-09-03: `SCRIPTS.md` names 4 of **40** scripts, not 4 of ~26, and `scripts/oneoff/` does not exist.

### Docs
- ~~`FRONTEND.md` references non-existent `web/src/lib/` six times (actual: `utils/`,
  `hooks/`).~~ Fixed in #477's PR. The count was **ten**, not six — five spelled
  `src/lib/` and five bare `lib/` — and the same stale prefix also sat in
  `ARCHITECTURE.md`, `INGESTION.md` and four source comments, all corrected there.
  `MobileSheet.tsx` resolves to `components/shell/`, not `utils/` or `hooks/`.
- `block-structure-remediation-plan.md:3` says IN PROGRESS; tracker shows all 8 items ✅ → flip to
  DONE. Archivable: `CODE_AUDIT_2026-06-10.md`, `orthography-normalization-plan.md`,
  `aquinas_cite_survey.md`, stale `corpus-quality-audit.md` + `dashboard_aggregates.json`.

  > **Split** (#481, 2026-09-03): the plan's stale `IN PROGRESS` header is corrected in #481's PR. The four archivable docs are **live** → #505 — and `CODE_AUDIT_2026-06-10.md` must be triaged before it is archived, not after.
- `ARCHITECTURE.md:70` still calls `server.py` the stdlib server.

  > **Live** (#481) → #504; the doc line is corrected in #481's PR. Note the audit's own pointer was stale: it is `ARCHITECTURE.md:125`, not `:70`.
- `pyproject.toml` — `pyyaml` required at runtime by `refs/rules/loader.py` but only in
  `[lemma]`/`[dev]` extras.

  > **Corrected** (#481, 2026-09-03): `pyyaml` is **not** required at runtime as written. All
  > three `import yaml` sites are lazy and guarded — `glossary_spec.py:125` and
  > `refs/spec.py:128` raise a `SpecError` naming the extra, and `glossary_spec.py:122-123`
  > documents the deferral as deliberate ("keeps `import minerva.glossary_spec` cheap on
  > plain installs"). A base install does not crash on import. The real residue is narrower:
  > `refs/rules/specs/` holds `boulainvilliers.yaml` and `gobineau.yaml`, so `refs build` for
  > those two in-corpus authors reaches `loader.load_author_rules_from_yaml` on the default
  > path. Its error message was the only one of the three that did not name the extra —
  > aligned with its siblings in #481's PR. Whether that makes `pyyaml` a core dependency
  > rather than an extra is a packaging decision → #493.
- `Makefile` — `make test` is frontend-only (python is `test-py`) — naming trap.

  > **Live** (#481) → #502. Renaming `test` is a decision, not a one-line correction, so it is filed rather than folded into #481's PR.

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
