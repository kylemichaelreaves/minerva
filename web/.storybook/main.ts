import type { StorybookConfig } from "storybook-solidjs-vite";

// Storybook 10 + community-maintained SolidJS adapter
// (https://github.com/solidjs-community/storybook). The adapter bundles
// its own Vite builder + vite-plugin-solid; we don't import them
// directly. Vite 8 is in the adapter's peer range (^5 || ^6 || ^7 || ^8),
// so no overrides block is needed in package.json.
const config: StorybookConfig = {
  framework: {
    name: "storybook-solidjs-vite",
    options: {},
  },
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [
    // Storybook 10 split the old `addon-essentials` bundle. Controls,
    // actions, viewport, and backgrounds are built into core; docs and
    // a11y remain separate packages.
    "@storybook/addon-docs",
    "@storybook/addon-a11y",
  ],
  // Skip the TypeScript check that Storybook's own pipeline runs
  // separately — we already gate on `npm run typecheck` (tsc --noEmit)
  // in the parent app and don't need it duplicated on every story load.
  typescript: {
    check: false,
  },
};

export default config;
