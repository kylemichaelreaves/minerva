# Frontend conventions

`web/` is a Solid.js single-page app with vanilla CSS and a hash-based router.
These rules codify the de-facto patterns already present in the codebase. Match
them when adding or editing components; reviewers will hold the diff to them.

These are conventions for human-and-AI engineers alike. The shapes here are
chosen because they line up with Solid's reactivity model — deviating breaks
reactivity in ways that are hard to diagnose.

## Single-file components (SFC)

Every UI component and its surface-specific utilities live in **one `.tsx` file**
(SFC). Do not add parallel `hooks/foo.ts` or `utils/bar.ts` trees under feature
surfaces.

| Rule | Detail |
|------|--------|
| **Extension** | `.tsx` under `src/<Surface>/` and for UI hooks in `src/hooks/`. |
| **Colocation** | `interface Props`, `function useFoo()`, pure helpers in the **same** file as the component. |
| **Named exports** | Export testable helpers from the SFC (e.g. `export function selectArcPairs`). |
| **Large files** | Split into **child component SFCs**, not `.ts` util modules. |
| **Layout** | `src/<Surface>/index.tsx` orchestrator + sibling `*.tsx` files; avoid `hooks/`, `utils/`, `components/` subfolders. |
| **Tests** | `web/tests/` (flat); import named exports from the SFC under test. |

**Exceptions (`.ts` allowed):** `src/api/` and `src/api/types/` (wire clients);
root controllers (`routing.ts`, `*Ctrl.ts`, `conversationsSend.ts`); `routes/routeUtils.ts`;
generated data (`src/data/atlasData.ts`); shared pure libs in `src/utils/`
(`util.ts`, `renumber.ts`, `popoverPosition.ts`, …). Shared hooks use
`src/hooks/use*.tsx`.

**`src/Syntax/` is a deliberate structural exception.** It carries
`conllu/`, `layout/` and `corrections/` subtrees of pure `.ts` modules plus a
`components/` folder, which the Layout rule above otherwise forbids. The
justification is that every one of those modules is pure, independently
testable, and the thing most likely to be subtly wrong: arc levels,
projectivity, row wrapping, the CoNLL-U round trip, and the correction replay
are all cheap to unit-test in isolation and expensive to debug through a
rendered SVG. Note the subtree names — `conllu`, `layout`, `corrections`, not
`hooks` or `utils` — which is what clears the `no-restricted-syntax` rule in
`eslint.config.js`. That rule matches `src/**/hooks/**/*.ts` and
`src/**/utils/**/*.ts` structurally, so `Syntax/` needs no exception and a
surface added tomorrow is guarded without editing it (#477). Don't read this as a general licence: it applies to
provably pure geometry and format code, not to component state.

**Types:** API wire shapes in `src/api/types/`; UI domain types in `src/utils/uiTypes.ts`.
The barrel `src/utils/types.ts` re-exports both for legacy imports. Change Python
handlers, JSON fixtures (`tests/fixtures/api/*.keys.json`), and TS types together;
`make check` runs `scripts/check_api_types.py` and `tests/test_api_contract.py`.

## Components

- **One component per file.** PascalCase; file name matches the export.
- **Co-locate by surface**: `src/features/<Surface>/<Component>.tsx`. Genuinely
  cross-surface components go in `src/components/`, which is grouped by *kind*
  rather than left flat (#324, #475):

  | group | what belongs there |
  |---|---|
  | `components/primitives/` | Surface-agnostic UI with no domain knowledge — `Select`, `HoverTip`, `Icons`, `LoadingDots`, `Toasts`, `PopoverCard`, `ConfirmDialog`, `ExtLinkIcon`. |
  | `components/shell/` | The app's framing, both viewports: `Topbar`, `topbarStyles`, `ThemeToggle`, `MobileTopBar`, `MobileSheet`, `MobileShellContext`, `FilterSheet`. |
  | `components/cards/` | Components that know about corpus domain types — `ReferenceCard`, `TermCard`, `XrefMarker`, `ComposeField`. |

  The test for `shell/` is *framing*, not viewport: the desktop `Topbar` and the
  `MobileTopBar` are the same job answered twice, so they sit together rather
  than in a `chrome/` and a `mobileShell/` that would have to be read as a pair.
  `SurfaceErrorBoundary` is deliberately **not** here — it is infrastructure
  rather than UI, and lives in `src/routes/` beside the route surfaces that
  mount it.
- **Pure functions** of `props`: `function X(props: XProps) { … }`.
- **Never destructure props** — `function X({ a, b })` loses reactivity. The
  destructure happens once at call time; later updates to `a` or `b` are
  invisible to the JSX.
- **Read `props.x` inside JSX or inside an accessor** (`() => props.x`,
  `createMemo`). Don't capture `const x = props.x` at the top of the function
  body — that snapshot won't update.

## State

| Scope                            | Tool                                              |
|----------------------------------|---------------------------------------------------|
| Shareable / bookmarkable         | URL params via `src/routing.ts` Route shape       |
| Ephemeral UI (open, expanded, …) | `createSignal` in the component body              |
| Derived from props / signals     | `createMemo` when read more than once             |
| Server data                      | `createResource`, in the same SFC as the consumer |
| Listeners, intervals, observers  | clean up with `onCleanup`                         |

For URL-bound filters, accept `undefined` patches and route them through
`mergeRoutePatchAllowClear` (see `src/routes/routeUtils.ts`). That's what makes
"remove this chip" navigations work.

## JSX

- **`class`, not `className`.** Solid uses the DOM attribute name.
- **`classList={{ on: cond, dim: other }}`** for conditional classes — cleaner
  than string concatenation.
- **`<For each={list()}>{(item, index) => …}</For>`** for lists. `item` is the
  value; `index` is an *accessor* — call it as `index()`. Solid keys by identity
  by default.
- **`<Show when={cond}>…</Show>`** for conditionals. Avoid ternaries that
  conditionally render JSX trees — `<Show>` keys correctly and short-circuits.
- **Inline `style={{}}`** is fine for ≤ 2 declarations or genuinely one-off
  cases. Three or more → extract to a class in the surface stylesheet.

## CSS

- **One stylesheet per surface**, colocated with the entry (e.g.
  `src/Concordance/concordance.css`). Import it once at the top of the surface
  entry file. No CSS modules, no CSS-in-JS.
- **Tokens come from `src/styles.css`**: `--ink`, `--paper`, `--accent`,
  `--rule`, `--serif`, `--sans`, `--mono`, etc. Never hardcode colors or font
  stacks — that breaks the light/dark toggle.
- **BEM-style prefixes per surface** (`.conc-*`, `.kwic-*`, `.fr-*`, `.lb-*`)
  to avoid collisions — class names are global.
- **Mobile overrides live in the surface stylesheet's `@media (max-width: 768px)`
  block**, not in a separate file (`src/mobile.css` is for shell-level rules
  only — sidebar drawer, top-bar swap).

## TypeScript

- **Prefer inline prop types** for components used once:
  `function X(props: { a: string; onPick: () => void })`. Export
  `interface XProps` when the type crosses files.
- **Avoid `as` casts.** If a `Dropdown<T>` needs to carry a value type, make it
  generic. `value as ConcSort` hides real shape mismatches that bite at runtime.
- **No `any`.** Narrow via type-guards (`is`-predicates) or discriminated unions.

## Accessibility

The project's pattern (not a strict WCAG ramp, but consistent):

- Clickable `<span>` / `<div>` carry `role="link"` or `role="button"` — see
  `Concordance/components/LbRow.tsx`.
- Real `<button type="button">` is used for actions that submit, close, or
  open a sheet — see `src/components/shell/MobileSheet.tsx`.
- Dialog-role containers carry `aria-label`.
- Keyboard nav: every page-level shortcut lives in the owning SFC (e.g.
  `LemmaDetail.tsx`) with cleanup via `onCleanup`. Don't sprinkle ad-hoc
  `addEventListener` calls in JSX.
- **Escape is a ladder, innermost first.** Each transient surface dismisses
  itself, and only a press with nothing open does the outer thing. In the
  Reader that outer thing is *leave for the landing*, gated on
  `escapeExitsReader` (`Reader/utils.ts`), which names every surface that owns
  the key: rail, term card, xref card, selection toolbar, mobile settings
  sheet, syntax layer. `useEscape`'s `active` argument is how a rung stands
  down — a false gate registers no listener at all, so it cannot race the
  surface that should win. A new transient surface in the Reader adds itself to
  `ReaderSurfaces`, and the type turns forgetting into a compile error.

## Solid reactivity gotchas

The three pitfalls that recur in this codebase:

1. **`const x = props.x` at the top of the component** captures a stale value.
   Always read inside JSX or wrap in an accessor:
   ```tsx
   // ❌ stale after the first render
   function Row(props: { row: Row }) {
     const lemma = props.row.lemma;
     return <span>{lemma}</span>;
   }
   // ✅ reactive
   function Row(props: { row: Row }) {
     return <span>{props.row.lemma}</span>;
   }
   ```
2. **`<For>` row body destructuring** has the same problem — the item is a value
   but JSX inside the row reads through it lazily. Read fields directly off the
   item, not into a const, if you want the row to update in place.
3. **`createResource(() => deps, …)`** refetches when the deps object's
   *identity* changes. Build a fresh object each tick by reading reactive
   accessors inside the deps function:
   ```tsx
   createResource(
     () => ({ lang: args.lang(), scope: args.scope() }),
     async (p) => fetchX(p),
   );
   ```

## Linting and types — keep them live

`web/eslint.config.js` is strict (`typescript-eslint` `strictTypeChecked` +
`eslint-plugin-solid`). Run it constantly, not just at the gate:

- **Editor**: install the ESLint and Prettier extensions and turn on
  `eslint.validate` for `javascript`, `typescript`, `typescriptreact`. The
  shipped `.vscode/settings.json` does this. Format-on-save kills the
  "but it ran locally" class of CI failures.
- **Commit**: install the pre-commit hook (`./scripts/install-git-hooks.sh`).
  It runs `make lint typecheck` — under 10 seconds, catches the same things
  CI would.
- **Don't introduce a rule that only CI enforces.** If you add or unmute
  an ESLint rule, also wire it into the editor's lint-on-save loop and
  bring the existing codebase up to it in the same change (or with a
  follow-up tracked PR). Otherwise lint debt accrues silently.

When ESLint flags something, prefer fixing the code over disabling the
rule. Use `// eslint-disable-next-line <rule> — <reason>` only when the
defensive pattern is real and the type system can't see it (async
ResizeObserver callbacks, array-index access without
`noUncheckedIndexedAccess`, dynamic record keys). Always include the
reason — the disable becomes self-documenting and the next reader doesn't
have to guess.

## Tests

Tests live under `web/tests/` (flat layout, not co-located).

**Required for every PR that touches `web/src/`:**
- A hook with non-trivial logic ships with a `<Name>.test.ts` (memo derivations,
  keyboard handlers, debouncing, reactive composition).
- A util / data-shaping function (named export on an SFC, or
  `src/utils/popoverPosition`, `src/utils/renumber`) ships with
  `<Name>.test.ts`.
- A component with behavior beyond "render props as-is" ships with
  `<Name>.test.tsx`. "Behavior" includes: conditional rendering thresholds
  (e.g. the `LemmaIdentityCard` 95% gender-lock heuristic), local state
  (sheet open/closed), event handlers (chip-remove, reset), and clamping
  (`FreqRange`).

**Optional** — pure presentational components with zero conditional logic
(e.g. `LbRow` rendering one row of static props) — but add a test the moment
the component grows a branch.

**Pattern** — see `tests/ActiveFilterStrip.test.tsx`,
`tests/LemmaIdentityCard.test.tsx`, `tests/FreqRange.test.tsx` for the
vitest + `@solidjs/testing-library` shape. `render(() => <X />)`,
`screen.getBy*`, `fireEvent.*`, `vi.fn()` for callbacks.

`make check` runs `vitest` unit tests; the PR fails on the first failing test.
E2E (`make test-e2e`) is on-push-to-main only.

## Where to look

| Pattern you need                | Look at                                            |
|---------------------------------|----------------------------------------------------|
| Hook backed by `createResource` | `src/Concordance/IndexPage.tsx`                    |
| Mobile breakpoint signal        | `src/hooks/useMobile.tsx`                          |
| Bottom-sheet (portal + scrim)   | `src/components/shell/MobileSheet.tsx`             |
| Clickable row with `role`       | `src/Concordance/components/LbRow.tsx`             |
| Route shape + URL serializer    | `src/routing.ts`                                   |
| Allow-clear route patch         | `src/routes/routeUtils.ts` `mergeRoutePatchAllowClear` |
| Active-filter chip strip        | `src/Concordance/components/ActiveFilterStrip.tsx` |
