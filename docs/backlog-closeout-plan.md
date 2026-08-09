# Backlog close-out plan

Plan of record for closing the twelve issues open on 2026-08-08. Written
so the work survives session boundaries: it names the batches, the order,
the decisions already taken, and the verification each PR owes.

**The open issue list is the progress bar.** An issue still open is still
to do; this document does not track state separately, because a second
tracker rots. Start any session by re-reading it against reality:

```
gh issue list --state open
gh pr list --state open
```

## Context

All twelve issues were verified against `main` at `dd30678` and against
the live `data/index.sqlite` on 2026-08-08. None had been silently fixed,
and every measured number in every issue body still reproduced — the
`refs_scan_state` orphan count (31,629 / 460,235), the lemma residue
(419 eng / 299 fra / 126 deu / 15 grc), the 753 chunks over 8,000 chars,
`terms`/`term_occurrences` at 0/0, and Agamemnon (eng) as a single
82,256-character chunk.

Six of the twelve came out of a single operator re-ingest (#262, #263,
#264, #274) or out of PRs merged the same week (#272, #276). That context
is expensive to rebuild, which is what sets the ordering.

Decisions taken 2026-08-08 by the repo owner:

- **#136 fact 2** — split the reformat into separate PRs. Measured: this
  works, but the cut is by *file coverage*, not by directory.
- **#182** — build the named-passage table; do not park or close.
- **#176** — add the gate, then re-chunk the worst parser failures only.
- **Delivery** — one PR per batch, each carrying both issues' `Closes`
  lines.

## Standing gates

From [CLAUDE.md](../CLAUDE.md) — not optional, and each has failed a PR
before:

- **Every round ends with a PR.** A batch is not finished when the code
  works locally; it is finished when there is a pushed branch and an open
  PR against `main` carrying its `Closes`/`Refs` lines. Work that stops at
  a local commit is invisible to CI, to Sonar, and to the next session —
  the same failure mode this document exists to prevent. This applies to
  every round, including doc-only ones like the one that added this file.
- `make check` before every push, and **again after any edit made while
  fixing its output**.
- `check-diff-coverage` ≥80% **including branches** — Sonar scores a
  one-line guard's untested false branch 3/4, not 100% (#250).
- `Closes #N` in the PR **body**, base `main`, then verify the link
  registered. A stacked PR records nothing, and retargeting does not
  backfill.
- Duplication ≤3% on new code. Copying a component wholesale fails at any
  coverage (#254).
- Anything found along the way that isn't tracked gets its own issue
  before moving on. A correction to a wrong claim goes **on the source** —
  a comment on the issue, or a fix to the doc in the same PR — never into
  a new issue.

## Order

| # | Batch | Issues | Why here |
|---|---|---|---|
| 1 | refs verify follow-ups | #272, #276 | Deferred scope from PRs #271/#277, merged 2026-08-08. Decays fastest. |
| 2 | `terms lemmatize` | #262, #263 | Blocks the next Latin-touching re-ingest; #262 is a 19-minute silent hang. |
| 3 | reset preservation | #274, #264 | Same file as each other; low risk, no data migration. |
| 4 | chunk-length gates | #268, #176 | #268 is the only user-visible bug in the set. #176's re-chunk needs an operator window. |
| 5 | perseus verification | #151, #152 | Network-only, `perseus/**` is coverage-excluded, no gate risk. |
| 6 | named-passage index | #182 | Largest design surface; nothing depends on it. |
| 7 | ruff reformat tranches | #136 | Last, deliberately — see batch 7. |

Reformatting last is a measured choice, not a default. Batches 1–4 add
tests to files that currently sit *below* the 80% gate and are therefore
un-reformattable, so running them first shrinks batch 7's blocked tranche
instead of fighting it — and batches 1–6 never rebase across a 130-file
diff.

---

## Batch 1 — refs verify follow-ups (#272, #276)

### #272 — `LLMError` counted as `parse_errors`, never retried

`src/minerva/refs/llm_verify.py:654` increments `n_parse_errors` on the
backend-error path. Two independent halves: do the counter split, decide
the retry separately.

- Add `backend_errors: int = 0` to `LLMVerifyStats`
  (`llm_verify.py:164-177`); count the `LLMError` path into it.
- Print it in the CLI summary (`src/minerva/cli/refs/build.py:317-326`).
- `tests/test_refs_llm_verify.py::TestBudgetAndErrorHandling::test_llm_error_counted_and_processing_continues`
  asserts `stats.parse_errors == 1` today. The test is correct about
  current behaviour and must be **updated, not deleted** — it is the pin.
- Bounded retry with backoff on `LLMError`: in scope only if it stays
  inside the existing `pending`-queue loop. `sleep_between_calls` is fixed
  pacing, not backoff. If it grows past ~20 lines, leave it and say so in
  the PR body — the counter split is worth landing alone.

### #276 — lexical quote binder picks arbitrarily on a tie

`refs/quote_match.py:178-240`. `best_lexical_match` keeps one winner and
breaks ties on lowest `chunk_id`. Two real Psalm ties exist today
(Ps 113:12 / Ps 134:15 both carry *simulacra gentium argentum et aurum,
opera manuum hominum*), and the count grows once the formulaic-quote rule
extends past the Psalter to the synoptics.

Approach — cosine among tied candidates only:

- Return every candidate tying at the winning `_sort_key`
  (`quote_match.py:243-247`). Either add `all_lexical_matches` beside
  `best_lexical_match` or have the latter return a list; the sole caller
  is `refs/embed_verify.py:320`, so either is cheap.
- In `embed_verify.py:320-350`, when more than one ties: score
  `phrases[i]` against each tied chunk's embedding via the existing
  `_load_embedding_for_chunk` and take the argmax. This is a legitimate
  use of cosine — the choice is between two known-correct texts, not a
  search over 2,527 verses, which is the distinction #269 turned on.
- Record the runner-up in `curator_note` via the existing `_lexical_note`,
  so the pick is visible rather than silent.
- Keep the `chunk_id` tie-break as final fallback when no tied candidate
  has an embedding — the stable-pick rationale (no parallel rows through
  `insert_candidate`'s dedup key) still holds.

Verification: the two ties are `chunk_id` 15474 and 53753. Re-run the
uniqueness audit from #276's body; both resolve by cosine among
{Ps 113:12, Ps 134:15}, and the 121 uniquely-determined rows are
unchanged.

---

## Batch 2 — `terms lemmatize` (#262, #263)

### #262 — `--n-process 4` default cannot run for `lat`

LatinCy's `la_core_web_sm` holds a module-level lambda and `spawn` cannot
pickle it. The traceback prints and the process then **hangs** — 18m47s
wall for 1.62s CPU, requiring `kill -9`.

**Corrected 2026-08-08 while implementing, on two counts. Both were
measured; the plan as written above would not have fixed the bug.**

1. *"Wrap the `nlp.pipe` call so `PicklingError` falls back."* This does
   not stop the hang. spaCy primes its worker queues (`sender.send()`
   twice) **before** `for proc in procs: proc.start()`, and its cleanup
   `try/finally` begins only after that loop — so a failed spawn leaks
   `mp.Queue` objects whose feeder threads
   `multiprocessing.util._exit_function` joins at interpreter shutdown,
   blocked forever in `os_write` on a pipe no child will drain.
   Demonstrated: a script that *caught* the `PicklingError`, printed, and
   ran off the end was still alive at 45 s and had to be killed. Had the
   plan been followed, the operator would have got a friendlier message
   and the same `kill -9`. The payload has to be checked **before** the
   pipe is entered — `Lemmatizer._safe_n_process`.
2. *"`la_core_web_sm` … cannot be parallelised"* / #262's "Latin only …
   it is `la_core_web_sm` that will not pickle". The **model** pickles
   fine. What does not is spaCy's process-global `Underscore.get_state()`
   extension registry, which importing `la_core_web_sm` poisons with a
   `Token.set_extension(..., getter=lambda …)` at
   `la_core_web_sm/functions.py:121-126`. Measured in one process, after
   that import, `en_core_web_sm`, `de_core_news_sm`, `fr_core_news_sm`
   and `grc_dep_web_sm` are *all* unpicklable, each reporting the
   *Latin* lambda; each is picklable in a fresh process. So a probe of
   the pipeline object alone — the natural reading of the plan — reports
   "picklable" and prevents nothing, and the defect is not confined to
   `lat`: any language lemmatized in a process that has already loaded
   LatinCy hangs the same way.

- Correct the help text at `src/minerva/cli/terms/__init__.py:303-313` —
  "4 is a safe default" is false. Changing the default to 1 is defensible
  but is the lesser fix alone: it leaves `--n-process 4` a trap. With the
  pre-flight probe in place the default stays at 4, since it is now
  honoured wherever it is safe and downgraded with a notice where it is
  not.

### #263 — zero-lemma chunks reprocessed forever, and miscounted

419 eng / 299 fra / 126 deu / 15 grc chunks re-tokenize on every
incremental pass. `chunk_lemmas` serves as both output table and
done-marker, so a chunk yielding no valid lemma writes no row and is never
recorded as attempted.

- Add a separate attempt marker. **Follow the `chunk_syntax_state` /
  `work_aliases` precedent, not `refs_scan_state`** — the latter is
  precisely what #264 is about: no FK, so it accumulates orphans forever.
  `chunk_lemma_state(chunk_id PK REFERENCES chunks(chunk_id) ON DELETE
  CASCADE, text_hash, token_count, lemmatized_at)` gets orphan reaping for
  free.
- Migration `0027_chunk_lemma_state.sql` — **corrected while
  implementing: it must be `.py`.** The table cannot ship empty. Moving
  the skip predicate off `chunk_lemmas` while no state rows exist means
  the next incremental pass sees the whole corpus as unattempted and
  re-lemmatizes 26M tokens. So the migration backfills a marker for every
  chunk that already has lemma rows, which needs `sha1` over
  `chunks.text` — and SQLite has no builtin for it. `.py` plus
  `sqlite_util.register_text_hash`, the same shape as 0021's
  canonicalizer.
- `text_hash` is not redundant with the content-derived `chunk_id`, which
  is the obvious objection to it: `tei._make_chunk_id` hashes only
  `text[:120]`, so a chunk edited past that point keeps its id and would
  inherit its stale marker.
- Add the new table to the preservation path in
  `src/minerva/store/preserved_state.py`. Otherwise the first
  `index --reset` annihilates it and the bug returns silently — the #192
  failure mode. Do not skip this.
- Amend the candidate predicate (`cli/terms/lemmatize.py:66-72`) to skip
  on the state table rather than on `chunk_lemmas`.
- Report productive chunks separately from attempted at
  `lemmatize.py:165-173`: `done · N chunks (M productive) · T tokens`.

Out of scope, and to be said in the PR body: why 126 clean German Plato
chunks (`KLEINIAS: Das ist recht von euch…`) produce zero lemmas. #263
records the observation without diagnosing it, and the caching fix is what
makes it visible. File the diagnosis as its own issue if this batch does
not answer it.

**Answered 2026-08-08 — no issue needed.** They were never attempted, not
attempted-and-failed; the deu pass had simply not been run over them, which
is the ambiguity the whole batch exists to remove. `KLEINIAS: Das ist recht
von euch…` yields 19 lemmas on its first actual pass. Of the 126 deu
candidates, 2 are productive and the other 124 are Marx footnote citations
(`(131) l.c.p. 35 u. p. 455, 456.`). The remaining residue is Cicero
apparatus (eng) and Renan/Gobineau OCR garbage (fra) — 857 chunks that are
legitimately unlemmatizable and now recorded as such. Correction filed on
the issue.

---

## Batch 3 — `index --reset` preservation (#274, #264)

### #274 — `reference_targets` restored only when xrefs exist

`src/minerva/store/preserved_state.py:115-128`. The outer gate ignores
`reference_targets` entirely, and both the `DELETE` and the restore sit
inside `if xref_count:`. A targets-only snapshot therefore keeps migration
0012's seed rows and loses the curator's `citation_system` and `notes`.

- Probe `target_count` alongside the other four counts
  (`preserved_state.py:105-112`).
- Add it to the outer early-return condition at line 115.
- Decouple the two `DELETE`/`_restore_from_snap` pairs so a targets-only
  snapshot round-trips. Restore `reference_targets` **before**
  `cross_references` — the FK direction requires it.
- #273's PR seeds an xref as a workaround, with a comment pointing here.
  Remove that workaround as part of this fix so it cannot become the
  expected behaviour.

**Corrected 2026-08-08 while implementing. The plan above names only the
restore gate, and fixing only that leaves the bug in place.** The
snapshot gate has to change too. `cmd_index` calls
`_maybe_snapshot_pre_index` and then `store.reset_db`, which *unlinks
the DB file* — so on a targets-only DB the probe's early return fires
(all five counts zero), no `.bak.pre-index` is written, and there is
nothing for the restore to replay however well-gated it is. Measured:
with only the restore fixed, the new regression test still failed
`the curated target did not survive --reset`. `reference_targets` must
be counted in **both** functions.

Consequence, accepted and filed as #289: migration 0012 seeds 20 targets
into every migrated DB, so the snapshot probe is now effectively
unconditional and its "no-op for fully-empty DBs" property is gone. A
narrower predicate cannot be made sound by row count or by which
`(author, work)` pairs are present — the case #274 names is a curator
editing a seed row's `notes` in place, which changes neither.

### #264 — `refs_scan_state` orphans (part 1 only)

31,629 of 460,235 rows point at deleted chunks. Because `chunk_id` is
content-derived, a chunk deleted and later recreated gets **the same id
back** and inherits the stale "already scanned" marker — so a rules module
edited in between never fires for it, and the run looks like a clean
exit 0.

- Reap at the end of `index`, beside where the other derived tables
  reconcile: `DELETE FROM refs_scan_state WHERE chunk_id NOT IN (SELECT
  chunk_id FROM chunks)`. Prefer this to adding an FK — the table rebuild
  needs the PRAGMA/view dance, which is separate risk for no extra benefit
  here.
- One-off cleanup of the existing 31,629 rows: `scripts/snapshot-db.sh`
  first, then the same `DELETE` inside a `BEGIN; … ROLLBACK;` preview with
  a verifying `SELECT` before committing for real.

**Part 2 is out of scope**: keying the skip predicate on a hash of the
loaded rules modules, so `refs build` rescans affected chunks itself
instead of relying on the operator remembering `--rescan-all`. That is a
design change. Either use `Refs #264` and state that part 1 landed and
part 2 did not, or file part 2 separately and close #264.

**Done 2026-08-08: filed separately as #287, so #264 closes.** Also
found while reaping: `refs_scan_state` is *not* on the `--reset`
preservation path, so a single `index --reset` discards all 428,606
markers and the next rules build is a full-corpus pass (#288). The two
defects are opposite — the cache is over-kept in the non-reset path and
under-kept in the reset path — and neither was visible from the other.

---

## Batch 4 — chunk-length gates (#268, #176)

### #268 — `min_chunk_chars=60` hides short chunks from search entirely

`src/minerva/retrieve.py:447`, applied to both BM25 and vector paths, with
nothing in the app overriding it (`agent/retrieval.py:221` omits it). The
floor's rationale is real — Nietzsche letter signatures outranked his
philosophy on queries naming him — so it cannot simply be dropped.

**Approach: exempt verse-addressed works via the existing
`works.citation_system` column.** Measured on the live index:

| citation_system | chunks under 60 chars |
|---|---:|
| `bcv` | 15,968 |
| `surah_ayah` | 1,937 |
| `paragraph` | 31,610 |
| others | 4,259 |

Exempting `citation_system IN ('bcv','surah_ayah')` makes 17,905
legitimately short verses reachable — all 1,937 Quran chunks, plus
`Non occides.` (Exod 20:13, 12 chars) and `Ego et Pater unum sumus.`
(John 10:30, 24 chars) — while leaving the 31,610 `paragraph` ones
filtered. Sampling confirms those are what the floor is for: Renan
footnote markers (`2. Zach., I, 1-6.`), French OCR garbage, running heads.

No new taxonomy and no hardcoded corpus list. `block_type` cannot carry
this — it is NULL on 49,728 of the 53,774 short chunks.

- BM25 (`retrieve.py:145-185`): widen `AND length(chunks.text) >= ?` to
  `AND (length(chunks.text) >= ? OR <exempt>)`. The work's citation system
  is **not** in `chunks_full`, and `<exempt>` must cover **both**
  `chunks.edition_id` and `chunks.translation_id`.

  **Corrected 2026-08-08 while implementing.** The reason given above —
  "scripture is present as editions (Vulgate, SBLGNT) *and* as translations
  (KJV, Luther), so a predicate on one silently misses half" — is false.
  Every short scripture chunk is on the **edition** side; the verse-addressed
  works have no `translations` rows at all, and the KJV and Luther are
  `editions.name` values, not translators:

  ```
  $ sqlite3 data/index.sqlite "SELECT count(*) FROM translations t
      JOIN works w ON w.id=t.work_id
      WHERE w.citation_system IN ('bcv','surah_ayah')"
  0
  ```

  17,905 short chunks on the edition side, 0 on the translation side. Both
  halves are still worth writing — a chunk reaches its work through exactly
  one of the two columns, and the next scripture ingest could land either
  way — but the *verification* changes: the translation half cannot be
  exercised against the live index and needs a fixture, which is what
  `_seed_verse_db` in `tests/test_retrieve.py` is for. Had the claim been
  trusted, "confirmed on both paths" would have been reported on the
  strength of a path that has no data in it.
- Vector (`retrieve.py:330-340`): filtering is numpy over
  `meta.text_lens`. Do **not** extend `EmbeddingMeta`
  (`src/minerva/store/embeddings.py:179`) — `meta.work_ids` is already
  there, so compute the exempt `work_id` set once and use
  `keep &= (meta.text_lens >= min_chunk_chars) | np.isin(meta.work_ids, exempt)`.
- `_reserved_term_ids` (`retrieve.py:250-306`) passes the floor through to
  `_fts_match` and should inherit the fix for free — confirm, don't assume.

Verification: both Latin verses above retrievable by exact phrase where
they were not before, and the regression the floor exists to prevent stays
fixed — a query containing "Nietzsche" must not surface letter signatures.

### #176 — chunk granularity: gate, then the worst outliers

**Part 1, the gate.** Reuse the existing snapshot pattern rather than
inventing one: `scripts/chunk_count_validation.py` already has
`build_snapshot` / `write_snapshot` / `validate_chunk_counts` against a
committed `data/authors/chunk_counts.json`, wired into
`make generate-authors` and validated in CI without the DB
(`.github/workflows/check.yml:133`). Add a granularity check the same
way — a committed snapshot of per-work/lang max and mean chunk length —
called from `scripts/check_author_ingest.py::main` beside
`validate_corpus_authors`.

**The gate must be baseline-pinned, failing only on new violations.** A
bare "no chunk over N characters" assertion fails immediately on all 753
existing ones and is unlandable — the same trap that has #229 stuck.

**Built 2026-08-08, with one addition the plan did not specify.** The
policy and the measurement had to go in *different* files, because the
counts pattern this copies regenerates its snapshot from the DB — and a
gate whose baseline is regenerated the same way blesses every new
violation and checks nothing. So: thresholds and the reviewed
`known_coarse` baseline live in `manifest.yaml` (hand-edited),
measurements in the generated `data/authors/chunk_granularity.json`. Both
dimensions the issue names are gated — per-pair `max` (8,000) and `mean`
(3,000) — because a max-only gate misses a uniformly coarse work, which is
the Epictetus asymmetry. 94 pairs are on the baseline; `tolerance_pct: 5`
keeps an ordinary text edit from failing CI, and a stale entry fails as
loudly as a new violation so the list shrinks as part 2 lands.

**Part 2, re-chunk the clear parser failures only**: Aeschylus
*Agamemnon* (eng), Hobbes *De Cive* and *Leviathan* (lat), Epictetus
*Discourses* (eng, where **four** chunks hold 97% of the text — see the
correction below). The Aquinas commentaries are **out of scope** — their
coarseness is a real structural level, and changing it is a
chunking-design decision, not a bug fix.

**Corrected 2026-08-08 while implementing #176's baseline.** This plan and
#176 both say "one chunk holds 97% of the English *Discourses*", from the
issue's `max=560,187`. No chunk that large exists, anywhere in the corpus:

```
$ sqlite3 data/index.sqlite "SELECT max(length(text)) FROM chunks"
151427
```

The work has 85 chunks (not 81) and its four largest are 151,427 /
146,461 / 131,035 / 129,821 = 558,744 characters, 97% of its 573,263 — so
the *proportion* holds and the *singular* does not. The earliest snapshot
on disk, `data/snapshots/20260808T013610Z-…`, already reads 85 / 151,427,
so this is not recent drift. Consequences, both material:

1. A part-2 fix verified by "the mega-chunk is gone" would have declared
   success with three 130,000-character chunks still in place.
2. The granularity baseline would have been pinned at 560,187 — a ceiling
   3.7× the real maximum, so a genuine regression up to half a million
   characters would have passed the gate silently. It is pinned at 151,427.

Corrected on the issue as well.

Part 2 is an operator job needing its own session:

1. `scripts/snapshot-db.sh chunk-regranularize`
2. Measure churn by aligning parser output **positionally**. Never join
   before/after on `section` — it repeats per book and inflated a previous
   measurement 20×.
3. `minerva index --incremental --corpora <those>`
4. `minerva embed` (incremental by default), then `terms lemmatize`.
   **Corrected 2026-08-08: this step used to read "`--n-process 1` for
   `lat` until batch 2 lands".** Batch 2 has landed (PR #286), so the
   default `--n-process 4` is now correct for every language —
   `Lemmatizer._safe_n_process` (`src/minerva/lemmatize.py:560`) probes
   the payload before entering the pipe and downgrades to 1 with a notice
   on stderr where spawn cannot pickle it. Passing `--n-process 1` by
   hand now just makes the pass slower for no reason.
5. Full refs rebuild: rules, then `--strategy embed-verify`, then
   `--strategy llm-verify`. Source-side chunk churn invalidates anchors;
   `refs build` alone is not enough.
6. **Remove each re-chunked pair from `granularity.known_coarse` in
   `data/authors/manifest.yaml`.** The gate fails on a stale baseline
   entry as loudly as on a new violation, so a work that has been fixed
   but left on the allowlist breaks `make check-authors` — which is
   deliberate, and is what keeps the list shrinking. Keys are
   `author|title|lang`.
7. `make generate-authors` and commit, including the regenerated
   `data/authors/chunk_granularity.json`.

**Status, 2026-08-08: part 1 landed in PR #292; part 2 has not.** This is
the one place the document records state, against its own rule at the top,
because the open-issue list cannot express it: #176 is open, and reading
only the issue list would suggest the gate still needs building. Nothing
else here is tracked twice.

Part 1 carried `Refs #176`, so the issue is still open by design. Part 2's
PR is the one that should carry the closing keyword for it.

**Written that way on purpose, and the reason is worth reading.** An
earlier revision of this line spelled the keyword out next to the issue
number. That sentence went into a squash-merge commit message, GitHub's
parser read the keyword out of the surrounding prose — backticks are no
protection — and closed #176 on the spot, three minutes after the same
paragraph explained that it must stay open. Reopened by hand. Never put a
closing keyword adjacent to an open issue's number in any text that can
reach a commit message, including this document.

---

## Batch 5 — perseus scraper verification (#151, #152)

**Landed 2026-08-08.** Both issues closed; four new issues filed
(#297–#300) and corrections recorded on both. The measurements are in the
PR body and in each script's docstring; what follows is the plan as
written, annotated where it was wrong.

Both hold values written in #149 that were never checked against live
pages. Both scripts are manual one-shots nothing imports, and both raised
`NameError` before #149, so neither can have contaminated the corpus
through this path. `perseus/**` is coverage-excluded, so no Sonar gate
applies.

**Confirmed: no contamination, on every path checked.** The committed
`deutsche_ideologie.txt`, the six PG-DE files and all 14 Cicero Latin
files carry none of the chrome the broken skip-sets let through, and the
live index has none of it either. The defect was an *inert guard*, not a
dirty corpus.

**Corrected while implementing — `data/*` is gitignored, so "fetch the
missing work" is an operator action, not a commit.** The plan and #151
both describe fetching `de_officiis_lat.txt` as filling a gap in
`data/cicero/raw_la/` (15 declared, 14 present). It does — but in the
*local* data tree only:

```
$ git ls-files data/cicero | wc -l
0
$ git check-ignore -v data/cicero/raw_la/de_officiis_lat.txt
.gitignore:13:data/*	data/cicero/raw_la/de_officiis_lat.txt
```

So the file cannot ride along in the PR, CI cannot verify it, and a fresh
clone will not have it. Had this been trusted, the batch would have been
reported as "gap filled" on the strength of a file no reviewer could see.
The work is real and done locally (715 lines, 237,829 bytes, three Libri,
ending at the true `[121] Habes a patre munus, Marce fili`); it is staged
for the next ingest on that machine, and re-fetching it elsewhere is one
`--only` invocation.

- **#152** — fetch one page each from projekt-gutenberg.org (Marx) and the
  archived mlwerke.de `me03_NNN.htm`, inspect what `_extract_paragraphs`
  returns, and confirm or extend `_SKIP_CLASS_TOKENS` in
  `perseus/download_marx_pgde.py` and `perseus/download_marx_archive.py`.
  Expect layers: the Kapital MEW re-source found three (site chrome,
  Wayback wrapper, intra-file duplicate paragraphs). If the wrapper needs
  more than class tokens, note that in the docstring rather than widening
  the set — `"footer"` and `"navbar"` are already generic enough to eat
  real content.

  **Measured: worse than "some tokens are stale". Of the eleven tokens
  across the two scripts, exactly one matched anything.** All seven in
  `download_marx_archive.py` matched **zero** elements on all three of
  its sources, and three of four in `download_marx_pgde.py` did too
  (`site-header` was the only live one). The reason no widened class set
  can fix the wayback half: the toolbar carries **no class at all** — it
  is keyed on `id` (`id="wm-ipp"`, `id="donato"`). The guidance above was
  right that the wrapper needs markers beyond class tokens, and the
  answer was `skip_id_tokens` plus web.archive.org's own
  `<!-- BEGIN/END WAYBACK TOOLBAR INSERT -->` boundary comments, because
  attribute skipping alone still leaked — see #297.

  The predicted third layer was there: PG-DE renders each chapter body
  **twice**, text-identical, so the pre-fix parse emitted every Marx
  paragraph twice. Taking the body's own container
  (`div.book-reader__chapter-content-wrapper`) both de-duplicates it and
  survives WordPress theme churn, which enumerating chrome classes does
  not — after widening the set to every chrome class actually present,
  four paragraphs still came through.

  And the caution about generic tokens was well aimed: `sidebar` would
  have been harmless only by luck, since PG-DE's one `sidebar`-ish token
  is `no-sidebar` **on `<body>`** — a substring match there empties the
  document. Token matching is exact per whitespace-split token; there is
  now a test pinning that.
- **#151** — fetch the one genuine gap, `de_officiis_lat.txt` (15 declared
  works, 14 present), which exercises the multi-Liber path for real.
  Dry-run the other 12 works **to a scratch directory** and diff. Decide
  and encode whether per-Liber page titles and Arabic section markers are
  matched or deliberately diverged from; `_ROMAN_ONLY_RE` already filters
  the Roman ones and the Arabic are the same class of artifact.

  **Decided and encoded: filter the markers, and do *not* touch the
  titles.** `_ROMAN_ONLY_RE` was `^[IVXLC]+$`, which caught only the bare
  form — 18 of the 543 markers present across a full 15-work re-fetch,
  3%. The dotted Roman form (`XIII.`) is the commonest at 381, Arabic adds
  144, and De re publica carries 46 `(*****)` lacuna sigils. The
  committed files contain **zero** of any form, so the lost original
  filtered them all. The widened filter also had to be applied to the
  root page, not just sub-pages, which is where the 18 survivors were.
  Result: `de_amicitia` went from 70.5% to **100.0%** line-identical,
  `topica` stays 100%, and 11 of 14 works are now ≥97%.

  **Corrected: #151's "per-Liber page titles absent from the
  reconstruction" is false, and acting on it would have been actively
  harmful.** The reconstruction emits them correctly wherever the source
  still has them — `de_legibus` produces `M. TVLLI CICERONIS De legibus -
  Liber I` and `- Liber II` exactly as committed. Only De natura deorum's
  Liber II and III are missing, and those sub-pages now contain no
  `M. TVLLI` string at all upstream; the committed file preserves titles
  la.wikisource has since deleted. Had the issue been trusted, the fix
  would have synthesised per-Liber titles — fabricating source text, and
  injecting titles into the ~10 works that never had them, churning their
  `chunk_id`s to "fix" two lines in one work.

  Also worth not re-deriving: the committed Latin files are
  **post-cleanup** artifacts (`scripts/clean-cicero-chrome.py` strips a
  title/breadcrumb header after the fetch), so a raw scraper-vs-committed
  diff conflates two transformations.

**Do not re-run either script over the committed corpus.** Residual
differences would churn `chunk_id`s and cost those works their embeddings,
lemmas and cross-references. Byte-identity is unreachable in principle —
la.wikisource has changed since the May 2026 fetch — so the target is
"correct and structurally stable", not "reproduces the old bytes".
Honoured: every fetch in this batch went to a scratch `--data-root`, and
nothing was written under `data/` except the one missing work.

**One process note worth keeping.** A half-finished version of the
void-tag fix — guarding `handle_starttag` but not `handle_endtag` — turned
a latent bug into an active one, letting la.wikisource's `ws-noexport`
header chrome (`EPUB MOBI PDF RTF TXT`, `fons: incognitus`) into 15 of 15
Cicero files. The original code leaked none of it. The new fixture test
for the self-closed `<br/>` case is what caught it, before any of it
reached `data/`. Asymmetric guards on a paired counter are the failure
mode; test both halves.

Second process note: a background dry-run silently did nothing because
the backgrounded shell did not inherit an earlier `cd`, and
`grep -rl` over the missing output directory returned "0 chrome, 0
markers" — a clean bill of health measured against an empty set. Check
that a verification actually ran over files that exist before believing
its zero.

---

## Batch 6 — named-passage index (#182)

Two verified instances: the divided line (Politeia 509d–511e) and Meno's
slave boy (Menon 82b–85b). Both fail the same way — the query names no
work, and the passage is known by words its text never contains.

Two constraints already established on the issue, both of which hold:

- `terms` / `term_occurrences` is the **wrong** vessel. It is a
  lemma-keyed lexical glossary anchored on character offsets; "the divided
  line" has no lemma, no `source_form` in any source language, and no span
  to anchor to.
- Anything keyed on a surrogate id rots. `works.id` is reassigned by
  `--reset` (#193), and tables outside the preservation path get wiped
  (#192) — which is why `terms` is empty today despite a curator having
  authored nine Aristotle entries.

**Follow the `work_aliases` pattern** (migration 0025, issue #195). It was
built for this class of problem and satisfies both constraints: the data
lives in code (`src/minerva/authors/work_aliases.py`) keyed on the natural
key `(author, works.title)`, and is re-materialized into the DB on every
index run, so it cannot rot and cannot be wiped.

- **Phase 0 — measure before building.** `work_aliases` already resolves
  an arbitrary string to a `work_id`, and `detect_work`'s matcher requires
  every significant token of the name to appear in the query. On a scratch
  branch, add "the divided line" → Politeia and "slave boy" → Menon as
  aliases, then re-measure both queries through the real chat ordering.
  #182's own numbers suggest work-level scoping alone reaches rank ≤3
  (work-scoped queries already rank the divided line at 3), in which case
  the table's remaining value is semantic honesty plus section ranges for
  citation, not retrieval. Decide against that number, not in advance.
- **Phase 1** — `named_passages`: migration `0028_named_passages.sql`
  (0027 is taken by batch 2), source of truth
  `src/minerva/authors/named_passages.py` keyed on `(author, title)` →
  `(label, section_start, section_end, tradition)`, materialized in the
  index run next to `work_aliases`.
- **Phase 1 hook** — resolve labels where `_best_title_matches`
  (`src/minerva/agent/detect.py:190`) runs, so the same conservative
  token-matching applies and #194's corpus fallback gets it for free:
  "the divided line" with nothing else named then resolves both corpus and
  work in one step.
- Keep the section range **out of the retrieval filter** for now.
  `work_id` scoping already exists end to end; a section-range filter is a
  second change the measurements do not yet call for. Use the range for
  citation and display.

Do not curate broadly on the first pass. Seed the four labels the issue
names — divided line, Meno's slave boy, Kant's "Copernican revolution",
Hegel's "master and slave" — and measure the last two, which have never
been tested. Curation scope is a decision for after those numbers.

---

## Batch 7 — ruff reformat (#136 fact 2), last

Fact 1 is already fixed by #230: the `[tool.ruff.format]` exclusion is in
`pyproject.toml:148-156`, so `make format-py` no longer breaks
`make check`. Fact 2 is the drift plus the missing gate — **130 files**
would be reformatted as of 2026-08-08, up from 122 in the issue's audit
comment and 109 at filing. Draft PR #229 carries the full reformat and
fails Sonar at `new_coverage 64.9%` and
`new_duplicated_lines_density 3.7%`.

### Do not merge #229 as it stands

Re-checked 2026-08-08 after batch 4, because "BLOCKED" in a PR title is a
claim like any other. It holds — the gate is genuinely red, not stale:

```
$ gh pr checks 229
SonarCloud Code Analysis   fail   ...      # every other check passes
```

| condition | threshold | actual |
|---|---|---|
| `new_coverage` | ≥ 80 | **64.9** |
| `new_duplicated_lines_density` | ≤ 3 | **3.7** |

SonarCloud is a **required** check (#158), so merging this would mean an
admin bypass of a red gate — `enforce_admins` is false, so it is possible,
and it is still the wrong move. Two reasons:

1. **It is superseded by this batch's own plan.** #229 is the single
   130-file reformat; the tranche cut below exists precisely because that
   shape cannot pass. Merging it whole would land the version the plan was
   written to replace, and forfeit the one thing the tranches buy —
   knowing which files are safe.
2. **Its numbers predate batches 1–4** (last analysed 2026-08-06). Those
   batches added tests to several of the below-80% files, so 64.9% is
   stale in the *favourable* direction. Re-measure before deciding
   anything, including whether to close #229 in favour of tranche PRs.

**The drift keeps growing while this waits**, which is the argument
against deferring it forever. Measured on `main` at `38554e1`, after
batch 4:

```
$ ./.venv/bin/ruff format --check src tests | tail -1
136 files would be reformatted, 245 files already formatted
$ ./.venv/bin/ruff format --check src | grep -c '^Would reformat'
70
```

136 files / 70 under `src/`, against the 130 / 69 recorded above the same
day — every batch that adds a file adds to it.

**First move for whoever picks this up**, before writing any code:
`git rebase origin/main` on `fix/136-enforce-ruff-format`, then
`make check DIFF_BASE=origin/main` and read `check-diff-coverage`. That
evaluates the same thing Sonar does (#255), so the current coverage
position is knowable locally without burning a CI run — and the tranche-1
file list should be cut from *that* measurement, not from the 48/21 split
recorded below, which is itself from 2026-08-08.

**Separate PRs do work, but the cut is by file coverage, not by
directory.** Splitting by directory was already tested and cannot help:
`sonar.tests=tests` means the test files never counted toward coverage, so
the `src/` files were always the whole problem. Splitting by coverage is a
different cut, and the numbers are favourable:

- 69 `src/` files need reformatting.
- **48 are already at ≥80% coverage** on `main`. Reformatting those should
  clear the new-code gate, because the lines that become "new" carry their
  file's existing coverage.
- **21 are below 80%** and stay blocked: `lemmatize.py` (22.7%),
  `cli/terms/lemmatize.py` (68.4%), `llm.py` (70.6%), `refs/schema.py`
  (64.1%), `refs/spec.py` (75.9%), `reader/queries.py` (78.7%), the
  `authors/*_works.py` data modules at 0%, and the `corpus/split_*.py`
  scripts.

So:

- **Tranche 1** — the 48 files at or above 80%. Before pushing, run
  `make check DIFF_BASE=origin/main` and read `check-diff-coverage`: it
  evaluates the same thing Sonar does (#255), so the gate can be predicted
  locally without burning a CI run. Watch duplication too — #229 hit 3.7%
  against a 3% threshold and whether a smaller tranche clears it is
  unmeasured.
- **Tranche 2** — the 21 below-80% files, after batches 1–4, which add
  tests to several of them (`lemmatize.py`, `cli/terms/lemmatize.py`,
  `refs/schema.py`). Re-measure before assuming any specific file has
  crossed; batch tests may not lift a 22.7% module to 80%.
- **Residue** — whatever remains below 80% needs the gate decision the
  issue already frames: a Sonar-side exemption, or a visible admin push
  (`enforce_admins` is false). That is not a code problem.
- **The `ruff format --check src tests` gate lands with the final
  tranche.** It cannot be added while any file is unformatted, so #136
  fact 2 does not close until then; earlier tranches carry `Refs #136`.

One caveat to state in the PR: file-level coverage ≥80% is a strong
predictor, not a guarantee. Sonar measures the *changed lines*, and a
well-covered file's reformatted lines could still be its uncovered ones.
`check-diff-coverage` settles it per tranche before pushing.

---

## Verification

Per PR:

```
make check          # after every edit, not only at the end
gh pr view <n> --json closingIssuesReferences \
  --jq '[.closingIssuesReferences[].number]'      # must be non-empty
```

Per batch, the end-to-end check:

1. Re-run #276's uniqueness audit — the 2 ties resolve by cosine among the
   tied pair, the 121 unique rows unchanged. Force an `LLMError` and
   confirm `backend_errors=1, parse_errors=0`.
2. `minerva terms lemmatize --lang lat --skip-aggregate` at the default
   `--n-process` completes (or warns and falls back) instead of hanging.
   Run an incremental pass twice; the second reports 0 candidates, not 419.
3. Create a `reference_targets` row with no xref, `index --reset`, confirm
   it survives. `refs_scan_state` orphan count is 0 after an index run.
4. `Non occides.` and `Ego et Pater unum sumus.` retrievable by phrase; a
   "Nietzsche" query still free of letter signatures; the granularity gate
   fails on an injected oversized chunk and passes on `main`'s 753.
5. `de_officiis_lat.txt` present and structurally consistent with its
   siblings; scratch-dir diffs for the other 12 reviewed; nothing written
   into `data/`.
6. Both measured queries reach the target passage corpus-wide with only
   the label in the query; `index --reset` does not lose the table.
7. `ruff format --check src tests` exits 0, and `make format-py &&
   make check` both pass.

Before any DB-mutating step in batches 3, 4 (part 2) or 6:
`scripts/snapshot-db.sh <reason>`. For any cleanup running more than one
`UPDATE`/`DELETE`, preview inside `BEGIN; … ROLLBACK;` with verifying
`SELECT`s first. See [MEMORY.md](MEMORY.md) for the operator rules.
