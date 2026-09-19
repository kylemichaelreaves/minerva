# Metrics / instrumentation audit

Phase 0. Read-only: no source file was modified. Measured against `main` at
`5fa2206`, 2026-09-18.

Phase 3 was written against Postgres; clarified as SQLite, which is what this
project uses. §7 is answered for SQLite and the measured consequence is there —
the technique ports, but **what makes it valuable does not**, and the
per-query cost depends entirely on one implementation choice.

---

## 1. Where timing is recorded, and the call-site API

One module, `src/minerva/metrics/`, three files:

| file | role |
|---|---|
| `recorder.py` | `Span`, `Recorder`, `current_span()`, `sub_span()` |
| `store.py` | SQLite schema, `write()`, `summary()`, `series()` |
| `histogram.py` | 14 fixed log-scale latency buckets, `quantile()` |

Two call-site APIs, and they nest:

**Whole request** — a context manager on the `Recorder` instance, used only at
the four HTTP dispatch sites:

```python
with self.deps.metrics.record(label, "POST", error_status=_route_error_status) as span:
    ...                      # span.status is set by the dispatch site
```

`src/minerva/http/serve.py` lines 439 (POST), 482 (GET), 505 (PATCH), 532.
That is the complete list — there are **no other `record()` call sites in
`src/`**.

**Phase inside a request** — a module-level context manager, no object needed:

```python
with sub_span("embed_search"):
    ...
```

`sub_span` is a no-op when no request is in flight (`_CURRENT.get() is None`),
which is what lets the same code path run from the CLI untouched.

## 2. Correlation ID

**There is none.** Not in a ContextVar, not passed explicitly, not stored.

What the ContextVar *does* carry is the `Span` itself:

```python
_CURRENT: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "minerva_metrics_span", default=None
)
```

`recorder.py:28-31`. Per-thread by construction, which is what makes it safe
under `ThreadingHTTPServer`. `Recorder.record` sets it; `sub_span` and
`_send_sse` read it via `current_span()`.

The `Span` has no id field — `__slots__` is exactly
`("_clock", "_subs", "_t0", "_ttfe_ms", "label", "method", "status")`. The
identity available downstream is `(label, method, status_class)`, which is a
*route*, not a *request*. Two concurrent `POST /api/chat` calls are
indistinguishable in everything that is written.

Adding an id is therefore additive in the ContextVar (the Span is already
there) but **not** additive in the table — see §5.

## 3. Clocks

Two, deliberately separated, both injectable:

```python
now:   Callable[[], float] = time.time           # WALL: the `at` timestamp
clock: Callable[[], float] = time.perf_counter   # DURATIONS: elapsed_ms, sub_span
```

`recorder.py:101-102`, and `sub_span`'s own default at `recorder.py:73`.

- `time.time()` is used **only** to stamp *when* a request happened (`at`,
  which becomes `bucket_start`).
- `time.perf_counter()` is used for **every duration**.

**No CPU time is recorded anywhere.** `process_time`, `thread_time`,
`getrusage` and `resource` return zero hits across `src/minerva`. So Phase 2
starts from nothing, not from something partial.

One trap for Phase 2: `sub_span`'s `clock` default is **bound at import**, so
monkeypatching `time.perf_counter` later does not reach it. Any new clock has
to be threaded the same way, or injected at the call site.

## 4. Instrumented phases — enumerated from call sites, not inferred

Exactly **three** phase names exist. Every occurrence in `src/`:

| phase | call site | condition |
|---|---|---|
| `llm_call` | `llm.py` 230, 262, 416, 451, 505, 536 | six sites: OpenAI/Anthropic/Ollama × `complete`/`stream_complete` |
| `embed_search` | `retrieve.py:421` | vector search only |
| `stanza_parse` | `syntax/queries.py:354` | syntax route only |

`tests/test_metrics_subspans.py` freezes these three names with a
source-scanning guard, because the frontend drill-down keys on them.

**All three are conditional**, which matters more than the count: a request
with no LLM call, no vector search and no parse records **zero** phases. That
is not a corner case — see §6.

There is also a second `kind` axis that is not a phase: `ttfe`
(time-to-first-event), set by `Span.first_event()` from `_send_sse` on the
streaming route only.

## 5. Where records go, and their shape

**Two sinks, with different shapes and different lifetimes.**

**(a) SQLite — durable, aggregated.** Its own file (`data/metrics.sqlite`),
deliberately *not* a table in `data/index.sqlite`, because `minerva index
--reset` unlinks that file and a re-index is exactly the event these numbers
bracket.

```sql
CREATE TABLE request_timings (
    bucket_start INTEGER, label TEXT, method TEXT, kind TEXT,
    span TEXT NOT NULL DEFAULT '', status_class INTEGER,
    count INTEGER, sum_ms REAL, min_ms REAL, max_ms REAL,
    b0..b13 INTEGER,                      -- 14 log-scale histogram buckets
    PRIMARY KEY (bucket_start, label, method, kind, span, status_class)
) WITHOUT ROWID;
```

`kind` and `span` are **different axes**, which is easy to misread:

- whole request → `kind='total'`, `span=''`
- a phase → `kind='total'`, `span='llm_call'`
- time-to-first-event → `kind='ttfe'`, `span=''`

Rows are folded into 5-minute buckets on write (`UPSERT ... ON CONFLICT`), so
**individual requests do not survive**. Observed shape after one GET and one
streaming POST:

```
label=chat        kind=total  span='' count=1 sum_ms=1.95
label=chat        kind=ttfe   span='' count=1 sum_ms=1.32
label=works list  kind=total  span='' count=1 sum_ms=0.11
```

**(b) In-memory ring — per-request, volatile.** `deque(maxlen=200)`. This is
the **only** place a request's total and its phases are paired:

```python
{"at": ..., "label": ..., "method": ..., "status": ..., "ms": total_ms,
 "subs": [(name, ms), ...]}
```

**`Recorder.recent()` has no production caller.** The only references in the
repo are five assertions in `tests/`; the router exposes `/api/metrics/summary`
and `/api/metrics/series` and nothing else. So the per-request pairing is
computed, stored in memory, and never read by anything but tests.

Consumers to keep working: `_handle_metrics_summary` and
`_handle_metrics_series` (`http/handlers/metrics.py`), reached from the
`#/metrics` frontend.

**Write failures are swallowed by design** — `_finish` catches `sqlite3.Error`
and calls `_note_write_failure()`, dropping the sample rather than failing the
request that produced it. Worth knowing while measuring overhead: a
misconfigured metrics connection produces *silence*, not an error. I hit this
during the audit — a `check_same_thread=True` connection wrote nothing and
raised nothing.

## 6. The accounting gap — measured, not inferred

**Yes, there is unaccounted time, and on most routes it is 100%.**

Driving real requests through the real dispatch path (`ThreadingHTTPServer`,
stub LLM backend, no embedder):

```
GET   works list  status=200 total=0.11ms  phases=0.00ms  UNACCOUNTED=0.11ms (100.0%)
POST  chat        status=200 total=1.95ms  phases=0.00ms  UNACCOUNTED=1.95ms (100.0%)
```

Both phases legitimately did not fire — the stub backend makes no HTTP call and
there is no embedder — which is the point: **the three phases are optional, so
the floor is 0% coverage, not "total minus a bit".** Even fully exercised, a
chat request spends unmeasured time in SQLite FTS retrieval, context assembly,
JSON encoding and socket writes, none of which has a `sub_span`.

**What is and isn't computable today:**

| | per request | in aggregate |
|---|---|---|
| ring (last 200, in memory) | ✅ `ms - sum(subs)` | ✅ |
| SQLite table | ❌ requests are folded into buckets | ✅ `sum_ms(span='') - Σ sum_ms(span≠'')` |

So the premise of proposed Phase 1 — *"record total duration alongside phase
durations"* — is **already satisfied in both sinks**. Total is recorded
(`kind='total', span=''`). The actual gap is narrower and different:

1. The per-request pairing exists only in a 200-entry volatile ring that
   nothing reads.
2. The durable sink cannot attribute a gap to a request, only to a bucket —
   and a bucket mixes requests, so a single slow outlier is not recoverable.
3. `min_ms`/`max_ms`/histogram exist for `total` and for each phase
   *separately*, so "the request where the gap was worst" is not expressible.

That reframes Phase 1 from "record the total" (done) to "decide whether the
durable sink keeps per-request rows at all" — which is a schema change, not an
additive column, and is the one place the backward-compatibility constraint
actually bites.

## 7. SQLite: connection setup, and what correlation can actually mean

**Centralization is already there, in one function.** `sqlite_util.open_sqlite`
(`src/minerva/sqlite_util.py:44`) is the single choke point — every `open_db`
delegates to it: `store`, `conversations`, `translations`, `concept_cache`,
`metrics.store`. 73 modules import `sqlite3`; none of them call `connect`
directly for a satellite database. There is no ORM by policy
(`migrations/__init__.py:43`: *"intentionally minimal (no Alembic, no
SQLAlchemy)"*), and no Postgres driver anywhere.

Separate files per concern, not one database — so "the connection layer" is
one function opening five different files.

### What ports from the Postgres design, measured

```
sqlite 3.50.4

1. leading /*comment*/ accepted:  yes
2. set_trace_callback saw:        "/*request_id='abc-123'*/ SELECT count(*) FROM t"
3. PRAGMA application_id -> 0     (file-level int in the DB HEADER, not per-connection)
```

- **The comment works.** SQLite parses a leading block comment and
  `Connection.set_trace_callback` receives the statement text with it intact.
- **`application_name` has no equivalent.** `PRAGMA application_id` is a 32-bit
  int in the *database file header*, shared by every connection and **written
  to the file**. It is not a per-connection label and setting it would mutate
  the corpus. Wrong tool; there is no right one.

### The part that does not port, and it is the point

In Postgres the comment is valuable because a **separate server process**
writes it to a slow-query log you read later. SQLite is in-process. There is no
server, no slow-query log, and **no consumer of that comment except our own
trace callback** — which can already read `current_span()` directly and does
not need the id smuggled through the SQL text.

So the comment is not load-bearing here. What is load-bearing is **timing the
statement**, which the Postgres design got for free from the server and which
we would have to do ourselves. `set_trace_callback` fires *before* execution
only, so it cannot time anything on its own; real timing wants a `Cursor`
subclass via the `factory=` argument, installed once in `open_sqlite`.

That still satisfies "centralize at the connection/cursor layer — do not touch
individual queries". It just makes the comment optional rather than the
mechanism.

### Measured cost, and the one rule that decides it

50,000 point lookups (`SELECT b FROM t WHERE a = ?`), in-memory DB:

```
no comment                         0.59 us/query
CONSTANT comment                   0.58 us/query    0.98x   free
UNIQUE comment per QUERY           3.49 us/query    5.88x
```

The mechanism is Python's prepared-statement cache (`cached_statements`,
default 128), confirmed by disabling it:

```
cached_statements=128, same SQL          0.56 us/query
cached_statements=0,   same SQL          1.03 us/query   <- cache disabled
cached_statements=128, unique comment    1.65 us/query   <- worse: also churns the cache
```

**A distinct comment makes every statement a cache miss.** But a real
implementation builds the comment **once per request**, not per query — and
then repeated shapes within a request still hit. Simulated at 200 queries per
request across 250 requests:

```
  1 distinct SQL shape  per request ->  0.69 us/query
  5 distinct SQL shapes per request ->  0.64 us/query
 20 distinct SQL shapes per request ->  0.73 us/query
200 distinct SQL shapes per request ->  1.65 us/query   (cache defeated anyway)
```

So: **+0.1–0.2 us/query, ~15–25% on the cheapest query SQLite can run, and
invisible in absolute terms.** On an execute-dominated query (a 5,000-row
scan at 115 us) the same change measures 1.00–1.04x — noise.

**The rule that decides whether this is negligible or 6x: build the comment
string once per request and reuse it.** Interpolating a fresh id at each call
site costs 6x on small queries. This is worth writing into the code as a
comment, because the expensive version is the one that looks more natural.

Caveat on these numbers: in-memory database, single thread, synthetic queries.
They bound the *instrumentation* cost, not this app's real query mix — the
representative-workload measurement the constraints ask for still has to be run
against the real corpus.

## Cross-cutting notes for Phases 1–5

**A second, unconnected timing mechanism exists.** Relevant to Phase 5:

- `ingest/registry.py:612-623` — per-**source** `perf_counter` elapsed + chunk
  count, printed to **stderr** as `timing: ingest:<id>  1.23s (456 chunks)`.
  Gated on a `per_source_timing` flag.
- `ingest/parallel.py:86-115` — per-**source** elapsed + count, returned in a
  dict, with `counts` keyed by `f"{chunk.corpus}/{chunk.lang}"`.
- `cli/_shared.py:255` — a `Timer` class, deliberately side-effect-free.

None of these touch `Recorder`. So Phase 5 is not "extend the existing layer";
it is either a **third** mechanism or the first bridge between two existing
ones. Also note the granularity mismatch: today's unit is a **source**, and
Phase 5 asks for a **document**. Language is available in `parallel.py`; a
"NLP pipeline" label does not exist anywhere and would be new vocabulary.

**Overhead baseline.** Not yet measured — Phase 0 is read-only and a
before/after delta needs a change to compare against. The representative
workload should be the ingest path or a scripted request loop, not the
fixture server: observed totals there are 0.11–1.95ms, where
`perf_counter` resolution and `ThreadingHTTPServer` jitter dominate any
instrumentation delta.

**Ordering.** Phase 2 (CPU time) is the cleanest additive change: `Span._subs`
is a `list[tuple[str, float]]` and every consumer unpacks exactly two
elements, so widening it to three breaks `_finish`, `recent()`'s `subs`, and
the frontend drill-down. A parallel `_subs_cpu` list avoids that; a widened
tuple does not. Worth deciding before writing either.

## Decisions taken, 2026-09-18

Answers to the four open questions. Recorded here so the reasoning survives
the session; the per-phase plans still come before any implementation.

| # | Decision |
|---|---|
| Phase 1 | **Per-request durable rows** in a NEW table beside `request_timings`. Nothing existing changes. |
| Phase 3 | **Both** — cursor-layer timing in `open_sqlite`, with the `/*request_id*/` comment riding along. |
| Phase 5 | **Per-document, folded into the existing histograms**, keyed by `(lang, pipeline)`. Reuses `histogram.py` unchanged. |
| The ring | **Folded into Phase 1**, not decided separately — per-request rows may make it redundant. |

### Consequence: a correlation ID is now a shared prerequisite

Two of those four need a request id, and **§2 established there is none**.

- Phase 1's table is keyed on one.
- Phase 3's comment carries one.

So the id lands first, before either. It is cheap and additive where it
matters: the `Span` is **already** in a ContextVar (`recorder.py:28-31`), so
the id rides an object that every call site can already reach — no new
ContextVar, no threading through signatures, no call-site changes. Adding a
field to `Span.__slots__` and stamping it in `Recorder.record` is the whole
change.

It is *not* additive in `request_timings`, and it does not need to be: that
table stays untouched, aggregated, and id-free. The id exists for the new
per-request table and the SQL comment.

### Open sub-decisions, deferred to the per-phase plans

- **Retention for the per-request table.** Unbounded growth: one request per
  second is ~86k rows/day. Options are a row cap, an age cap, or sampling. The
  Phase 1 plan owes an answer; this is not something to discover later.
- **What counts as "pipeline" in Phase 5.** The label does not exist anywhere
  in the codebase today — `latincy` / `stanza` / `none` is a guess at the
  vocabulary, not something read off a call site. The Phase 5 plan has to name
  it from the actual dispatch.
- **Phase 2 needs nothing.** The backward-compatibility constraint settles it:
  `Span._subs` is `list[tuple[str, float]]` and every consumer unpacks exactly
  two elements, so CPU time goes in a parallel structure, not a widened tuple.

