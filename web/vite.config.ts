import { fileURLToPath, URL } from "node:url";
import { configDefaults, defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";

export default defineConfig({
  plugins: [solid()],
  resolve: {
    // `~/` resolves to `src/` so cross-directory imports stay stable
    // when files move. Picked up by vite (dev/build), vitest, and the
    // Storybook vite builder (which merges this config).
    alias: {
      "~": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  test: {
    // happy-dom, not jsdom: building the environment was ~60% of the run,
    // on the critical-path CI job (#687). Two files still ask for jsdom with
    // a `// @vitest-environment jsdom` docblock, because they stub jsdom's own
    // internals (Element.prototype.clientWidth, document.fonts). Files that
    // touch no DOM at all say `// @vitest-environment node` and skip building
    // one. tests/setup.ts keeps happy-dom's fetch off the network.
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    // Playwright specs are `*.spec.ts`, which vitest's default glob collects
    // as readily as `*.test.ts`. Without this they run under vitest's node
    // environment and fail on an import they cannot resolve. Spread the
    // defaults rather than replacing them — assigning a bare array drops
    // vitest's own node_modules/dist exclusions.
    exclude: [...configDefaults.exclude, "tests/browser/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "json-summary"],
      // Skip non-source dirs (config, storybook glue) and exclude
      // tests themselves from the coverage source — coverage is about
      // production code, not the test files measuring it.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/**/*.stories.{ts,tsx}",
        "src/main.tsx", // bootstrap entry
        "tests/**",
      ],
      thresholds: {
        // Baseline from the orchestration-layer test pass (Jun 2026).
        // Kept ~5 points below measured totals to catch regressions
        // without blocking incremental coverage work on routes/ingest.
        lines: 56,
        statements: 52,
        branches: 45,
        functions: 46,
      },
    },
  },
});
