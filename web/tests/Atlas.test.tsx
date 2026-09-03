import { describe, it, expect, vi } from "vitest";
import { render } from "@solidjs/testing-library";
import { Atlas } from "~/features/Landing/components/Atlas";
import type { LandingStats } from "~/api/landingApi";

// Found by the ErrorBoundary added for #426, which is the point of having one.
//
// `<Show when={props.stats}>` proves the stats OBJECT arrived; it says nothing
// about its fields. A 200 carrying a partial payload therefore reached
// `s().works.toLocaleString()` with `works` undefined and threw — taking the
// whole landing down, since the caption sits inside it.
//
// Worse, that failure was invisible before the boundary existed: the throw
// escaped mid-render and left the DOM frozen with everything *above* the
// caption still present. A test in PR #429 asserted on the scope chip, which
// renders above it, and passed over a crashed landing.

const FULL: LandingStats = { authors: 48, works: 866, xrefs: 54155 };

function renderAtlas(stats: LandingStats | null) {
  return render(() => (
    <Atlas onPickAuthor={vi.fn()} stats={stats} isMobile={() => false} />
  ));
}

describe("<Atlas /> corpus-fact caption", () => {
  it("renders all three numbers, thousands-separated, when the payload is complete", () => {
    const { container } = renderAtlas(FULL);
    const cap = container.querySelector(".landing-atlas-caption");
    expect(cap).not.toBeNull();
    expect(cap!.textContent).toMatch(/48\s*AUTHORS/);
    expect(cap!.textContent).toMatch(/866\s*WORKS/);
    // `toLocaleString` under the test locale — assert the grouping happened
    // rather than hard-coding a separator.
    expect(cap!.textContent).toMatch(/54[,.\s]?155/);
  });

  it("renders nothing at all when stats have not arrived", () => {
    const { container } = renderAtlas(null);
    const cap = container.querySelector(".landing-atlas-caption");
    expect(cap).not.toBeNull();
    expect(cap!.textContent.trim()).toBe("");
  });

  it.each([
    ["works", { authors: 48, xrefs: 54155 }],
    ["xrefs", { authors: 48, works: 866 }],
    ["authors", { works: 866, xrefs: 54155 }],
    ["every field", {}],
  ])("does not throw when %s is missing from the payload", (_label, partial) => {
    // The crash. Before the fix each of these threw
    // "Cannot read properties of undefined (reading 'toLocaleString')".
    expect(() => renderAtlas(partial as unknown as LandingStats)).not.toThrow();
  });

  it("shows an em dash for a missing number rather than blank or NaN", () => {
    const { container } = renderAtlas({ authors: 48 } as unknown as LandingStats);
    const cap = container.querySelector(".landing-atlas-caption")!;
    expect(cap.textContent).toMatch(/—\s*WORKS/);
    expect(cap.textContent).toMatch(/—\s*VERIFIED CROSS-REFERENCES/);
    // The field that IS present must still render its real value.
    expect(cap.textContent).toMatch(/48\s*AUTHORS/);
    expect(cap.textContent).not.toMatch(/NaN|undefined/);
  });
});
