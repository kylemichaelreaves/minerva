# Orthographic normalization for search — long-term plan

> **Status (2026-06-02): the long-term fix below is SHIPPED** (option B1 —
> normalized FTS, German only). Migration `0021_chunks_fts_norm` adds
> `chunks.text_norm` + the `chunks_fts_norm` index; `retrieve._bm25_search`
> fuses exact + normalized matches; `orthography.canonicalize` is the shared
> fold. The short-term query-expansion stopgap was *replaced* by this (one
> mechanism, not two). Remaining future work: extend canonicalizers to
> `grc`/`lat`/`heb`/`ara` (Phase 4 below). Work-level retrieval scoping
> (`work_id` filter + `agent.detect_work` auto-detection) shipped alongside.

Retrieval misses passages when the spelling a user types diverges from the
spelling the ingested edition stored. The triggering case: a search for
Nietzsche's historical *Mißrathenen* (1887, `-th-`) returned nothing because
our zeno.org edition modernized it to *Mißratenen* (`-t-`). The FTS tokenizer
(`unicode61 remove_diacritics 2`) folds case + umlauts on both sides
symmetrically, so those already match; it cannot bridge letter-sequence
differences (`th`↔`t`, `ey`↔`ei`, `-iren`↔`-ieren`, `ß`↔`ss`, `c`↔`k/z`,
final `-dt`↔`-t`, long-ſ OCR artifacts).

## Short-term fix (shipped)

Query-side, additive spelling-variant expansion, language-scoped.

- `src/minerva/orthography.py` — `search_variants(token, lang)` returns the
  original token plus historical→modern folds (`th→t`, `ey→ei`, `-iren→-ieren`)
  for `deu`.
- `retrieve._sanitize_fts_query(q, fold_lang=...)` OR-expands each token.
- Threaded `fold_lang` through `retrieve.search` → `agent.retrieve_passages`;
  `chat_service` passes the resolved corpus's `original_language_for_corpus`.

Verified on the live index: the *Mißrathenen* query went from **0/8** hits
containing the term to **4/8**.

**Limitations this leaves open** (the reason for the long-term work):

1. **One-directional.** It folds historical→modern, so it helps a historical
   query against a modernized index (zeno Nietzsche/Kant/Hegel/Marx). It does
   **not** help a *modern* query against a *historical* index — e.g. the Luther
   1545 Frühneuhochdeutsch text, where "Mut" should find "Muth". Inserting `th`
   is too ambiguous to do at query time.
2. **Recall-only, query-side.** Variants are OR-ed into BM25; the embedding
   (vector) leg and any phrase logic still see the raw query.
3. **Hand-maintained per-token regex**, easy to drift from the actual corpus.

## Long-term fix: canonicalize both index and query

Normalize **both** the indexed text and the query to a single canonical
orthographic form, so matching is symmetric and direction-independent. A
historical index and a modern query both canonicalize to the same form and
meet in the middle.

### Core idea

One shared function — `orthography.canonicalize(text, lang)` — used in two
places:

- **Ingest:** populate a normalized full-text index from the canonicalized
  text (the human-readable original stays in `chunks.text` for display and
  exact search).
- **Query:** canonicalize the MATCH term with the same function before BM25.

Because both sides pass through the identical fold, `Muth`/`Mut`,
`Mißrathenen`/`Mißratenen`, `thun`/`tun` all collapse to one searchable token
regardless of which side is historical.

### Approach options

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| **B1. Normalized FTS table/column (recommended)** | New `chunks_fts_norm` FTS5 populated with `canonicalize(text, lang)`; query the folded MATCH term against it | Pure stock SQLite; symmetric; keeps original `text` intact for display + exact search | Extra index (~text-size storage); full rebuild; keep in sync on insert |
| B2. Custom FTS5 tokenizer | A tokenizer that folds during tokenization | No extra column; canonical tokens natively | FTS5 custom tokenizers need a C extension / `apsw`; not reachable from stdlib `sqlite3`. Heavy dep. Rejected. |
| B3. Fold the existing index in place | Index canonical text into the current `chunks_fts` | No new table | Loses exact-spelling search; couples display + search; harder to evolve rules |

Recommend **B1**: an additional normalized FTS alongside the existing exact
one. Fuse the two BM25 signals (exact match scores higher, normalized match
catches spelling variants), mirroring the existing BM25⊕cosine fusion in
`retrieve.search`.

### Phases

1. **Canonicalizer.** Promote `orthography.py` to a whole-text
   `canonicalize(text, lang)` plus the existing token helper, sharing one rule
   table. Expand `deu` rules (`th→t`, `ß→ss`, `ey→ei`, `-iren→-ieren`,
   `c→k/z` in native words, final `-dt→-t`, long-ſ→s). Golden tests of
   historical/modern pairs mined from the corpus. Precision guard: assert
   common Greek/Latin loanwords (Theater, Theologie, Mathematik) don't collide
   with real native tokens after folding.
2. **Schema + backfill.** Migration `NNNN_chunks_fts_norm`: create the
   normalized FTS5 table; backfill from existing `chunks.text`. Wire the
   `store` insert path and `minerva index` to populate it (incremental index
   already exists — extend it). Reuses the snapshot-before-destructive-ops flow.
3. **Retrieval.** `_bm25_search` runs a second MATCH against the normalized
   table with `canonicalize(query, lang)`, fused with the exact match. Tune the
   exact-vs-normalized weight. Keep behavior identical when no canonicalizer is
   registered for the language.
4. **Language coverage.** Add canonicalizers incrementally where they pay off:
   `grc` (polytonic accent/breathing normalization, final sigma), `lat`
   (u/v, i/j, æ/ae), `heb` (final forms, niqqud stripping), `ara`
   (alef/hamza variants, tatweel). Each gated and tested independently.
5. **Retire the stopgap.** Once the index is normalized, the short-term
   query-side `fold_lang` expansion is redundant; keep it as a thin
   belt-and-suspenders fallback or remove the plumbing.

### Cost & risk

- **Storage:** one extra FTS index ≈ size of the text column (small next to the
  ~6.6 GB dominated by embeddings).
- **Rebuild:** a full FTS backfill, folded into the next `index` run.
- **Precision:** over-folding can merge distinct words. Mitigation: keep the
  exact FTS as the primary signal and fuse, rather than replacing it; validate
  with a golden recall/precision set per language before enabling.
- **Maintenance:** rules live in one module with tests; pairs sourced from the
  corpus, not invented.

### Validation

Build a small golden set of (historical, modern) query pairs per author
(Nietzsche zeno vs. original; Luther 1545 vs. 1912; Kant), assert each pair
retrieves the same target chunks, and track recall before/after. Re-run the
live *Mißrathenen* check as a regression anchor.
