import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { blankComments } from "./helpers/blankComments";

// Two properties about how the app builds navigations, checked against the
// source rather than against behaviour — because both failure modes are
// silent. A hand-built hash that has drifted from `readRoute` is a link that
// goes somewhere wrong, not a compile error; a route with no constructor is
// a screen nobody can reach, and it renders perfectly in isolation.
//
// Both are enforced here because both have already happened: the Reader built
// two concordance hashes by hand and one of them split work titles on a comma
// (#236), and the syntax overlay shipped with no way in at all (#232, #237).

const SRC = resolve(process.cwd(), "src");

/** Where route hashes are *supposed* to be built. Exempt from both rules. */
const ROUTING_PLUMBING = ["routing.ts", "routes/routeUtils.ts"];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(path));
    else if (/\.tsx?$/.test(entry.name) && !/\.stories\.tsx?$/.test(entry.name)) out.push(path);
  }
  return out;
}

// Comments are blanked, not stripped (#349). Both properties below are
// regexes over source text, and without this a **commented-out**
// constructor satisfies the reachability half — which is the state #232
// was filed on, one comment marker away. `blankComments` preserves every
// character position, so the `file:line` these guards report stays true.
//
// The blindness was one-directional and only the reachability half was
// unsafe: a commented-out hand-built hash made the drift half report a
// false positive, which fails loudly. Both are fixed here anyway, because
// a guard that reports a line nobody needs to fix trains people to ignore
// it.
const files = sourceFiles(SRC).map((path) => ({
  rel: relative(SRC, path),
  text: blankComments(readFileSync(path, "utf8")),
}));

const appFiles = files.filter((f) => !ROUTING_PLUMBING.includes(f.rel));

describe("the guards read code, not comments (#349)", () => {
  // Guards the guard. Both properties below are regexes over source text,
  // and the blanking that makes them comment-aware is one `.map` away from
  // being silently dropped in a refactor — at which point every case here
  // goes back to passing on commented-out source, which is how #232's
  // unreachable route stayed green.
  //
  // Verified by mutation as well as by this test: with
  // `syntaxChunkId: chunkId` commented out in `Reader/index.tsx`, the
  // modifier case below failed. Before the blanking it passed.
  const readerRaw = readFileSync(join(SRC, "Reader", "index.tsx"), "utf8");
  const readerBlanked = appFiles.find((f) => f.rel === join("Reader", "index.tsx"));

  it("blanks comment text out of the sources it scans", () => {
    expect(readerBlanked).toBeDefined();
    // A phrase that exists only inside a comment in the raw file.
    const commentOnly = "which is the failure the old peer route caused";
    expect(readerRaw).toContain(commentOnly);
    expect(readerBlanked!.text).not.toContain(commentOnly);
  });

  it("keeps every character position while doing it", () => {
    // The reported `file:line` is derived from a character offset, so a
    // transform that shifted anything would send readers to the wrong line.
    expect(readerBlanked!.text).toHaveLength(readerRaw.length);
    expect(readerBlanked!.text.split("\n")).toHaveLength(readerRaw.split("\n").length);
  });

  it("leaves live code intact", () => {
    // The constructor the modifier case depends on must survive blanking.
    expect(readerBlanked!.text).toContain("syntaxChunkId: chunkId,");
  });
});

describe("every hash assignment goes through routeHash", () => {
  // `routing.ts` owns both the construction and the parsing of every hash.
  // A second, hand-written copy of that format can drift from the parser
  // with nothing failing — and had: `#/concordance?...&work=` built by hand
  // single-encodes the title, `URLSearchParams.get` then hands a literal
  // comma to `decodeCsv`, and "Das Kapital, Band I" arrives as two scope
  // entries. Through `routeHash` the same title round-trips intact.
  const offenders: string[] = [];
  for (const { rel, text } of appFiles) {
    for (const m of text.matchAll(/window\.location\.hash\s*=\s*([\s\S]{0,40})/g)) {
      if (!m[1]?.includes("routeHash(")) {
        const line = text.slice(0, m.index).split("\n").length;
        offenders.push(`${rel}:${String(line)}`);
      }
    }
  }

  it("finds no hand-built hash outside the router", () => {
    expect(offenders).toEqual([]);
  });
});

describe("every route kind has a constructor outside the router", () => {
  // A route that parses and renders but that nothing navigates to is
  // reachable only by typing the hash. `#/syntax` shipped that way.
  //
  // Matched on the bare quoted kind, NOT on `kind: "x"`. The network
  // drilldowns pass theirs as an argument — `networkRouteFromFilters(
  // "network-arc", filters)` — so a `kind:`-shaped search reports them as
  // orphans when they are wired to the mobile network footer. That false
  // positive is what #232 was filed on.
  // Every kind named in routing.ts, however it is written — the union spells
  // some on their own line (`kind: "network-arc";`) and some inline
  // (`| { kind: "landing" }`), and `readRoute` repeats them all.
  // Blanked too (#349): a kind commented out of the union is not a route,
  // and demanding a constructor for it would fail this suite for a screen
  // that no longer exists. `kinds.length` is asserted below, so blanking
  // cannot quietly shrink what this checks either.
  const union = blankComments(readFileSync(join(SRC, "routing.ts"), "utf8"));
  const kinds = [...new Set([...union.matchAll(/kind: "([a-z-]+)"/g)].map((m) => m[1] ?? ""))];

  it("reads every kind out of the Route union", () => {
    // Guards the guard: a refactor that reshapes the union must not silently
    // reduce this suite to checking nothing.
    //
    // Ten, not eleven, since #342: "syntax" stopped being a kind and became
    // `syntaxChunkId` on the reader route, so the overlay has no route of its
    // own for this suite to hold to account. What replaces that check for it
    // is the modifier case below.
    expect(kinds).toContain("landing");
    expect(kinds).toContain("network-arc");
    expect(kinds.length).toBeGreaterThanOrEqual(10);
  });

  it("constructs the syntax layer modifier somewhere in the app", () => {
    // The syntax overlay is the screen this whole suite exists for: it shipped
    // reachable only by typing its hash (#232, #237). It is now a modifier
    // rather than a kind (#342), so `constructorsOf` cannot see it — and a
    // route field that nothing sets is the same unreachable screen, one
    // refactor later.
    //
    // Inside a navigation call, like every other case here, and NOT a bare
    // mention: the first draft of this looked for `syntaxChunkId:` anywhere in
    // a file, which `SyntaxLayer`'s `const { syntaxChunkId: _dropped, ...rest }`
    // satisfies — the line that CLEARS the modifier would have stood in for the
    // line that sets it, and the guard passed with the constructor commented
    // out. The window is wider than `constructorsOf`'s 240 because this
    // constructor spells the whole reader location out, one field per line.
    const setters: string[] = [];
    for (const { rel, text } of appFiles) {
      for (const m of text.matchAll(NAV)) {
        if (text.slice(m.index, m.index + 600).includes("syntaxChunkId")) setters.push(rel);
      }
    }
    expect(setters).not.toEqual([]);
  });

  // A *constructor*, not a mention. `App.tsx` compares against nearly every
  // kind to decide which chrome to render (`k === "network-arc"`), and
  // counting those is how a guard convinces itself an unreachable route is
  // reachable — it is why the first draft of this test passed while
  // `network-arc` had no navigation at all. So: the kind has to appear inside
  // a `navigate(` / `replace(` / `routeHash(` call.
  const NAV = /(?:navigate|replace|routeHash)\s*\(/g;

  const constructorsOf = (kind: string): string[] => {
    const found: string[] = [];
    for (const { rel, text } of appFiles) {
      for (const m of text.matchAll(NAV)) {
        // A window, not a parse: the longest of these calls is ~120 chars,
        // and a brace-matcher here would be more machinery than the property
        // is worth.
        if (text.slice(m.index, m.index + 240).includes(`"${kind}"`)) {
          found.push(`${rel}:${String(text.slice(0, m.index).split("\n").length)}`);
        }
      }
    }
    return found;
  };

  it("does not count a mere mention as a constructor", () => {
    // Pins the distinction the first draft got wrong. `App.tsx` names these
    // kinds without ever navigating to one.
    const appTsx = appFiles.find((f) => f.rel === "App.tsx");
    expect(appTsx?.text).toContain(`"network-arc"`);
    expect(constructorsOf("network-arc").some((w) => w.startsWith("App.tsx"))).toBe(false);
  });

  for (const kind of kinds) {
    it(`constructs ${kind} somewhere in the app`, () => {
      expect(constructorsOf(kind)).not.toEqual([]);
    });
  }
});
