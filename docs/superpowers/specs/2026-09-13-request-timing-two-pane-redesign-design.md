# Request timing, second pass: triage before percentiles

**Status:** draft 2026-09-13. Not yet approved; no issue filed yet.
**Source design:** `Request Timing.html` in the `minerva` Claude Design
project (`019e0d6a-55f3-7e90-b2bf-130118cf440b`), pulled via `DesignSync`
on 2026-09-13.
**Supersedes the View section of:**
[2026-09-13-request-timing-observability-design.md](2026-09-13-request-timing-observability-design.md) (#581)
**Related:** #586 (llm_call measures time-to-headers), #585 (useElementSize
drops its fallback on a 0×0 measure), #599 (TimeSeriesChart ResizeObserver
comment names the wrong element), #589 (readRoute cognitive complexity),
#559 (cognitive complexity gate), #547 (frontend test location), #254
(duplication gate), #573 (local-vs-CI coverage divergence)

The surface that shipped with #581 answers "what are the percentiles?"
It does not answer "is anything wrong?" — the question an operator
actually opens it with. Today every route is one undifferentiated row in
a p95-sorted table, and a route returning 5xx on a fifth of its requests
looks exactly like a route that is merely slow. The redesign's whole
claim is that ordering by severity and saying so in a sentence is worth
more than another decimal place.

This is a **view-layer** change plus **one small endpoint addition**. The
store, the recorder, and the histogram are untouched.

## Measured

### What ships today

| Piece | File | Shape |
|---|---|---|
| Route shell | `web/src/routes/MetricsRoute.tsx:9` | Fully controlled; `window` + `label` in the URL |
| Panel | `web/src/Metrics/MetricsPanel.tsx:79` | Single column: window pills → optional detail block → full-width leaderboard sorted by p95 desc |
| Chart | `web/src/Metrics/TimeSeriesChart.tsx` | Hand-rolled SVG, two polylines, 4 gridlines, first/last x ticks |
| Styles | `web/src/Metrics/metrics.css` | `max-height: 100dvh` flex column; only `.metrics-table-wrap` scrolls |
| API client | `web/src/api/metricsApi.ts` | `fetchMetricsSummary(window, label?)`, `fetchMetricsSeries(label, {window, kind, span})` |
| Endpoints | `src/minerva/http/handlers/metrics.py` | `/api/metrics/summary`, `/api/metrics/series` |
| Route parse/serialize | `web/src/routing.ts:267`, `:421` | `window`, `label` |
| Tests | `web/tests/{MetricsPanel,MetricsRoute,metricsApi,metricsRouting}.*` | Four files |

Per-row fields available from `summary` (`store.py:141-155`): `label`,
`method`, `kind`, `span`, `count`, `mean_ms`, `min_ms`, `max_ms`,
`error_rate`, `p50_ms`, `p95_ms`, `p99_ms`. Nothing else.

### What the design asks for, and whether the data exists

| Design element | Backing | Verdict |
|---|---|---|
| Header subtitle "last 6 hours · 372 requests" | Window name + `Σ count` over `kind==="total"` rows | **Build** |
| Window pills | Unchanged | **Keep** |
| Two-pane split (list ‖ detail) | Layout only | **Build** |
| Severity dot `bad`/`warn`/`ok` | Nothing. No severity concept exists | **Invent a rule** (below) |
| Group headers "Needs a look" / "Inside usual range" | Follows from the severity rule | **Build** |
| Sort `severity / p95 / count / name` | All four derivable client-side | **Build, local state** |
| Row: dot, name, method chip, error %, count, p95 + bar | All present; bar = `p95 / max(p95)` | **Build** |
| Error cell "—" when clean | `error_rate === 0` | **Build** |
| Detail meta "streaming · 128 requests" | "streaming" = a `kind:"ttfe"` row exists | **Build (partial)** |
| Detail meta "· cached" | Nothing. No cache-hit signal is recorded | **Cut** |
| Tabs "Total" / "Time to first event" | `spanKind` signal already exists (`MetricsPanel.tsx:89`) | **Keep, rename, widen** |
| Tiles p50 / p95 / p99 / errors | Values present | **Build** |
| Tile deltas "+310% vs 24h" | Nothing. One `summary` call sees one window | **Needs an endpoint change** |
| Errors sub-label "9 of 47" | `Math.round(error_rate * count)` | **Build, with a caveat** |
| Chart card + legend + gridlines | Exists | **Keep** |
| Dashed event marker "deploy 21:40" | Nothing. No deploy or event stream exists anywhere in the repo | **Cut** |
| Per-route prose note under the chart | Nothing. Hand-written narrative in the mock | **Cut; replace with a derived line** |
| Waterfall "Where the time goes · p95 request" | Labeled `summary` returns `span != ''` rows with p95 | **Build** |
| `wfTotal` "9800 ms total" | The route's own p95 | **Build** |
| Per-route `wfNote` | Nothing, except the `llm_call` caveat already in the code | **Cut, except llm_call** |
| Empty "No sub-spans recorded for this route." | Replaces today's hide-the-table | **Build** |

**The waterfall percentages are a straight ratio, and the mock's own
numbers prove it.** `range_scan` 8900/9800 = 90.8 → the mock's `pct: 91`;
`hydrate` 620/9800 = 6.3 → `6`; `serialize` 180/9800 = 1.8 → `2`. Same on
the chat route: 3420/4320 = 79.2 → `79`, 640/4320 = 14.8 → `15`,
180/4320 = 4.2 → `4`. So `pct = span.p95_ms / route.p95_ms`, and the mock's
`k` flag marks the largest span — which is always first, because
`summary()` already sorts by p95 desc (`store.py:160`). Note both routes
sum to 99% and 98%, not 100: the mock is itself consistent with spans not
summing to the total.

### Gap 1: there is no baseline, and no way to ask for one

`_range()` (`handlers/metrics.py:48`) derives `since` from the window name
and `until` from `time.time()`. There is no parameter that moves the
window, so a second call can only ever fetch a window *anchored to now*.
Comparing a 6h window against a 24h window is comparing a set against its
own superset: a spike inside the last 6h also raises the 24h number,
damping the very delta the tile is trying to show. And at `window=24h`
the comparison is against itself, and at `window=all` there is nothing
left to compare to.

### Gap 2: the design is dark-theme only

Its `:root` block is character-for-character the repo's
`[data-theme="dark"]` palette (`web/src/styles/styles.css:64-80`) —
`--paper:#14110e`, `--ink:#e2d8c4`, `--accent:#c97a65`, and so on. The
`--p50:#3a93d1` / `--p95:#c97a65` pair likewise matches `metrics.css`'s
existing dark `--metric-p50` / `--metric-p95`. So the chart colours are
unchanged and the surrounding chrome is already tokenized. What is
genuinely new is the severity triad — `--bad:#c85a4a`, `--warn:#d9a441`,
`--ok:#6f8f6a` — which has **no light-theme counterpart anywhere**, and
those three values are too light to carry on `#f4efe6` paper.

### Gap 3: the list's ARIA in the mock is invalid

The mock nests `<button role="option">` inside `role="listbox"`. `option`
is not a valid role for a `button`, and a listbox owning buttons is not a
listbox. This is a mock artifact, not a requirement.

### Correction: "Errors" counting only 5xx is deliberate, not a bug

`summary()` counts `SUM(CASE WHEN status_class = 5 THEN count ELSE 0 END)`
(`store.py:136`), so a 4xx never reaches `error_rate` even though
`status_class` is recorded for every class. That reads like an oversight.
It is not — `recorder.py:119-126` says so explicitly:

> `error_status` maps a failing exception to the status the client is
> actually going to receive, so a handler that raises a 404 or a 400 is
> not filed under `status_class = 5`.

**Had I trusted the surface label instead of the source, I would have
filed a bug against intended behaviour and "fixed" it by folding 4xx into
`error_rate` — which would turn every bot probing for `/wp-admin` into a
`bad`-severity route on this dashboard.** No issue filed. The correction
this spec *does* make is cosmetic: the column and tile say "Errors" when
they mean server errors, so they get relabelled (below).

### Gap 4: two open issues land directly on this work

- **#585** — `useElementSize` discards its fallback on a 0×0 measurement,
  collapsing four SVG components. A two-pane layout that collapses to one
  pane on mobile measures the chart while its pane is hidden. This is the
  exact trigger.
- **#589** — `readRoute`'s cognitive complexity is already over the Sonar
  limit "and grows with every new surface". Adding a `sort=` query
  parameter to the metrics route makes a failing gate worse.

## Hypothesis

### Decisions taken

1. **The sort control is local state, not a URL parameter.** It follows
   `spanKind`'s precedent (`MetricsPanel.tsx:89`) and, per #589, adding a
   parameter to `readRoute` worsens a gate that is already red. Revisit
   only after #589 lands.
2. **Baselines come from a new `offset` parameter, not a wider window.**
   Rationale in Gap 1 — a superset comparison damps the signal and
   degenerates entirely at `24h` and `all`.
3. **Everything the mock narrates in prose is cut.** The chart's per-route
   note, the event markers, and the `wfNote` lines are hand-written
   analysis, not derived values. A dashboard that invents sentences it
   cannot recompute is worse than one that stays quiet.
4. **The verdict line stays**, because it *is* recomputable — it is a
   template over counts, not narration.
5. **The detail pane is always present.** No "← All routes" on desktop;
   it returns only in the mobile collapsed layout.

### The `offset` parameter

`/api/metrics/summary` and `/api/metrics/series` gain an optional
`offset` — an integer count of whole windows to shift back. `offset=1` at
`window=6h` means "the 6 hours before the last 6 hours". This keeps the
API's vocabulary of named windows rather than accepting arbitrary
timestamps, so the query stays bounded.

```python
def _range(qs: dict[str, str]) -> tuple[float, float, str]:
    name = qs.get("window", "24h")
    width = _parse_window(name)
    offset = _parse_offset(qs.get("offset"))   # >= 0; default 0
    if width is None:
        if offset:
            raise _HTTPError(HTTPStatus.BAD_REQUEST, "offset is not valid for window=all")
        return 0.0, time.time(), name
    until = time.time() - width * offset
    return until - width, until, name
```

`window=all` with a non-zero offset is a 400: an unbounded window has no
previous one. A negative or non-integer offset is a 400 by the same
parser.

### Severity, and the sentence it produces

One exported constant object, one pure function, both unit-testable
without a DOM:

```ts
export const SEVERITY_THRESHOLDS = {
  warnP95Delta: 0.10,   // +10% vs the previous window
  badP95Delta: 1.00,    // +100%
  minCountForDelta: 10, // below this, percentiles are noise
} as const;

export type Severity = "bad" | "warn" | "ok";
export function severityOf(row, prior, t = SEVERITY_THRESHOLDS): Severity
```

Rules, in order:

1. `error_rate > 0` → **bad**. A 5xx is a failure at any volume, so this
   branch ignores `minCountForDelta`.
2. `count < minCountForDelta`, or no `prior` row, or `prior.p95_ms === 0`
   → **ok**. A delta computed from four requests is not a signal; the
   mock's own copy says so ("Only 4 requests in this window, so the
   percentiles are noisy").
3. `(p95 - prior.p95) / prior.p95 >= badP95Delta` → **bad**.
4. `… >= warnP95Delta` → **warn**.
5. Otherwise **ok**.

At `window=all` no prior exists, so rule 2 makes every non-erroring route
`ok` and the grouping degenerates to a flat list. That is correct and
should not be special-cased.

**These three numbers are a guess.** They are the one part of this spec
written before anyone ran it against real traffic, which is why they live
in a single exported constant rather than inline. Expect to tune them.

The verdict line is a template over the resulting counts — `bad`, `warn`,
`ok`, and the worst route's name and error figures. Three shapes:

- some `bad`: "**N routes are failing.** *name* returned errors on X of Y
  requests." + the warn/ok tail.
- no `bad`, some `warn`: "**Nothing is failing.** M routes are slower than
  the previous window; the other K are inside their usual range."
- no rows at all: "No requests recorded in this window." (today's empty
  state, promoted into the verdict slot).

Cut from the mock's wording: "its p95 sits at the 10 s timeout" — the
server does not know the client's timeout.

### Layout

`main` becomes `grid-template-columns: minmax(340px, 420px) 1fr`. The left
column scrolls; the right column scrolls independently. The design's
`minmax(380px,460px)` is narrowed slightly because the repo's app shell
takes horizontal chrome the standalone mock does not.

Selection: `selected() = props.label ?? worstRouteLabel()`. A bare
`#/metrics` lands on the highest-severity route without writing to the
URL; `onNavigate` fires only on an explicit click. The panel stays
controlled — the default is derived, not stored.

### The TTFE tab now drives the tiles, not just the chart

Today the toggle relabels the chart and nothing else, and the panel says
so in a note reading "trend chart only" (`MetricsPanel.tsx:232`). That
note exists because the toggle under-delivers. It need not: the unlabeled
summary already carries a full second row per streaming route at
`kind:"ttfe"` — its own `count`, `error_rate`, `p50/p95/p99`. Under the
"Time to first event" tab the **tiles and the chart** both switch to that
row.

The **waterfall does not**, and this is where the caveat moves to. Every
sub-span row is `kind:"total"` — the recorder never tags a sub-span
`ttfe` (`recorder.py:144-153`) — so the card carries "Sub-spans are
measured on the whole request" while the TTFE tab is active, replacing
the old head-level note.

### The waterfall card

`pct = span.p95_ms / route.p95_ms`, clamped to `[0, 100]` for the bar
width only — the printed percentage is not clamped, because a value over
100% is real information. The existing `llm_call` note is preserved
verbatim and is the only surviving per-span note; it is the user-visible
face of **#586**, and this card should link it once #586 is resolved.

Rows come back p95-sorted from the server (`store.py:160`); do not re-sort.
Empty state: "No sub-spans recorded for this route." — only three code
paths are instrumented, so this is the common case, not the edge one.

### Chart

`TimeSeriesChart`'s public shape is unchanged. Two changes inside:

- Gridline tick labels switch to the mock's `1.4s` form above 1000 ms.
- The y-domain gets a 15% headroom factor, as the mock does
  (`max = Math.max(...p95s) * 1.15`), so the top line is not flush
  against the frame.

**Do not adopt the mock's `viewBox="0 0 880 250" preserveAspectRatio="none"`.**
It stretches stroke widths and text with the container. Keep the existing
measured-width / fixed-height arrangement, and keep the comment above
`height()` explaining why height is not measured — with **#599**'s
correction applied to the element name it cites while this file is open
anyway.

Before this lands, **#585 must be checked**: a pane that is
`display: none` at mobile width measures 0×0, and #585 says the fallback
is discarded in exactly that case. If #585 is still open, the mobile
layout must unmount the hidden pane rather than hide it.

### Theme and tokens

Three new tokens in `web/src/styles/styles.css`, both themes, beside the
existing palette rather than in `metrics.css` — severity is a concept the
Refs and Network surfaces will want too:

| Token | Dark (from the design) | Light |
|---|---|---|
| `--bad` | `#c85a4a` | TBD — darken until ≥ 4.5:1 on `--paper: #f4efe6` |
| `--warn` | `#d9a441` | TBD — amber fails contrast fastest; expect a large shift |
| `--ok` | `#6f8f6a` | TBD — same treatment |

Light values are **not** in the design and must be picked and measured
against `--paper: #f4efe6`, not eyeballed. `metrics.css`'s existing
"do not retint by eye" comment on the chart pair applies here too.

Severity is never signalled by colour alone: the dot is accompanied by
the group heading ("Needs a look"), and the row's error cell carries the
figure. That keeps the list readable without colour.

The mock's `--p50` / `--p95` duplicate `metrics.css`'s `--metric-p50` /
`--metric-p95`. Keep the existing names; do not introduce a second pair.

### Mobile

The design is `overflow: hidden` over a 380px-minimum two-column grid; at
the repo's ~400px target it has no viable layout. Below the repo's
768px breakpoint (`web/src/styles/mobile.css:35`) the panes stack and
become mutually exclusive: the list is the default view, selecting a route
replaces it with the detail, and the "← All routes" control — deleted on
desktop — returns as the way back. The tile grid drops from four columns
to two. Per #585 above, the inactive pane is unmounted, not hidden.

### Component split

`MetricsPanel.tsx` is 379 lines of dense nested conditionals today, and
#559 established that adding to an already-dense function is enough to
fail Sonar's maintainability rating at **A** even while coverage is green
— `check-diff-coverage` read 91.7% the whole time #559 was blocked at
cognitive complexity 29. Nothing local warns, and `ruff --select C901` is
not this metric and flags a different function.

So the split is not optional cleanup; it is how this change passes the
gate:

| New file | Holds |
|---|---|
| `Metrics/severity.ts` | `SEVERITY_THRESHOLDS`, `severityOf`, `verdictOf` — pure, no JSX |
| `Metrics/RouteList.tsx` | Grouping, sorting, rows, bars |
| `Metrics/StatTiles.tsx` | The four tiles and their delta formatting |
| `Metrics/SpanWaterfall.tsx` | The waterfall card, its total, the `llm_call` note |
| `Metrics/MetricsPanel.tsx` | Resources, selection, tab state, composition |

`severity.ts` being pure is what lets the thresholds be tested exhaustively
without mounting anything — which is also how the branch coverage gets
paid for cheaply.

Sonar's duplication gate (≤3% on new code, #254) is the reason
`RouteList` and `SpanWaterfall` are separate rather than one "list of
rows with bars" abstraction: they share a visual motif and no data shape,
and #254 is the precedent for extracting a shared shell only when the
shapes actually match. They do not here.

### Testing and gates

New tests, all under `web/tests/` — **never colocated under `web/src`**,
which fails the Sonar gate invisibly (#547):

- `severity.test.ts` — the rule table, branch by branch: 5xx at low count,
  low count without errors, missing prior, `prior.p95 === 0`, each
  threshold boundary from both sides, and each of the three verdict shapes.
- `RouteList.test.tsx` — grouping, all four sort orders, bar widths,
  the `—` error cell, selection.
- `StatTiles.test.tsx` — delta sign and direction class, the `—` state
  when no prior exists, the "X of Y" derivation.
- `SpanWaterfall.test.tsx` — ratio, the over-100% case, the empty state,
  the `llm_call` note.
- `MetricsPanel.test.tsx` — extended: default selection lands on the worst
  route without calling `onNavigate`; the TTFE tab switches tiles *and*
  chart but not the waterfall.
- Python: `_parse_offset` — 0, positive, negative, non-integer, and
  `window=all` with an offset, which must be 400.

Gate notes carried from CLAUDE.md:

- `make check` before any claim, and **again after every edit made while
  fixing its output**.
- ≥80% new-code coverage **including branches**; a guard whose false arm
  is untested scores 3/4 (#250).
- These tests read no `data/` corpus, so the local and CI numbers should
  agree — the #573 divergence does not apply here. That is worth stating
  rather than assuming.
- `make check-pr-link PR=<n> ISSUES="<n>"` at close-out.

### Estimate

| Slice | Size |
|---|---|
| `offset` parameter + its tests | ~40 lines, small |
| `severity.ts` + tests | ~90 lines |
| Component split of the existing panel | mechanical, no behaviour change — land it as its own commit so the redesign diff is readable |
| `RouteList` + verdict + header subtitle | ~180 lines |
| `StatTiles` + baseline fetch | ~110 lines |
| `SpanWaterfall` | ~70 lines |
| CSS: two-pane, tokens, mobile | ~200 lines |

The component split landing **first and separately** is the part that
matters: a single commit that both restructures and redesigns is one no
reviewer can read, and it is the shape that got #559 blocked.

### Out of scope

- Event markers on the chart. There is no deploy or event feed to draw
  from; adding one is its own piece of work.
- A "cached" badge. Nothing records cache hits.
- Per-route written analysis. Not recomputable; see decision 3.
- Folding 4xx into `error_rate`. Deliberately excluded — see the
  correction above.
- Putting the sort order in the URL. Blocked behind #589.
- `mean_ms` / `min_ms` / `max_ms`. Available, unused today, unused here.
