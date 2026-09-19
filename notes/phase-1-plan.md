# Phase 1 plan — request id + per-request durable rows

Scope: items 1–5 of the Phase 1 brief. Nothing from Phases 2, 3 or 5.
`notes/metrics-audit.md` is authoritative and is not re-derived here.

**No code has been edited.** Everything below is a proposal.

---

## 0. One correction to the brief, before the plan

> *"the failure counter from `_note_write_failure`"*

It is **not a counter — it is a boolean latch.** `Recorder._write_failed` is set
`True` on the first failure and short-circuits every subsequent call, so one
warning is logged per Recorder and nothing counts (`recorder.py:174-201`).

This matters for item 4 exactly as you framed it: exposing the flag as-is gives
you "something failed, once, at some point", which is barely better than the
silence you said you feared most. **The plan turns it into a real counter**
(`_write_failures: int`) and keeps the log-once behaviour separate. That is an
internal change; the log output is unchanged.

Second, smaller: §5's "a connection that wrote nothing and raised nothing" was
**my test probe**, not the production path. Verified — see item 4.

---

## 1. `Span.id`

```python
__slots__ = ("_clock", "_subs", "_t0", "_ttfe_ms", "id", "label", "method", "status")
```

Stamped in `Recorder.record` when the Span is constructed. **No new
ContextVar** — `_CURRENT` already carries the Span (`recorder.py:28-31`), so
every existing reader (`sub_span`, `_send_sse`) reaches the id for free.

**`secrets.token_hex(8)`**, not `uuid4`. Measured, 200k iterations:

```
secrets.token_hex(8)    0.684 us/call
uuid4().hex             1.253 us/call
```

16 hex chars, 64 bits, CSPRNG-backed — random, so it survives restarts and
stays unique across them, as required. Against the observed mean request of
**111 ms** this is 6e-7 of the request. (Honest caveat: observed `min_ms` is
0.005 ms, so on the very cheapest request it is ~14% — of 5 microseconds.)

`request_timings` is untouched: the id never reaches it.

## 2. The new table

Same file (`data/metrics.sqlite`), created by the same `SCHEMA` executescript,
so no migration runner is involved and an existing file gains the table on next
open.

```sql
CREATE TABLE IF NOT EXISTS request_spans (
    id            TEXT    PRIMARY KEY,   -- Span.id
    at            REAL    NOT NULL,      -- wall clock, same source as bucket_start
    label         TEXT    NOT NULL,
    method        TEXT    NOT NULL,
    status        INTEGER NOT NULL,      -- full status, not status_class
    total_ms      REAL    NOT NULL,
    accounted_ms  REAL    NOT NULL,      -- sum of phases; unaccounted = total - this
    phases        TEXT    NOT NULL       -- JSON array, see below
);
CREATE INDEX IF NOT EXISTS request_spans_at   ON request_spans(at);
CREATE INDEX IF NOT EXISTS request_spans_slow ON request_spans(total_ms DESC);
-- Partial: only 0.22% of rows carry a phase, so this indexes thousands of
-- rows instead of millions and keeps the json_each rollup off a full scan.
CREATE INDEX IF NOT EXISTS request_spans_phased ON request_spans(at)
    WHERE phases != '[]';
```

All three are created with the table, while it is empty and they are free.
See item 3 for why they are the mitigation rather than a retention cap.

`unaccounted` is stored as its complement (`accounted_ms`) rather than
precomputed, so the two numbers that were measured are the two that are kept.

### Phase representation: **JSON column, not a child table**

Three reasons, in order of weight.

**1. Phase 2 widens with no schema change at all.** This was your stated
criterion. A child table needs `ALTER TABLE ... ADD COLUMN cpu_ms` — which the
repo's migration runner can do, but it is still a migration. A JSON array grows
a key:

```json
[{"name": "llm_call", "ms": 812.4}]                      → Phase 1
[{"name": "llm_call", "ms": 812.4, "cpu_ms": 3.1}]       → Phase 2, same column
```

**2. 99.8% of rows would have no phases at all.** From the real
`data/metrics.sqlite`: 4,029 recorded requests, and phases fired **9 times**
(`llm_call` 4, `stanza_parse` 4, `embed_search` 1). A child table would be
empty for all but a handful of rows; a JSON column stores `[]` in two bytes.

**3. One INSERT per request instead of one plus N.** Matters because this is on
the request path — see the transaction note below.

**It stays queryable.** SQLite 3.50.4 has JSON1 compiled in; verified:

```sql
SELECT json_extract(p.value,'$.name'), AVG(json_extract(p.value,'$.ms'))
  FROM request_spans r, json_each(r.phases) p GROUP BY 1;
```

Rows with `[]` drop out of the join, which is the correct semantics.

**The cost, stated:** phase names are not indexable without a generated column,
so "every request where `llm_call` > 1s" is a scan. At the retained row counts
in item 3 (tens of thousands) that is milliseconds, and it is a read off the
request path.

### Both sinks, one transaction

`store.write()` opens `with conn:` — a transaction and a commit. Adding a
second `with conn:` for the new row would mean **two commits per request**.
The plan adds:

```python
def write_request(conn, samples, span_row) -> None:   # NEW
    with conn:                                        # ONE transaction
        _fold_samples(conn, samples)                  # existing body of write()
        _insert_span(conn, span_row)
```

`write()` keeps its current signature and behaviour for its existing callers
and tests; its body moves into `_fold_samples`. `Recorder._finish` calls
`write_request`. One lock acquisition, one commit, unchanged fsync count.

## 3. Retention — **no cap by default**

**This reverses my earlier recommendation of a 90-day cap.** That was
reflexive; measured, it is not justified.

**Observed rate**, from the real `data/metrics.sqlite`, 2026-09-13 → 09-18
(corrected 2026-09-19: this file also receives e2e/browser test traffic, #627 —
so the rate is an upper bound on operator use, which is the safe direction for
a sizing decision):

```
4,039 requests over 5.38 days  ->  751 requests/day
busiest day: 2,339    busiest 5-min bucket: 227 (~0.76/s)
```

The audit's 86k/day was a synthetic worst case — **115x** the observed rate.

**Growth and query cost, measured** on synthetic tables at the real row shape
and the real 0.22% phase rate:

```
      rows years@751/d      file |  last 24h  slowest 20  json scan
    50,000         0.2       6MB |     0.1ms         1ms        2ms
   250,000         0.9      28MB |     0.1ms         8ms       12ms
 1,000,000         3.6     113MB |     0.1ms        32ms       51ms
 5,000,000        18.2     567MB |     0.1ms       172ms      266ms
```

**Eighteen years of complete per-request history is 567 MB, and the query that
runs constantly is 0.1 ms at every scale** — the `at` index keeps it flat.
There is no size danger.

What grows is the **unindexed** scans, and those are exactly the queries that
make history worth keeping. They are fixed with indexes, not with deletion:

```
      rows |  slowest20 NO idx  with idx |  json NO idx  with idx |    size
   250,000 |               8ms     0.0ms |          8ms     0.5ms |    32MB
 1,000,000 |              33ms     0.0ms |         33ms     2.1ms |   130MB
 5,000,000 |             177ms     0.0ms |        170ms    15.3ms |   652MB
```

`total_ms DESC` goes **flat at 0.0 ms**. The partial index on
`phases != '[]'` takes the phase rollup from 170 ms to 15 ms at 5M rows, and
what remains grows with the count of *phased* rows (~11k at 5M), not the table.
Both indexes together cost **+85 MB at 5M rows, ~15%** — cheap against what
they buy.

### The plan

- **Retention cutoff defaults to `None` — nothing is deleted.** The prune runs
  at `open_db` as designed, and is a no-op unless a cutoff is configured. You
  keep everything; switching a cap on later needs no schema change and no
  migration.
- **All three indexes ship now**, while the table is empty.

### The hazard that is real, and it is not row count

**A rate change, not a size limit.** `metrics summary` (546) and
`metrics series` (261) are already **20% of observed traffic** — the metrics UI
records the requests that read it. A `#/metrics` tab left open polling every
5 seconds is **17,280 requests/day, 23x the observed rate**, which turns
"18 years to 5M rows" into about **9 months**. Same table, same code, two
orders of magnitude of difference driven by a browser tab.

That is worth watching, and the `health` block in item 4 is the natural place
to surface a rows/day figure later. It is **not** an argument for a cap: even
at 23x, the numbers above say the table stays comfortable and the indexes stay
flat.

**One thing I have not verified:** how `data/metrics.sqlite` is backed up. If
anything copies it wholesale, a multi-hundred-megabyte file has a cost outside
SQLite that none of these measurements capture. Worth a look before the table
has years in it, not after.

## 4. Write failures must be visible

**(a) Count them.** `_write_failed: bool` → `_write_failures: int`. Log-once
behaviour is preserved by keeping a separate `_logged: bool`, so the log is
unchanged and the count is real.

**(b) Expose through `/api/metrics/summary`.** The response gains one key:

```json
{"window": "...", "since": 0, "until": 0, "rows": [...],
 "health": {"write_failures": 0, "persisting": true}}
```

`persisting` is `deps.metrics_conn is not None`, which distinguishes the two
silent-zero cases you named: *nothing is being written* vs *writes are
failing*. Both currently look identical from the UI.

Three files move together, and the gate enforces it:
`tests/fixtures/api/metrics_summary.keys.json`, `MetricsSummaryResponse` in
`web/src/api/metricsApi.ts`, and the handler. `scripts/check_api_types.py`
fails if the fixture and the TS interface drift.

Additive: existing consumers ignore an unknown key, and the four existing keys
are unchanged.

**No UI renders it, and that is a deliberate, tracked choice** (agreed
2026-09-18). There is no open plan to update `#/metrics` — the two design docs
behind it (`docs/superpowers/specs/2026-09-13-request-timing-observability-design.md`
and `...-two-pane-redesign-design.md`) both shipped, via #590 and #601, and the
only open issues touching those files are #599 and #585, neither a redesign.

So `health` ships as API-only: visible by curling `/api/metrics/summary`, not
on the page. That is the same shape as `Recorder.recent()` — computed, stored,
read by nothing — which this very plan criticises in item 5. The difference is
that it will be **filed rather than forgotten**, with the issue carrying the
real `file:line` once the field exists, so it is evidence-bearing rather than a
placeholder. Widening Phase 1 into `web/src` is out of the stated scope ("the
request id, and per-request durable rows. Nothing else").

**(c) `check_same_thread` — verified correct in production.** Traced:

```
serve_cmd.py:43   metrics.open_db(path, check_same_thread=False)
serve.py:676      metrics_lock = threading.Lock()
serve.py:692      metrics=Recorder(metrics_conn, metrics_lock)
serve.py:694      metrics_lock=metrics_lock          <- SAME lock object
handlers/metrics.py:88,106   with deps.metrics_lock: ...
```

One lock, shared by the writer and both readers, and the connection is opened
thread-safe. **The §5 incident was my own probe** using a bare
`sqlite3.connect(":memory:")` (default `check_same_thread=True`); the resulting
`ProgrammingError` is a `sqlite3.Error` subclass and was swallowed by the
existing policy. Production is not affected.

**A latent trap, noted not fixed:** `ServerDeps.metrics_lock` has
`default_factory=threading.Lock` and `metrics` defaults to its own `Recorder`,
so deps built by hand (as `make_deps` does) get **two different locks**. Only
`serve()` wires the shared one. Not a production bug today; it is how a future
caller gets unserialised read/write. Worth an issue, not a Phase 1 change.

## 5. The ring — **keep it, unchanged**

My audit called it "computed, stored, and never read", and on consumer count
that is true. On purpose it is wrong, and two existing tests say so:

```python
def test_recorder_without_a_connection_still_fills_the_ring():   # no conn at all
def test_error_status_records_what_the_client_actually_received(conn):
    _cannot_be_written(conn)
    # "Sample dropped, request unharmed, ring still filled."
```

**The ring is the only record that survives a failed or absent SQLite write** —
which is precisely the state item 4 exists to make visible. Backing `recent()`
with the new table would delete the fallback exactly when it is needed, and
would make your worst case worse, not better.

So: the table is the durable record, the ring is the degraded-mode record, and
they are complementary rather than duplicative. No change to the deque, no
change to `recent()`, no new endpoint in this phase — the brief folds that
decision here, and my recommendation is **not yet**: an endpoint is more useful
once it can serve the durable table with a window, which is a Phase 1b-sized
question, not a Phase 1 one.

## 6. Overhead — measured

**Against a real request, negligible.** `works list` over `data/index.sqlite`,
driven through the real handler, 300 calls each side:

```
                  mean       p50       p95       p99
no recorder   312.356ms  311.754ms  316.394ms  328.662ms
recorded      313.290ms  312.584ms  320.122ms  341.676ms

delta mean   +0.934 ms/request  (+0.30%)
```

**The prediction in this plan was wrong in its reasoning, and right in its
conclusion.** It said "one `token_hex` (0.68 us) plus one INSERT inside an
already-existing transaction... expected well under 1%". The 1% holds. But the
INSERT is not the cheap part, and the cost is not where the plan looked —
isolated on a file-backed DB, 20,000 iterations each:

```
  Recorder(None)  — ring only, no durable write        2.26 us
  aggregate only  — the pre-Phase-1 shape            275.03 us
  aggregate + per-request row                        387.08 us   (+112 us)
```

Of that +112 us, index maintenance on the three new indexes is +62 us
(+19% of a bare insert); the partial `phases != '[]'` index is free, because
every row in the benchmark is `[]` and excluded from it.

**And 275 us of the 387 us predates this work.** The dominant cost is the
commit, not the insert: `data/metrics.sqlite` runs in `journal_mode=delete`,
so every metrics write is an fsync of a rollback journal.

```
20,000 INSERT + commit:   DELETE journal  340.62 us      WAL  62.17 us
```

**Filed as #617, not fixed here** — it is a connection-configuration change
with durability and snapshot consequences, and this phase is scoped to the id
and the table. It is worth knowing that WAL would take the whole metrics write
*below* its pre-Phase-1 cost rather than merely restoring it.

**The honest caveat.** 21 of 24 live route labels have a p50 of **1 ms**, and
the recorded duration excludes the write, so on a fast route the metrics commit
is a large fraction of the request. That was already true at 275 us; this work
raises it to 387 us. Negligible against the 111 ms observed mean, material
against a 1 ms handler, and #617 is the lever for both.

## 7. Notes and non-goals

- **`sub_span`'s import-bound `clock` default is not touched by this plan.**
  Flagged as the brief requires; Phase 2 has to solve it properly.
- **No phase is added, renamed or removed.** `tests/test_metrics_subspans.py`
  keeps passing untouched.
- **No new dependency.** `secrets` and `json` are stdlib.
- **`request_timings` schema is byte-identical.** `_handle_metrics_summary`
  and `_handle_metrics_series` keep their existing four keys plus one new one;
  `#/metrics` renders unchanged.

## 8. What I would build, in order

1. `Span.id` + `secrets.token_hex(8)` in `record`. Test: two requests get
   different ids; the id is reachable via `current_span()`.
2. `request_spans` table + `write_request` one-transaction path. Test: one row
   per request, `total_ms - accounted_ms` equals the unaccounted time, `[]`
   when no phase fired.
3. `_write_failures` counter + `health` block on the summary response, with
   the fixture and TS interface updated together.
4. Retention prune at `open_db`. Test: a row older than the cutoff is deleted
   at open, a newer one is not.
5. Overhead run, both sides, numbers into the PR.

## Decisions — nothing open

| Question | Decision |
|---|---|
| Retention cap | **None by default.** Prune ships, runs at `open_db`, no-ops unless configured. Indexes are the mitigation, not deletion. |
| Cutoff as CLI flag or constant | **Module constant** (agreed 2026-09-18). A `minerva serve` flag is scope this phase does not need; adding one later is additive. |
| Phase representation | **JSON column.** Phase 2 widens with no schema change. |
| The ring | **Keep unchanged.** It is the only record surviving a failed or absent write. |
| Id generation | **`secrets.token_hex(8)`** — 0.684 us, ~2x faster than `uuid4`. |
| `health` in the UI | **Not in Phase 1.** Ships API-only; an issue to surface it is filed with the PR, citing the real line. |

Ready to implement on approval. Build order is in item 8.
