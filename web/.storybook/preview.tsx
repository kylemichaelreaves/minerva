import type { Preview } from "storybook-solidjs-vite";

// Global app styles. styles.css owns the `--paper` / `--ink` / `--accent`
// tokens for both light and dark; reader.css adds the reader-only
// `--r-*` token namespace used by Lines/Chrome/TermCard and (soon)
// ReferenceCard; mobile.css adds the ≤768px overrides that drive the
// mobile design (atlas-to-top landing, drawer sidebar, bottom-sheet
// rail, chip-strip filters, hero+cards network). All must load on
// every story so component CSS resolves the same as in the live app.
import "../src/styles/styles.css";
import "../src/Reader/reader.css";
import "../src/styles/mobile.css";

// Mobile-design viewports. The two iPhone sizes here mirror the
// wireframes (mobile-wireframes.html 1a/1b · 3a/3b): primary 390×844
// and narrow check 375×812. Storybook 10 ships viewport in core; no
// addon install required — stories opt in via
// `parameters.viewport.defaultViewport = "iphone14"`.
const VIEWPORTS = {
  iphone14: {
    name: "iPhone 14 (390 × 844)",
    styles: { width: "390px", height: "844px" },
    type: "mobile",
  },
  iphoneSE: {
    name: "iPhone SE narrow (375 × 812)",
    styles: { width: "375px", height: "812px" },
    type: "mobile",
  },
};

const preview: Preview = {
  parameters: {
    // Default to the warm paper from `styles.css`'s `:root`. Stories
    // can override per-component via `parameters.backgrounds`.
    backgrounds: {
      default: "paper",
      values: [
        { name: "paper", value: "#f4efe6" },
        { name: "paper-dark", value: "#14110e" },
      ],
    },
    viewport: {
      viewports: VIEWPORTS,
    },
    // Most early stories are popover-style components (TermCard,
    // ConfirmDialog, the upcoming ReferenceCard); center layout
    // gives them room to render. Reader-shell stories override to
    // `padded` or `fullscreen`.
    layout: "centered",
  },
  globalTypes: {
    theme: {
      description: "Color theme (sets html[data-theme])",
      defaultValue: "light",
      toolbar: {
        title: "Theme",
        icon: "paintbrush",
        items: [
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [
    // Theme decorator: flips `data-theme` on <html> to match the real
    // app's contract (web/src/theme.ts line 55). styles.css's
    // `[data-theme="dark"]` selector picks up the rest. No call to
    // `applyAccent()` from data.ts is needed — the CSS file's `:root`
    // and dark-mode blocks already populate `--accent` / `--accent-soft`
    // with the oxblood defaults that match `ACCENTS.oxblood`.
    (Story, ctx) => {
      // The cast must admit `undefined`: a story rendered before the
      // toolbar global is set has no `theme`, which is exactly what the
      // `??` is for. Asserting it non-nullable made the `??` dead code and
      // was the one real finding this file's first-ever lint turned up
      // (typescript-eslint/no-unnecessary-condition, #480).
      const theme = (ctx.globals.theme as "light" | "dark" | undefined) ?? "light";
      document.documentElement.setAttribute("data-theme", theme);
      return Story();
    },
  ],
};

export default preview;
