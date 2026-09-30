# Reader work URLs: slugs the eye can read

**Status:** drafted 2026-09-14; implemented 2026-09-18, with two corrections
and one omission recorded below
**Issues:** #602
**Related:** #589 (readRoute cognitive complexity), #428 (lazy works list vs.
route-driven render), #50 (edition switcher), #547 (frontend test location),
#559 (cognitive complexity gate), #573 (local-vs-CI coverage divergence)

A work's Reader URL is keyed on its raw title string, so it arrives at the
reader's eye as `#/r/Beantwortung%20der%20Frage%3A%20Was%20ist%20Aufkl%C3%A4rung%3F`.
The operator wants to read, type, and recognise these. This is a URL-format
change with a surprisingly long tail, because the title in the route is not
only a URL — it is also a localStorage key, a display string, and a filter
value.

## Measured

### The title is the path segment

`routeHash` serialises the reader route as
`` `#/r/${encodeURIComponent(route.workId)}` `` (`web/src/routing.ts`), and
`workId` is the title, confirmed at `src/minerva/reader/queries.py:264`:

> ``work_id`` (the path segment) is the work TITLE string — the SPA hash
> routes pre-date the works table.

Three encoders fire on one title — spaces, punctuation, non-ASCII letters:

```
$ ./.venv/bin/python -c "
import urllib.parse as u
for t, a, l in [('Beantwortung der Frage: Was ist Aufklärung?','Kant','deu'),
                ('Die fröhliche Wissenschaft','Nietzsche','deu'),
                ('Nicomachean Ethics','Aristotle','grc')]:
    print(f'#/r/{u.quote(t)}?lang={l}&author={u.quote(a)}')"
#/r/Beantwortung%20der%20Frage%3A%20Was%20ist%20Aufkl%C3%A4rung%3F?lang=deu&author=Kant
#/r/Die%20fr%C3%B6hliche%20Wissenschaft?lang=deu&author=Nietzsche
#/r/Nicomachean%20Ethics?lang=grc&author=Aristotle
```

54 of 866 works have a non-ASCII title:

```
$ sqlite3 data/index.sqlite "select count(*) from works where title glob '*[^ -~]*';"
54
```

Chunk ids are hex (`49cd31f54fea9ab6b20c`), so `focus=`, `syntax=` and `term=`
are already clean. The title segment is the entire problem.

### The slug scheme is collision-free today

NFKD fold, `ß→ss` / `æ→ae` / `œ→oe` / `ø→o`, lowercase, `[^a-z0-9]+ → -`, trim:

```
works: 866  distinct slug pairs: 866
COLLIDING slug pairs: 0
empty-slug titles: []

longest:  #/r/kant/uber-den-gemeinspruch-das-mag-in-der-theorie-richtig-sein-taugt-aber-nicht-fur-die-praxis
```

Zero collisions is a property of *today's* corpus, not of the scheme. It is
the reason for the gate in "Keeping the two slugifiers honest" below.

### Four consumers read the title out of the route

| Consumer | Site | What breaks if the route stops carrying a title |
|---|---|---|
| Saved-highlight localStorage key | `Reader/useSelectionToolbar.tsx:147` | Every saved highlight orphaned — needs a data migration |
| Displayed work title | `Reader/index.tsx:406` | Reader header shows a slug |
| Concordance scope filter | `Reader/index.tsx:418` | `scopeWorks` sends a slug to a title-keyed API |
| Remembered reading location | `Reader/readerCtrl.ts:212` | Stored blob holds titles; restore path navigates |

This is what makes the change more than a serialisation edit, and the
localStorage key is the one with a genuine migration cost attached.

### `work_range` already returns the canonical title

`src/minerva/reader/queries.py:354-372` returns `work_id`, `corpus`, `author`,
`work`, `display_title`, `display_subtitle`, `lang`. So the title is already in
the payload the Reader fetches regardless. Nothing new has to be requested to
recover it.

### The works list is lazy, and that has bitten before

`readerCtrl.ts:170` is a lazy single-flight loader — "only fetch the first time
the user enters Reader" — while `routes/ReaderRoute.tsx` documents the Reader
rendering straight off the route. The same lazy-list-vs-route race is recorded
there as #428:

> Both exits used to do this synchronously off `currentWork()`, which reads the
> LAZILY-loaded `works()` list while the Reader renders straight off the route.
> Leaving inside the `/api/works` round-trip therefore seeded `null` and dropped
> the work with no sign it had happened.

### The route table is ordered, and the works regex is greedy

```
$ grep -n "_WORK_PATH_RE\|_WORK_OCCURRENCES_RE\|_WORK_REFERENCES_MAP_RE" src/minerva/http/router.py
47:_WORK_PATH_RE = re.compile(r"^/api/works/(.+)$")
58:_WORK_OCCURRENCES_RE = re.compile(r"^/api/works/(\d+)/term_occurrences$")
64:_WORK_REFERENCES_MAP_RE = re.compile(r"^/api/works/(\d+)/references_map$")
125:            _WORK_REFERENCES_MAP_RE,
153:            _WORK_OCCURRENCES_RE,
189:            _WORK_PATH_RE,
```

The numeric sub-resource routes are registered at 125-163 and the greedy
`(.+)` catch-all last at 189. A two-segment slug route must sit between them:
after the numeric ones (or `/api/works/42/term_occurrences` matches
`([^/]+)/([^/]+)$`), before the catch-all (or `(.+)` swallows the pair).

### `readRoute` is already over the maintainability gate

```
$ awk '/^export function readRoute/,/^}/' web/src/routing.ts | wc -l
     162
```

#589 records that its cognitive complexity is well past Sonar's limit of 15,
and — the part that matters here —

> This has not turned the maintainability gate red, because the rating applies
> to **new code** and `readRoute`'s declaration line is unchanged... That
> protection disappears the moment someone touches its signature or the lines
> around it move.

This change edits the `#/r/` branch inside that function. Per CLAUDE.md a line
that merely moves counts as new code in full. There is no local check — `web/`
has no `sonarjs` plugin installed — so nothing warns before CI.

## Design

### URL grammar

```
#/r/<authorSlug>/<titleSlug>?lang=<l>&focus=<chunk>&term=<n>&syntax=<chunk>
```

`author` leaves the query string and becomes part of identity. `lang` stays a
parameter: it selects an edition of a work, not a work. Every other parameter
is unchanged and already URL-clean.

A single-segment form `#/r/<titleSlug>` stays legal. It is what
`openAtChunk` can produce (see "Back-compat", below) and it resolves exactly as
an author-less title does today.

### Slugify

One algorithm, two implementations, one committed fixture (below):

1. NFKD-normalise.
2. Replace `ß→ss`, `æ→ae`, `œ→oe`, `ø→o` — characters NFKD does not decompose.
3. Strip combining marks.
4. Lowercase.
5. `[^a-z0-9]+ → -`, then trim leading/trailing `-`.

Step 2 must precede step 3, and both must be spelled identically in Python and
TypeScript. That is the fixture's job.

### Resolution is server-side

A new route `^/api/works/([^/]+)/([^/]+)$` registered between `router.py:163`
and `:189`, resolving the slug pair to a work and delegating to the existing
`work_range`. The server slugifies `works.author`/`works.title` to match; at
866 rows a per-request scan is free relative to the range query itself.

Client-side resolution is rejected, not merely unchosen: it would put an
`/api/works` round-trip in front of every cold deep link, which is the #428
shape quoted above.

### The route carries slugs; the title arrives with the data

`Route.reader` becomes `{ kind: "reader", authorSlug?, workSlug, sourceLang?,
focusChunkId?, openTermId?, syntaxChunkId? }`.

The Reader gains a `workTitle()` accessor derived from the loaded range
response (`work`) and an `author()` from the same payload. The four consumers
in the table above read those instead of the route. Because the highlight key
keeps its title-based value, **no localStorage migration is required** — the key
is simply computed a beat later, after the range resolves, which is already
when highlights can be applied to rendered text.

Navigation *into* the Reader needs no round-trip: `openWork(work)` holds
`work.author` and `work.work`, and the localStorage restore path holds the same
pair, so both slugify locally.

### Back-compat: two legacy shapes, both self-healing

- **Old bookmarks.** The `#/r/<Title>?author=X` branch stays, and resolves
  entirely client-side with no round-trip: the old URL *contains* the title and
  author, so the branch slugifies both and returns an ordinary slug-carrying
  route. The Reader is therefore never aware of a second route shape, and
  `useRouting`'s existing first-load `replaceState` rewrites the address bar to
  the canonical form. Same mechanism `#/syntax/<chunk>` already uses.

  This is why `Route.reader` can carry slugs *only*, with no title field: every
  entry point either holds the author/title pair already (`openWork`, the
  localStorage restore path, a legacy hash) or needs no work identity at all
  (a chunk deep-link, resolved off `around=`).
- **Chunk deep-links.** `App.tsx:50` calls `openAtChunk(workTitle, undefined,
  chunkId)` — a title with **no author**, so no author slug can be computed.
  (Corrected 2026-09-18: there are **two** author-less callers, not one —
  `ChatRoute.tsx:39` is the other, and it passes a `sourceLang` as well. Same
  shape, same treatment; the design is unchanged.)
  These emit the single-segment form. Resolution is unaffected, because the
  server resolves work, lang and edition off `around=<chunk>` regardless of the
  path segment. Once the response supplies the canonical author, the Reader
  `replace()`s up to the two-segment form and the link self-heals.

  > **Deferred from #602, shipped in #611.** A bare `replace()` writes the
  > route signal, which changed `useWorkRange`'s `windowKey` memo (#347),
  > which reloaded the window and blanked the stage — the exact failure that
  > memo exists to prevent. Measured on the naive wiring: four assertions
  > went red across **three** files, not two — `readerSyntaxLayer` ("does not
  > tear down the rendered chunks when the overlay opens"), `readerKeepAlive`
  > ("… on the way out or back"), and two in `readerEscape`. The two
  > `readerEscape` ones were never the reload: they assert the hash is still
  > the one-segment form after a modifier closes, so they fail under *any*
  > fix that grows the URL and were updated to the canonical form.
  >
  > What shipped is the issue's shape (1). The Reader calls
  > `onAuthorResolved(slugify(range.author))` when the route has no author
  > **and** `slugify(range.work)` is the route's title slug — a focus link
  > resolves off `around=` whatever the title says, and pairing another
  > work's author with that slug would build a URL that 404s. `readerCtrl`'s
  > `growAuthorSlug` then `replace()`s. `windowKey` is now an object memo
  > whose `equals` (`sameWindow`) treats an author-less key followed by the
  > author the loaded range named as the same window; the range is read
  > untracked, so it does not become a dependency of the memo that gates
  > loading it. Any other author change — a different author, or one arriving
  > before a range has loaded — still reloads. Acceptance:
  > `web/tests/readerSlugTitle.test.tsx` ("a one-segment reader URL").

### Keeping the two slugifiers honest

`make generate-authors` also writes `data/authors/work_slugs.json`: the full
`{authorSlug, titleSlug} → {author, title}` table generated from the live
index. `make check-authors` fails if the committed table contains a collision,
or has drifted from the index. This is the `chunk_counts.json` pattern —
generated artifact committed, because `data/*` is gitignored and CI has no
index to regenerate from.

Two consequences worth stating, both learned the hard way in this repo:

- ~~The file needs an explicit `!data/authors/work_slugs.json` line in
  `.gitignore`.~~ **Corrected 2026-09-18: it does not, and no such line was
  added.** `.gitignore` carries `!data/authors/` — the whole directory, not
  just `manifest.yaml` — so a new file inside it is not ignored:

  ```
  $ touch data/authors/__probe.json && git check-ignore -v data/authors/__probe.json
  $ echo $?
  1                                    # not ignored
  $ git status --porcelain data/authors/
  ?? data/authors/__probe.json
  ```

  Material because the claim also implies `chunk_counts.json` and
  `chunk_granularity.json` survive only by being pre-tracked, which is false
  and would send the next person adding a snapshot hunting a hazard that is
  not there. The hazard it names is still real — a gate artifact that fails to
  commit leaves CI checking nothing — it is simply not this one.
- The same committed table is the shared fixture the Python and TypeScript
  slugifiers are both tested against. A test that read the live index would
  pass locally and measure nothing in CI.

### Complexity: pay #589's tax on the branch we touch

Do not restructure all of `readRoute` here — that is #589's job and a much
larger diff. Extract *only* the reader-route parsing into its own
`parseReaderRoute(hash)` function, called from the ladder. The new code is then
a small, independently-testable unit with its own low score, and the ladder
entry it leaves behind is one line. If the gate still comes back red on
`readRoute` itself, that is #589 surfacing and should be handled as #589,
not absorbed silently here.

### Testing

- **Round-trip property test** over `routeHash ∘ readRoute` for every reader
  shape: two-segment, single-segment, each optional parameter, and each legacy
  form. #589 asks for this across all route kinds; the reader slice of it lands
  here.
- **Cross-language slugify agreement** against `data/authors/work_slugs.json`,
  asserted from both `tests/` (Python) and `web/tests/` (Vitest). Frontend
  tests go in `web/tests`, never colocated — a colocated test is analysed as
  production source and fails the new-code gate (#547).
- **Backend resolution**: slug pair resolves; unknown slug 404s; the
  single-segment form resolves; route ordering asserted by requesting
  `/api/works/42/term_occurrences` and confirming it still reaches the numeric
  handler.
- **Canonicalisation**: an old-form hash and a single-segment chunk deep-link
  each end at the canonical two-segment URL, via `replaceState` — assert the
  history length did not grow.
- Coverage is measured on changed lines including branches; the backend
  resolver needs a committed fixture rather than a live-index test, or it reads
  high locally and low in CI (#573).

## Out of scope, deliberately

`#/concordance/%E1%BD%81` — the lemma `ὁ`, 344,718 occurrences — is a worse URL
than anything in the Reader, and is **not** fixable this way. There the
non-ASCII is the content: folding `ὁ` to `o` destroys the lemma and collides it
with every other `o`-ish token. Percent-encoding is the correct representation
for that route. Named here so the omission reads as a decision rather than an
oversight.

Also untouched: `#/refs?work=`, and the concordance's `scopeWorks` CSV. Both
are title-keyed and both would want the same treatment eventually; neither is
the Reader.

## Risks

| Risk | Mitigation |
|---|---|
| Sonar maintainability gate turns red from moved lines in `readRoute` | Extract `parseReaderRoute`; escalate to #589 rather than absorb |
| Python and TypeScript slugifiers drift | Committed generated fixture, asserted from both test suites |
| A future author introduces a colliding slug pair | `check-authors` gate over the committed table |
| The new work_slugs artifact is never actually committed | Explicit `.gitignore` negation, not `git add -f` |
| A title consumer is missed and renders a slug to the user | The four sites are enumerated above; the round-trip test covers the route, manual check covers the render |
