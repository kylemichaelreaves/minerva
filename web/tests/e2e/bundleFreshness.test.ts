// The harness serves `web/dist`, so it must own building it (#610).
//
// It already owns the *index* build — `startFixtureServer` runs `minerva
// index` before booting so no suite can be measured against a stale
// database. The bundle had no such guarantee: the build lived in the
// caller (`make test-browser`, and a workflow step in CI), so every other
// entry point — `npx playwright test`, which is what you run when
// iterating on one spec — served whatever bundle happened to be on disk.
// On a branch that changed the frontend, that is the previous branch's
// build.
//
// @vitest-environment node

import { describe, it, expect, afterAll } from "vitest";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { hasMinervaBin, startFixtureServer, type FixtureServer } from "../helpers/fixtureServer";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const DIST_INDEX = join(REPO_ROOT, "web/dist/index.html");
const SENTINEL = "<!-- stale bundle from a previous branch -->";

const describeOrSkip = hasMinervaBin() ? describe : describe.skip;

describeOrSkip("the fixture server rebuilds the bundle it serves", () => {
  let server: FixtureServer | undefined;

  afterAll(() => {
    server?.stop();
  });

  it("replaces a stale web/dist instead of serving it", async () => {
    // Stand in for "the previous branch's build": a dist that exists and is
    // served happily, but was not produced from the current source.
    mkdirSync(dirname(DIST_INDEX), { recursive: true });
    writeFileSync(DIST_INDEX, SENTINEL);
    expect(readFileSync(DIST_INDEX, "utf8")).toContain(SENTINEL);

    server = await startFixtureServer();
    const body = await (await fetch(`${server.baseUrl}/`)).text();

    expect(existsSync(DIST_INDEX)).toBe(true);
    expect(body).not.toContain(SENTINEL);
    expect(body).toContain("<script");
  }, 120_000);
});
