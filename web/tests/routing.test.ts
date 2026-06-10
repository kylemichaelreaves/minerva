import { describe, it, expect, vi } from "vitest";
import { createRoot } from "solid-js";
import { readRoute, routeHash, useRouting, type Route } from "~/routing";

function withHash<T>(hash: string, fn: () => T): T {
  // jsdom carries `window.location.hash` between tests when set with a
  // direct assignment; switch via history.replaceState so the URL bar
  // is stable and don't leak across cases. The trailing "" preserves
  // pathname so node-url doesn't choke on an empty href.
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try {
    return fn();
  } finally {
    window.history.replaceState(null, "", prev || "#");
  }
}

describe("readRoute", () => {
  it("returns landing for empty hash", () => {
    expect(withHash("", readRoute)).toEqual({ kind: "landing" });
    expect(withHash("#/", readRoute)).toEqual({ kind: "landing" });
  });

  it("parses conversation route", () => {
    expect(withHash("#/c/abc-123", readRoute)).toEqual({
      kind: "conversation",
      id: "abc-123",
    });
  });

  it("URL-decodes the conversation id", () => {
    // Encoded characters in the id must round-trip back to the
    // original — needed for spaces, plus signs, etc.
    expect(withHash("#/c/foo%20bar", readRoute)).toEqual({
      kind: "conversation",
      id: "foo bar",
    });
  });

  it("parses reader route with lang and focus", () => {
    expect(
      withHash("#/r/Republic?lang=grc&focus=rep-509d", readRoute),
    ).toEqual({
      kind: "reader",
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
      openTermId: undefined,
    });
  });

  it("parses reader route with a valid term=", () => {
    const route = withHash("#/r/Republic?term=42", readRoute);
    expect(route.kind).toBe("reader");
    if (route.kind === "reader") {
      expect(route.openTermId).toBe(42);
    }
  });

  it("ignores a non-integer term= defensively", () => {
    // A stale bookmark or extension shouldn't crash the reader; the
    // expected behavior is just "no card opens on first paint."
    const route = withHash("#/r/Republic?term=abc", readRoute);
    expect(route.kind).toBe("reader");
    if (route.kind === "reader") {
      expect(route.openTermId).toBeUndefined();
    }
  });

  it("parses refs route with all filters", () => {
    expect(
      withHash(
        "#/refs?source=Aquinas&target=Aristotle&work=Metaphysics&type=cites&include_rejected=1",
        readRoute,
      ),
    ).toEqual({
      kind: "refs",
      sourceAuthor: "Aquinas",
      targetAuthor: "Aristotle",
      targetWork: "Metaphysics",
      referenceType: "cites",
      includeRejected: true,
    });
  });

  it("treats absent include_rejected as false", () => {
    const route = withHash("#/refs?source=Aquinas", readRoute);
    expect(route.kind).toBe("refs");
    if (route.kind === "refs") {
      expect(route.includeRejected).toBe(false);
    }
  });

  it("parses refs-review route", () => {
    expect(withHash("#/refs/review?source=Aquinas&type=quotes", readRoute)).toEqual({
      kind: "refs-review",
      sourceAuthor: "Aquinas",
      referenceType: "quotes",
    });
  });

  it("refs/review without query is still refs-review, not refs", () => {
    // The two regexes overlap on the prefix; review must win to keep
    // the curator queue reachable without filters.
    expect(withHash("#/refs/review", readRoute)).toEqual({
      kind: "refs-review",
      sourceAuthor: undefined,
      referenceType: undefined,
    });
  });

  it("falls back to landing on a malformed conversation id", () => {
    // A truncated percent-escape makes decodeURIComponent throw
    // URIError; the router must swallow it instead of blank-screening.
    expect(withHash("#/c/100%", readRoute)).toEqual({ kind: "landing" });
  });

  it("falls back to landing on a malformed reader workId", () => {
    expect(withHash("#/r/100%", readRoute)).toEqual({ kind: "landing" });
  });

  it("falls back to landing on a malformed concordance lemma", () => {
    expect(withHash("#/concordance/100%", readRoute)).toEqual({
      kind: "landing",
    });
  });
});

describe("routeHash", () => {
  it("landing serializes to #/", () => {
    expect(routeHash({ kind: "landing" })).toBe("#/");
  });

  it("encodes conversation id", () => {
    expect(routeHash({ kind: "conversation", id: "foo bar" })).toBe(
      "#/c/foo%20bar",
    );
  });

  it("reader omits absent optional params", () => {
    expect(routeHash({ kind: "reader", workId: "Republic" })).toBe(
      "#/r/Republic",
    );
  });

  it("reader includes term=", () => {
    expect(
      routeHash({
        kind: "reader",
        workId: "Republic",
        sourceLang: "grc",
        openTermId: 7,
      }),
    ).toBe("#/r/Republic?lang=grc&term=7");
  });

  it("refs serializes filters in deterministic order", () => {
    expect(
      routeHash({
        kind: "refs",
        sourceAuthor: "Aquinas",
        targetAuthor: "Aristotle",
        referenceType: "cites",
        includeRejected: true,
      }),
    ).toBe("#/refs?source=Aquinas&target=Aristotle&type=cites&include_rejected=1");
  });

  it("refs with no filters is bare", () => {
    expect(routeHash({ kind: "refs" })).toBe("#/refs");
  });

  it("refs-review with filters", () => {
    expect(
      routeHash({
        kind: "refs-review",
        sourceAuthor: "Aquinas",
        referenceType: "quotes",
      }),
    ).toBe("#/refs/review?source=Aquinas&type=quotes");
  });
});

describe("round-trip", () => {
  // Each case: a Route → routeHash → readRoute → must equal original.
  // The reader case carries openTermId=undefined explicitly because
  // readRoute always sets that field (vs the input shape which may
  // omit it); use the readRoute output to normalize.
  const cases: Route[] = [
    { kind: "landing" },
    { kind: "conversation", id: "abc-123" },
    {
      kind: "reader",
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
      openTermId: 42,
    },
    {
      kind: "refs",
      sourceAuthor: "Aquinas",
      referenceType: "quotes",
      includeRejected: true,
    },
    {
      kind: "refs-review",
      sourceAuthor: "Augustine",
    },
  ];

  for (const route of cases) {
    it(`round-trips ${route.kind}`, () => {
      const hash = routeHash(route);
      const parsed = withHash(hash, readRoute);
      // For the reader case, the readRoute output normalizes
      // openTermId to `undefined` when missing — accept that.
      expect(parsed).toMatchObject(route);
    });
  }
});

describe("useRouting history discipline", () => {
  it("canonicalizes a malformed hash on load via replaceState, never push", () => {
    withHash("#/c/100%", () => {
      const pushSpy = vi.spyOn(window.history, "pushState");
      const replaceSpy = vi.spyOn(window.history, "replaceState");
      try {
        createRoot((dispose) => {
          const routing = useRouting();
          expect(routing.route()).toEqual({ kind: "landing" });
          // The address bar is rewritten to the canonical form without
          // adding a history entry — back still leaves the app.
          expect(window.location.hash).toBe("#/");
          expect(replaceSpy).toHaveBeenCalledTimes(1);
          expect(pushSpy).not.toHaveBeenCalled();
          dispose();
        });
      } finally {
        pushSpy.mockRestore();
        replaceSpy.mockRestore();
      }
    });
  });

  it("canonicalizes a non-canonical but parseable hash on load", () => {
    // `id=abc` is dropped by the defensive integer parse; the URL
    // should be rewritten to the serialized form of what we parsed.
    withHash("#/refs/review?id=abc", () => {
      const pushSpy = vi.spyOn(window.history, "pushState");
      try {
        createRoot((dispose) => {
          const routing = useRouting();
          expect(routing.route()).toMatchObject({ kind: "refs-review" });
          expect(window.location.hash).toBe("#/refs/review");
          expect(pushSpy).not.toHaveBeenCalled();
          dispose();
        });
      } finally {
        pushSpy.mockRestore();
      }
    });
  });

  it("leaves a canonical hash alone on load", () => {
    withHash("#/refs", () => {
      const replaceSpy = vi.spyOn(window.history, "replaceState");
      try {
        createRoot((dispose) => {
          useRouting();
          expect(replaceSpy).not.toHaveBeenCalled();
          dispose();
        });
      } finally {
        replaceSpy.mockRestore();
      }
    });
  });

  it("navigate pushes exactly one entry and skips redundant pushes", () => {
    withHash("#/", () => {
      const pushSpy = vi.spyOn(window.history, "pushState");
      try {
        createRoot((dispose) => {
          const routing = useRouting();
          routing.navigate({ kind: "refs" });
          expect(window.location.hash).toBe("#/refs");
          expect(pushSpy).toHaveBeenCalledTimes(1);
          // Navigating to the same route again must not stack another
          // history entry (the old effect-driven writer was guarded the
          // same way; keep the invariant).
          routing.navigate({ kind: "refs" });
          expect(pushSpy).toHaveBeenCalledTimes(1);
          dispose();
        });
      } finally {
        pushSpy.mockRestore();
      }
    });
  });

  it("replace rewrites the entry without pushing", () => {
    withHash("#/refs/review", () => {
      const pushSpy = vi.spyOn(window.history, "pushState");
      const replaceSpy = vi.spyOn(window.history, "replaceState");
      try {
        createRoot((dispose) => {
          const routing = useRouting();
          replaceSpy.mockClear();
          routing.replace({ kind: "refs-review", referenceId: 7 });
          expect(window.location.hash).toBe("#/refs/review?id=7");
          expect(replaceSpy).toHaveBeenCalledTimes(1);
          expect(pushSpy).not.toHaveBeenCalled();
          dispose();
        });
      } finally {
        pushSpy.mockRestore();
        replaceSpy.mockRestore();
      }
    });
  });

  it("popstate reads the route into the signal without writing history", async () => {
    await withHash("#/refs", async () => {
      await createRoot(async (dispose) => {
        const routing = useRouting();
        // onMount's popstate listener registers on the next effect
        // flush — wait a tick before dispatching.
        await Promise.resolve();
        // Simulate the browser restoring a different entry (back).
        window.history.replaceState(null, "", "#/network");
        const pushSpy = vi.spyOn(window.history, "pushState");
        const replaceSpy = vi.spyOn(window.history, "replaceState");
        try {
          window.dispatchEvent(new PopStateEvent("popstate"));
          expect(routing.route()).toMatchObject({ kind: "network" });
          // No write-back: a pushState here is exactly the back-button
          // trap this regression test pins.
          expect(pushSpy).not.toHaveBeenCalled();
          expect(replaceSpy).not.toHaveBeenCalled();
        } finally {
          pushSpy.mockRestore();
          replaceSpy.mockRestore();
        }
        dispose();
        // withHash's finally already ran (the async body resumes after
        // it); restore the hash ourselves so nothing leaks.
        window.history.replaceState(null, "", "#/");
      });
    });
  });
});
