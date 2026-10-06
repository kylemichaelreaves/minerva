// @vitest-environment node
import { describe, expect, it } from "vitest";

// tests/setup.ts registers its unhandledRejection filter on `process`. Under
// `pool: "vmThreads"` every test file gets a fresh VM context but shares the
// worker's real `process`, so a registration that is never removed leaves one
// more listener behind per file (#775). Counted by name, so vitest's own
// listeners on the same event do not enter into it.
describe("tests/setup.ts unhandledRejection filter", () => {
  it("is registered exactly once, however many files this worker has run", () => {
    const ours = process
      .listeners("unhandledRejection")
      .filter((l) => l.name === "swallowApiRejection");
    expect(ours).toHaveLength(1);
  });
});
