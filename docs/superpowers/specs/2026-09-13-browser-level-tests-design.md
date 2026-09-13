# Browser tests: five assertions jsdom cannot make

**Status:** approved 2026-09-13
**Issues:** #593
**Related:** #591 (the selection-toolbar defect), #590 (the PR the chart shipped
in), #585 (`clientHeight` is always 0 in jsdom), #133 (e2e assertions that
rotted because they skipped in CI), #573 (local-vs-CI coverage divergence),
#254 (duplication gate), #547 (frontend test location and the Sonar gate)

Three defects found on 2026-09-13 are invisible to jsdom by construction: they
depend on real layout and real input hit-testing, neither of which jsdom
implements. This adds `@playwright/test` and five assertions — one per defect,
plus two guarding the regressions their fixes create — to the `web · e2e` job
that already exists and is already a required check.

The scope is deliberately five tests. See "What this does not buy" before
expecting more from it.

## Measured

**There is no browser coverage of any kind, and the job named `web · e2e` is
not a UI test.**

```
$ cd web && grep -cE "playwright|puppeteer|@web/test-runner" package.json
0

$ grep -rn 'vitest-environment' tests/e2e/
tests/e2e/serve.test.ts:12:// @vitest-environment node

$ grep -rln 'goto\|document.body' tests/e2e/ | wc -l
0
```

`serve.test.ts` spawns the real Python server on an ephemeral port against a
throwaway index and drives the **API through `fetch`**, asserting response
shapes. It never loads a page. It is a good test of something else.

### Four facts that shaped every decision below

| Fact | Where | Why it matters |
|---|---|---|
| `web · e2e` is **already a required status check** | branch protection | "Required gate" costs zero protection changes. Putting tests in that job is the whole delivery. |
| `make check` does **not** run e2e | `Makefile:222` | It runs `test-unit-cov`, not `test-e2e`. A CI-only e2e suite is the established precedent here, not a new divergence. |
| The harness already serves `web/dist` | `web/tests/e2e/serve.test.ts:25,122` | `--static web/dist` is already passed to `minerva serve`. "vite dev or built dist" is settled by what exists. |
| `web · e2e` runs in 23s and is nowhere near the critical path | CI run 34783948637 | There is ~2.3 min of slack before it becomes the long pole. |

Branch protection contexts:

```
$ gh api repos/:owner/:repo/branches/main/protection \
    --jq '.required_status_checks.contexts'
["python · lint · pytest","web · lint · typecheck · vitest","web · e2e",
 "SonarCloud Code Analysis"]
```

Per-job timing, latest `main` run:

| job | total | notes |
|---|---|---|
| `web · e2e` | **23s** | install 15s, tests 2s |
| `python · lint · pytest` | 160s | |
| `web · lint · typecheck · vitest` | 168s | |
| `sonarqube` | 132s | `needs: [python, web]` |

Critical path ≈ 5.1 min: `web` → `sonar`. Adding ~70–100s to a 23s job that
runs in parallel with a 168s job changes total wall-clock by **zero**.

### `--static` already points at a directory CI never builds

`web-e2e` in `check.yml` has no `npm run build` step, so `web/dist` does not
exist in CI. The server does not crash on it — it 404s per request and logs:

```python
# src/minerva/http/serve.py:461-470
def _serve_static(self, request_path: str) -> None:
    root = self.deps.static_dir.resolve()
    if not root.is_dir():
        self.log_message("static dir not found: %s", root)
        self._send_error_json(
            _HTTPError(
                HTTPStatus.NOT_FOUND,
                "static assets not available (run `npm run build` in web/)",
            )
        )
        return
```

Nothing notices because nothing requests `/`. The implementing PR fixes this by
adding the build step, so per CLAUDE.md it is recorded in the PR body rather
than filed as its own issue.

### Vitest browser mode was considered and rejected on its type surface

`@vitest/browser-playwright@5.0.0` is an optional peer of the vitest 5 already
installed, which made "a third vitest project rather than a second runner" look
like the cheap answer. The published types say otherwise:

```
$ npm pack @vitest/browser@5.0.0 && tar xzf vitest-browser-5.0.0.tgz
$ grep -rn 'goto' package/context.d.ts
(no match)
$ grep -rn 'dragAndDrop\|viewport(' package/context.d.ts
379:  dragAndDrop: (source: Element | Locator, target: Element | Locator, …)
859:  viewport(width: number, height: number): Promise<void>
      /** Change the size of iframe's viewport. */
```

Two disqualifications:

1. **Tests run in an iframe vitest serves.** There is no navigation to the
   Python server's origin, so the app as actually shipped — production bundle,
   same-origin `/api`, no vite proxy — cannot be loaded at all.
2. **`dragAndDrop` takes elements you name.** `(source: Element | Locator,
   target: Element | Locator)`. The test author still picks the target node,
   which is *precisely* #591's blindness reproduced inside a real browser. The
   guard there read `e.target.closest(".gw, …")`, and every existing test
   passed `{ target: null }` — the suite was blind to the only parameter the
   guard read. Coordinate-level hit-testing is the entire point.

It would have fixed one of the three defects: real layout means `clientHeight`
is no longer 0, so the runaway chart's feedback loop can start and be caught.
It also *does* ship `toBeInViewport` (`package/jest-dom.d.ts:63`), contrary to
an assumption made early in this design that the matcher was Playwright-only.

**Had we trusted the "just another vitest project" framing:** we would have
built a suite that cannot load the app, cannot reproduce #591's failing input,
and catches 1 of 3 defects — while reporting green as a required check.

## Design

### 1. Extract the fixture server

`serve.test.ts`'s `beforeAll` builds a throwaway index from
`tests/fixtures/corpus.jsonl` and spawns `minerva serve --llm none` on an
ephemeral port. Playwright needs the identical thing from `globalSetup`.

Extract it to `web/tests/helpers/fixtureServer.ts` — beside the existing
`blankComments.ts` and `testRouting.ts` — exposing `start(): Promise<{ baseUrl,
stop }>`. `serve.test.ts` calls it from `beforeAll`; Playwright calls it from
`globalSetup`. `helpers/` rather than `e2e/` because both consumers now live in
sibling directories and neither owns it.

This is motivated by Sonar's ≤3% duplication gate on new code (#254 had to
extract a shared picker shell for the same reason), not only by tidiness.

The `RUN_E2E = existsSync(MINERVA_BIN)` skip and the deliberate **non**-skip on
a missing fixture both move with it. The fixture is committed; its absence is a
real failure, and skipping on it would rebuild the trap #133 was fixed to
escape.

### 2. Serve the production bundle

`npm run build` → `web/dist`, served by the same `minerva serve --llm none
--static web/dist`. One origin, real bundle, no vite proxy, no CORS. This is
what the harness was already configured for.

### 3. Five tests, no more

| assertion | defect it pins |
|---|---|
| drag-select a phrase → toolbar visible with Translate / Syntax / Copy | #591 |
| click a single word → lookup rail opens, toolbar does **not** | the regression #591's fix could introduce |
| chart `<svg>` `height` equals its fixed value | runaway height (measured live at +480px/frame, 164220 → 221788) |
| chart `toBeInViewport()` after selecting a route | rendered 780px down, 472px below the fold |
| metrics table scrolls internally while the chart stays in view | the layout contract the previous two imply |

`page.mouse.down/move/up` at coordinates is the mechanism for the first two:
the mouseup's `target` comes from real hit-testing rather than from the test's
choice of node.

### 4. Flake defense

A flaky required check on a repo with one merger becomes decoration — the first
flaky red becomes a re-run, and once re-running is routine the gate consumes
attention and pays nothing. That is strictly worse than no gate. So:

- **Chromium only**, browser version pinned by the `@playwright/test` dependency.
- **`retries: 0`** in CI. A retry budget is the mechanism by which a gate
  becomes decoration.
- **No `waitForTimeout`.** Web-first, auto-waiting assertions only.
- **`fullyParallel: false`, one worker.** A single shared server process.
- **Written policy**, in the config comment and in CONTRIBUTING: a flaky test
  is a defective test. It is deleted, not retried.

### 5. CI

Absorbed into `web · e2e`, after the existing `npm run test:e2e` step. Three
new steps: `npm run build`; `npx playwright install --with-deps chromium`,
cached on the Playwright version via `actions/cache`; and `npm run
test:browser` (`playwright test`). The build must precede both, since
`--static web/dist` is what the browser tests load.

Estimated job time 23s → ~90–120s. **This is an estimate, not a measurement** —
the browser download and `--with-deps` apt install have not been timed on this
runner. It is verified during implementation, and if the job overshoots `web`'s
168s it becomes the critical path and the caching needs revisiting.

No branch protection change: `web · e2e` is already required.

### 6. Gate interactions

`test:coverage` already excludes `tests/e2e/**` (`vite.config.ts`), and
`fixtureServer.ts` lives under `tests/`, so none of this moves the Sonar
new-code coverage number in either direction. Stated explicitly because #573's
lesson is that the local and CI numbers diverge silently.

**Playwright specs live in `web/tests/browser/`, not `web/tests/e2e/`.** This
is not cosmetic. Vitest's default `include` glob collects `*.spec.ts` as
readily as `*.test.ts`, so a Playwright spec dropped into `tests/e2e/` would be
picked up and executed by `npm run test:e2e` (`vitest run tests/e2e`) — a
Playwright file run under vitest's node environment, failing on an import it
cannot resolve. A separate directory plus `tests/browser/**` added to
`test.exclude` in `vite.config.ts` makes every vitest invocation skip it
regardless of which npm script is used, rather than relying on each script's
`--exclude` flag staying in step.

`sonar.tests=tests,web/tests` covers `web/tests/browser`, so the specs are
analysed as tests rather than as uncovered production source — the failure #547
measured at 65.2% vs 93.4%. `scripts/check_test_location.py` scans only
`web/src` and already knows `*.spec.ts` (`_PATTERNS`), so the new directory
neither trips it nor needs it widened.

### 7. `make check` is unchanged

Browser tests run in CI, and locally via a new `make test-browser`. This follows the
precedent the existing e2e suite already set (`Makefile:222` omits `test-e2e`).

This is a deliberate local/CI divergence in a repo whose scar tissue is largely
about exactly that, so the reasoning is recorded rather than assumed: the
alternative is every local `make check` running a vite build and a Chromium
download. The divergence is safe here in a way #573's was not, because the
browser suite's inputs are committed fixtures — there is no `data/`-gated test
that runs locally and skips in CI. The failure mode #133 describes requires a
test that silently skips; these do not skip, they fail.

## What this does not buy

**This is regression protection, not discovery.**

All three defects were found by loading the page in Chrome and looking at it —
not by an assertion, and not by ten task reviews, an opus whole-branch review
that stood up a live server, or `make check`. Five assertions pin those three
defects permanently. They will not find the fourth.

If the goal is "catch the next layout bug," the intervention is a habit of
loading the app, not this suite. If the goal is "make sure #591 never comes
back," this suite is exactly right and a local-only one would be exactly wrong.

## #593's open questions, resolved

The issue listed four unknowns under Hypothesis. Three are now measured:

| unknown | resolution | evidence |
|---|---|---|
| `vite dev` or built `web/dist`? | **dist** | the harness already passes `--static web/dist` (`serve.test.ts:25,122`) |
| new job or absorb into `web · e2e`? | **absorb** | 23s job, ~2.3 min of slack under the critical path; the server spawn is already there |
| flakiness budget | **zero retries**, five tests | policy above |
| browser download time in CI | **not yet measured** | estimated ~70–100s; verified during implementation |

The issue's Hypothesis section also proposed reusing the `serve.test.ts`
harness. That is adopted, with the refinement that the harness is *extracted*
rather than copied, for the duplication gate.
