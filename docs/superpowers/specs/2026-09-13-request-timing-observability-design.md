# Request timing: record it, bucket it, keep it

**Status:** approved 2026-09-13; storage location corrected 2026-09-13 (see
"Correction" below)
**Issues:** #581
**Related:** #559 (cognitive complexity gate), #547 (frontend test location),
#254 (duplication gate), #573 (local-vs-CI coverage divergence)

The operator wants to see how request latency changes over time. The corpus
grows by ingest, and ingests are precisely the events most likely to move query
latency — #573 re-sourced Hobbes to ~11k paragraph chunks, the Kapital
re-source went 55 chunks to 11,167. Those land weeks apart. Any store that
does not outlive a process restart cannot answer the question being asked.

## Measured

There is no request timing in the server today. `grep -rn
'perf_counter\|monotonic\|elapsed\|duration\|latency' src/minerva/http/`
returns six hits, all unrelated: a rate-limiter window in `server_core.py:100`,
a poll loop in `handlers/translate.py:50-52`, and two prose comments.

Four facts shape the design:

| Fact | Where | Why it matters |
|---|---|---|
| Every route carries a stable `label` | `http/router.py` | The rate limiter already keys on it "because labels are the only stable name a route has" (`server_core.py:38`). It is the correct metric key, already in place. |
| `ServerDeps` carries four SQLite connections | `http/server_core.py:153` | A connection per write concern is the established pattern. A fifth is the idiom, not a new risk. |
| Request paths already write to SQLite | `handlers/chat.py:57`, `handlers/translate.py:104` | Chat persists conversations; translate writes its cache on every miss. Per-request writes are not novel here. |
| `solid-js` is the only runtime dependency | `web/package.json` | Network hand-rolls its visuals (`HeatmapPanel`, `ArcPanel`, `MatrixPanel`). The chart is hand-rolled SVG. |

The four `do_*` methods share a skeleton but diverge in ways that do not
factor cleanly:

| | cross-origin | rate limit | body | response |
|---|---|---|---|---|
| `do_POST` | yes | yes | JSON | 200, or SSE |
| `do_GET` | no | yes | none | 200, or static fallthrough |
| `do_PATCH` | yes | no | JSON | 200 |
| `do_DELETE` | yes | no | none | 204, or custom 404 on falsy |

**`NULL` in a composite primary key silently defeats the upsert.** SQLite does
not enforce `NOT NULL` on a non-integer `PRIMARY KEY`, and an `ON CONFLICT`
target never matches `NULL`. Measured on sqlite 3.50.4:

```
$ .venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE t (bucket INTEGER, label TEXT, span TEXT, count INTEGER,"
          " PRIMARY KEY (bucket, label, span))")
for _ in range(3):
    c.execute("INSERT INTO t VALUES (1,'work range',NULL,1) "
              "ON CONFLICT (bucket,label,span) DO UPDATE SET count = count + 1")
print(c.execute("SELECT count(*), sum(count) FROM t").fetchone())
PY
(3, 3)      # three duplicate rows; counts never accumulated
```

With `''` in place of `NULL` the same loop yields `(1, 3)`. No error either
way. Hence `span TEXT NOT NULL DEFAULT ''`.

### Correction: the index DB is the wrong home

This spec's first draft put the table in `data/index.sqlite` via a migration
`0036_request_timings`. That is wrong, and wrong in a way that would have
silently destroyed the feature's entire purpose.

`minerva index --reset` unlinks the index database outright:

```
src/minerva/cli/index_cmd.py:84       store.reset_db(args.db)
src/minerva/store/schema.py:101-107   for p in (path, path+"-wal", path+"-shm"):
                                          if p.exists(): p.unlink()
```

Not `DROP TABLE` — `unlink`. Every table in that file goes, migration history
included. And a `--reset` re-index is exactly what a re-source performs: it is
the event whose latency impact this feature exists to bracket. Timing history
stored there would be deleted by the very change it was recorded to measure,
with no error and nothing to notice.

The same mechanism wiped 21,751 `cross_references` rows on the 2026-05-29
Hegel-Preface rechunk, which is why `_maybe_snapshot_pre_index` exists.

**Metrics therefore get their own database file**, alongside
`conversations`, `translations` and `concept_cache` — all three of which are
already separate files for related reasons. No migration `0036`; a `SCHEMA`
constant in a new `store/metrics.py`, opened through the same `open_sqlite`
helper the siblings use.

## Hypothesis

*Everything below is a design, not a measurement. It has not been built.*

### Decisions taken

1. **Streaming routes record both** time-to-first-event and total, as two
   `kind` values. TTFE is what the server controls and can fix; total is what
   the operator waited. Recording only total would make `chat`'s p95 a
   measurement of Anthropic's latency, under which a server-side regression
   would be invisible.
2. **Sub-spans ship in v1**, mechanism plus three instrumented hot paths —
   Stanza parse, embed search, LLM call. Whole-request timing says *which*
   route is slow, never *why*, and those three are the costs most likely to
   move after an ingest. Instrumenting everything would inflate the changed-line
   surface the coverage gate applies to, for paths nobody suspects yet.
3. **A new `#/metrics` surface**, wired like `#/network`.
4. **Single local operator.** No auth, no cardinality guard, no rollup job,
   single writer assumed throughout. This assumption is load-bearing; if the
   server ever binds beyond loopback for real use, revisit all four.

### Recording

A context manager at each of the four `do_*` sites, rather than a unified
dispatcher:

```python
with self.deps.metrics.record(label, self.command) as span:
    ...existing body, unchanged...
    span.status = HTTPStatus.OK
```

Unifying the four would mean a function taking four or five boolean flags —
the shape that drives cognitive complexity up, which is the Sonar gate that
blocked #559 at 29 while `check-diff-coverage` stayed green at 91.7%. Two
lines per method keeps complexity flat and is honest about the divergence.

Timing inside `_send_json` is the tempting single-site answer and is wrong: it
has no label, and it serves error and non-routed paths too.

`_send_sse` calls `span.first_event()` once inside its write loop, which is
the only place TTFE is observable.

### Storage

A fifth connection, `metrics_conn`, against its **own database file**
(`data/metrics.sqlite`, overridable via `--metrics-db`), opened by a new
`store/metrics.py` that mirrors `store/conversations.py`. Not a migration on
the index DB — see the Correction above. `ServerDeps` gains `metrics_conn` and
a `metrics_lock`, following the existing per-resource lock pattern
(`server_core.py:195-205`).

```sql
CREATE TABLE request_timings (
  bucket_start  INTEGER NOT NULL,          -- unix seconds, floored to 300
  label         TEXT    NOT NULL,          -- router label
  method        TEXT    NOT NULL,
  kind          TEXT    NOT NULL,          -- 'total' | 'ttfe'
  span          TEXT    NOT NULL DEFAULT '',
  status_class  INTEGER NOT NULL,          -- 2, 4, 5
  count         INTEGER NOT NULL DEFAULT 0,
  sum_ms        REAL    NOT NULL DEFAULT 0,
  min_ms        REAL    NOT NULL,
  max_ms        REAL    NOT NULL,
  b0 … b13      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_start, label, method, kind, span, status_class)
) WITHOUT ROWID;
```

Fourteen log-scale buckets with upper bounds 1, 2.5, 5, 10, 25, 50, 100, 250,
500, 1000, 2500, 5000, 10000 ms and an overflow bucket — sub-millisecond
static assets through a ~10s Stanza cold start.

Counts are **per-bucket, not cumulative**. Cumulative would be the Prometheus
convention and makes quantile lookup marginally simpler, but incrementing one
column per request beats incrementing every column at or above the observed
value. Cumulate at query time; summation aggregates either form.

One `INSERT … ON CONFLICT DO UPDATE SET count = count + 1, sum_ms = sum_ms +
?, …` per request. One row touched, no read-modify-write in Python, no flush
thread to get wrong.

Rows stay small enough to keep indefinitely, so there is no retention job.
Only routes actually hit write rows.

An in-memory ring buffer of the last ~200 requests sits alongside for
slow-request detail. Lost on restart by design; the histograms are the durable
record.

**Known limitation: p95 is approximate.** A p95 landing in the 250–500ms
bucket carries roughly ±250ms of uncertainty, so a small regression can hide
inside a bucket. The mitigation is that `sum_ms` and `count` are exact, so the
**mean is exact and free** — it is the precise trend signal, and the
approximate p95 is the tail-shape signal. Read them together.

### API

```
GET /api/metrics/summary?window=24h[&label=chunk+syntax]
    → per (label, method, kind): count, mean, p50, p95, p99, max, error rate
      with `label`, returns that route's sub-span breakdown instead

GET /api/metrics/series?label=work+range&kind=total&span=&window=7d
    → [{ t, count, mean, p50, p95, max }]
```

Granularity is derived in SQL, never stored: ≤6h reads 5-minute rows raw, ≤7d
groups by hour, beyond that by day. Summing histogram columns is what lets
quantiles survive that rollup — the reason for buckets over raw rows.

`bucket_start` leads the primary key, so its index covers every time-range
scan. No secondary index.

### View

`#/metrics`: a regex in `routing.ts`, a route file in `web/src/routes/`, a
`<Match>` in `AppRoutes.tsx`, an api module in `web/src/api/`.

Window selector; a route table sorted by p95 descending (*what is slow*);
click-through to a time-series chart (*how did it change*); sub-span breakdown
beneath it; a total/TTFE toggle on the two streaming routes.

The chart is hand-rolled SVG following Network's precedent, leaning on the
axis-tick and label-collision helpers in `web/src/utils/atlasGeometry.ts`.
A charting library would be the project's first new runtime dependency, and a
metrics page does not earn that.

### Testing and gates

- **Frontend tests go in `web/tests`**, never colocated. Sonar analyses
  `web/src` as production source, so a colocated `.test.tsx` is scored at 0%
  and fails the required gate for an unrelated reason (#547).
  `check-test-location` enforces it; `check-diff-coverage` cannot see it.
- **Two endpoints means two API fixtures.** `scripts/check_api_types.py`
  requires a JSON fixture under `tests/fixtures/api/`, a TS interface, and a
  `FIXTURE_TYPES` entry. An unmapped fixture is an error, not a skip.
- **80% new-code coverage including branches.** Bucketing and quantile
  interpolation are pure functions and test densely. The context manager's
  exception path is a branch needing its own test — a guard whose false branch
  is untested scores 3/4, not 100%.
- **Cognitive complexity ≤15.** The quantile-from-buckets function and the
  granularity selector are the two that drift. Extract early; ruff's `C901`
  will not warn (it disagrees with Sonar about which function is the problem).
- **Duplication ≤3%.** The summary table will want to be `LeaderboardPanel`
  with different columns. Copying it wholesale fails at any coverage (#254).
- Nothing here reads `data/`, so the local-vs-CI coverage divergence that cost
  #573 its gate (97% local, 63% CI) cannot occur. The local number is real.
- No migration is involved, so the "migration recorded but the repair never
  ran" trap does not apply. The metrics DB is created on first open from its
  own `SCHEMA` constant, the same way `conversations` and `translations` are.
- `data/metrics.sqlite` is gitignored like its siblings, and no test may
  depend on its contents — every test builds its own throwaway DB.
- No ingest, so `make generate-authors` is not involved.

### Estimate

~300 LOC backend, ~400 frontend, plus tests. Roughly two sessions. The
frontend dominates because the chart is hand-rolled.

### Out of scope

OpenTelemetry or a Prometheus exporter. New dependency, new CI surface, and it
answers questions a single-operator local instance does not have.
