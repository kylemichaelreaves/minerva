# Phase 5 plan — distributions from the batch pipeline

Scope: per-item duration and token counts from the NLP pipeline, keyed by
language and engine, as a **distribution across the corpus**. Nothing about
the Breakdown surface, which is a separate change.

**No code has been edited.** Everything below is a proposal.

---

## 0. Three corrections before anything is built

**1. My own audit pointed this at the wrong subsystem.**
`notes/metrics-audit.md` puts Phase 5 next to `ingest/registry.py:612` and
`ingest/parallel.py:86`, because that is where the existing *timing* code
lives. But `ingest` parses sources into chunks: it runs no NLP and counts no
tokens. The brief asks for durations *"labeled by language and NLP pipeline"*
with *"token counts"* — neither exists in `ingest`.

Both do exist in **`lemmatize`**. That is the pipeline this phase is about.

**2. The unit is a CHUNK, not a document.** The brief says "per-document".
`lemmatize` iterates chunks —

```
cli/terms/lemmatize.py:90
    "SELECT cf.chunk_id, cf.text FROM chunks_full cf ..."
```

— and there is no document unit anywhere in that path. A *work* is the nearest
document-like grouping, and chunks are what actually get processed. The plan
uses the chunk and says so, rather than inventing a document boundary to
satisfy the word.

**3. "NLP pipeline" is real, and it is not what my design brief guessed.**
`notes/metrics-ui-design-brief.md` shows `lat / latincy` and `grc / stanza`.
`latincy` is not a value anything produces. What exists is
`Lemmatizer._backend`, already set to `"spacy"` or `"stanza"`
(`lemmatize.py:644, 733`), plus the model actually loaded:

```
deu → spaCy de_core_news_sm
grc → spaCy grc_dep_web_sm     (Stanza grc as fallback)
lat → spaCy la_core_web_sm     (Stanza la  as fallback)
```

The label must carry **which engine actually served**, because the fallback
means the same language can be either on different machines — and a
distribution that silently mixes spaCy and Stanza timings for `lat` would be
worse than no distribution. `(lang, backend, model)` is the real key; the
brief's `(lang, pipeline)` is that flattened.

## 1. The constraint this phase collides with

> *"Don't instrument inside hot loops — phase boundaries only."*

**A chunk is the loop.** There are **428,982 chunks**:

```
deu 114,537   eng 85,244   fra 73,696   lat 69,219
grc  56,837   heb 23,213   ara  6,236
```

So per-chunk timing is per-iteration timing, and the constraint as written
forbids exactly what the phase asks for. The tension is real and the way out
is the cost, not the principle: two `perf_counter` calls are ~46 ns, against
a per-chunk NLP cost measured in **milliseconds**. That is a ratio of roughly
1:100,000.

I will measure it rather than assert it, and the plan's exit condition is a
number, not an argument. If it is not negligible the answer is sampling —
time every Nth chunk — which changes the distribution's precision but not its
shape.

## 2. Nothing from the request layer reaches this

`Recorder`, `Span`, `sub_span` and `current_span()` are all built on a
`ContextVar`, and **none of them cross a process boundary**:

- `ingest` runs a `ProcessPoolExecutor` (`ingest/parallel.py:173`).
- `lemmatize` uses spaCy's own `Language._multiprocessing_pipe`
  (`lemmatize.py:935`).

So Phase 5 cannot reuse the request machinery, and should not try. It
accumulates in whichever process does the work and returns the histogram
through the result path that already exists — `parallel.py` already hands a
dict back per source.

This also means there is **no request id** to key on, which is correct: this
is not a request.

## 3. Storage

A **new table** in `data/metrics.sqlite`, reusing `histogram.py` unchanged:

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    at        REAL    NOT NULL,   -- when the run finished
    pipeline  TEXT    NOT NULL,   -- 'lemmatize'
    lang      TEXT    NOT NULL,
    backend   TEXT    NOT NULL,   -- 'spacy' | 'stanza' — which ACTUALLY served
    model     TEXT    NOT NULL,   -- 'la_core_web_sm', ...
    kind      TEXT    NOT NULL,   -- 'duration' | 'tokens'
    count     INTEGER NOT NULL,
    sum       REAL    NOT NULL,
    min       REAL    NOT NULL,
    max       REAL    NOT NULL,
    b0..b13   INTEGER NOT NULL DEFAULT 0
);
```

**Not `request_timings`.** That table's vocabulary is route, method and
status, and this has none of them — the design brief says so explicitly, and
borrowing it would make `label` mean two different things.

**One row per (run, lang, backend, model, kind)**, not per chunk. 428,982
chunks become a handful of rows, which is the whole point of folding into
histograms: a distribution across the corpus, not a log of individual runs.

`kind='tokens'` reuses the same bucket edges for token counts. They are not
milliseconds, and the edges are powers of two either way, so the axis reads
the same — which the design brief argues for on the grounds that a reader who
has learned one has learned both.

## 4. What it answers

Today `lemmatize` prints `{done}/{total} chunks` and a final line. After this,
the question *"is `grc` slow because Stanza fell back, or because Greek is
hard"* is answerable, because `backend` is in the key. So is *"which language
has the long tail"*, which is what a p99 across 56,837 chunks is for.

## 5. Risks

- **Sampling changes what p99 means.** If overhead forces it, the stored
  `count` must be the sampled count, not the total, or every rate derived
  from it is wrong by the sampling factor. Pinned by a test.
- **A run that crashes mid-way** should still write what it measured —
  otherwise the expensive runs, which are the interesting ones, are the ones
  that record nothing.
- **Fallback mid-run.** If spaCy fails and Stanza takes over, the key changes
  underneath the accumulator. Two rows, not one mislabelled row.
- **`metrics.sqlite` may not exist** on a machine that has only ever run the
  CLI. Creating it is fine; failing the lemmatize run because metrics could
  not be written is not — same swallow-don't-fail posture as `Recorder`.

## 6. Build order

1. The accumulator: `(lang, backend, model) -> histogram`, fed per chunk,
   with the token count alongside. Pure, no I/O, unit-tested.
2. `pipeline_runs` table + writer, reusing `histogram.bucket_index`.
3. Wire into `lemmatize`, including the fallback-mid-run case.
4. Overhead measurement on a real slice, reported as a ratio against per-chunk
   NLP cost. **Sampling only if that number demands it.**
5. A read path — CLI output at minimum. A UI surface is Breakdown's job, not
   this phase's.

## Built — and the unit changed under measurement

**Per-chunk duration is not obtainable from this pipeline.** `batch_pipe`
delegates to spaCy's `nlp.pipe(batch_size=64)`, so time-since-last-yield is
queue drain, not work. Measured over 400 `lat` chunks:

```
  TRUE mean per chunk :    2.598 ms   (total 1039 ms / 400 chunks)
  per-iteration p50   :    0.115 ms   <- what the planned timing reports
  iterations over 10ms:    7 of 400  carrying 96% of the total
```

A per-chunk p50 would have understated by **22.6x**. The shipped design,
chosen by the repo owner from the corrected options:

- **durations per WINDOW of N chunks** (`observe_windows`), because windows
  partition the stream, so they sum to the run and throughput is exact;
- **token counts per chunk**, which are unaffected by batching.

Real output, 512 `lat` chunks:

```
  lat/spacy/la_core_web_sm   batch_duration  batches=8  chunks=512
      p50 185.7ms  p95 400.0ms  throughput 331.2 chunks/s
  lat/spacy/la_core_web_sm   tokens          chunks=512
      p50 16.5  p95 29.4  max 49 tokens
```

331 chunks/s reconciles with the 2.598 ms/chunk measured independently.

## Open question

**`ingest` as well, or `lemmatize` only?** `ingest` already prints per-source
timings to stderr and returns them in a dict; folding those into the same
table would give one place to look, but its unit is a *source*, it has no
NLP engine and no tokens, so three of the five key columns would be empty or
invented. My recommendation is **lemmatize only** — and if ingest timings are
worth persisting, that is a separate, differently-shaped change rather than a
column-compatible one.
