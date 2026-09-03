import { describe, expect, it } from "vitest";
import { ESLint } from "eslint";

// The SFC-migration guard in `web/eslint.config.js` forbids new
// `hooks/*.ts` and `utils/*.ts` modules under a feature surface
// (docs/FRONTEND.md). It is enforced by a `files:` glob list, so it fails
// silently — a surface the globs do not name is simply not guarded, and the
// rule still reports zero errors. #477: four globs went dead when `Refs/`
// and `Landing/` moved under `features/`, and three more surfaces had never
// had one.
//
// These assertions read the resolved config rather than linting real files,
// so they hold for paths that do not exist yet — which is the whole point:
// the guard exists to stop such a file from being *added*.

// Vitest runs with `web/` as the cwd, which is where eslint.config.js sits.
const eslint = new ESLint({ cwd: process.cwd() });

// `calculateConfigForFile` is typed `Promise<any>` upstream; narrow it to the
// one field these assertions read rather than letting `any` spread.
interface ResolvedConfig {
  rules?: Record<string, unknown>;
}

/** Whether `no-restricted-syntax` resolves to an error for `relPath`. */
const isGuarded = async (relPath: string): Promise<boolean> => {
  const config = (await eslint.calculateConfigForFile(
    relPath,
  )) as ResolvedConfig;
  const entry = config.rules?.["no-restricted-syntax"];
  const severity: unknown = Array.isArray(entry) ? entry[0] : entry;
  return severity === 2 || severity === "error";
};

describe("the SFC-migration rule covers every feature surface", () => {
  // Every directory under src/ that holds a user-facing surface, whether it
  // sits at the top level or under features/. A new one added tomorrow is
  // covered by the same glob pair, which is why this list is the full set
  // rather than a sample.
  const surfaces = [
    "src/Reader",
    "src/Concordance",
    "src/Network",
    "src/Thread",
    "src/Syntax",
    "src/features/Refs",
    "src/features/Landing",
    "src/features/Composer",
    "src/features/conversations",
    "src/features/Sidebar",
  ];

  for (const surface of surfaces) {
    it(`guards ${surface}/hooks/*.ts`, async () => {
      expect(await isGuarded(`${surface}/hooks/useThing.ts`)).toBe(true);
    });

    it(`guards ${surface}/utils/*.ts`, async () => {
      expect(await isGuarded(`${surface}/utils/thing.ts`)).toBe(true);
    });
  }

  it("guards a surface nested deeper than one level", async () => {
    expect(await isGuarded("src/Syntax/components/hooks/useThing.ts")).toBe(
      true,
    );
  });
});

describe("the SFC-migration rule leaves the legitimate cases alone", () => {
  // src/hooks/ and src/utils/ are top-level shared infrastructure, not
  // feature subtrees — the convention puts shared helpers there on purpose.
  const allowed = [
    "src/hooks/useMobile.ts",
    "src/hooks/nested/deep.ts",
    "src/utils/renumber.ts",
    "src/utils/nested/deep.ts",
    // Syntax's own subtrees are named conllu/layout/corrections, which is
    // exactly why they clear the rule (docs/FRONTEND.md).
    "src/Syntax/layout/arcs.ts",
    "src/Syntax/corrections/pos.ts",
    "src/Syntax/conllu/parse.ts",
    "src/api/client.ts",
    "src/routes/routeUtils.ts",
  ];

  for (const path of allowed) {
    it(`leaves ${path} alone`, async () => {
      expect(await isGuarded(path)).toBe(false);
    });
  }

  it("leaves .tsx under a feature hooks/ dir alone — SFCs are the point", async () => {
    expect(await isGuarded("src/features/Refs/hooks/useThing.tsx")).toBe(false);
  });
});
