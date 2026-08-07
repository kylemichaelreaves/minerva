# Storybook for minerva-web

Component dev sandbox for the SolidJS frontend. Run with:

```bash
cd web
npm run storybook         # dev server on :6006
npm run build-storybook   # static build to web/storybook-static/
```

Stack: Storybook 10 + `storybook-solidjs-vite` (community SolidJS adapter,
`solidjs-community/storybook`). The adapter is in the storybook-bot Vite-8
peer range, so no `overrides` in `package.json` are needed.

## Layout

```
web/.storybook/
  main.ts           # framework + addons + stories glob
  preview.tsx       # global CSS imports, theme toolbar, paper backgrounds
  decorators.tsx    # reusable decorators (withTheme is the only one wired today)
  README.md         # this file

web/src/**/*.stories.tsx
                    # one story file alongside each component
```

## Writing a new story

```tsx
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import MyComponent from "./MyComponent";

const meta: Meta<typeof MyComponent> = {
  title: "Category/MyComponent",
  component: MyComponent,
  args: {
    /* default args for every story */
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { /* per-story overrides */ },
};
```

The seed stories in `web/src/components/ConfirmDialog.stories.tsx` and
`web/src/components/TermCard.stories.tsx` are the templates to copy from —
the former is a pure props-in component, the latter shows how to
mock `/api/*` fetches and pass a `DOMRect` anchor to a popover.

## Theme toolbar

The toolbar (top-right) has a Theme dropdown (`light` / `dark`) that
flips `data-theme` on `<html>`. This mirrors `web/src/theme.ts`'s
contract; the `[data-theme="dark"]` selectors in `web/src/styles.css`
do the rest. The accent palette (`--accent`, `--accent-soft`,
`--selection`) is driven by the static `:root` + dark-mode CSS blocks
in `styles.css`; no JS `applyAccent()` call is needed.

To pin a story to one theme regardless of the toolbar (useful for
side-by-side comparisons), use `withTheme("dark")` from
`.storybook/decorators.tsx`. See `TermCard.stories.tsx::DarkTheme`.

## Mocking fetch

Components that call `fetch('/api/...')` need their requests
intercepted in stories. Pattern from `TermCard.stories.tsx`:

```tsx
const originalFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url;
  if (url.startsWith("/api/terms/")) {
    return new Response(JSON.stringify(mockData), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }
  return originalFetch(input, init);
};
```

This is sufficient for the dev sandbox. If we grow into MSW-style
full-request mocking later (e.g. for visual regression in CI), the
pattern can be lifted into a shared `.storybook/mocks.ts`.

## Deferred / future work

- **Visual regression testing.** Chromatic-style snapshot diffs on
  PR. Storybook's `build-storybook` already emits the static bundle
  needed for this; it's just unwired.
- **Full MSW integration.** Replace the ad-hoc `globalThis.fetch`
  overrides with `msw` + `@storybook/addon-mocks` for type-safe
  request handlers and inspectability.
- **Remaining component stories.** As of the initial implementation,
  these have stories: `ConfirmDialog`, `LoadingDots`, `HoverTip`,
  `TermCard`. Still without stories: `App`, `Topbar`, `Sidebar`,
  `Landing`, `Composer`, `Icons`, `Reader/Lines`, `Reader/Chrome`,
  `Reader/Rail`, `Thread/index`. Write these as needed — explicitly
  NOT a back-catalog effort.
- **Decorator stubs.** `withRouting` and `withReaderShell` in
  `.storybook/decorators.tsx` are documented placeholders. Fill them
  in when the first context-heavy component story is needed.
- **ESLint scope for stories.** Story files currently pass
  `npm run lint` without any rule overrides. If `eslint-plugin-solid`
  trips on a future story's export shape, scope an override under
  `**/*.stories.tsx` in the eslint config rather than disabling
  inline.
