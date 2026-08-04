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
