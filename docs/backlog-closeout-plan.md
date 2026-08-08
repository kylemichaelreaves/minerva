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

- In `Lemmatizer.batch_pipe` (`src/minerva/lemmatize.py:431-457`), wrap
  the `nlp.pipe(..., n_process=n_process)` call so `PicklingError` falls
  back to `n_process=1` with a warning. This is the part that turns a
  silent stall into a one-line notice, and it covers any future model with
  the same defect rather than just `lat`.
- Correct the help text at `src/minerva/cli/terms/__init__.py:303-313` —
  "4 is a safe default" is false. Changing the default to 1 is defensible
  but is the lesser fix alone: it leaves `--n-process 4` a trap.

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
- Migration `0027_chunk_lemma_state.sql`.
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
  `chunks.edition_id` and `chunks.translation_id` — scripture is present
  as editions (Vulgate, SBLGNT) *and* as translations (KJV, Luther), so a
  predicate on one silently misses half.
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

**Part 2, re-chunk the clear parser failures only**: Aeschylus
*Agamemnon* (eng), Hobbes *De Cive* and *Leviathan* (lat), Epictetus
*Discourses* (eng, where one chunk holds 97% of the text). The Aquinas
commentaries are **out of scope** — their coarseness is a real structural
level, and changing it is a chunking-design decision, not a bug fix.

Part 2 is an operator job needing its own session:

1. `scripts/snapshot-db.sh chunk-regranularize`
2. Measure churn by aligning parser output **positionally**. Never join
   before/after on `section` — it repeats per book and inflated a previous
   measurement 20×.
3. `minerva index --incremental --corpora <those>`
4. `minerva embed` (incremental by default), then `terms lemmatize`
   (`--n-process 1` for `lat` until batch 2 lands)
5. Full refs rebuild: rules, then `--strategy embed-verify`, then
   `--strategy llm-verify`. Source-side chunk churn invalidates anchors;
   `refs build` alone is not enough.
6. `make generate-authors` and commit, including the new granularity
   snapshot.

Land part 1 with `Refs #176`; close #176 only when part 2's re-ingest is
committed.

---

## Batch 5 — perseus scraper verification (#151, #152)

Both hold values written in #149 that were never checked against live
pages. Both scripts are manual one-shots nothing imports, and both raised
`NameError` before #149, so neither can have contaminated the corpus
through this path. `perseus/**` is coverage-excluded, so no Sonar gate
applies.

- **#152** — fetch one page each from projekt-gutenberg.org (Marx) and the
  archived mlwerke.de `me03_NNN.htm`, inspect what `_extract_paragraphs`
  returns, and confirm or extend `_SKIP_CLASS_TOKENS` in
  `perseus/download_marx_pgde.py` and `perseus/download_marx_archive.py`.
  Expect layers: the Kapital MEW re-source found three (site chrome,
  Wayback wrapper, intra-file duplicate paragraphs). If the wrapper needs
  more than class tokens, note that in the docstring rather than widening
  the set — `"footer"` and `"navbar"` are already generic enough to eat
  real content.
- **#151** — fetch the one genuine gap, `de_officiis_lat.txt` (15 declared
  works, 14 present), which exercises the multi-Liber path for real.
  Dry-run the other 12 works **to a scratch directory** and diff. Decide
  and encode whether per-Liber page titles and Arabic section markers are
  matched or deliberately diverged from; `_ROMAN_ONLY_RE` already filters
  the Roman ones and the Arabic are the same class of artifact.

**Do not re-run either script over the committed corpus.** Residual
differences would churn `chunk_id`s and cost those works their embeddings,
lemmas and cross-references. Byte-identity is unreachable in principle —
la.wikisource has changed since the May 2026 fetch — so the target is
"correct and structurally stable", not "reproduces the old bytes".

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
