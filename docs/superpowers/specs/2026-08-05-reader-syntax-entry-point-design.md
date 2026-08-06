# Reader → Syntax entry point

**Status:** approved 2026-08-05
**Issues:** the syntax overlay is unreachable from the app; #231 (ungated parser)
**Related:** `docs/syntax-annotation-plan.md` (the overlay's own spec, all 7 phases ✅ DONE)

Two changes, deliberately together: the entry point, and the German-only guard
that must exist before the entry point makes the ungated path reachable.

## Problem

The dependency-syntax overlay is built end to end and cannot be opened.

- Backend: `/api/chunks/<id>/syntax`, corrections create/delete, CLI `minerva syntax parse` — live.
- Frontend: `ArcDiagram`, `SentenceList`, `TokenInspector`, `RelationPicker`, `RefusalPanel`, corrections store with drag-reattach, topological fields, minimap — all built.
- Route: `#/syntax/<chunkId>` parses and renders.
- **Navigation into it: none.**

Counting references to each route kind outside the routing plumbing
(`routing.ts`, `routeUtils.ts`):

```
concordance          3      network-arc          0
concordance-lemma    2      network-coverage     0
conversation         3      syntax               0
landing              6      reader               5
network              2      refs                 5
                            refs-review          3
```

Three routes have no door. The syntax overlay is reachable only by hand-typing
`#/syntax/<chunkId>` with a chunk id taken from the database.

### How a seven-phase feature shipped without an entry point

`docs/syntax-annotation-plan.md:43` says:

> The UI is a **full-bleed overlay** off the Reader, following the existing
> `#/network/arc` drilldown pattern.

No phase in the execution tracker owns building that link, and every phase is
marked ✅ DONE. The plan describes where the overlay *sits* and never assigns
the work of getting there.

The pattern it points at — `#/network/arc` — is itself doorless. The gap was
inherited from the thing being copied, which is why nobody caught it: the
overlay does follow the existing pattern, faithfully, including its defect.

## Design

### The change

One button in `SelectionToolbar`, alongside the existing actions. The toolbar
has two shapes today; the button joins both:

```
single-word:  [ Look up  L ] | [ Translate  T ] | [ Syntax  S ] | [ Copy ] | 1
multi-word:                    [ Translate phrase  T ] | [ Syntax  S ] | [ Copy ] | 5
```

**Shortcut `S`.** Verified free — the single-letter keys bound anywhere in
`web/src` are `f/F`, `j/k`, `l/L`, `r/R`, `t/T`.

**Prop shape.** `SelectionToolbar` does not receive the chunk id, and this
change does not give it one. It takes `onSyntax?: () => void`, mirroring the
existing optional `onLookup?`. The parent resolves the target, exactly as it
already does for the other actions (`Reader/index.tsx:344-345`):

```tsx
onTranslate={() => { selection.commitTranslate(t()); }}
onLookup={() => { selection.commitLookup(t()); }}
onSyntax={() => { selection.commitSyntax(); }}      // new
```

so `chunkId`, `workId` and the language check live in the Reader's selection
controller, where the selection state already is. The toolbar stays
presentational.

Clicking navigates to `{ kind: "syntax", chunkId, workId }`. The route already
exists and renders; `SyntaxRoute.onClose` already navigates back to
`{ kind: "reader", workId }`, so the return path needs no work.

### Why the selection toolbar

- It is where the user already is when asking a question about a passage.
- It adds no new chrome to the reading pane.
- The selection state already resolves to a chunk, so the controller can
  supply the target without new plumbing.

### Language gate

**The button renders only when the chunk's language is `deu`.**

Two independent reasons:

1. **Scope.** `syntax-annotation-plan.md:38` — "German only. Not in scope, and
   no scaffolding for them: multi-language comparison, parallel text, word
   alignment, RTL, constituency trees, an in-app parser, or a theming layer."
2. **Correctness.** `syntax/parse.py:30` hardcodes `_LANG = "de"`, and nothing
   between the HTTP handler and the parser inspects the chunk's language.
   `load_or_parse` parses on demand and `save_parse` **caches the result**. An
   ungated button would therefore run the German model over Greek, Latin,
   French or English text and persist the output into `chunk_syntax` as
   authoritative. Today that is latent only because the route is unreachable;
   adding the door makes it live on 99.5% of the corpus.

The gate is on the chunk's language, not the work's — a work can carry chunks
in more than one language.

### Server-side guard (#231)

The UI gate is not the only gate. `load_or_parse` reads the chunk's `lang` and
refuses anything but `deu`.

**The guard lives in `load_or_parse`, not in the handler.** That is the
function which parses and then calls `save_parse`, so putting the check there
means no caller can reach the write — the HTTP handler, the CLI, a future
second entry point, or a hand-rolled request all inherit it. A handler-level
check would protect only the path it sits on, which is the mistake this whole
issue is an instance of.

Behaviour for a non-German chunk:

- **No parse, and no write.** This is the point: today the request is the
  trigger and the write is silent.
- The endpoint answers **400** with an explicit reason naming the chunk's
  language, distinct from the existing 404 "chunk not found" so the two
  failures stay tellable apart.

Rejecting rather than dispatching per language matches the plan's stated
scope — `syntax-annotation-plan.md:38`, "German only. Not in scope, and no
scaffolding for them: multi-language comparison, parallel text, word
alignment, RTL, constituency trees, an in-app parser, or a theming layer."
This makes that scope true in code instead of true by accident.

### Data flow

```
selection in Reader
  → SelectionToolbar (already knows the selection's chunk)
  → onSyntax()
  → routing.navigate({ kind: "syntax", chunkId, workId })
  → SyntaxRoute → SyntaxOverlay
  → GET /api/chunks/<id>/syntax  (load_or_parse: cached, else parse + cache)
  → close → navigate({ kind: "reader", workId })
```

Nothing new server-side. Nothing new in the overlay.

### Error handling

The overlay owns its own states already — it renders *No syntax for this
passage* for an empty parse, and `RefusalPanel` covers correction failures. The
first parse of an unseen chunk costs a Stanza pipeline load (~4s once per
process) plus ~0.15s for the paragraph; the overlay's existing loading state
covers it. No new error surface is introduced.

## Out of scope

Recorded here so the omissions are deliberate rather than silent:

1. **Per-language parsing.** The guard rejects non-German rather than
   dispatching a model per language. Dispatching is explicitly out of scope in
   `syntax-annotation-plan.md` and would be a much larger change (a model per
   language, coverage and accuracy claims for each, and the arc-direction
   heuristic re-checked against non-UD outputs).
2. **`network-arc` and `network-coverage` stay unreachable.** Same class of
   defect, different features. Bundling three entry points into one change
   would make the diff harder to review and the revert coarser. Own issue.
3. **No new morphology view.** The Reader's existing word card already shows
   per-word POS and features from `chunk_lemmas`, corpus-wide. This change adds
   a door to the sentence-structure overlay, not a second morphology surface.

## Testing

Two levels, because the gate and the button live in different places.

**`SelectionToolbar`** (presentational): renders the Syntax button when
`onSyntax` is supplied, omits it when the prop is absent, and calls it on
click. No language logic here.

**The selection controller** (where the gate lives): supplies `onSyntax` for a
`deu` chunk and withholds it otherwise, and navigates with the correct
`chunkId` and `workId`.

The gate is the assertion that matters most — it is what prevents garbage
writes into `chunk_syntax` — so it gets an explicit negative case for `grc`,
`lat`, `eng` and `fra` rather than one representative non-German case. A
single representative would pass even if the check were written against the
wrong field.

**`load_or_parse`** (pytest, the guard that actually protects the data):

- A `deu` chunk parses and caches as before.
- A non-German chunk is refused, and — asserted directly against the table —
  **writes no `chunk_syntax` row**. Testing only the return value would pass
  against an implementation that rejects after saving.
- The endpoint answers 400 for a non-German chunk and 404 for a chunk that
  does not exist, so the two stay distinguishable.

These run without the `[lemma]` extra, which CI does not install: the refusal
path must return before `parse_text(...)` is called, so a test for it needs
no parser. That is worth asserting deliberately — a guard placed after that
call would still pass a return-value test locally and fail in CI.

*(Corrected during Task 2 review. The two sentences above originally said the
refusal must return "before importing Stanza" / "before the import," on the
premise that a module-level `import stanza` was the boundary CI's missing
`[lemma]` extra would trip over. That premise was false: `syntax/parse.py`
has no module-level Stanza import — it's lazy inside `_pipeline()` and
`_stanza_version()`, reached only from `parse_text()`/`parser_id()`. `from
.parse import parse_text, parser_id` alone succeeds in CI regardless of the
extra. The call to `parse_text` is what actually triggers the import and the
~4s pipeline load, so that call, not the import statement, is the boundary a
guard and its tests must respect.)*

## Acceptance criteria

- A German chunk selected in the Reader offers a Syntax action.
- The action opens the existing overlay on that chunk.
- Closing returns to the Reader at the work it came from.
- No Syntax action appears on a non-German chunk.
- `GET /api/chunks/<non-german-id>/syntax` returns 400 and leaves
  `chunk_syntax` unchanged.
- `GET /api/chunks/<unknown-id>/syntax` still returns 404.
- `make check` green.
