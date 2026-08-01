# Dependency-syntax close reading — implementation plan

> **Status (2026-07-31): phases 0–3 shipped; the overlay renders real trees.**
> The execution tracker below is the resume point. **Phase 4 is next**, and it
> is the first phase that writes: corrections, the relation picker, and the two
> refusals. Two design questions are open before it starts — see
> *Open questions* at the end.

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
  layout/{measure,arcs,fields}.ts      the real geometry
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
| **4** | Corrections: append/undo endpoints, `store.ts`, pure `apply()` + tests, relabel picker, cycle + single-root validation, both exports | **next** |
| **5** | Drag reattach with refusal flash, ROOT drop-zone, keyboard reattach | pending |
| **6** | Topological fields overlay, toggleable | pending |
| **7** | Long-sentence minimap | pending — added by the design, see below |

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
| 02 Long sentence, wrapped | 3 ✅ (minimap → 7) |
| 03 Subtree on hover | 3 ✅ |
| 04 Non-projective below the row | 3 ✅ |
| 05 Token inspector | 3 ✅ read-only; its action buttons → 4/5 |
| 09 Sentence list | 3 ✅ |
| 07 Relation picker | 4 |
| 08 Refused · cycle | 4 |
| 06 Mid-reattachment | 5 |
| Topological fields (in 01, 04) | 6 |
| Minimap (in 02) | 7 |

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

## Open questions before Phase 4

**Corrections have no author.** The design's inspector reads
`Hand-corrected · a.reuter · 12 Mar · was obj`. `created_at` and `from_val`
cover the date and the "was"; there is **no author column** on
`chunk_syntax_corrections`. For a single-operator tool that may be right — but
it is a migration, and cheaper to decide before Phase 4 starts writing rows
than after.

**The minimap has no home.** It is scope the design added, it addresses the
109-token tail, and it depends on nothing in Phases 4–6. Listed as Phase 7
above, but it could equally be a Phase 3 follow-up.

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

## Validation

**TypeScript.** `npx vitest run tests/syntax*.test.ts` — round-trip, the level
table, both non-projective arcs, and `apply()` reproducing an edited state from
an exported patch.

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
