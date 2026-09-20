# Phase 3 plan — SQLite time, attributed to the request

Scope: database time measured at the connection layer, and the
`/*request_id*/` comment. Nothing from Phase 5.

**No code has been edited.** Everything below is a proposal.

---

## 0. The audit's proposed mechanism does not work

`notes/metrics-audit.md` §7 says:

> *"real timing wants a `Cursor` subclass via the `factory=` argument,
> installed once in `open_sqlite`"*

**`conn.execute()` does not go through the cursor factory.** Measured — a
`TimedCursor` installed via a `Connection.cursor()` override, exercised four
ways:

```
intercepted calls:
   cursor.execute         'SELECT * FROM t'        <- explicit .cursor() only

Connection.execute intercepted:     False
Connection.executemany intercepted: False
```

CPython's `Connection.execute` creates its cursor in C and ignores a Python
`cursor()` override. **Nearly every query in this codebase uses that
shortcut**, so the audit's design would have instrumented approximately
nothing while appearing to work — the tests would pass on a hand-made cursor
and production would record zero.

**What works instead: override `Connection.execute` / `executemany` /
`executescript` on a `Connection` subclass**, installed via
`sqlite3.connect(..., factory=...)` in `open_sqlite`. Verified to intercept
all three:

```
intercepted:
   executescript  'CREATE TABLE t(a INTEGER P'
   execute        "INSERT INTO t VALUES (1,'x"
   executemany    'INSERT INTO t VALUES (?,?)'
   execute        'SELECT * FROM t WHERE a = '
```

**The gap that leaves:** an explicit `conn.cursor().execute(...)` still
escapes. Today that is not a real gap —

```
$ grep -rn "\.cursor()" src/minerva | wc -l
0
```

— zero call sites. The plan adds a **guard test** that fails if one appears,
rather than instrumenting a second layer for a path nobody uses.

## 1. What it buys, measured

The audit established that essentially 100% of a typical request is
unaccounted, with database time the largest known component. Now quantified,
on the real corpus:

```
works list
  request total :    241.3 ms
  sqlite total  :    240.5 ms   (99.7% of the request)

     240.5 ms  SELECT cf.work_id, cf.corpus, cf.author, cf.work, cf.lang, ...
       0.1 ms  SELECT work_id, language, title_local FROM editions WHERE ...
```

**One statement is the entire route.** Phase 3 turns a bar that reads
100% unaccounted into one that is fully explained, and it does so without a
new `sub_span` at any call site — which is the point of measuring at the
connection layer.

`open_sqlite` is the single install point and every database goes through it,
including the index (`store/schema.py:85`) which is where that 240 ms lives.

## 2. How the time is accumulated

**Not as a `sub_span`.** A phase is one contiguous interval; database time is
a sum over many disjoint ones, and putting it in `phases` would make the
waterfall's ordering a lie. It gets its own fields:

```
request_spans.sqlite_ms       REAL      nullable — NULL means not measured
request_spans.sqlite_queries  INTEGER   nullable — the count, so a mean is derivable
```

Nullable for the reason Phase 2 established: *not measured* and *measured, and
zero* are different answers, and a route that genuinely touches no database
must not be indistinguishable from a row written before this phase.

Accumulation goes onto the `Span` through a new `add_db(ms)`, reached via
`current_span()` — the same ContextVar path `sub_span` already uses, so it is
per-thread and needs no lock even though the *connection* is shared across
threads.

## 3. The feedback loop, and why it does not happen

The metrics write is itself a SQLite write, on a connection that
`open_sqlite` will now instrument. If it were attributed, every request would
record the cost of recording the previous one.

It is not, and the reason is an ordering that already exists:

```python
finally:
    _CURRENT.reset(token)     # span is no longer current
    self._finish(span)        # ... THEN the metrics write happens
```

By the time `_finish` runs its INSERT, `current_span()` is `None` and the
instrumentation is a no-op. **This is load-bearing and currently incidental**,
so the plan adds a test that pins the ordering, not merely the outcome.

## 4. The `/*request_id*/` comment

Built **once per request** and cached on the Span, never interpolated per
query. That is not a style preference — measured in the audit:

```
50,000 point lookups
  no comment                   0.59 us/query
  CONSTANT comment             0.58 us/query    free
  UNIQUE comment per QUERY     3.49 us/query    5.88x
```

A distinct comment per query defeats Python's prepared-statement cache. Per
request it is +0.1–0.2 us/query, because repeated shapes within one request
still hit.

**Stated plainly, because it did not change since the audit:** in SQLite this
comment has **no reader**. There is no server and no slow-query log; only our
own trace callback would ever see it, and that can read the ContextVar
directly. Its value is `EXPLAIN` output and a future trace log. It was chosen
deliberately with that known — I am not re-litigating it, only noting that if
a route ever issues hundreds of distinct statements the cache-miss cost scales
with them while the benefit does not.

`application_name` has no SQLite equivalent and is not attempted.
`PRAGMA application_id` is a 32-bit integer in the **database file header**,
shared by every connection and written to the file — the wrong tool, not a
different one.

## 5. Overhead

The Python-level override costs, on the cheapest query SQLite can run:

```
60,000 point lookups
  plain sqlite3.Connection      0.512 us/query
  Connection.execute override   0.633 us/query     -> +0.121 us/query (+24%)
```

+24% sounds alarming and is not: it is 121 nanoseconds, and `works list`
issues **2 statements**, so the per-request cost is **~0.24 us** against a
241 ms request. The percentage is large only because the baseline is a
sub-microsecond no-op.

**The number to watch is queries per request, not the per-query percentage.**
A route issuing 1,000 statements would pay 0.12 ms — still small, but it is
the quantity that scales. The overhead run will report queries-per-request
alongside the delta, measured with the interleaved method
[[benchmark-ab-interleaved]].

## 6. Risks

- **A future `.cursor()` call silently escapes.** Zero today; guard test.
- **`executescript` is instrumented too.** It is schema/migration work, not
  request work, and normally runs outside a span. Harmless, and the test
  suite will show if a handler ever calls it.
- **Recursion.** The instrumentation issues no queries of its own.
- **Old rows.** `sqlite_ms` is NULL for every row written before this phase;
  the UI must render that as *not measured*, exactly as it does `cpu_ms`.

## 7. Build order

1. `TimedConnection` in `sqlite_util.open_sqlite`, accumulating via
   `current_span()`. Tests: all three entry points intercepted; a `.cursor()`
   guard; no attribution when no span is in flight.
2. The ordering test that pins `_CURRENT.reset` before `_finish`.
3. `sqlite_ms` / `sqlite_queries` columns via the additive `_ADDED_COLUMNS`
   path Phase 2 built, plus the `RequestRow` fields.
4. The per-request comment prefix, built once, with a test that the SQL the
   database receives carries it and that it is constant within a request.
5. API + TS types + contract fixture together; the ledger detail shows
   database time in the waterfall, tagged as measured at the connection layer
   rather than as a span.
6. Overhead run, interleaved, reporting queries-per-request.

## Open question

**Does the Breakdown surface come with this phase?** Phase 3 is what makes it
worth building — it is the toggle across phases 2 and 3, and both halves now
exist. But it is a new surface with its own design, tests and page objects,
and this phase is already the largest of the three. My recommendation is to
land the measurement plus the ledger's waterfall here, and build Breakdown as
its own change against real data rather than against a projection. Say if you
would rather have it in one.
