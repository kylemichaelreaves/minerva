# Phase 2 plan — CPU time beside wall time

Scope: distinguishing I/O-bound from CPU-bound work. Nothing from Phases 3 or 5.
`notes/metrics-audit.md` and `notes/phase-1-plan.md` are authoritative and not
re-derived.

**No code has been edited.** Everything below is a proposal.

---

## 0. The brief names the wrong clock, and it matters

> *"capture `time.process_time()` alongside `perf_counter()` for each phase"*

**`process_time()` is process-wide.** The server is a `ThreadingHTTPServer` —
one thread per request, concurrent by construction — so a span opened on one
thread would absorb every other in-flight request's CPU.

Measured. A span doing ~50 ms of work, with N other threads burning
concurrently:

```
  0 concurrent thread(s):   process_time = 50.0 ms    thread_time = 50.0 ms
  1 concurrent thread(s):   process_time = 50.2 ms    thread_time = 25.0 ms
  3 concurrent thread(s):   process_time = 56.5 ms    thread_time = 12.5 ms
```

With three neighbours the span **actually used 12.5 ms of CPU** and
`process_time` reports **56.5 ms** — a 4.5x overattribution, and it grows with
traffic. The `thread_time` column is correct: under the GIL this thread really
does get about a quarter of the CPU over that window.

**What would have gone wrong had it been trusted:** the feature's entire
purpose is to separate "this phase is computing" from "this phase is waiting".
`process_time` would report a *waiting* phase as CPU-bound whenever anything
else was running — worst exactly when the server is busy, which is when anyone
looks. It would not fail; it would quietly answer the opposite question.

**Use `time.thread_time()`.** It is also cheaper:

```
time.perf_counter     23.2 ns/call
time.thread_time      90.0 ns/call
time.process_time    174.0 ns/call
```

Availability: present on this machine; CPython documents it for Linux, macOS
and Windows. It is not universal, so the plan resolves it once at import with a
`getattr(time, "thread_time", None)` fallback that disables CPU capture rather
than substituting `process_time` — a wrong number is worse than no number here.

## 1. Where the CPU number is captured

**`sub_span` gains a second clock**, and both become call-time defaults rather
than import-time ones:

```python
def sub_span(name, *, clock=None, cpu_clock=None):
    c   = clock or time.perf_counter
    cpu = cpu_clock or _THREAD_TIME        # None when unavailable
```

That fixes the trap the audit flagged and the Phase 1 brief deferred: the
current `clock=time.perf_counter` default binds at **import**, so patching
`time.perf_counter` afterwards never reaches it. Resolving inside the function
makes it patchable and keeps every existing `sub_span(name, clock=...)` caller
working unchanged — `tests/test_metrics_llm_call_span.py` and
`tests/test_metrics_request_spans.py` both pass one.

**`Span` also times the whole request**, not only its phases. This is the part
worth arguing for: **99.8% of requests carry no phase at all**, so a
phase-only CPU number is absent from almost every row. A request-level
`cpu_ms` beside `total_ms` makes the wall-vs-CPU question answerable for
*every* request — including the ones where the answer is most interesting,
because nothing is instrumented inside them.

## 2. Where it is stored

**`request_spans.phases`** gains a key per phase. **No schema change** — this
is the reason Phase 1 chose a JSON column over a child table:

```json
[{"name": "llm_call", "ms": 812.4, "cpu_ms": 3.1}]
```

**`request_spans` gains one column** for the request-level number:
`cpu_ms REAL NOT NULL DEFAULT 0`. A defaulted `ADD COLUMN` is additive, reads
on old rows return 0, and nothing that selects by name breaks.

**`request_timings` — recommend NOT touching it in this phase.** A `kind='cpu'`
row per phase would be additive and would give aggregate CPU percentiles, but
it is a second decision with its own surface (`RouteDetail`'s drill-down), and
"smallest change first" says the per-request view earns it before the aggregate
does. Easy to add later; hard to remove once the frontend reads it.

## 3. What the UI does with it

`MetricsRequestRow` gains `cpu_ms`, and `MetricsRequestPhase` gains `cpu_ms`.

The design's Breakdown surface already specifies the rendering — a dark inset
on each wall bar, and a "cpu-bound / mixed / waiting" label from the ratio:

```
io = cpu / wall     >0.6 cpu-bound    <0.1 waiting    else mixed
```

Those thresholds come from `obs-render.js` and are the design's, not mine.
**In this phase I propose the ledger only**, not the Breakdown surface: the
ledger exists and per-request CPU drops straight into its detail panel, while
Breakdown's value is the toggle across phases 2 *and* 3 and is better built
once Phase 3 lands. Stated so it is a decision rather than an omission.

## 4. Overhead — measured

Isolated on the ring-only path, which is the only place the capture is visible
at all: the durable write is commit-dominated and swamps it (and varies 357-387
us between sessions on the same code, which is why it cannot be the measurement).

```
40,000 iterations, ring only
  cpu capture OFF, no phase   mean 2.212 us
  cpu capture ON,  no phase   mean 2.311 us      -> +99 ns per request
  cpu capture OFF, 1 phase    mean 3.211 us
  cpu capture ON,  1 phase    mean 3.564 us      -> +254 ns per phase
```

Predicted +180 ns per request and per phase; measured **+99 ns** and
**+254 ns**. Same order, and the per-request half came in cheaper than the
prediction. Against the observed **111 ms** mean request that is 0.0001%, and
only 0.22% of requests carry a phase at all.

End to end, interleaved pairs against the real corpus:

```
N = 400 interleaved pairs, `works list` over data/index.sqlite
no recorder     260.12ms      recorded  261.08ms
paired delta    median +0.490 ms  (+0.19%)
```

That +0.49 ms is the *whole* recorder, not this phase — Phase 1 measured
+0.382 ms on the same workload, and the difference between the two runs is
inside the commit's own session-to-session variance. The isolated number above
is the one to trust for Phase 2's cost; this one confirms nothing regressed.

## 5. What could go wrong, and what pins it

- **A generator-spanning phase.** `sub_span("llm_call")` wraps a generator that
  yields across `_send_sse`'s loop, so its wall clock spans suspension. Its CPU
  clock must not count the consumer's work while suspended — but `thread_time`
  on the *same thread* will, because the consumer runs there too. **This is a
  real limitation, not a bug**: for a streaming call, `cpu_ms` includes the
  handler's own work between yields. A test will pin the behaviour and the
  docstring will state it, rather than leaving a wrong number unlabelled.
- **`thread_time` missing.** Capture disables; `cpu_ms` stays 0 and the UI
  renders no inset. Pinned by a test that patches the module constant to None.
- **Backward compatibility.** Old `request_spans` rows have no `cpu_ms` in
  their JSON and 0 in the column. The reader must treat absent as unknown, not
  as zero-CPU — a test for that, since "0 ms of CPU" and "not measured" render
  identically otherwise, which is the same class of mistake `health` fixed.

## 6. Build order

1. `_THREAD_TIME` resolution + `sub_span`'s call-time clock defaults. Tests:
   patching reaches it; an explicit `clock=` still wins; a missing
   `thread_time` disables cleanly.
2. `Span` records request-level CPU; `RequestRow` carries it; migration adds
   the column.
3. Phase-level `cpu_ms` into the JSON. Test: absent on an old row reads as
   unknown, not zero.
4. API + TS types + contract fixture together.
5. Ledger detail shows wall and CPU with the design's ratio labels.
6. Overhead run, interleaved, both sides, numbers into the PR.

## Open question

**Should `request_timings` get `kind='cpu'` rows in this phase?** My
recommendation is no — it is a separate decision about the aggregate drill-down,
and the per-request view is where CPU first earns its place. Say if you want it
folded in and I will do it here instead of later.
