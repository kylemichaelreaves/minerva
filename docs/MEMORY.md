# Operator memory — binding rules

Short, enforceable rules for corpus and database work. Referenced from
[`INGESTION.md`](INGESTION.md). These are not suggestions.

## snapshot-before-destructive-ops

Always snapshot before any operation that mutates `data/index.sqlite` or
that you cannot trivially undo:

```sh
scripts/snapshot-db.sh pre-<short-reason>
```

Writes `data/snapshots/<timestamp>-<reason>/` with copies of `index.sqlite`
and `chunks.jsonl` (when present). Required before:

- `minerva index` (especially `--reset`)
- `minerva refs build` with LLM verify
- Manual SQL cleanups on the corpus DB

The auto-snapshot inside `cmd_index` is a fallback; the manual snapshot
from pre-flight is the primary recovery point.

## reingest-wipes-lemmas

`minerva index` rebuilds chunk rows. The `chunk_lemmas` table is tied
to chunk IDs.

Since Phase 1d (2026-05-29), `cmd_index` snapshots the live DB to
`.bak.pre-index` and restores `chunk_lemmas` afterwards — so a
**content-stable** re-index preserves every lemma keyed by a surviving
chunk_id; an orphan sweep drops rows whose chunk_id changed (i.e. text
changed). When a splitter update alters every chunk_id in a corpus
(re-OCR, re-clean), the post-index re-lemmatize is essentially a
fresh pass for the affected chunks only.

After every `minerva index`:

```sh
.venv/bin/minerva terms lemmatize --lang <lang>   # repeat per language tier
```

`terms lemmatize` is incremental — chunks already in `chunk_lemmas`
are skipped, so a content-stable re-ingest's lemmatize is a few
seconds, not hours. Pass `--all` only to force a full re-pass after
swapping the lemmatizer backend (e.g., Stanza → LatinCy).

## reingest-wipes-cross-references

Cross-reference rows used to be wiped on re-ingest. Migration 0013 plus
the shadow-address rebind in `store.py` preserves verified xrefs across
re-ingest **when chunk IDs stay stable**.

Snapshot discipline is still mandatory: if a splitter change alters
`chunk_id` hashes, rebind cannot recover orphaned xrefs. See
`transactional-preview-for-multistatement-sql` before bulk SQL fixes.

## reingest-wipes-the-term-glossary

`index --reset` used to destroy all five `terms*` tables outright — they
were in neither the snapshot probe nor the restore list (#192). Since
that fix, `cmd_index` restores them **after** `insert_chunks`, rebinding
`edition_id` / `translation_id` through natural keys (author + title +
edition name / translator name) rather than copying the surrogate ids,
which a `--reset` reshuffles (#193).

Two consequences for operators:

- A DB carrying nothing but curated terms now triggers the pre-index
  snapshot on its own; it no longer needs xrefs/lemmas/embeddings to be
  backed up.
- Occurrences are dropped when their chunk's text changed (the stored
  character offsets no longer address anything) or when their edition
  left the corpus. Both are reported with counts on stderr. Re-run
  `minerva terms import data/glossary/<file>.yaml` to re-find them —
  the terms themselves (the curator prose) survive either way.

## reingest-wipes-the-rules-scan-cache

`refs_scan_state` is the skip cache for `refs build --strategy rules`:
one row per chunk already scanned, with the `text_hash` and the
`rules_hash` it was scanned at. `index --reset` used to discard all of
it — 428,606 markers — for
the same reason the glossary was lost, absence from the snapshot probe
and the restore list (#288). Since that fix it is snapshotted and
restored like `chunk_lemmas`, and stderr reports how many markers came
back.

What this means in practice: after a **content-stable** `--reset`, the
next `refs build --strategy rules` skips the corpus instead of
re-scanning it. That is a cost saving only — rescanning was always
idempotent — but the pass it saves is a full-corpus one.

Three things still invalidate a marker, all deliberately:

- Its chunk did not come back (the text changed enough to change the
  content-hashed `chunk_id`). The end-of-index orphan sweep drops it and
  says so (#264).
- Its chunk came back with the same id but different text — possible
  because `chunk_id` hashes only `text[:120]` (#285). The `text_hash`
  comparison in the skip predicate catches this one, so the chunk is
  re-scanned.
- The **rules** changed rather than the text. `rules_hash` is a
  fingerprint of the compiled rule set for the chunk's author, compared
  alongside `text_hash` (#287). Invalidation is per author, so a Renan
  edit re-scans Renan's ~20K chunks and leaves the other 408K markers
  alone — the distinction that makes this worth more than the
  `--rescan-all` it replaces.

  The fingerprint covers rule fields, class-level config and the module
  constants a rule reads (#287), plus the logic of every method the rule
  can reach (#304) — hashed from the AST, so a reformat or a rewritten
  docstring moves nothing. `--rescan-all` is no longer needed for any
  rules edit; it stays as the escape hatch for a fingerprint that is
  itself wrong. `refs/rules/fingerprint.py` states what goes in.

  Markers written before #287 carry `rules_hash IS NULL`, which
  compares unequal to every fingerprint — one rescan per author, then it
  settles. Same for a marker restored from a `.bak.pre-index` snapshot
  taken before migration 0028.

## transactional-preview-for-multistatement-sql

For any multi-statement cleanup on `index.sqlite`:

```sql
BEGIN;
-- your UPDATE/DELETE statements
SELECT ... AS verify;
ROLLBACK;
```

Inspect `verify` in the output. Only after it looks right, re-run with
`COMMIT` (or run the same statements outside a rolled-back transaction).

Never commit a bulk xref or chunk cleanup without a preview pass.

## Related pitfalls (see INGESTION.md)

- **LLM verify retries:** `llm.py` retries transient failures; re-run
  `refs build --strategy llm-verify` — idempotence skips rows already
  containing `llm` in `source_method`.
- **Chunk-id stability:** Do not change existing splitter hashing when
  adding a new author; only add new splitter modules.
