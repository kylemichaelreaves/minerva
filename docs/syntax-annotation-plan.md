# Dependency-syntax close reading — implementation plan

> **Status (2026-08-01): all seven phases shipped.** Every frame of
> `syntax-wireframes/index.html` now has an implementation. Relabel, reattach
> by drag or keyboard, undo, both exports, the derived topological fields and
> the whole-sentence strip all work, and both refusals are reachable and
> visible. What is left is listed under *Known gaps*.

## Problem

Minerva can say what a German word *is* — `chunk_lemmas` holds 26,163,969 rows
carrying surface form, lemma, UPOS and raw UD `feats`:

```
2 | Pessimismus | Pessimismus | NOUN | Case=Nom|Gender=Masc|Number=Sing
5 | endet       | enden       | VERB | Mood=Ind|Number=Sing|Person=3|VerbForm=Fin
```

It cannot say how the words *hang together*. There is no `head`, no `deprel`,
and no sentence boundary anywhere in the schema. The dependency step was
switched off deliberately for throughput — every spaCy pipeline loads with
`disable=["parser"]` (`lemmatize.py:210,230,261,324,348`, the last citing a
2–3× per-chunk cost) and every Stanza pipeline is `tokenize,pos,lemma`
(`lemmatize.py:295,302`).

For Hegel and Nietzsche that gap is the interesting one. No gold German
treebank exists for philosophical prose, and statistical parsers fail
precisely where the syntax is doing interpretive work: extraposed relatives,
heavy Mittelfeld, verb-final subordination. So a viewer alone is not the
deliverable — **correcting the parse is the primary activity**, and the tool
has to be built around the ergonomics of reattaching a node and relabelling an
edge.

The same chunk above already shows why: `d. h.` was split into two tokens and
lemmatized as `der` (PRON) + `heißen` (VERB).

## Scope

German only. Not in scope, and no scaffolding for them: multi-language
comparison, parallel text, word alignment, RTL, constituency trees, an in-app
parser, or a theming layer.

The UI is a **full-bleed overlay** off the Reader, following the existing
`#/network/arc` drilldown pattern.

## Design decisions

| Question | Decision | Why |
|---|---|---|
| Where trees come from | Parse on demand, cache | No 26M-row re-pass; the corpus fills in where you actually read. The bulk CLI writes the same table, so the two aren't in tension. |
| Token layer | Fresh Stanza parse into a new `chunk_syntax` table | `chunk_lemmas` stays untouched, so `term_occurrences`, the glossary importer and concordance are unaffected. Aligned to the reading pane by character offset. |
| Parser | Stanza German (UD), **not** spaCy | See below — spaCy German emits TIGER, not UD. |
| Persistence | SQLite | Corrections are hand labour and must survive a browser, a device, and a re-ingest. |
| Correction shape | Append-only log, replayed over the pristine parse | Real undo, full history, and the DB knows which tokens are hand-corrected — which is what drives the epistemic colouring. |

### What Stanza German actually produces (measured 2026-07-31)

Run against the two fixture sentences, `stanza 1.13.0`, model
`de` (`tokenize,pos,lemma,depparse`):

**The projective fixture — 8 of 9 tokens exact**, including the shape that
matters: `entwickelt` root, `hat` as its `aux`. The one divergence is `sich`
→ `obj` where the fixture has `expl:pv`.

**The non-projective fixture — Stanza cannot produce it.** It attaches the
relative clause to `gesehen` (the root) rather than to `Mann`, i.e. it makes
the extraposition error:

```
              Stanza           fixture
9  steht      head=5  acl      head=2  acl:relcl

non-projective arcs, Stanza:  NONE
non-projective arcs, fixture: 2->9 [2,9], 5->10 [5,10]
```

Two consequences worth holding onto:

1. **The fixtures are corrected trees, not machine output.** Both crossings
   exist only after a human reattaches `steht` to `Mann`. This is the tool's
   premise demonstrating itself on the brief's own example sentence, and it is
   the clearest justification for colouring by epistemic status.
2. **Stanza's German is GSD-trained; the fixtures are HDT-style.** `obj` vs
   `expl:pv`, `acl` vs `acl:relcl` — the machine emits one subtype family and
   the corrector will reach for the other. Phase 4's relation picker must
   offer both, or the correction the user wants will not be in the list.

Performance, for the on-demand decision: **4.3 s** one-time pipeline load,
then **0.15 s** for a 284-character chunk. Lazy singleton, warmed once per
process.

### spaCy German is unusable here

`de_core_news_sm` has a parser; it is only disabled. But it emits TIGER labels
and an inverted verbal-complex tree:

```
spaCy:  hat = ROOT,  entwickelt = oc,  Geist = sb,  Der = nk
UD:     entwickelt = root,  hat = aux,  Geist = nsubj,  Der = det
```

That breaks the relation inventory, the fixtures, and the topological-field
rule, which depends specifically on UD attaching `aux` *to* the participle.
Stanza German (GSD/HDT) is the only option producing UD. Note German is
currently absent from `_init_stanza_generic`'s `{"heb": "he", "ara": "ar"}` map
at `lemmatize.py:287`; the syntax pipeline is a separate one, not a change to
that.

## Two corrections to the source brief

Found by hand-checking the golden fixtures against the brief's own algorithms.
Both change acceptance criteria.

### 1. `fixture_nonprojective.conllu` has two non-projective arcs, not one

The brief asserts only `acl:relcl` is non-projective. Apply `isNonProjective`
to token 10 (`.`, head 5, span `[5,10]`): interior token 9 has `head = 2`, and
`2 < 5`, so it returns true.

This is not an artefact of the rule. Arcs `9→2` and `10→5` genuinely interleave
(`2 < 5 < 9 < 10`) and would cross if both were drawn above the row. Running
`assignLevels` over the non-projective set gives the below-line stack:

| relation | span | level |
|---|---|---|
| `punct` (10→5) | [5,10] | 1 |
| `acl:relcl` (9→2) | [2,9] | 2 |

The level table for `fixture_projective.conllu` **is** correct as briefed — all
eight rows were traced and the specified sort (width ascending, then start) plus
the "disjoint or share exactly one endpoint" rule reproduce it exactly.

### 2. The Rechte Klammer rule is inverted for UD

The brief defines RK as "tokens depending on LK". In UD the participle is the
head and the finite auxiliary is its `aux` dependent — so in fixture 1, `hat`
(3) depends on `entwickelt` (8), nothing depends on `hat`, RK computes empty,
and the Mittelfeld swallows the rest of the clause. The briefed expectation is
`RK = entwickelt`.

Corrected heuristic:

```
LK = finite verb (VerbForm=Fin, UPOS in {VERB, AUX})
if deprel(LK) in {aux, aux:pass}:
    V  = head(LK)                       # the non-finite verbal head
    RK = {V} ∪ {dependents of V with deprel in
               {aux, aux:pass, xcomp, compound:prt} and index > LK}
else:
    V  = LK
    RK = {dependents of LK with deprel in {compound:prt, xcomp}}   # may be empty
```

Punctuation must also be excluded from field assignment, or fixture 1's
Nachfeld contains `.` rather than being empty as briefed.

This stays a heuristic and will be wrong on complex sentences. It renders in
the derived colour and is toggleable. Do not special-case to improve accuracy —
if it is wrong, the user corrects the tree and the fields recompute.

## Backend

### Migration `0024_chunk_syntax.sql`

`0023` is the latest on disk and applied (`schema_migrations` → 23).

```sql
CREATE TABLE chunk_syntax (               -- the machine parse; immutable
  chunk_id      TEXT    NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  sent_ord      INTEGER NOT NULL,         -- 0-based sentence within the chunk
  tok_id        INTEGER NOT NULL,         -- 1-based, CoNLL-U ID
  form, lemma, upos, xpos, feats, misc  TEXT,
  head          INTEGER NOT NULL,         -- 0 = root
  deprel        TEXT    NOT NULL,
  surface_start INTEGER NOT NULL,         -- offsets into chunks.text
  surface_end   INTEGER NOT NULL,
  PRIMARY KEY (chunk_id, sent_ord, tok_id)
);

CREATE TABLE chunk_syntax_state (         -- what parsed it, when
  chunk_id  TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  parser    TEXT NOT NULL,                -- 'stanza-de-<version>'
  parsed_at REAL NOT NULL
);

CREATE TABLE chunk_syntax_corrections (   -- hand labour; NO foreign key
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id   TEXT    NOT NULL,
  sent_ord   INTEGER NOT NULL,
  tok_id     INTEGER NOT NULL,
  kind       TEXT    NOT NULL CHECK (kind IN ('head','deprel')),
  from_val   TEXT,
  to_val     TEXT    NOT NULL,
  created_at REAL    NOT NULL
);
```

**The missing FK on the corrections table is deliberate.** This repo has lost
annotation to re-ingest three times — see `docs/MEMORY.md`, the `0013` cascade
relaxation, and the lemma/xref snapshot machinery in
`src/minerva/store/preserved_state.py`. Hand corrections will be the most
expensive data the system holds. They must survive `index --reset`: no cascade,
plus an entry in `preserved_state.py` alongside the existing snapshots.

`chunk_syntax` itself *does* cascade — it is reproducible machine output, and a
re-ingest should invalidate it.

### `src/minerva/syntax/`

- **`parse.py`** — lazy Stanza German singleton
  (`tokenize,pos,lemma,depparse`). Model downloads to `~/stanza_resources/` on
  first use. Emits sentences with per-sentence 1-based ids and character
  offsets back into `chunks.text`.
- **`queries.py`** — `load_or_parse(conn, chunk_id)`, `append_correction`,
  `delete_correction`, and the replay `materialise(pristine, corrections)`.
  Keep `materialise` pure and tested; it is the integrity guarantee for the
  whole tool.

**Tests must mock the pipeline.** `.github/workflows/check.yml` installs
`.[dev,hegel,embed]` — *not* `[lemma]` — so there is no `stanza` in CI and no
model in `~/stanza_resources/`. A test that constructs a real pipeline would
pass locally and fail the moment it ran anywhere else. Follow the precedent
the lemmatizer tests already set: mock at the pipeline boundary and test the
storage, replay and endpoint logic against fixed token structures.

### HTTP

```
GET    /api/chunks/{id}/syntax              parse-if-absent → sentences, corrections applied
POST   /api/chunks/{id}/syntax/corrections  append one correction
DELETE /api/syntax/corrections/{id}         undo
```

Each token carries `corrected: bool` so the client can colour by epistemic
status without re-deriving it.

Two things to get right, both from the July 2026 audit:

- **Rate-limit the GET.** An uncached parse is CPU-bound; add it to
  `_RATE_LIMITS` in `http/server_core.py`. That limiter has a known
  bucket-eviction bug (#121).
- **This adds the third state-changing POST**, and unlike chat it mutates
  durable scholarly data. There is still no CSRF protection (#118). Land #118
  first, or at minimum enforce `Content-Type: application/json` on this route.

### CLI

`minerva syntax parse --work <id>` warms a whole work in bulk, following the
`cli/terms/lemmatize.py` shape. Writes the same table the endpoint reads, so a
warmed chunk is simply a cache hit.

## Frontend — `web/src/Syntax/`

```
Syntax/
  conllu/{types,parse,serialise}.ts    export + external-treebank import + test substrate
  layout/{measure,arcs,fields,minimap}.ts  the real geometry
  corrections/store.ts                 optimistic queue over the API
  components/{ArcDiagram,TokenInspector,SentenceList}.tsx
  index.tsx
  syntax.css
web/public/data/fixture_{projective,nonprojective}.conllu
```

`conllu/`, `layout/` and `corrections/` are not `hooks/` or `utils/`, so they
clear the `no-restricted-syntax` rule at `eslint.config.js:70-96`. This departs
deliberately from the single-file-component convention in `docs/FRONTEND.md`:
every one of these modules is pure and independently testable, which is worth
the exception.

**No new dependencies.** SVG is hand-written; the CoNLL-U parser is written,
not installed. The format is tab-separated, ten columns, sentences separated by
blank lines, `#` comments carrying metadata.

**Route.** New `{ kind: "syntax"; chunkId: string; workId: number }` at
`#/syntax/<chunkId>?work=<id>`, added to the regex cascade in `routing.ts` and
special-cased out of the chrome in `App.tsx` the way `network-arc` is at line
147.

**Reuse.** `computePopoverPosition` (`utils/popoverPosition.ts`) for the token
card; `POS_LABEL` (`Reader/wordInfoMorph.ts`) for UPOS display;
`useElementSize` for the canvas. `layoutLabelsGreedy`
(`utils/atlasGeometry.ts`) is **not** reusable — it packs label boxes with no
nesting awareness, and arc levels need nested-interval logic. Write
`assignLevels` fresh.

**Measurement is greenfield.** Nothing in the repo measures text; everything
estimates `chars × 0.55 × fontSize` (`atlasData.ts:274`, `NetworkArc.tsx:129`).
`measure.ts` introduces the first real `getComputedTextLength`, gated on
`document.fonts.ready` — measuring before fonts resolve makes arcs land wrong
on first paint and then snap, which reads as broken. Cache by
`(text, fontKey)`. jsdom returns `0`, so `tests/setup.ts` needs a stub; width
proportional to length suffices, since the golden assertions are about levels
and projectivity, not pixels.

**Fonts.** Token text needs full German diacritic coverage (and polytonic Greek
later). Add Gentium Plus to the single Google Fonts `<link>` in
`web/index.html`. There are no self-hosted fonts in this repo and this need not
be the first. UI chrome keeps the existing grotesque; do not set token text in
the UI font.

**Colour encodes epistemic status** — the one thing this tool genuinely knows.
Feature-scoped tokens under `:root` and `[data-theme="dark"]`, following the
`--net-*` / `--atlas-*` precedent:

```
--syn-gold      saturated ink blue      hand-corrected
--syn-machine   same hue, desaturated   uncorrected parse
--syn-derived   muted oxide, dashed     topological fields
```

Non-projective arcs use the same blue but render *below* the row — position
carries the meaning, not hue. Do not redefine `--accent`, `--accent-soft` or
`--selection`; `theme.ts:43-48` writes those inline on `<html>` and will win.
Prefix every class `syn-`; `net-`, `atlas-`, `r-`, `conc-`, `refs-` are taken
and all stylesheets are global.

**Signature interaction.** Hovering a token dims every arc except the subtree
it governs, so the constituent it heads becomes visible as a shape. This is the
thing that makes the tool worth using over a printed text.

**Quality floor**, without announcing it in the UI: arrow-key navigation
between tokens, visible focus rings, `prefers-reduced-motion` respected.

## Execution tracker

| # | Scope | Status |
|---|---|---|
| **0** | `conllu/` types + parse + serialise, both fixtures, round-trip tests | ✅ DONE 2026-07-31 (#131) |
| **1** | `measure.ts`, `arcs.ts` + golden-fixture tests. No rendering. **Stop and report.** | ✅ DONE 2026-07-31 (#131) |
| **2** | Migration 0024, `syntax/parse.py`, `queries.py`, endpoint, CLI, `preserved_state` entry, pytest | ✅ DONE 2026-07-31 (#134) |
| **3** | Route, overlay shell, `ArcDiagram`, `SentenceList`, `TokenInspector`, fonts, CSS. Read-only. | ✅ DONE 2026-07-31 (#135) |
| **4** | Corrections: append/undo endpoints, `store.ts`, pure `apply()` + tests, relabel picker, cycle + single-root validation, both exports | ✅ DONE 2026-08-01 (#137) |
| **5** | Drag reattach with refusal flash, ROOT drop-zone, keyboard reattach | ✅ DONE 2026-08-01 (#138) |
| **6** | Topological fields overlay, toggleable | ✅ DONE 2026-08-01 |
| **7** | Long-sentence minimap | ✅ DONE 2026-08-01 |

### Where we stopped

**2026-08-01, after Phase 7.** All seven phases are shipped and every frame of
the design has an implementation. Nothing is half-built, and
`chunk_syntax_corrections` is back to 0 rows (the corrections made while
verifying in the browser were test data and were removed). What remains is in
*Known gaps* — two latent defects and a handful of deliberate departures, none
of them blocking.

Subtree-hover dimming moved from Phase 5 into Phase 3: it needs no correction
machinery, and it is the interaction that makes the diagram worth looking at,
so shipping it with the read-only view was cheaper and better.

Commit at each boundary.

Seven phases rather than the briefed six: the backend is work the brief did not
anticipate (its standalone `scripts/parse_text.py` is absorbed into Phase 2),
and the briefed Phase 3 was doing too much — it is split into 4 and 5 so the
correction loop is exportable and under test one commit before pointer
interaction lands on top of it.

**Phase 0 detail worth not forgetting:** multiword-token ranges (`1-2`) and
empty nodes (`1.1`) are skipped for rendering but must be **retained as raw
lines with their ordinal**, because byte-identical round-trip requires
re-emitting them in place.

**Where this could overrun.** Phase 5. Drag-to-reattach in SVG with a
live-updating layout, a refusal path, and subtree dimming is more than it reads
as. If it bloats, the cut is to ship keyboard reattach alone — it satisfies
every acceptance criterion except the word "drag", and it is the faster input
method anyway.

## The wireframes, and what they settled

Designed in Claude Design (project `minerva`, `syntax-wireframes/index.html`)
and imported 2026-07-31. Nine frames. `design-canvas.jsx` is the pan/zoom
artboard shell for *viewing* wireframes and is deliberately not ported.

### Wrapping, not scrolling — the width problem's answer

The brief's nine-token example hid the real constraint. Measured across 80
sentences of German from the live corpus at 20px type:

| | |
|---|---|
| median token-row width | 1328px |
| wider than a 1440px viewport | **44%** |
| wider than 1920px | 20% |
| widest (109 tokens) | 7824px — **5.4 screens** |
| arc stack on a 53-token sentence | 8 levels above, 2 below |
| longest single arc | spans 47 tokens |

Zoom-to-fit puts the median sentence at 22px type and the tail far below
legibility; horizontal scroll means a 47-token arc is never visible as one
shape. Neither lets a reader see both endpoints *and* the label at once, which
is the entire job.

So **rows wrap**. An arc crossing a boundary is cut at the measure edge and
resumes on the next row carrying the partner token's index (`→ 53`); an arc
spanning a row it does not touch leaves a pass-through bar at its level. Rows
break just after punctuation in the last fifth of the measure, so cuts land at
clause edges where fewest arcs are severed.

This required geometry Phase 1 did not have — `layout/rows.ts` (`breakRows`,
`segmentArcs`) and cut-end support in `arcPath`.

### Frame → phase

| Frame | Phase |
|---|---|
| 01 At rest (+ dark) | 3 ✅ |
| 02 Long sentence, wrapped | 3 ✅ · minimap 7 ✅ |
| 03 Subtree on hover | 3 ✅ |
| 04 Non-projective below the row | 3 ✅ |
| 05 Token inspector | 3 ✅ read-only; its action buttons → 4/5 |
| 09 Sentence list | 3 ✅ |
| 07 Relation picker | 4 |
| 08 Refused · cycle | 4 |
| 06 Mid-reattachment | 5 |
| Topological fields (in 01, 04) | 6 |
| Minimap (in 02) | 7 ✅ |

### Two rules from the design worth carrying into Phase 4

**No free text in the relation picker.** A mistyped deprel validates, exports,
and is wrong — silent data corruption. The field filters; it never accepts.

**The inventory needs both subtype families.** Stanza's German is GSD-trained
while the fixtures are HDT-style: the machine emits `obj` and `acl` where a
corrector reaches for `expl:pv` and `acl:relcl`. If the picker offers only one
family, the correction the user wants is not in the list.

## What Phase 3 actually ships

Verified in Chrome at 1440×900 against a real 53-token Nietzsche chunk
(`001067f31d657a9dbcc4`): three rows at 20/19/14 tokens, none overflowing the
1344px measure, 58 arcs with geometry, cut markers spanning boundaries, and
hovering `Pessimismus` dimming 55 of 59 arcs so *Auch dieser Pessimismus der
Stärke* reads as one shape.

**Not in Phase 3**, and not a regression: reattachment, the relation picker,
the refusal states, topological fields, the minimap.

### One bug worth remembering

The first `ArcDiagram` read token positions back from the laid-out DOM and
produced a diagram with every arc collapsed into a vertical stack at the left
edge. The measurement was **circular**: widths decide the row breaks, the row
breaks decide the DOM, and measuring the DOM decided the widths — so the
metrics were always one layout stale.

Fixed by measuring each token's width once off a hidden probe and computing
row-local positions analytically. A token's width does not depend on which row
it lands on, which is what breaks the cycle. A second instance of the same
class followed immediately: the probe measures `.syn-form`, but each
`.syn-tok` adds 8px of padding, so every row underestimated itself by 8px per
token and the last few overflowed.

Neither would have failed a test written from the spec. Both were found by
looking at the rendered page — which is why Phase 4 and 5 should also be
checked in a browser and not only under vitest.

## What Phase 4 actually ships

The relabel loop, end to end: select a token, `L`, filter a closed inventory,
Enter. The edit shows immediately, posts behind you, and rolls back whole if
the server says no. Revert takes it off again, including a correction made in
an earlier session.

**Decided: corrections have no author.** There is no user or auth concept
anywhere in this codebase — it is a single-operator tool — so the inspector
reads `Hand-corrected · was obj` and drops the design's `a.reuter`. Not a
one-way door: the log is append-only with no backfill need, so
`ALTER TABLE chunk_syntax_corrections ADD COLUMN author TEXT` is a one-liner
whenever a second operator turns up.

**The GET contract changed.** It now answers with the *pristine* parse and the
correction log side by side, instead of the two already merged. Undo has to
recompute the tree without one entry, and that is impossible from a merged
tree — the first attempt shipped a Revert button that was correctly rendered,
correctly wired, and pointed at nothing after a reload. The client replays via
`corrections/apply.ts`, the mirror of `materialise`.

**Deprels are validated twice, differently, on purpose.** The client checks
membership of the 47-entry inventory, because the picker is right there and
nothing off-list should reach the wire. The server checks only the *shape*
(`^[a-z]+(:[a-z]+)?$`), because duplicating the inventory across two languages
means two lists to keep in step. The shape check is what stops a TIGER label
or a paste from reaching storage.

**Root is checked before cycles.** In a well-formed tree the root governs every
token, so *every* reattachment of the root is also a cycle. Reporting that
would be true and useless; "give the root to another token first" is the
sentence that tells the user what to do.

### Three bugs the tests could not have found

All three were found by opening the page, which is why the plan says to.

1. **`<Show when={x && x !== "_"}>` renders an empty row.** The callback form
   receives the *condition*, not the value — so `xpos()` was `true`, which
   Solid renders as nothing, and XPOS showed a label with no tag. Narrow to
   the value, never to a boolean.
2. **A capture-phase `stopPropagation` ate the picker's own Enter.** The
   picker registered a window listener to stop the overlay's shortcuts firing
   underneath it. Capture runs *before* the target, so the component's own
   `onKeyDown` never ran and Enter silently did nothing. The overlay already
   ignores keys while the picker is open; that is the right place for it.
3. **Revert was dead after a reload** — the merged-tree contract above.

A fourth, caught by curl rather than the browser: a 502 from the dev proxy was
rendering as `Refused · 502 Bad Gateway`, telling the user their edit had been
rejected on the merits. 5xx and dropped sockets now read "Not saved".

### Not in Phase 4

Reattachment of any kind — both of Phase 4's gaps (no user-reachable refusal,
no token focus) were closed by Phase 5 below.

## What Phase 5 actually ships

Reattachment, two ways, over the machinery Phase 4 already had under test.

**Keyboard first, on purpose.** The plan named this phase as the one likely to
overrun, with keyboard reattach as the cut. Building it first meant the risky
half was optional rather than load-bearing: `R` lifts the focused token, ←/→
walk the legal heads, `↵` commits, `⌥R` goes straight to root, `Esc` cancels.

**Tokens are `<button>`s now**, one tab stop for the diagram with arrows moving
between them — fifty-three tab stops in a row is not navigation. This closes
the acceptance criterion Phase 4 left open. Sentence navigation moved to ↑/↓:
a chunk has a handful of sentences and a sentence has dozens of tokens, so the
arrows that matter should drive the thing you use constantly.

**`legalHeads` is derived from `validateHead`,** not reimplemented beside it.
A ring the user can see but not drop on, and a drop refused after it looked
legal, are both worse than either failure alone — so a test asserts the set
and the predicate agree on every token of a sentence.

**Drag is what makes the refusals reachable.** Keyboard aiming only ever
offers legal heads, so no keyboard gesture can produce a cycle. A drag can be
released anywhere, and an illegal release is passed to `store.reattach`
deliberately rather than ignored — being told nothing happened, and why, beats
nothing happening. The drop target is resolved with `elementFromPoint` (the
ghost is `pointer-events: none`) so a release on empty space is
distinguishable from one on a token, and reads as "cancelled" rather than as
an error.

Verified live at 1440×900 in both themes: `sie` dragged onto `Freistadt`
committed and persisted; the root dragged onto `sie` was refused with
*"gaben is the sentence root — give the root to another token first"*, the
target struck through, nothing written. Dragging `sie` under `Freistadt` also
produced a genuine non-projective `nsubj`, which rendered below the row — the
tool demonstrating its own premise on live corpus text.

One affordance deliberately withheld: the ROOT bar is not offered to the token
that is already the root. `0` is a legal head for it, but only because it is
where it already sits, and a drop zone that does nothing is worse than none.

## What Phase 6 actually ships

The topological fields, derived from the live tree and drawn as dashed oxide
brackets under each row. `Fields` in the top bar or `F` toggles them; on by
default, because the wireframes carry them in the at-rest frame and because a
layer nobody turns on is a layer nobody checks.

**The corrected Rechte-Klammer rule is the one implemented**, and the fixtures
prove the correction was needed: on `Der Geist hat sich in der Geschichte
entwickelt`, `layout/fields.ts` gives `VF=Der Geist · LK=hat · MF=sich in der
Geschichte · RK=entwickelt`, where the brief's rule gives an empty RK and a
Mittelfeld that swallows the clause. The non-projective fixture is the better
demonstration: `VF=Den Mann · LK=habe · MF=ich · RK=gesehen · NF=der dort
steht` — the crossing arc *is* the extraposition, so the arc geometry and the
field model agree about the same fact by two different derivations.

**Which finite verb holds the left bracket** is a choice the brief does not
make. Every subordinate clause has one, and the model here describes a single
matrix clause, so `findLeftBracket` anchors at the root: the root when it is
finite, otherwise its finite `aux`. That picks the matrix verb without any
clause segmentation, and falls back to the brief's literal "first finite verb"
only when the root's own complex has none.

**Two honest degenerate answers, rather than a confident wrong one.** No
finite verb at all — a heading, a fragment — yields no fields. A right bracket
that computes to the *left* of the left one (verb-final subordination promoted
to root) yields no right bracket, because the fields are ordered by definition
and an inverted pair cannot be drawn.

**Bands are runs, not extents.** A field is drawn from the left edge of its
first token to the right edge of its last, so a field with a hole in it would
bracket words it never claimed — `hat versucht … das zu tun` claims both verbs
and nothing between them. `fieldRuns` splits on unclaimed words but *bridges*
punctuation, which is excluded by rule rather than by the heuristic failing;
without that, every comma would saw the Mittelfeld in half. The same function
is what makes a field spanning a wrap draw one band per row.

Verified live at 1440×900 in both themes on a 53-token Nietzsche chunk (one MF
spanning three rows) and on Schiller `0012c7a73206b19f4958` sentence 8, where
all five fields appear at once and the Nachfeld bridges a comma. Relabelling
`muß` from `aux` to `advmod` collapsed RK and NF into the Mittelfeld and Revert
restored them — the fields recomputing from a corrected tree, which is the
whole argument for deriving them.

**Amended by Phase 7.** The field marks shipped here as rounded brackets
labelled with the abbreviations `VF`/`LK`/`MF`/`RK`/`NF`. Re-reading the design
during Phase 7 showed that is not what it specifies: `.field` is a **dashed
rule** over the field's extent with the **full German name** centred beneath
it, in alternating vertical slots. The stagger is the point — `RECHTE KLAMMER`
is wider than the one participle it labels, so two adjacent names on one line
collide, and the names are worth the trouble because `MF` means nothing to a
reader who has not been told. Phase 7 brought the marks in line;
`fieldRuns` and everything else about the derivation is unchanged.

## What Phase 7 actually ships

The whole-sentence strip from frame 02, the last piece of the design without an
implementation: one tick per token, its height the depth of the arc stack over
that token, hand-corrected tokens in the corrected colour, and a frame showing
which part of the sentence is on screen.

**It is for the tail.** The median German sentence measures 1328px at 20px
type; the worst is 7824px, 5.4 screens. Wrapping is what makes that readable,
and wrapping is also what makes it easy to lose your place in — so the strip
answers *where am I*, *where does the structure get deep*, and *where have I
already corrected something*, in one glance.

**Shown only when the sentence wraps.** A strip over a sentence you can see
whole is decoration, and the design agrees: it appears on exactly one of nine
frames, the 53-token one.

**Depth counts a token at both ends of an arc**, not only as the dependent. A
root governing a level-8 arc is precisely where the sentence is deepest;
counting dependents only would draw it as the flattest token there is.

**Sticky, which the design could not show.** Frame 02 is a 1180px artboard
holding the whole sentence at once. The live pane scrolls, and a frame saying
where you are is worth nothing if it scrolls away with you. One wrinkle worth
remembering: a sticky child pins below its scroll pane's *own* top padding, so
28px of scrolled arcs showed through above the strip until a `::before` was
put there to paint over it.

**Deliberately not interactive.** Keyboard focus already scrolls a token into
view and the sentence list already moves between sentences, so a click target
here would be a third route to what two things already do — and an interactive
control hidden from assistive technology, which a picture of a sentence has to
be, is worse than none.

Verified live at 1440×900 in both themes on the 53-token Nietzsche chunk: the
frame reads 0–73.6% with rows 1–2 on screen and 37.7–100% scrolled to the
bottom, matching the token arithmetic exactly, and it disappears on a
single-row sentence.

## Known gaps

Two latent defects, both found while verifying and neither in scope for the
phase that found them:

1. **#141 — `createCorrectionStore` captures `chunkId` by value**, and `sentOrd` is
   not reset when the chunk changes. Navigating from one syntax overlay
   straight to another — editing the hash, which does not remount the
   component — leaves the store posting corrections against the previous chunk
   (`no token N in sentence M of this chunk`), and a chunk with fewer sentences
   than the last renders *No syntax for this passage*. Unreachable from the
   app's own links: going via the Reader unmounts the overlay. The fix is an
   accessor rather than a string, `sentOrd` reset on change, and clearing
   `session`.
2. **#142 — analytic token positions drift ~8px from the DOM over a long
   row**, because the probe is measured with integer `offsetWidth` while the
   flex row lays out fractionally. Pre-existing since Phase 3 and shared by the
   arcs. `getBoundingClientRect().width` on the probe would fix both, but it
   changes row breaking and belongs with a re-check of the overflow bug.

Deliberate departures from the design, all still current: no author on a
correction (single-operator tool), no `Levels · all` or `Measure` readouts (the
wireframe styles them `ghost`, i.e. as annotation rather than control), and
`design-canvas.jsx` not ported — it is the artboard shell for *viewing*
wireframes.

## Acceptance criteria

- Both fixtures parse and round-trip through `writeConllu` byte-identically
- Level assignment matches the eight-row table for fixture 1 exactly
- Fixture 2 flags **both** `acl:relcl` [2,9] and `punct` [5,10] as
  non-projective, and both render below the row
- No arc path crosses the bounding box of any token's text
- No token row overflows the measure; arcs cut at a wrap resume on the next
  row carrying the partner token's index
- No two relation labels overlap at any zoom level
- Reattaching re-lays out without a full remount and without a visible reflow jump
- A cycle-creating reattachment is refused with a visible reason
- Exactly one token per sentence has `head = 0`; an edit that would orphan or
  duplicate the root shows what is wrong inline rather than silently repairing
- Exported JSON patch, reapplied to the pristine parse, reproduces the edited state
- Exported CoNLL-U reparses cleanly
- Arrow keys move token focus; focus is visibly ringed
- The topological fields are toggleable, render in the derived colour, and
  recompute from a corrected tree rather than from the machine parse
- A wrapped sentence carries a whole-sentence strip whose viewport frame
  tracks the rows actually on screen; a sentence that fits on one row has
  none

## Validation

**TypeScript.** `npx vitest run tests/syntax*.test.ts` — round-trip, the level
table, both non-projective arcs, `apply()` reproducing an edited state from an
exported patch, both fixtures' field assignments derived by hand from the
*corrected* Rechte-Klammer rule rather than from the implementation, and the
minimap's depth profile and viewport span.

**Python.** `pytest tests/test_syntax_parse.py tests/test_syntax_queries.py` —
parse a known German sentence and assert UD deprels not TIGER (`nsubj`, not
`sb`); replay ordering; corrections survive a simulated `index --reset`.

**End to end.** `make run`, open a German work, open the overlay on a chunk.
Confirm arcs land on token centres after fonts resolve with no snap; no arc
crosses a token's text box; reattach re-lays out without remount; a
cycle-creating drop is refused visibly; export CoNLL-U and re-parse it through
`parseConllu`. Drive it with Chrome DevTools MCP at 1440×900 to check label
overlap at several zoom levels and keyboard focus behaviour.

**Regression.** `npm run typecheck`, `npx eslint src tests --quiet`,
`npm run test:unit` and `ruff check src tests` stay clean. Watch the coverage
thresholds (lines 56 / statements 52 / branches 45 / functions 46) — new
`src/**` files are auto-included, though these modules are mostly pure and
should lift rather than drag them.
