// @vitest-environment node
import { describe, expect, it } from "vitest";
import { ESLint } from "eslint";
import { execFileSync } from "node:child_process";

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
  languageOptions?: {
    parserOptions?: {
      project?: string | string[] | boolean;
    };
  };
}

/** Whether `no-restricted-syntax` resolves to an error for `relPath`. */
const isGuarded = async (relPath: string): Promise<boolean> => {
  const config = (await eslint.calculateConfigForFile(relPath)) as ResolvedConfig;
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
    expect(await isGuarded("src/Syntax/components/hooks/useThing.ts")).toBe(true);
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

describe("every tracked TypeScript file gets the type information its rules need", () => {
  // `tseslint.configs.strictTypeChecked` is spread with no `files:` key, so
  // its type-aware rules apply to every file ESLint visits — but
  // `parserOptions.project` is set only inside a scoped block. A file caught
  // by the first and missed by the second does not produce a lint error; it
  // kills the whole run at rule-load time and reports nothing, so a caller
  // cannot tell "clean" from "never ran" (#480).
  //
  // Driven off `git ls-files` rather than a hand-written list, because an
  // enumeration is the thing that goes stale — the defect #477 fixed one
  // file over.
  const tracked = execFileSync("git", ["ls-files", "*.ts", "*.tsx"], {
    cwd: process.cwd(),
    encoding: "utf8",
  })
    .split("\n")
    .filter(Boolean);

  it("finds tracked files at all, so an empty sweep cannot pass vacuously", () => {
    expect(tracked.length).toBeGreaterThan(100);
  });

  it("leaves no tracked file with typed rules but no project", async () => {
    const orphans: string[] = [];
    for (const file of tracked) {
      if (await eslint.isPathIgnored(file)) continue;
      const config = (await eslint.calculateConfigForFile(file)) as ResolvedConfig;
      if (config.languageOptions?.parserOptions?.project === undefined) {
        orphans.push(file);
      }
    }
    expect(orphans).toEqual([]);
  });

  it("ignores generated output instead of trying to lint it", async () => {
    // `coverage/` is written by `npm run test:coverage`, which `make check`
    // runs — so a bare `eslint .` met it before `ignores` covered it.
    expect(await eslint.isPathIgnored("coverage/lcov-report/block-navigation.js")).toBe(true);
    expect(await eslint.isPathIgnored("dist/assets/index.js")).toBe(true);
  });

  it("really lints .storybook — a dot-dir needs an explicit tsconfig glob", async () => {
    // `include: [".storybook"]` is a no-op: TypeScript drops directories
    // beginning with `.` when it expands `include`, so the entry matches
    // nothing and these files stay out of the program. ESLint then reports
    // `"parserOptions.project" has been provided … The file was not found in
    // any of the provided project(s)` — which reads as an ESLint problem
    // rather than a glob that quietly matched zero files. Only linting the
    // file for real catches that; resolving its config does not.
    const results = await eslint.lintFiles([".storybook/preview.tsx"]);
    const blocking = results
      .flatMap((r) => r.messages)
      .filter((m) => m.fatal === true || m.ruleId === null)
      .map((m) => m.message);
    expect(blocking).toEqual([]);
    // Unlike every other assertion here, this one lints for real rather than
    // resolving config, so it builds a TypeScript program. That costs a few
    // seconds on its own and more when vitest is running 98 other files
    // alongside it — it timed out at the 5s default on a loaded machine and
    // passed on the next run, which is the worst way for a test to behave.
  }, 60_000);
});
