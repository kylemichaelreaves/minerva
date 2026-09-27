// @vitest-environment node
/** Every database the fixture server opens must live in the run's tmp dir.
 *
 * `startFixtureServer` routed `--db` and `--conversations-db` to tmp and left
 * three flags unpassed, so `minerva serve` fell back to its defaults under
 * `data/` — the operator's real databases. `metrics.sqlite` is written on
 * every request, so every e2e and browser run added rows to it; measured at
 * +449 across one session (#627).
 *
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import { serveArgs } from "../tests/helpers/fixtureServer";

describe("serveArgs", () => {
  const dirs = {
    port: 5555,
    indexDb: "/tmp/run/index.sqlite",
    convDb: "/tmp/run/conversations.sqlite",
    metricsDb: "/tmp/run/metrics.sqlite",
    translationsDb: "/tmp/run/translations.sqlite",
    conceptCacheDb: "/tmp/run/concepts.sqlite",
    staticDir: "/repo/web/dist",
  };

  it("routes every database flag somewhere other than data/", () => {
    const args = serveArgs(dirs);
    const flags = args.filter((a) => a.endsWith("-db") || a === "--db");
    expect(flags.sort()).toEqual([
      "--concept-cache-db",
      "--conversations-db",
      "--db",
      "--metrics-db",
      "--translations-db",
    ]);
  });

  it("gives each flag the tmp path it was handed", () => {
    const args = serveArgs(dirs);
    const valueOf = (flag: string) => args[args.indexOf(flag) + 1];
    expect(valueOf("--db")).toBe(dirs.indexDb);
    expect(valueOf("--conversations-db")).toBe(dirs.convDb);
    expect(valueOf("--metrics-db")).toBe(dirs.metricsDb);
    expect(valueOf("--translations-db")).toBe(dirs.translationsDb);
    expect(valueOf("--concept-cache-db")).toBe(dirs.conceptCacheDb);
  });

  it("never points a database at the repo's data/ directory", () => {
    // The specific failure: a flag omitted entirely means `serve` supplies a
    // data/-relative default, and nothing says so.
    const args = serveArgs(dirs);
    expect(args.some((a) => a.includes("/data/"))).toBe(false);
  });
});
