# Browser-Level Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `@playwright/test` and five browser tests covering the three
defects jsdom cannot see, running in the already-required `web · e2e` CI job.

**Architecture:** Playwright drives the production bundle (`web/dist`) served by
the real `minerva serve --llm none` against a throwaway index built from the
committed fixture corpus — the harness `serve.test.ts` already uses, extracted
so both suites share one copy. Tests address the DOM through accessible names
and the data attributes the app's own code queries; page objects expose intent
and return `Locator`s.

**Tech Stack:** `@playwright/test` (Chromium only), Solid, vitest 5, vite 8,
Python 3.13 + `minerva` CLI.

**Spec:** `docs/superpowers/specs/2026-09-13-browser-level-tests-design.md`

## Global Constraints

- **Locator tiers, in order.** 1) `getByRole` + accessible name. 2) Production
  data attributes the app itself queries (`data-chunk-id`, `data-offset`).
  3) `data-testid`, with a comment saying why tiers 1–2 failed. 4) **Never**
  CSS class selectors, positional indexing as a substitute for identity,
  literal corpus text, or coordinates from anything but a bounding box measured
  at call time.
  - *Clarification the spec leaves implicit:* selecting "the 1st and 4th word
    of a line" is **not** banned positional indexing. The ban is on position
    standing in for identity (*which* control is Translate). A word's position
    in a sentence **is** its identity. Reading `data-offset` values off the
    rendered line is tier 2, not tier 4.
- **`retries: 0`.** A retry budget is how a required gate becomes decoration.
- **No `waitForTimeout`, ever.** Web-first auto-waiting assertions only.
- **Page objects return `Locator`, never `ElementHandle`,** and never assert.
- **Fixtures derive corpus values at run time and throw — never skip — when the
  corpus cannot satisfy them** (#133).
- **A flaky test is a defective test: delete it, do not retry it.**
- Playwright specs live in `web/tests/browser/`, never `web/tests/e2e/`
  (vitest's default glob would collect `*.spec.ts` there and run it under
  node).
- Every new file must pass `npm run lint` and `npm run typecheck`, which means
  being inside both `tsconfig.json#include` and eslint's `files` list.

---

## File Structure

| File | Responsibility |
|---|---|
| `web/src/Reader/components/SelectionToolbar.tsx` | *(modify)* hide decorative key hints from the accessibility tree |
| `web/src/Metrics/MetricsPanel.tsx` | *(modify)* name the two tables |
| `web/tests/helpers/fixtureServer.ts` | *(create)* build throwaway index, spawn `minerva serve`, return `{ baseUrl, stop }` |
| `web/tests/e2e/serve.test.ts` | *(modify)* consume the helper instead of inlining the spawn |
| `web/playwright.config.ts` | *(create)* Chromium project, zero retries, global setup |
| `web/tests/browser/globalSetup.ts` | *(create)* start one server for the run, publish its URL |
| `web/tests/browser/fixtures.ts` | *(create)* `test`/`expect` with `baseURL` and corpus fixtures |
| `web/tests/browser/pages/ReaderPage.ts` | *(create)* reader intent API |
| `web/tests/browser/pages/MetricsPage.ts` | *(create)* metrics intent API |
| `web/tests/browser/smoke.spec.ts` | *(create)* the bundle is served and boots |
| `web/tests/browser/reader.spec.ts` | *(create)* the two selection tests |
| `web/tests/browser/metrics.spec.ts` | *(create)* the three layout tests |
| `.github/workflows/check.yml` | *(modify)* build, install Chromium, run the suite |
| `Makefile` | *(modify)* `make test-browser` |
| `docs/CONTRIBUTING.md` | *(modify)* locator + flake policy |

---

## Task 1: Accessible names on the Selection toolbar (#594)

Prerequisite for Tasks 5. Three of the five tests address these buttons, and
under the locator policy they are currently unaddressable.

**Files:**
- Modify: `web/src/Reader/components/SelectionToolbar.tsx:90-120`
- Test: `web/tests/SelectionToolbar.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: buttons whose accessible names are exactly `"Look up"`,
  `"Translate"` (single-word fork), `"Translate phrase"` (multi-word fork),
  `"Syntax"`, `"Copy"`. Tasks 5 depends on these exact strings.

**Scope decision — narrower than #594 proposed, deliberately.** #594's
Hypothesis proposed `aria-hidden` on the hint spans *plus* an explicit
`aria-label` on each control, reasoning that Playwright's `getByRole` name
option matches by substring, so `"Translate"` would still match
`"Translate phrase"`. `exact: true` on the locator solves that without
inventing user-facing copy that differs from the visible label, so only the
`aria-hidden` half is implemented. Step 6 records the correction on the issue.

**Also deliberately excluded: the four prose-context `kbd` spans.** #594 lists
them as a milder version of the same problem. They are not. In
`features/Composer/index.tsx:37` the markup is
`<span class="kbd">Enter</span> &nbsp;send` — the hint span carries the *key*
and the surrounding text carries the *verb*. Hiding it would announce "send"
with no indication of how, which is worse than the run-on. Only the three
`SelectionToolbar` spans — where the key duplicates information already in
`title` and the label reads complete without it — are hidden.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/SelectionToolbar.test.tsx`:

```tsx
it("names each control exactly, with key hints out of the a11y tree (#594)", () => {
  const anchor = { rect: new DOMRect(10, 100, 80, 20) };
  const noop = () => {};

  const multi = render(() => (
    <SelectionToolbar
      anchor={anchor}
      count="4 words · 22 chars"
      singleWord={false}
      onTranslate={noop}
      onSyntax={noop}
      onCopy={noop}
      onDismiss={noop}
    />
  ));
  expect(multi.getByRole("button", { name: "Translate phrase" })).toBeTruthy();
  expect(multi.getByRole("button", { name: "Syntax" })).toBeTruthy();
  expect(multi.getByRole("button", { name: "Copy" })).toBeTruthy();
  multi.unmount();

  const single = render(() => (
    <SelectionToolbar
      anchor={anchor}
      count="1 word · 5 chars"
      singleWord={true}
      onTranslate={noop}
      onLookup={noop}
      onSyntax={noop}
      onCopy={noop}
      onDismiss={noop}
    />
  ));
  expect(single.getByRole("button", { name: "Look up" })).toBeTruthy();
  expect(single.getByRole("button", { name: "Translate" })).toBeTruthy();
  single.unmount();
});
```

Testing Library's `name` option matches the full normalized accessible name by
default, so `"Translate phrase"` will not match the current
`"Translate phraseT"`. That is what makes this test fail before the fix.

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run tests/SelectionToolbar.test.tsx`
Expected: FAIL — `Unable to find an accessible element with the role "button"
and name "Translate phrase"`, with the printed DOM showing `Translate phraseT`.

- [ ] **Step 3: Hide the three hint spans**

In `web/src/Reader/components/SelectionToolbar.tsx`, add `aria-hidden="true"`
to each of the three `<span class="kbd">` elements (currently lines 94, 105,
116) and record why:

```tsx
        <span class="kbd" aria-hidden="true">L</span>
```
```tsx
        <span class="kbd" aria-hidden="true">T</span>
```
```tsx
          <span class="kbd" aria-hidden="true">S</span>
```

Add above the first button, inside the component's return:

```tsx
      {/* The `.kbd` hints are decorative: the same shortcut is already in
          each button's `title`. Without aria-hidden they concatenate into
          the accessible name with no separator — "Translate phraseT" — which
          both misnames the control for screen readers and puts it out of
          reach of a role+name locator (#594, #593). The close button's icon
          in Rail.tsx already uses this pattern. */}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd web && npx vitest run tests/SelectionToolbar.test.tsx`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add web/src/Reader/components/SelectionToolbar.tsx web/tests/SelectionToolbar.test.tsx
git commit -m "fix(a11y): keep key hints out of the toolbar's accessible names

The <span class=\"kbd\"> hint inside each Selection toolbar button was part
of the button's content, so it concatenated into the accessible name with no
separator: \"Translate phraseT\", \"Look upL\", \"SyntaxS\". Screen readers
announced the run-on, and a role+name locator could not address the control
at all.

aria-hidden on the three hint spans. Their shortcut is already carried by
each button's title, and Rail.tsx's close icon already uses this pattern.

Narrower than the issue proposed, on purpose: the issue also wanted an
explicit aria-label per control, because Playwright's getByRole matches
names by substring and \"Translate\" would otherwise also match \"Translate
phrase\". exact: true on the locator settles that without inventing
user-facing copy that differs from the visible label.

The four prose-context kbd spans are deliberately left alone — there the
span carries the key and the surrounding text carries the verb, so hiding
it would announce \"send\" with no indication of how.

Closes #594.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Record the correction on the issue**

Per CLAUDE.md, a correction goes on the thing that was wrong — not into a new
issue.

```bash
direnv exec . gh issue comment 594 --body 'Implemented narrower than the Hypothesis proposed, and the reasoning there needs correcting on two points.

**1. The `aria-label` half is unnecessary.** The Hypothesis argued both halves were needed because a locator for `"Translate"` would still match `"Translate phrase"` under substring matching. Playwright'"'"'s `getByRole` takes `exact: true`, which settles it at the call site. Implementing only `aria-hidden` avoids introducing an announced name ("Translate word") that differs from the visible label — copy nobody asked for, and a WCAG 2.5.3 risk for no gain.

**2. The four prose-context spans must NOT be hidden.** The Hypothesis called them "a separate, milder problem" that "could reasonably be left out of a first fix" — implying the fix would be the same, only later. It would be a regression. In `features/Composer/index.tsx:37` the markup is `<span class="kbd">Enter</span> &nbsp;send`: the span carries the *key*, the adjacent text carries the *verb*. `aria-hidden` there announces "send" with no indication of how to do it — strictly worse than the run-on it removes.

**What would have gone wrong had the Hypothesis been implemented as written:** four instruction hints silently stripped of their key names for screen-reader users, plus two invented button labels diverging from their visible text.

The Measured half reproduced exactly.'
```

---

## Task 2: Name the two metrics tables

`MetricsPanel` renders `.metrics-table` always and `.metrics-subspan-table`
when a route is selected, so `getByRole("table")` is ambiguous in exactly the
state Task 6 tests. Neither has a name.

This is a finding discovered while designing the locators. Per CLAUDE.md it is
fixed in this same change, so it is recorded in the PR body rather than filed.

**Files:**
- Modify: `web/src/Metrics/MetricsPanel.tsx:276`, `web/src/Metrics/MetricsPanel.tsx:337`
- Test: `web/tests/MetricsPanel.test.tsx`

**Interfaces:**
- Produces: `getByRole("table", { name: "Requests by route" })` and
  `getByRole("table", { name: "Sub-span breakdown" })`. Task 6 depends on
  these exact strings.

- [ ] **Step 1: Write the failing test**

Add to the `describe("MetricsPanel", …)` block in
`web/tests/MetricsPanel.test.tsx`, reusing the `row` and `mockSummary` helpers
the file already defines at lines 7 and 27:

```tsx
  it("names the route table so it is addressable by role (#593)", async () => {
    mockSummary([row("fast", 5), row("slow", 900)]);
    const view = render(() => <MetricsPanel />);
    expect(await view.findByRole("table", { name: "Requests by route" })).toBeTruthy();
  });
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run tests/MetricsPanel.test.tsx`
Expected: FAIL — no accessible element with role "table" and name "Requests by
route".

- [ ] **Step 3: Add the labels**

```tsx
              <table class="metrics-table" aria-label="Requests by route">
```
```tsx
                  <table class="metrics-subspan-table" aria-label="Sub-span breakdown">
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd web && npx vitest run tests/MetricsPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/Metrics/MetricsPanel.tsx web/tests/MetricsPanel.test.tsx
git commit -m "fix(a11y): name the two metrics tables

MetricsPanel renders the route table always and the sub-span table when a
route is selected, so with a route open getByRole('table') matches two
elements and neither has a name. Unlabelled tables are also a plain
accessibility gap.

Found while designing the browser-test locator strategy (#593); fixed in
the same change rather than filed.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Extract the fixture server

`serve.test.ts`'s `beforeAll` is the only thing that knows how to stand up a
real server against the committed fixture. Playwright's `globalSetup` needs the
identical procedure, and Sonar gates duplication at ≤3% on new code.

**Files:**
- Create: `web/tests/helpers/fixtureServer.ts`
- Modify: `web/tests/e2e/serve.test.ts:78-145`

**Interfaces:**
- Produces:
  ```ts
  export interface FixtureServer { baseUrl: string; stop: () => void }
  export function minervaBinPath(): string
  export function hasMinervaBin(): boolean
  export function fixtureChunkCount(): number
  export async function startFixtureServer(): Promise<FixtureServer>
  ```
  Tasks 4 and 5 consume `startFixtureServer` and `hasMinervaBin`.

- [ ] **Step 1: Create the helper**

Create `web/tests/helpers/fixtureServer.ts`. Move `freePort`, `waitForHealth`,
the index build and the spawn out of `serve.test.ts` verbatim — this is a pure
move, so no behaviour changes and the existing assertions are the test.

```ts
// Stands up the real Python server against a throwaway index built from the
// committed fixture corpus. Shared by two suites with different runners:
// `tests/e2e/serve.test.ts` (vitest, node env, drives the API through fetch)
// and `tests/browser/globalSetup.ts` (Playwright, drives the built bundle in
// Chromium). It lives here rather than in either suite because both are
// siblings and neither owns it — and because copying it would put the two
// copies straight into Sonar's duplication gate (#254).

import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const MINERVA_BIN = resolve(REPO_ROOT, ".venv/bin/minerva");
const STATIC_DIR = resolve(REPO_ROOT, "web/dist");
const FIXTURE_JSONL = resolve(REPO_ROOT, "tests/fixtures/corpus.jsonl");

export interface FixtureServer {
  baseUrl: string;
  stop: () => void;
}

export function minervaBinPath(): string {
  return MINERVA_BIN;
}

/** Gate on the venv binary ONLY. A missing Python install is a legitimate
 *  environment difference; a missing fixture is not — it is committed, so
 *  its absence means something is wrong and startup should say so loudly
 *  rather than skip. Skipping on a missing fixture would rebuild the exact
 *  trap this suite was fixed to escape (#133). */
export function hasMinervaBin(): boolean {
  return existsSync(MINERVA_BIN);
}

export function fixtureChunkCount(): number {
  return readFileSync(FIXTURE_JSONL, "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0).length;
}

function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", rej);
    srv.listen(0, () => {
      const addr = srv.address();
      if (addr && typeof addr === "object") {
        const { port } = addr;
        srv.close(() => {
          res(port);
        });
      } else {
        srv.close(() => {
          rej(new Error("could not bind ephemeral port"));
        });
      }
    });
  });
}

async function waitForHealth(url: string, timeoutMs = 15000): Promise<unknown> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.json();
    } catch (_) {
      // server not up yet
    }
    await new Promise((res) => setTimeout(res, 150));
  }
  throw new Error(`server at ${url} did not become ready within ${timeoutMs}ms`);
}

export async function startFixtureServer(): Promise<FixtureServer> {
  const port = await freePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const tmpDir = mkdtempSync(join(tmpdir(), "minerva-e2e-"));
  const indexDb = join(tmpDir, "index.sqlite");
  const convDb = join(tmpDir, "conversations.sqlite");

  if (!existsSync(FIXTURE_JSONL)) {
    throw new Error(
      `fixture corpus missing at ${FIXTURE_JSONL}. It is committed — ` +
        `see tests/fixtures/README.md. Not skipping: a silent skip here ` +
        `is the bug this suite was fixed to avoid (#133).`,
    );
  }

  const built = spawnSync(
    MINERVA_BIN,
    ["index", "--db", indexDb, "--input", FIXTURE_JSONL, "--reset"],
    { cwd: REPO_ROOT, encoding: "utf8" },
  );
  if (built.status !== 0) {
    throw new Error(
      `fixture index build failed (exit ${String(built.status)}):\n` +
        `${built.stdout}\n${built.stderr}`,
    );
  }

  const proc: ChildProcess = spawn(
    MINERVA_BIN,
    [
      "serve",
      "--llm", "none",
      "--port", String(port),
      "--db", indexDb,
      "--static", STATIC_DIR,
      "--conversations-db", convDb,
    ],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] },
  );
  proc.stderr?.on("data", (b: Buffer) => process.stderr.write(`[serve] ${b.toString()}`));

  const health = (await waitForHealth(`${baseUrl}/api/health`)) as {
    chunks_total?: number;
  };
  const expected = fixtureChunkCount();
  if (health.chunks_total !== expected) {
    proc.kill("SIGTERM");
    rmSync(tmpDir, { recursive: true, force: true });
    throw new Error(
      `served index has ${String(health.chunks_total)} chunks, fixture has ` +
        `${String(expected)} — the server is reading some other database.`,
    );
  }

  return {
    baseUrl,
    stop: () => {
      if (!proc.killed) proc.kill("SIGTERM");
      rmSync(tmpDir, { recursive: true, force: true });
    },
  };
}
```

- [ ] **Step 2: Rewrite `serve.test.ts`'s setup to consume it**

Replace the imports, the module-level constants that moved, and the
`beforeAll`/`afterAll` bodies. Keep `describeOrSkip`, every existing `it`, and
every existing assertion untouched.

```ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import {
  hasMinervaBin,
  startFixtureServer,
  type FixtureServer,
} from "../helpers/fixtureServer";

const describeOrSkip = hasMinervaBin() ? describe : describe.skip;

describeOrSkip("e2e: minerva serve --llm none", () => {
  let server: FixtureServer;
  let baseUrl: string;

  beforeAll(async () => {
    server = await startFixtureServer();
    baseUrl = server.baseUrl;
  }, 60_000);

  afterAll(() => {
    server.stop();
  });

  // …every existing `it` unchanged…
});
```

The `expect(health.chunks_total).toBe(fixtureChunks)` assertion moves into the
helper as a thrown error, because Playwright's `globalSetup` has no `expect`.
The check itself — proving we serve the throwaway index and not some database
lying around — is preserved exactly.

- [ ] **Step 3: Run the existing suite to prove the move changed nothing**

Run: `cd web && npm run test:e2e`
Expected: PASS, the same number of tests as before the change. If the venv is
absent the suite skips — run `uv sync -p 3.13 --locked --extra dev` from the
repo root first, or the step proves nothing.

- [ ] **Step 4: Lint and typecheck the new file**

Run: `cd web && npm run lint && npm run typecheck`
Expected: both clean. `tests/**` is already in both `tsconfig.json#include` and
eslint's `files` list, so no config change is needed for this file.

- [ ] **Step 5: Commit**

```bash
git add web/tests/helpers/fixtureServer.ts web/tests/e2e/serve.test.ts
git commit -m "refactor(test): extract the fixture server from serve.test.ts

Playwright's globalSetup needs the same throwaway-index build and server
spawn that serve.test.ts inlines in beforeAll. Copying it would put both
copies into Sonar's duplication gate (#254), so it moves to
tests/helpers/fixtureServer.ts — helpers/ rather than e2e/ because both
consumers are siblings and neither owns it.

Pure move. Every assertion in serve.test.ts is unchanged, which is what
tests the refactor. The one behavioural translation: the chunk-count check
was an expect() and is now a thrown error, because globalSetup has no
expect. It still proves the server is reading the throwaway index and not
some database lying around — the failure mode from #133.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Playwright harness, smoke spec, and CI wiring

Deliberately wired into CI at this point, before any real test is written, so
the browser install time — the one number the spec flags as **estimated, not
measured** — is known before five specs depend on it.

**Files:**
- Create: `web/playwright.config.ts`, `web/tests/browser/globalSetup.ts`,
  `web/tests/browser/fixtures.ts`, `web/tests/browser/smoke.spec.ts`
- Modify: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`,
  `web/eslint.config.js`, `.github/workflows/check.yml`, `Makefile`

**Interfaces:**
- Consumes: `startFixtureServer`, `FixtureServer` (Task 3).
- Produces: `import { test, expect } from "./fixtures"` — a `test` whose
  `baseURL` is the running server. Tasks 5 and 6 import from here, never from
  `@playwright/test` directly.

- [ ] **Step 1: Install Playwright and add the scripts**

```bash
cd web && npm install --save-dev --save-exact @playwright/test
npx playwright install --with-deps chromium
```

Pinned exact, not caret: the browser binary is keyed to the package version, so
a float here silently changes what the gate runs.

Add to `web/package.json` `scripts`:

```json
    "test:browser": "playwright test",
```

- [ ] **Step 2: Keep vitest away from `tests/browser`**

In `web/vite.config.ts`, import `configDefaults` and extend — never replace —
the default excludes:

```ts
import { configDefaults, defineConfig } from 'vitest/config';
```

and inside `test: { … }`:

```ts
    // Playwright specs are `*.spec.ts`, which vitest's default glob collects
    // as readily as `*.test.ts`. Without this they run under vitest's node
    // environment and fail on an import they cannot resolve. Spread the
    // defaults rather than replacing them — assigning a bare array drops
    // vitest's own node_modules/dist exclusions.
    exclude: [...configDefaults.exclude, 'tests/browser/**'],
```

- [ ] **Step 3: Put the config file inside tsconfig and eslint**

`playwright.config.ts` sits at `web/` root, which is in neither
`tsconfig.json#include` nor eslint's `files` list. Left out, `tsc` ignores it
and eslint's `strictTypeChecked` errors with "file not found in project".

`web/tsconfig.json` — add to `include`:

```json
  "include": ["src", "tests", "vite.config.ts", "playwright.config.ts", ".storybook/**/*.ts", ".storybook/**/*.tsx"]
```

`web/eslint.config.js` — add to the `files` array at line 25:

```js
      "playwright.config.ts",
```

- [ ] **Step 4: Write the global setup**

Create `web/tests/browser/globalSetup.ts`:

```ts
// One server for the whole run. Playwright calls this once before any spec
// and awaits the returned teardown after the last one.
//
// The URL travels through the environment rather than a module export
// because globalSetup runs in a different process from the specs.

import { startFixtureServer } from "../helpers/fixtureServer";

export default async function globalSetup(): Promise<() => void> {
  const server = await startFixtureServer();
  process.env.MINERVA_E2E_BASE_URL = server.baseUrl;
  return () => {
    server.stop();
  };
}
```

- [ ] **Step 5: Write the config**

Create `web/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",

  // One worker against one shared server process. Parallelism here would buy
  // seconds on a five-test suite and cost cross-test interference, which is
  // the failure mode this suite cannot afford.
  fullyParallel: false,
  workers: 1,

  // Zero, permanently. A retry budget is the mechanism by which a required
  // gate becomes decoration: the first flaky red becomes a re-run, and once
  // re-running is routine the gate consumes attention and pays nothing. A
  // flaky test here is a defective test — delete it, do not retry it.
  retries: 0,

  forbidOnly: !!process.env.CI,
  globalSetup: "./tests/browser/globalSetup.ts",
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],

  use: {
    trace: "retain-on-failure",
  },

  // Chromium only. The three defects are layout and hit-testing bugs in the
  // engine the app is developed against; a second engine multiplies install
  // time and flake surface for coverage nobody asked for.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

- [ ] **Step 6: Write the fixtures module**

Create `web/tests/browser/fixtures.ts`:

```ts
// Every spec imports `test`/`expect` from here, never from @playwright/test.
//
// `baseURL` is an option fixture rather than a `use.baseURL` in the config
// because the config is evaluated BEFORE globalSetup runs — reading
// process.env there yields undefined. Overriding the fixture defers the read
// to test time, when the server is up.

import { test as base, expect } from "@playwright/test";

export const test = base.extend<object, object>({
  baseURL: async ({}, use) => {
    const url = process.env.MINERVA_E2E_BASE_URL;
    if (!url) {
      throw new Error(
        "MINERVA_E2E_BASE_URL is unset — globalSetup did not run or failed. " +
          "Not falling back to a default port: a fallback would silently " +
          "test whatever server happened to be listening.",
      );
    }
    await use(url);
  },
});

export { expect };
```

- [ ] **Step 7: Write the smoke spec**

The spec says "five tests, no more." This is a sixth file, and the exception is
deliberate: it asserts on the *harness*, not on the UI. Without it, a broken
build step or a server that never came up would surface as five confusing
failures in Tasks 5 and 6 rather than one clear one — and the 404 it guards
against is a live defect in `main` today, not a hypothetical.

Create `web/tests/browser/smoke.spec.ts`:

```ts
import { test, expect } from "./fixtures";

test("the built bundle is served and the app boots", async ({ page }) => {
  const response = await page.goto("/");

  // Guards the failure this suite exists to make visible: before this
  // change CI ran `minerva serve --static web/dist` without ever building
  // web/dist, so `/` returned a 404 JSON body and nothing noticed, because
  // no test requested `/` (#593).
  expect(response?.status()).toBe(200);

  // Solid has mounted, not merely served HTML.
  await expect(page.locator("#root, body > div").first()).toBeVisible();
});
```

- [ ] **Step 8: Run it locally**

```bash
cd web && npm run build && npm run test:browser
```

Expected: 1 passed. If it fails on a 404, `npm run build` did not run or wrote
somewhere other than `web/dist`.

- [ ] **Step 9: Add the Makefile target**

In `Makefile`, alongside `test-e2e` (line 90), add:

```make
test-browser:
	$(NPM) run build
	$(NPM) run test:browser
```

and add `test-browser` to the `.PHONY` list on line 27, and a line to the
`help` target near line 49:

```make
	@echo "  make test-browser Browser tests (Playwright, Chromium) against the built bundle"
```

Deliberately **not** added to `make check` — see the spec's section 11. The
existing e2e suite sets that precedent and this follows it.

- [ ] **Step 10: Wire CI**

In `.github/workflows/check.yml`, in the `web-e2e` job, after the existing
`E2E (vitest tests/e2e)` step:

```yaml
      - name: Build the web bundle
        # `minerva serve --static web/dist` has always been how the harness
        # starts the server, but nothing built web/dist here — so `/` 404'd
        # and no test noticed, because no test loaded a page (#593).
        run: npm run build

      - name: Cache Playwright browsers
        uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830 # v4
        id: playwright-cache
        with:
          path: ~/.cache/ms-playwright
          # Keyed on the resolved package version, not on a tag: the browser
          # binary is bound to it, so a bump must miss the cache.
          key: playwright-${{ runner.os }}-${{ hashFiles('web/package-lock.json') }}

      - name: Install Chromium
        # --with-deps installs the system libraries Chromium needs; it is
        # cheap when the browser itself is cached and required when it is not.
        run: npx playwright install --with-deps chromium

      - name: Browser tests (Playwright)
        run: |
          source ../.venv/bin/activate
          npm run test:browser

      - name: Upload Playwright trace on failure
        if: failure()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        with:
          name: playwright-trace
          path: web/test-results/
          retention-days: 14
```

That SHA is `v4`, resolved at planning time — every action in this workflow is
pinned to a commit SHA with a trailing version comment, because `@v4` is
mutable and a compromised action repo can move it. Re-resolve it if this plan
is executed long after it was written:

```bash
direnv exec . gh api repos/actions/cache/git/ref/tags/v4 --jq '.object.sha'
```

Dependabot's `github-actions` ecosystem bumps these pins and keeps the trailing
comment in step (#123), so it will maintain this one too.

- [ ] **Step 11: Add `test-results/` to gitignore**

```bash
printf 'web/test-results/\nweb/playwright-report/\n' >> .gitignore
```

- [ ] **Step 12: Verify the whole local gate still passes**

Run: `make check`
Expected: PASS. Re-run it after any edit made while fixing its output — two
pushes on #254 failed CI on errors introduced after the last local run.

- [ ] **Step 13: Commit and push, then measure the CI job**

```bash
git add -A
git commit -m "test(browser): Playwright harness, smoke spec and CI wiring

Adds @playwright/test (Chromium only, exact-pinned) driving the production
bundle served by the real minerva server, and wires it into the existing
web · e2e job — which is already a required check, so no branch protection
change.

Wired into CI before any real test is written, deliberately: the browser
install time was the one number the design could only estimate, and five
specs should not be built on top of an unmeasured assumption.

The smoke spec asserts GET / returns 200. That has not been true in CI:
the harness has always passed --static web/dist and CI has never built it,
so / returned a 404 JSON body and nothing noticed because no test loaded a
page. Fixed here by the build step; recorded in the PR body per CLAUDE.md
rather than filed, since it is fixed in the same change.

Three configuration traps worth naming:
  * vitest's default glob collects *.spec.ts, so tests/browser is excluded
    via configDefaults.exclude — spread, not replaced, or the default
    node_modules/dist exclusions are dropped.
  * baseURL is an option fixture, not use.baseURL: the config is evaluated
    before globalSetup runs, so reading process.env there yields undefined.
  * playwright.config.ts is added to tsconfig include and eslint files, or
    tsc ignores it and strictTypeChecked errors on it.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin HEAD
```

Then read the real number:

```bash
direnv exec . gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId'
direnv exec . gh api repos/:owner/:repo/actions/runs/<id>/jobs \
  --jq '.jobs[] | select(.name=="web · e2e") | .steps[] | "\(.name): \(((.completed_at|fromdate)-(.started_at|fromdate)))s"'
```

Record the total in the spec's section 9, replacing the estimate. If the job
now exceeds `web`'s ~168s it has become the critical path, and the cache key or
the `--with-deps` step needs revisiting before proceeding.

---

## Task 5: ReaderPage and the two selection tests

**Files:**
- Create: `web/tests/browser/pages/ReaderPage.ts`, `web/tests/browser/reader.spec.ts`

**Interfaces:**
- Consumes: `test`, `expect` (Task 4); accessible names from Task 1.
- Produces: `ReaderPage` with `goto`, `firstPopulatedLine`, `words`,
  `selectWords`, `clickWord`, `toolbar`, `lookupRail`.

- [ ] **Step 1: Write the page object**

Create `web/tests/browser/pages/ReaderPage.ts`:

```ts
import type { Locator, Page } from "@playwright/test";

/** Intent-level API for the Reader route.
 *
 *  Every accessor returns a Locator, never an ElementHandle: a Locator
 *  re-resolves on each use and carries Playwright's auto-waiting, while a
 *  handle is a snapshot that goes stale and then gets "fixed" with a sleep.
 *  Nothing here asserts — assertions belong in specs, so a failure names the
 *  behaviour that broke rather than a helper. */
export class ReaderPage {
  constructor(private readonly page: Page) {}

  async goto(workId: string): Promise<void> {
    await this.page.goto(`/#/r/${encodeURIComponent(workId)}`);
    await this.line().first().waitFor();
  }

  /** Rendered lines. `data-chunk-id` is not a test hook: production code
   *  queries it at Reader/index.tsx:246, utils.ts:92,
   *  useSelectionToolbar.tsx:263 and useWorkRange.tsx:225. */
  line(chunkId?: string): Locator {
    return chunkId === undefined
      ? this.page.locator("[data-chunk-id]")
      : this.page.locator(`[data-chunk-id="${chunkId}"]`);
  }

  /** Words within a line, in reading order. `data-offset` is the word's
   *  character offset in the chunk — app data, not styling. */
  words(line: Locator): Locator {
    return line.locator("[data-offset]");
  }

  /** The first line carrying at least `minWords` words.
   *
   *  Derived at run time rather than hardcoded: chunk ids come from the
   *  fixture corpus and churn whenever chunking changes — dropping one
   *  paragraph renumbers every chunk after it. serve.test.ts states the same
   *  rule for work rows (#133).
   *
   *  Throws rather than skipping. The fixture is committed, so a corpus that
   *  cannot satisfy this is a real failure. */
  async firstPopulatedLine(minWords: number): Promise<Locator> {
    const lines = this.line();
    const count = await lines.count();
    for (let i = 0; i < count; i++) {
      const candidate = lines.nth(i);
      if ((await this.words(candidate).count()) >= minWords) return candidate;
    }
    throw new Error(
      `no rendered line has ${String(minWords)} words. The fixture corpus is ` +
        `committed, so this is a real failure, not an environment difference — ` +
        `not skipping (#133).`,
    );
  }

  /** Drag-select from one word to another through real input.
   *
   *  Boxes are resolved at call time, never cached. The intermediate move is
   *  required: a single move-then-up does not reliably produce a selection in
   *  Chromium. This is the whole point of the suite — the mouseup's `target`
   *  comes from hit-testing, not from the test's choice of node, which is
   *  exactly the parameter every jsdom test was blind to in #591. */
  async selectWords(line: Locator, fromIndex: number, toIndex: number): Promise<void> {
    const words = this.words(line);
    const from = await words.nth(fromIndex).boundingBox();
    const to = await words.nth(toIndex).boundingBox();
    if (!from || !to) throw new Error("word has no box — is the line visible?");

    const mouse = this.page.mouse;
    await mouse.move(from.x + from.width / 2, from.y + from.height / 2);
    await mouse.down();
    await mouse.move(
      from.x + (to.x - from.x) / 2,
      from.y + (to.y - from.y) / 2,
      { steps: 8 },
    );
    await mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 });
    await mouse.up();
  }

  /** Press and release on a single word, without dragging. */
  async clickWord(line: Locator, index: number): Promise<void> {
    const box = await this.words(line).nth(index).boundingBox();
    if (!box) throw new Error("word has no box — is the line visible?");
    const mouse = this.page.mouse;
    await mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await mouse.down();
    await mouse.up();
  }

  get toolbar(): Locator {
    return this.page.getByRole("toolbar", { name: "Selection actions" });
  }

  /** The rail is inside `<Show when={state.kind !== "idle"}>`, so presence
   *  means open. Anchored on the close control's own label. */
  get lookupRail(): Locator {
    return this.page.getByRole("button", { name: "Close drawer" });
  }
}
```

- [ ] **Step 2: Write the failing specs**

Create `web/tests/browser/reader.spec.ts`:

```ts
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "./fixtures";
import { ReaderPage } from "./pages/ReaderPage";

/** The work the Reader opens, derived from the running server rather than
 *  written down: which works exist is a property of the fixture corpus, and
 *  work titles have been renamed wholesale before (#133). */
async function firstWorkTitle(request: APIRequestContext): Promise<string> {
  const res = await request.get("/api/works");
  const body = (await res.json()) as { works: { work: string }[] };
  const first = body.works[0];
  if (!first) {
    throw new Error(
      "/api/works returned no works — the fixture index is empty. Not " +
        "skipping: the fixture is committed, so this is a real failure (#133).",
    );
  }
  return first.work;
}

test.describe("Reader selection", () => {
  test("a drag that ends on a word shows the selection toolbar (#591)", async ({
    page,
    request,
  }) => {
    const reader = new ReaderPage(page);
    await reader.goto(await firstWorkTitle(request));

    const line = await reader.firstPopulatedLine(4);
    await reader.selectWords(line, 0, 3);

    await expect(reader.toolbar).toBeVisible();
    await expect(reader.toolbar.getByRole("button", { name: "Translate phrase", exact: true })).toBeVisible();
    await expect(reader.toolbar.getByRole("button", { name: "Copy", exact: true })).toBeVisible();
  });

  test("clicking a single word opens the rail and not the toolbar", async ({
    page,
    request,
  }) => {
    const reader = new ReaderPage(page);
    await reader.goto(await firstWorkTitle(request));

    const line = await reader.firstPopulatedLine(4);
    await reader.clickWord(line, 0);

    await expect(reader.lookupRail).toBeVisible();
    await expect(reader.toolbar).toBeHidden();
  });
});
```

`exact: true` on the button names is load-bearing: Playwright's `getByRole`
name option matches by substring, so a bare `"Translate"` would also match
`"Translate phrase"`. This is the refinement that made #594's `aria-label` half
unnecessary.

- [ ] **Step 3: Run them**

```bash
cd web && npm run build && npm run test:browser
```

Expected: both reader tests PASS against the fixed `SelectionToolbar` from
Task 1.

If the first test fails on the toolbar never appearing, that is the #591
regression — check the `closest()` guard in `useSelectionToolbar.tsx:194`
before touching the test. **Do not add a wait to make it pass.**

- [ ] **Step 4: Prove the test can actually fail**

A test that cannot fail is worse than no test. Temporarily revert the #591
fix — or stub `selectWords` to release on a non-word node — re-run, and
confirm the first test goes red. Restore afterwards.

```bash
git stash && npm run test:browser; git stash pop
```

Expected while stashed: the drag-select test FAILS. If it passes with the
fix reverted, the test is not exercising the guard and must be rewritten.

- [ ] **Step 5: Commit**

```bash
git add web/tests/browser/pages/ReaderPage.ts web/tests/browser/reader.spec.ts
git commit -m "test(browser): drag-select and single-word click in a real browser

Two assertions jsdom could not make. The mouseup's target now comes from
real hit-testing rather than from the test's choice of dispatch node, which
is the only parameter #591's guard read and the one every existing test was
blind to — they all called onMouseUp({ target: null }), which passes
closest() trivially.

Both were verified to fail with the #591 fix reverted.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: MetricsPage and the three layout tests

**Files:**
- Create: `web/tests/browser/pages/MetricsPage.ts`, `web/tests/browser/metrics.spec.ts`

**Interfaces:**
- Consumes: `test`, `expect` (Task 4); table names from Task 2.
- Produces: `MetricsPage` with `goto`, `chart`, `routeRow`, `selectRoute`,
  `table`.

- [ ] **Step 1: Write the page object**

Create `web/tests/browser/pages/MetricsPage.ts`:

```ts
import type { Locator, Page } from "@playwright/test";

export class MetricsPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/#/metrics");
    await this.table.waitFor();
  }

  get table(): Locator {
    return this.page.getByRole("table", { name: "Requests by route" });
  }

  /** The chart's own name, from TimeSeriesChart.tsx:148-149. */
  get chart(): Locator {
    return this.page.getByRole("img", { name: /Latency over time/ });
  }

  /** A row identified by the route it reports, via the one pre-existing
   *  data-testid in the codebase (MetricsPanel.tsx:357). Tier 1 cannot
   *  distinguish rows: a row's accessible name concatenates every cell,
   *  including counts that change between runs. */
  routeRow(label: string): Locator {
    return this.table.getByRole("row").filter({
      has: this.page
        .getByTestId("metrics-route-label")
        .and(this.page.getByText(label, { exact: true })),
    });
  }

  async selectRoute(label: string): Promise<void> {
    await this.routeRow(label).click();
  }

  /** The first route label the server actually reported. Derived, because
   *  which routes appear depends on what the suite happened to request. */
  async firstRouteLabel(): Promise<string> {
    const cell = this.page.getByTestId("metrics-route-label").first();
    const text = (await cell.textContent())?.trim();
    if (!text) {
      throw new Error(
        "no route rows rendered — the server recorded no requests. Not " +
          "skipping: the suite has already driven the API by this point.",
      );
    }
    return text;
  }
}
```

- [ ] **Step 2: Write the failing specs**

Create `web/tests/browser/metrics.spec.ts`:

```ts
import { test, expect } from "./fixtures";
import { MetricsPage } from "./pages/MetricsPage";

// DEFAULT_HEIGHT in TimeSeriesChart.tsx:15. Asserting the literal is the
// point: the defect was the height feeding back into the element being
// measured and growing without bound — 164220, then 220348 -> 220828 ->
// 221308 -> 221788, +480px per frame. Any assertion loose enough to accept
// a "reasonable" height would have accepted the first frame of that.
const CHART_HEIGHT = "220";

test.describe("Metrics layout", () => {
  test("the trend chart keeps a fixed height", async ({ page }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());

    await expect(metrics.chart).toHaveAttribute("height", CHART_HEIGHT);

    // A single reading cannot distinguish "fixed" from "caught early".
    // Re-read after a frame: the runaway loop grew on every one.
    await page.waitForFunction(() => true);
    await expect(metrics.chart).toHaveAttribute("height", CHART_HEIGHT);
  });

  test("selecting a route shows the chart without scrolling", async ({ page }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());

    // The chart rendered 780px down — 472px below the fold — so selecting a
    // route updated something the user could not see.
    await expect(metrics.chart).toBeInViewport();
  });

  test("the route table scrolls internally while the chart stays in view", async ({
    page,
  }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());
    await expect(metrics.chart).toBeInViewport();

    await metrics.table.evaluate((el) => {
      const wrap = el.parentElement;
      if (wrap) wrap.scrollTop = wrap.scrollHeight;
    });

    await expect(metrics.chart).toBeInViewport();
  });
});
```

- [ ] **Step 3: Run them**

```bash
cd web && npm run build && npm run test:browser
```

Expected: all five browser tests PASS.

If `firstRouteLabel` throws because no routes were recorded, the metrics store
is per-server-process and this spec file ran before anything hit the API. Fix
it by having the spec make a request first — `await page.goto("/#/")` then
`/#/metrics` — not by skipping.

- [ ] **Step 4: Prove the height test can fail**

Temporarily change `DEFAULT_HEIGHT` in `TimeSeriesChart.tsx:15` to `221`,
rebuild, re-run, confirm the height test goes red, then restore and rebuild.

```bash
sed -i '' 's/const DEFAULT_HEIGHT = 220;/const DEFAULT_HEIGHT = 221;/' src/Metrics/TimeSeriesChart.tsx
npm run build && npm run test:browser   # expect the height test to FAIL
sed -i '' 's/const DEFAULT_HEIGHT = 221;/const DEFAULT_HEIGHT = 220;/' src/Metrics/TimeSeriesChart.tsx
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add web/tests/browser/pages/MetricsPage.ts web/tests/browser/metrics.spec.ts
git commit -m "test(browser): chart height, viewport position and table scroll

Three assertions jsdom cannot make: it performs no layout, so clientHeight
is always 0 (#585) and there is no viewport at all.

The height assertion is deliberately a literal, not a range. The defect was
the measured height feeding back into the element being measured — 164220,
then +480px per frame past 221788 — and any assertion loose enough to
accept a 'reasonable' height would have accepted its first frame. Verified
to fail by flipping DEFAULT_HEIGHT to 221.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Write the policy down

The rules only survive if they are somewhere an author will hit them. The
existing jsdom suite locates by CSS class and positional index throughout, so
without this the new suite drifts to match the old one.

**Files:**
- Modify: `docs/CONTRIBUTING.md`
- Modify: `docs/superpowers/specs/2026-09-13-browser-level-tests-design.md`

- [ ] **Step 1: Add the section to CONTRIBUTING**

Add under the testing material in `docs/CONTRIBUTING.md`:

```markdown
### Browser tests

`web/tests/browser/` runs under Playwright against the production bundle
served by the real server. Five tests, Chromium only, in the `web · e2e` job.
Run locally with `make test-browser`.

**Locators, in order. Reach lower only when every tier above genuinely
cannot distinguish the target.**

1. `getByRole` with an accessible name.
2. Data attributes the app's own code queries — `data-chunk-id`,
   `data-offset`. These are load-bearing in `src/`, not test scaffolding.
3. `data-testid`, with a comment saying why tiers 1–2 failed.
4. Never: CSS class selectors, positional indexing as a substitute for
   identity, literal corpus text, or coordinates from anything but a box
   measured at call time.

Selecting the Nth word of a line is **not** tier 4 — a word's position in a
sentence is its identity. Picking the second `.st-btn` to mean "Translate"
is.

**This differs from the jsdom suite on purpose.** `tests/SelectionToolbar.test.tsx`
locates by `.st-btn` plus `buttons[0]`/`buttons[1]`. That suite is not being
converted, but do not "fix" the browser suite to match it — locating by class
and index is why #594 went unnoticed for the life of the component: nothing
ever consulted an accessible name.

**A flaky browser test is a defective test. Delete it; do not retry it.**
`retries: 0` is permanent. The first flaky red becomes a re-run, and once
re-running is routine the gate consumes attention and pays nothing — which is
worse than not having it. If a test needs a `waitForTimeout` to pass, it is
asserting on the wrong thing.

**Page objects return `Locator`, never `ElementHandle`, and never assert.**
A handle is a stale snapshot that gets repaired with a sleep.

**Fixtures derive corpus values at run time and throw — never skip — when the
corpus cannot satisfy them.** A silent skip is how #133's assertions rotted
for months.
```

- [ ] **Step 2: Replace the CI estimate with the measurement**

In the spec's section 9, replace the "**This is an estimate, not a
measurement**" paragraph with the real per-step timings recorded in Task 4,
step 13, and state whether the job became the critical path.

- [ ] **Step 3: Run the full gate**

Run: `make check`
Expected: PASS. Re-run after any edit made while fixing its output.

- [ ] **Step 4: Commit**

```bash
git add docs/CONTRIBUTING.md docs/superpowers/specs/2026-09-13-browser-level-tests-design.md
git commit -m "docs(test): locator and flake policy for the browser suite

Records the rules in the place an author will hit them, and replaces the
design's estimated CI timing with the measured one.

The locator policy deliberately contradicts the jsdom suite's house style,
so the divergence is written down rather than left to be discovered and
'fixed' back: locating by class and index is precisely why #594 went
unnoticed for the life of the component.

Refs #593.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Open the PR and verify the links registered

- [ ] **Step 1: Rebase onto main**

Branch protection is `strict: true`, so any merge to `main` puts this PR
`BEHIND`.

```bash
git fetch origin && git rebase origin/main
```

- [ ] **Step 2: Run the gate once more after the rebase**

Run: `make check`
Expected: PASS.

- [ ] **Step 3: Open the PR**

```bash
git push -u origin HEAD
cat > /tmp/pr-593.md <<'BODY'
Five browser assertions over the three defects jsdom cannot see, plus the
accessibility fix they turned out to depend on.

Design: `docs/superpowers/specs/2026-09-13-browser-level-tests-design.md`
Plan: `docs/superpowers/plans/2026-09-13-browser-level-tests.md`

## What landed

`@playwright/test`, Chromium only, exact-pinned, driving the production
bundle served by the real `minerva serve --llm none` against a throwaway
index built from the committed fixture corpus. It runs in the existing
`web · e2e` job, which was already a required check — no branch protection
change was needed.

| test | defect it pins |
|---|---|
| drag-select a phrase shows the toolbar | #591 |
| a single-word click opens the rail and not the toolbar | the regression #591's fix risks |
| the chart keeps `height="220"` across frames | the runaway height, measured at +480px/frame past 221788 |
| the chart is in the viewport after a route is selected | it rendered 472px below the fold |
| the table scrolls internally while the chart stays in view | the layout contract |

The suite is five tests plus one smoke assertion that `GET /` returns 200.
The smoke test is harness verification, not a sixth UI regression test —
see "Findings" below for why it earns its place.

## Locator policy

Recorded in CONTRIBUTING, because it deliberately contradicts the jsdom
suite's house style and would otherwise be "fixed" back. Role + accessible
name, then the data attributes the app's own code queries (`data-chunk-id`,
`data-offset` — load-bearing in four `src/` call sites), then `data-testid`,
and never CSS classes or positional indexing as a substitute for identity.

`retries: 0`, permanently. A retry budget is how a required gate becomes
decoration.

## Findings fixed here rather than filed

Per CLAUDE.md, both are fixed in this same change:

- **CI has never built `web/dist`.** The harness has always passed
  `--static web/dist` (`serve.test.ts:25,122`), and the `web-e2e` job had no
  build step, so `/` returned a 404 JSON body from `serve.py:461`. Nothing
  noticed because no test ever requested `/`. The smoke test is what makes
  this permanently visible.
- **Neither metrics table had an accessible name**, so `getByRole("table")`
  matched two elements whenever a route was selected.

## Correction to #594's stated fix

#594's Hypothesis proposed `aria-hidden` on the hint spans **plus** an
explicit `aria-label` per control, and described the four prose-context
`kbd` spans as the same problem deferred. Both parts needed correcting, and
the reasoning is recorded on the issue:

- `exact: true` on the locator makes the `aria-label` half unnecessary, and
  avoids introducing an announced name that diverges from the visible label.
- `aria-hidden` on the prose spans would be a **regression**: in
  `Composer/index.tsx:37` the span carries the key and the adjacent text
  carries the verb, so hiding it announces "send" with no indication of how.

The Measured half of #594 reproduced exactly.

## Verification

- `make check` green.
- Every browser test was verified to fail with its defect reintroduced —
  the #591 fix reverted, and `DEFAULT_HEIGHT` flipped to 221.
- `make check-pr-link` run against this PR.

Closes #593.
Closes #594.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
direnv exec . gh pr create --base main \
  --title "test(browser): five Playwright assertions over jsdom's blind spots" \
  --body-file /tmp/pr-593.md
```

- [ ] **Step 4: Verify the links actually registered**

Filing issues is worthless if closing them is manual, and three GitHub
behaviours make this fail silently.

```bash
make check-pr-link PR=<n> ISSUES="593 594"
```

Expected: exit 0. Empty output from `closingIssuesReferences` on a PR that
fixes something is a bug in the PR.

- [ ] **Step 5: Watch CI**

```bash
direnv exec . gh pr checks <n> --watch
```

All four required contexts must be green: `python · lint · pytest`,
`web · lint · typecheck · vitest`, `web · e2e`, `SonarCloud Code Analysis`.

Sonar gates this change has no local equivalent for: duplication ≤3% on new
code — Task 3 exists to keep the server harness from being copied — and
cognitive complexity ≤15 per function for maintainability rating A.
