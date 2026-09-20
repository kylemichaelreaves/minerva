# Design brief — observability surfaces for Minerva's metrics layer

For prompting the Claude Design project (`019e0d6a-55f3-7e90-b2bf-130118cf440b`).
Written 2026-09-18 against `main` at `5fa2206` + PR #615.

**Everything numeric below is measured from the live `data/metrics.sqlite`
(4,039 requests, 2026-09-13 → 09-18) or from the code.** Nothing is invented.

> **Corrected 2026-09-19 — the traffic is not purely an operator's.** The e2e
> and browser suites run `minerva serve` without `--metrics-db`, so they record
> into this same file (**#627**). The counts below therefore mix real use with
> test runs in an unknown proportion, and the loud days line up with sessions
> that ran the suites repeatedly. The *shapes* are still the right ones to
> design against — p50 of 1 ms nearly everywhere, four orders of magnitude of
> tail, three span names, 0.22% phase coverage — because those come from how
> the routes are built rather than from who called them. Treat the per-route
> **counts** as indicative, not as a usage measurement.
That matters here because in this project *the mock's fixture data is the
spec* — derived values get read back out and verified against the formula — so
a mock built on plausible-looking numbers propagates wrong assumptions into the
implementation.

---

## 1. What already exists, and what this is not

`#/metrics` shipped (#590) and was rebuilt around triage (#601). Its design
history is in the project already:

- `Request Timing.html` — the shipped surface.
- `observability-redesign.html` — the three-direction exploration (A triage
  split / B compact ledger / C roomy) that became #601.

**This brief is not a redesign of that page.** It is for the surfaces the next
four phases of backend work create, which have no design at all.

### Two things in `observability-redesign.html` are now wrong — do not carry them forward

1. **Its span names are invented.** It shows `llm_call`, `retrieve`, `embed`,
   `render`. The real instrumented names are exactly three, frozen by
   `tests/test_metrics_subspans.py`: **`llm_call`, `embed_search`,
   `stanza_parse`**. `retrieve` and `render` do not exist.
2. **Its explanatory note describes a defect that is now fixed.** It reads:
   *"llm_call is measured per attempt and closes when response headers arrive,
   so streamed body time falls outside it — the spans do not sum to the total
   on this route."* Both halves changed in PR #615: the span now covers the
   whole call including the streamed body, and it sits outside the retry loop,
   so a retried call reports one entry rather than one per attempt.

It also draws `deploy 21:40` event markers. There is no deploy or event feed —
the #601 spec ruled this out of scope for that reason. Still true.

---

## 2. The data that exists today

### Two sinks

| | shape | lifetime |
|---|---|---|
| `request_timings` (SQLite) | folded into **5-minute buckets**; individual requests do not survive | durable |
| in-memory ring | per-request, `deque(maxlen=200)` | lost on restart; **no endpoint today** |

### `/api/metrics/summary` — one row per (label, method, kind, span)

Fields per row: `label`, `method`, `kind`, `span`, `count`, `mean_ms`,
`min_ms`, `max_ms`, `error_rate`, `p50_ms`, `p95_ms`, `p99_ms`.

**Three traps in that shape, all measured:**

**(a) `kind` and `span` are different axes.** Easy to misread as one.

```
whole request        kind='total'  span=''
a phase              kind='total'  span='llm_call'
time-to-first-event  kind='ttfe'   span=''
```

**(b) `rows` mixes `kind='total'` and `kind='ttfe'` in one array.** A route list
that does not filter by `kind` will render `chat` twice. In the live data that
is exactly what happens: `chat` appears as `total` (count 334) and as `ttfe`
(count 1).

**(c) `p99_ms` can exceed `max_ms` — on 8 of 25 routes.** Quantiles are
estimated from 14 log-scale buckets; `max_ms` is exact. Worst case live:

```
chunk syntax    count=8    p95=220   p99=244   max=116      <- p99 is 2.1x the max
network summary count=61   p95=2195  p99=2439  max=2357
```

A "slowest request" panel showing a quantile beside an exact extreme will look
broken on a third of routes. Tracked as **#616**. Today's page sidesteps it by
not displaying `min_ms`/`max_ms` at all. **Any design that shows both must
label the quantile as an estimate.**

### Real route labels — 25 of them, not the mock's 11

`label` is a human-readable route name, not a path. The live set, with real
distributions (`count`, ms):

```
label                    method  count      p50       p95       p99       max   err%
conversations list       GET       611        1         1         4        68   0.0%
metrics summary          GET       546        1         4         8        24   0.0%
works list               GET       494        1       412      7650     23245   0.0%
chat                     POST      334        3        10        67     32772   2.7%
landing stats            GET       271        1       156       237     20497   0.0%
metrics series           GET       261        1         3         5         9   0.0%
work range               GET       245        1      3839     10000     21133   3.7%
health                   GET       212        1         2        98       157   0.0%
work references map      GET       172        1        64       820      1626   0.0%
work-occurrence-map      GET       171        1        17       645      1616   0.0%
translate                POST      169        1         9      1465      4776  10.7%
conversation get         GET       112        1         1         2         2   8.0%
conversation delete      DELETE    111        1         1         5         6   8.1%
network summary          GET        61        1      2195      2439      2357   0.0%
concordance index        GET        60        1       250      3500      4042   0.0%
word lookup              GET        58        1       262     10000     19150   0.0%
references list          GET        38        1       263       452       475   0.0%
terms list               GET        34        1         1         2         2   0.0%
review queue             GET        34        0         1         1         1   0.0%
work range by slug       GET        19        1       108       221       203   0.0%
chunk syntax             GET         8        5       220       244       116   0.0%
references sources       GET         4       375       488       498       477   0.0%
lemma-highlights         GET         2        2        48        50        28   0.0%
concordance lemma        GET         2       10        24        25        19   0.0%
```

**Design consequences of the real distribution, which is nothing like the mock's:**

- **p50 is 1 ms for 21 of 24 routes.** The mock assumed p50 ≈ 1150 ms. A layout
  that gives p50 equal visual weight to p95 will show a column of `1`s.
- **The spread is enormous** — `works list` runs p50 = 1 ms, max = 23,245 ms.
  Four orders of magnitude on one route. A linear bar chart is unreadable;
  the existing page uses log-scale buckets for a reason.
- **Four routes have DELETE/POST methods**; `conversation delete` is the only
  DELETE. Method badges need three values, not two.
- **Error rates are real and non-trivial**: `translate` 10.7%, `conversation
  delete` 8.1%, `conversation get` 8.0%. Not a rare state to design for.
- **Long labels exist** — `work-occurrence-map`, `work references map`,
  `conversation delete`. Budget for ~22 characters.

### Phases are rare — this is the single most important number here

```
4,029 recorded requests
    9 carried ANY phase   (llm_call 4, stanza_parse 4, embed_search 1)
```

**0.22%.** A waterfall/breakdown panel is empty for ~99.8% of requests. The
empty state is the common case, not the edge case, and it needs to say
something more useful than "no data" — most likely *why* (this route has no
instrumented phase; only chat/translate/syntax do).

Real sub-span rows, complete:

```
chunk syntax    span=stanza_parse   count=4  p50=100   p95=235
chat            span=llm_call       count=2  p50=2500  p95=4750
chat            span=embed_search   count=1  p50=2     p95=2
translate       span=llm_call       count=2  p50=2500  p95=4750
```

### Observed volume

```
751 requests/day       busiest day 2,339       busiest 5-min bucket 227
```

Note `metrics summary` (546) + `metrics series` (261) = **20% of all traffic**.
The metrics UI is one of the busiest routes on the instrument it is measuring.
A design that polls aggressively makes itself the top route.

---

## 3. What each backend phase adds

Phase 1 is planned (`notes/phase-1-plan.md`); 2, 3 and 5 are specified but not
built. **Design against the full target state** — otherwise this gets
redesigned three more times.

### Phase 1 — per-request durable rows + health

New table, one row per completed request:

```
id           16-char hex     at          unix seconds (float)
label        text            method      GET | POST | DELETE
status       int (full status, not the class)
total_ms     float           accounted_ms  float   -> unaccounted = total - accounted
phases       JSON array      e.g. [] or [{"name":"llm_call","ms":812.4}]
```

**This is the first time per-request data is durable.** It unlocks: a request
list, "the 20 slowest requests", and per-request unaccounted time. Retention is
uncapped by decision — the table is designed to hold years.

`/api/metrics/summary` also gains:

```json
"health": {"write_failures": 0, "persisting": true}
```

`persisting: false` means metrics are not being written at all (`--no-metrics`,
or the DB could not be opened). `write_failures > 0` means writes are being
attempted and failing. **These two states currently look identical to a reader:
an empty page.** Distinguishing them is the point — this is the highest-value
small thing in the brief.

### Phase 2 — CPU time per phase

Each phase gains a CPU number beside its wall time, so an I/O-bound phase and a
CPU-bound phase become distinguishable. Design need: a way to show *two*
durations per phase without doubling the visual weight. (`ms` vs `cpu_ms`; a
phase with `cpu_ms ≈ ms` is CPU-bound, `cpu_ms ≪ ms` is waiting on something.)

### Phase 3 — SQLite time per request

Time spent in SQLite, attributed to the request, measured at the cursor layer.
**This is the big one for the accounting gap**: §6 of the audit measured that
essentially 100% of a typical request is currently unaccounted, and database
time is the largest known component of it. Expect this to turn an empty
waterfall into a populated one for most routes.

### Phase 5 — ingestion distributions

A different surface entirely, not a request. Per-document duration and token
counts from the batch pipeline, aggregated into the same log-scale histograms,
keyed by `(lang, pipeline)`:

```
lat / latincy   count=4812  p50=12ms   p95=88ms   p99=310ms
grc / stanza    count=1203  p50=41ms   p95=402ms  p99=1.9s
```

The ask is explicitly a **distribution across a corpus**, not individual runs.
Note: the `pipeline` label does not exist in the codebase yet — treat
`latincy` / `stanza` as provisional vocabulary.

---

## 4. House rules for this project

Both of these were hit on the last round on this surface (#600):

- **Mocks are dark-theme only.** The `:root` block is character-for-character
  the repo's `[data-theme="dark"]` palette. Every new token needs a light value
  derived and contrast-measured — and do not trust the mock's own values: its
  `--bad` measured 4.49:1 on its own paper, just under AA.
- **Mock ARIA is decorative and gets re-derived.** `Request Timing.html` nests
  `<button role="option">` inside `role="listbox"`. This matters more than
  usual now: the Playwright suite anchors on role + accessible name by policy
  (#593), and changing an accessible name under a page object broke three
  required-gate tests during #601. Roles and names are load-bearing.

Existing palette tokens the current surface uses: `--p50` `#3a93d1`, `--p95`
`#c97a65` (the brand accent), `--warn` `#d9a441`, `--bad` `#c85a4a`, `--ok`
`#6f8f6a`. Fonts are Geist / Geist Mono, with tabular numerals on every metric.

---

## 5. What to ask for

In rough priority order:

1. **The degraded state.** How `#/metrics` should look when `persisting` is
   false, and when `write_failures > 0`. Smallest change, highest value —
   today both render as a normal-looking empty page.
2. **A per-request view.** The first surface that can exist once Phase 1 lands:
   a request list, the slowest N, and per-request unaccounted time. Must respect
   #616 if it shows exact extremes beside quantiles.
3. **A populated waterfall.** What the breakdown looks like once Phase 3 fills
   in database time and Phase 2 adds CPU alongside wall — including the empty
   state, which is 99.8% of requests today.
4. **The ingestion surface.** A distribution view keyed by `(lang, pipeline)`,
   reusing the same histogram vocabulary as the request surfaces.

### Fixture data to build the mocks on

Use the real tables in §2. In particular: p50 of 1 ms nearly everywhere, four
orders of magnitude of spread on a single route, 0.22% phase coverage, three
span names and no others, and error rates in the 8–11% range on three routes.
A mock that assumes a tidy 100–500 ms band will not survive contact.
