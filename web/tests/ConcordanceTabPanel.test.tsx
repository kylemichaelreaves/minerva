import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import { ConcordanceTabPanel } from "~/Reader/components/ConcordanceTabPanel";
import { must } from "./helpers/must";

// #426. Solid **rethrows** when an errored resource is read, so a component
// that reads its resource outside an error guard throws out of the update the
// rejection triggered — abandoning it, freezing the DOM at whatever it last
// rendered, and escaping to a tree that mounts no ErrorBoundary.
//
// `Syntax/index.tsx:118-125` documents this exact mechanism and guards it, under
// #235. `TermCard` was given the same guard in #361's PR. This panel is the
// third and last `createResource` site, and it was the one still exposed:
//
//   :75  <Show when={data() && !data.error && …}>
//   :95  <Show when={data() && … && !data.loading}>
//
// Line 95 has no error check. Line 75's is in the **wrong order** — `&&`
// evaluates left to right, so `data()` is called, and throws, before
// `!data.error` is ever reached. A guard that reads as protection and cannot
// run is worse than no guard, because it stops the next reader looking.

let fetchMock: MockedFunction<typeof fetch>;

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

const INDEX = {
  rows: [
    { lemma: "λόγος", pos: "NOUN", count: 52, distinct_works: 1, per_work: [] },
    { lemma: "φύσις", pos: "NOUN", count: 31, distinct_works: 1, per_work: [] },
  ],
  total_lemmas: 2,
  total_tokens: 83,
  letter_counts: {},
};

function renderPanel() {
  const onOpenWorkScope = vi.fn();
  const onOpenLemma = vi.fn();
  const utils = render(() => (
    <ConcordanceTabPanel
      workTitle="Categories"
      lang="grc"
      onOpenWorkScope={onOpenWorkScope}
      onOpenLemma={onOpenLemma}
    />
  ));
  return { onOpenWorkScope, onOpenLemma, ...utils };
}

describe("<ConcordanceTabPanel />", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the work's top lemmas on a good fetch", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(INDEX));
    const { container } = renderPanel();
    await waitFor(() => {
      expect(container.querySelectorAll(".rail-concord-row").length).toBe(2);
    });
    expect(container.textContent).toMatch(/λόγος/);
    expect(container.querySelector(".rail-concord-loading")).toBeNull();
  });

  describe("when the lemma-index fetch fails (#426)", () => {
    const renderFailed = async () => {
      fetchMock.mockRejectedValueOnce(new Error("boom"));
      const utils = renderPanel();
      await waitFor(() => {
        expect(utils.container.querySelector(".rail-concord-empty")).not.toBeNull();
      });
      return utils;
    };

    it("reaches its error message, and stops showing the loading line", async () => {
      const { container } = await renderFailed();
      // The panel's error copy names the remedy — it is the whole value of
      // this branch, and it never rendered.
      expect(container.textContent).toMatch(/Lemma index unavailable/);
      expect(container.textContent).toMatch(/minerva terms lemmatize/);
      expect(container.querySelector(".rail-concord-loading")).toBeNull();
    });

    it("does not let the rejection escape the component", async () => {
      const onError = vi.fn();
      const onRejection = vi.fn();
      window.addEventListener("error", onError);
      window.addEventListener("unhandledrejection", onRejection);
      try {
        await renderFailed();
        await new Promise((r) => setTimeout(r, 50));
        expect(onError).not.toHaveBeenCalled();
        expect(onRejection).not.toHaveBeenCalled();
      } finally {
        window.removeEventListener("error", onError);
        window.removeEventListener("unhandledrejection", onRejection);
      }
    });

    it("renders no lemma rows and no empty-work message", async () => {
      // The "No content lemmas in this work" line is for a work that
      // genuinely has none. A failed fetch is not that, and must not claim it.
      const { container } = await renderFailed();
      expect(container.querySelectorAll(".rail-concord-row").length).toBe(0);
      expect(container.textContent).not.toMatch(/No content lemmas/);
    });

    it("keeps the CTA usable so the reader is not stranded", async () => {
      const { container, onOpenWorkScope } = await renderFailed();
      const cta = container.querySelector<HTMLButtonElement>(".rail-concord-cta");
      expect(cta).not.toBeNull();
      must(cta).click();
      expect(onOpenWorkScope).toHaveBeenCalledTimes(1);
    });
  });

  it("says so when the work genuinely has no content lemmas", async () => {
    // The other side of the branch above: an empty-but-successful response
    // must still reach the empty message.
    fetchMock.mockResolvedValueOnce(
      okResponse({ ...INDEX, rows: [], total_lemmas: 0, total_tokens: 0 }),
    );
    const { container } = renderPanel();
    await waitFor(() => {
      expect(container.textContent).toMatch(/No content lemmas in this work/);
    });
    expect(container.querySelectorAll(".rail-concord-row").length).toBe(0);
  });
});
