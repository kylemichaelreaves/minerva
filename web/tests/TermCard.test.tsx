import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import TermCard from "~/components/cards/TermCard";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

const SAMPLE_TERM = {
  id: 4,
  source_form: "λόγος",
  source_language: "grc",
  transliteration: "logos",
  lemma: "λόγος",
  short_gloss: "account · definition · reason · speech",
  long_description: "Aristotle's term for…",
  renderings: [
    {
      id: 1,
      translation_id: 58,
      translator_name: "E. M. Edghill",
      year: null,
      language: "eng",
      work_title: "Categories",
      default_rendering: "account",
      translator_note: "Edghill renders λόγος as 'account'…",
    },
  ],
  occurrences_by_edition: [
    {
      edition_id: 58,
      name: "Bekker",
      language: "grc",
      is_canonical: 1,
      work_title: "Categories",
      occurrences: 52,
    },
  ],
  related: [],
};

function fakeRect(): DOMRect {
  return new DOMRect(80, 100, 80, 20);
}

describe("<TermCard />", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches and renders the term card on mount", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(SAMPLE_TERM));
    const { container } = render(() => (
      <TermCard termId={4} anchor={fakeRect()} onClose={() => undefined} />
    ));
    // Initially loading.
    expect(container.querySelector(".termcard-loading")).not.toBeNull();
    // Resource resolves; lemma appears.
    await waitFor(() => {
      expect(container.querySelector(".termcard-lemma")?.textContent).toBe("λόγος");
    });
    // Loading state cleared.
    expect(container.querySelector(".termcard-loading")).toBeNull();
    // One rendering → flat one-liner, not the cross-translator grid.
    expect(container.querySelector(".termcard-renderings")).toBeNull();
    const single = container.querySelector(".termcard-single-rendering");
    expect(single).not.toBeNull();
    expect(single?.textContent).toMatch(/E\. M\. Edghill/);
    expect(single?.textContent).toMatch(/account/);
    // Occurrence count surfaces.
    expect(container.textContent).toMatch(/Appears\s*52\s*times/);
    // Fetched the right endpoint. `input` is always a string in our
    // client (the fetch helper builds the URL inline) so narrow
    // explicitly rather than coercing through String().
    const input = must(fetchMock.mock.calls[0])[0];
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    expect(url).toBe("/api/terms/4");
  });

  it("hides the renderings section entirely when no translator has a rendering", async () => {
    // Kant KrV case: German term, no English translation loaded.
    const kantTerm = {
      ...SAMPLE_TERM,
      id: 11,
      source_form: "Anschauung",
      source_language: "deu",
      transliteration: null,
      lemma: "Anschauung",
      short_gloss: "intuition",
      renderings: [],
    };
    fetchMock.mockResolvedValueOnce(okResponse(kantTerm));
    const { container } = render(() => (
      <TermCard termId={11} anchor={fakeRect()} onClose={() => undefined} />
    ));
    await waitFor(() => {
      expect(container.querySelector(".termcard-lemma")?.textContent).toBe("Anschauung");
    });
    // Both layouts absent.
    expect(container.querySelector(".termcard-single-rendering")).toBeNull();
    expect(container.querySelector(".termcard-renderings")).toBeNull();
    // Gloss + occurrence count still surface.
    expect(container.querySelector(".termcard-gloss")?.textContent).toBe("intuition");
  });

  it("renders the cross-translator grid for 2+ renderings", async () => {
    const phgTerm = {
      ...SAMPLE_TERM,
      id: 12,
      source_form: "Geist",
      source_language: "deu",
      lemma: "Geist",
      short_gloss: "spirit; mind",
      renderings: [
        {
          id: 10,
          translation_id: 89,
          translator_name: "Pinkard",
          year: 2018,
          language: "eng",
          work_title: "Phenomenology of Spirit (Pinkard)",
          default_rendering: "spirit",
          translator_note: null,
        },
        {
          id: 11,
          translation_id: 90,
          translator_name: "Inwood",
          year: 2018,
          language: "eng",
          work_title: "Phenomenology of Spirit (Inwood)",
          default_rendering: "spirit",
          translator_note: null,
        },
      ],
    };
    fetchMock.mockResolvedValueOnce(okResponse(phgTerm));
    const { container } = render(() => (
      <TermCard termId={12} anchor={fakeRect()} onClose={() => undefined} />
    ));
    await waitFor(() => {
      expect(container.querySelector(".termcard-lemma")?.textContent).toBe("Geist");
    });
    expect(container.querySelector(".termcard-single-rendering")).toBeNull();
    expect(container.querySelector(".termcard-renderings")).not.toBeNull();
    const whos = container.querySelectorAll(".termcard-who");
    expect(Array.from(whos, (w) => w.textContent)).toEqual(["Pinkard", "Inwood"]);
  });
  describe("the load-error state (#361)", () => {
    // #358 gave `PopoverCard` an unconditional `×`, which subsumed the
    // recovery affordance `.termcard-close` was written to be back when the
    // shell had no close control at all. In the error state the card then
    // showed two controls doing the same thing — both calling `onClose()`
    // with no other effect — and `useDialogFocus` trapped Tab between them.
    //
    // That was true of the SOURCE and never of the running card, which is
    // #361's correction: the error branch was unreachable. Solid rethrows a
    // rejection when the errored resource is read, so the sibling
    // `<Show when={term()}>` threw inside the update the rejection
    // triggered, aborting it. Measured before the fix: `.termcard-error`
    // absent, `.termcard-loading` still mounted, one button, and an uncaught
    // "boom" escaping the render.
    //
    // The first test below is therefore the one that matters most — it is
    // the reachability regression guard, and it failed before this change
    // for a completely different reason than the duplicate control.
    const renderFailed = async () => {
      fetchMock.mockRejectedValueOnce(new Error("boom"));
      const onClose = vi.fn();
      const { container } = render(() => (
        <TermCard termId={9} anchor={fakeRect()} onClose={onClose} />
      ));
      await waitFor(() => {
        expect(container.querySelector(".termcard-error")).not.toBeNull();
      });
      return { container, onClose };
    };

    it("reaches the error state at all, and stops showing Loading…", async () => {
      const { container } = await renderFailed();
      expect(container.querySelector(".termcard-error")?.textContent).toMatch(
        /Could not load this term/,
      );
      // The stuck-spinner half. Before the fix this stayed mounted forever,
      // so a reader whose fetch failed saw "Loading…" and nothing else.
      expect(container.querySelector(".termcard-loading")).toBeNull();
    });

    it("does not let the rejection escape the component", async () => {
      // The uncaught error was the other half of the same defect, and the
      // app mounts no ErrorBoundary to catch it.
      const onError = vi.fn();
      window.addEventListener("error", onError);
      const onRejection = vi.fn();
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

    it("offers exactly one dismiss control", async () => {
      const { container } = await renderFailed();
      // Every button inside the card, error state included. The shell's `×`
      // is the only one that should be here.
      const buttons = Array.from(container.querySelectorAll("button"));
      expect(buttons).toHaveLength(1);
      expect(must(buttons[0]).className).toContain("popover-close");
      expect(must(buttons[0]).getAttribute("aria-label")).toBe("Close");
    });

    it("no longer renders the redundant Dismiss button", async () => {
      const { container } = await renderFailed();
      expect(container.querySelector(".termcard-close")).toBeNull();
      expect(container.textContent).not.toMatch(/Dismiss/);
    });

    it("dismisses through the shell control", async () => {
      const { container, onClose } = await renderFailed();
      const close = container.querySelector<HTMLButtonElement>(".popover-close");
      expect(close).not.toBeNull();
      must(close).click();
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
