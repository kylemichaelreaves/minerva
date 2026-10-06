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
    // vmThreads builds each worker's environment once and runs every file
    // in a fresh VM context, so files stay isolated without paying for a
    // new happy-dom per file: vitest reported "happy-dom was created 157
    // times · 35.49s total, 35% of tracked time" on CI. The gain needs two
    // workers: at --maxWorkers=2, 22.4s → 15.6s, all 1589 tests passing,
    // coverage identical file by file; at one worker it is a wash (42.5s vs
    // 43.6s). vitest defaults to availableParallelism() - 1 workers, i.e.
    // ONE on CI's 2-vCPU runner, so check.yml passes --maxWorkers=2.
    // `isolate: false`, the other fix vitest suggests, is not safe here —
    // 37 and 46 tests failed on two runs, so files leak state into each other.
    pool: "vmThreads",
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
        // 5 points below measured totals, floored, to catch a real regression
        // without failing on noise. Measured 2026-10-06 (#762): lines 87.94,
        // statements 85.61, branches 73.68, functions 85.56. The previous
        // values (56/52/45/46, set at #12 in Jun 2026) had sat 26–39 points
        // below actual for months while this comment said ~5, so the gate
        // could not fail on any realistic drop. Re-pin when totals move.
        lines: 82,
        statements: 80,
        branches: 68,
        functions: 80,
      },
    },
  },
});
