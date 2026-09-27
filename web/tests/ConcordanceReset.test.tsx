// What "reset all" clears, and what the strip claims is resettable (#387).
//
// Reported from use: scope to an author, apply a filter, click "↺ reset all",
// and the filter clears while the author chip and the reset control both stay
// — so the button reads as not having worked. Measured on the live app:
//
//   before  ?lang=deu&scope=author&author=Hegel&pos=NOUN&q=geist
//           strip: "Active · 1  author Hegel×  200 lemmas shown  ↺ reset all"
//   after   ?lang=deu&scope=author&author=Hegel
//           strip: "Active · 1  author Hegel×  200 lemmas shown  ↺ reset all"
//
// Excluding scope from the reset is deliberate and documented
// (`LemmaDetail.tsx`: "Scope is the one knob we DON'T touch — narrowing scope
// is a directed action the user took at the F1 page"). The defect is that the
// set the strip DISPLAYS and the set the reset CLEARS were different sets
// sharing one count and one control: "1 filter applied", "reset all", and a
// chip that survives the reset cannot all be true.
//
// So scope comes out of the applied-filter set. Nothing is lost — scope keeps
// the `ScopePill` breadcrumb, the filter bar's own chips, and on the detail
// page the segmented Work/Author/Corpus bar.

import { fireEvent, render, waitFor } from "@solidjs/testing-library";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchLemmaIndex = vi.fn();
const listWorks = vi.fn();

vi.mock("~/api/readerApi", () => ({
  listWorks: (...args: unknown[]) => listWorks(...args) as never,
}));

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaIndex: (...args: unknown[]) => fetchLemmaIndex(...args) as never,
  };
});

import { ConcordanceIndexPage } from "~/Concordance/components/IndexPage";
import { must } from "./helpers/must";

const RESPONSE = {
  scope: "author",
  scope_label: "Hegel",
  lang: "deu",
  letter: null,
  sort: "freq",
  total_lemmas: 19391,
  total_occurrences: 261391,
  letter_counts: { G: 12 },
  limit: 200,
  offset: 0,
  next_offset: null,
  rows: [
    {
      rank: 1,
      lemma: "Geist",
      pos: "NOUN",
      count: 682,
      distinct_works: 2,
      per_work: [
        { work: "A", n: 400 },
        { work: "B", n: 282 },
      ],
    },
  ],
};

/** The strip only — not the filter bar, which has scope chips of its own. */
const stripChips = () =>
  Array.from(document.querySelectorAll(".afs .afs-pill")).map((e) =>
    e.textContent.replace(/\s+/g, " ").trim(),
  );

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  fetchLemmaIndex.mockResolvedValue(RESPONSE);
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
});

describe("concordance index — reset clears exactly what the strip shows (#387)", () => {
  it("keeps scope out of the strip, so its count describes resettable filters", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Hegel"]}
        pos="NOUN"
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));

    await waitFor(() => expect(stripChips().length).toBeGreaterThan(0));
    const chips = stripChips();

    // The POS filter is resettable and belongs here.
    expect(chips.some((c) => c.includes("noun"))).toBe(true);
    // The author is scope, which reset deliberately does not touch.
    expect(chips.some((c) => c.includes("Hegel"))).toBe(false);
  });

  it("leaves no chip behind after reset", async () => {
    // The reported symptom, stated as an invariant: whatever the strip shows,
    // reset clears. If the strip still has chips afterwards, the control lied.
    const onNavigate = vi.fn();
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Hegel"]}
        pos="NOUN"
        q="geist"
        onNavigate={onNavigate}
        onOpenLemma={vi.fn()}
      />
    ));

    await waitFor(() => expect(document.querySelector(".afs-reset")).not.toBeNull());
    fireEvent.click(must(document.querySelector(".afs-reset")));

    const patch = must(onNavigate.mock.calls.at(-1))[0] as Record<string, unknown>;
    // Every key the strip could have shown a chip for is cleared…
    expect(patch.pos).toBeUndefined();
    expect(patch.q).toBeUndefined();
    expect(patch.letter).toBeUndefined();
    expect(patch.freqMin).toBeUndefined();
    expect(patch.freqMax).toBeUndefined();
    // …and scope is untouched rather than cleared, per the documented policy.
    expect("scopeAuthors" in patch).toBe(false);
    expect("scope" in patch).toBe(false);
  });

  it("hides the strip entirely when only scope is set", async () => {
    // The state the reader was left staring at: no resettable filter, but a
    // strip saying "Active · 1" with a reset control that does nothing.
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Hegel"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));

    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    expect(document.querySelector(".afs")).toBeNull();
    expect(document.querySelector(".afs-reset")).toBeNull();
  });
});
