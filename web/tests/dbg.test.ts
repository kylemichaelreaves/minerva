import { describe, it, expect } from "vitest";
import { readRoute, routeHash } from "~/routing";

function withHash<T>(hash: string, fn: () => T): T {
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try { return fn(); } finally { window.history.replaceState(null, "", prev || "#"); }
}

describe("dbg", () => {
  it("comma in workId", () => {
    const workId = "Discourse on Method, and Meditations";
    const handBuilt = `#/concordance?lang=${encodeURIComponent("fra")}` +
      `&scope=work&work=${encodeURIComponent(workId)}`;
    const viaRouter = routeHash({ kind: "concordance", lang: "fra", scope: "work", scopeWorks: [workId] });
    console.log("HAND  ", handBuilt);
    console.log("ROUTER", viaRouter);
    console.log("HAND parsed  ", JSON.stringify(withHash(handBuilt, readRoute)));
    console.log("ROUTER parsed", JSON.stringify(withHash(viaRouter, readRoute)));
    expect(true).toBe(true);
  });
});
