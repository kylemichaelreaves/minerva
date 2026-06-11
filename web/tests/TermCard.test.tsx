import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import TermCard from "~/components/TermCard";

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
    const input = fetchMock.mock.calls[0]![0];
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL ? input.href : input.url;
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
          id: 10, translation_id: 89, translator_name: "Pinkard", year: 2018,
          language: "eng", work_title: "Phenomenology of Spirit (Pinkard)",
          default_rendering: "spirit", translator_note: null,
        },
        {
          id: 11, translation_id: 90, translator_name: "Inwood", year: 2018,
          language: "eng", work_title: "Phenomenology of Spirit (Inwood)",
          default_rendering: "spirit", translator_note: null,
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
});
