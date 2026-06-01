// Reusable Storybook decorators for minerva-web.
//
// `withTheme` is the only decorator the seed stories actually need —
// and even then, only when a story wants to PIN the theme regardless
// of the toolbar global (e.g. side-by-side light + dark comparisons in
// a single canvas). Most stories should rely on the global theme
// decorator wired in `preview.tsx` and use the toolbar to switch.
//
// `withRouting` and `withReaderShell` are placeholders documented here
// for future use — they'll be filled in when the first context-heavy
// stories (Reader/Lines, Sidebar, Thread/index) are written. Keeping
// the empty exports + JSDoc serves as a contract for what shape
// future decorators should take.

import type { Decorator } from "storybook-solidjs-vite";

/**
 * Pin a story to a specific theme regardless of the toolbar global.
 * Useful in side-by-side variant comparisons where one story shows
 * light and another shows dark in the same canvas.
 *
 * Usage:
 *
 *   export const Dark: Story = {
 *     decorators: [withTheme("dark")],
 *   };
 */
export function withTheme(theme: "light" | "dark"): Decorator {
  return (Story, ctx) => {
    document.documentElement.setAttribute("data-theme", theme);
    return Story(ctx);
  };
}

/**
 * Stub the routing signal for components that read from `routing.ts`.
 * Not implemented yet — first usage will be `Sidebar.stories.tsx` or
 * `Topbar.stories.tsx`, when those are written. Will likely take a
 * `{ route: ..., conversationId?: ..., focusChunkId?: ... }` config and
 * return a decorator that installs a mock routing provider.
 */
export function withRouting(_config: unknown): Decorator {
  return (Story, ctx) => Story(ctx);
}

/**
 * Wrap a story in the reader column scaffolding so chunk-level
 * components (`Reader/Lines`, the upcoming inline cross-reference
 * gutter marker) render at production width with the `.line` grid in
 * place. Not implemented yet — first usage will be `Lines.stories.tsx`.
 */
export function withReaderShell(_config: { chunks?: unknown; lang?: string }): Decorator {
  return (Story, ctx) => Story(ctx);
}
