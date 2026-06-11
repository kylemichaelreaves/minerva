import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, fireEvent, waitFor } from "@solidjs/testing-library";
import Reader from "~/Reader";
import { MobileShellProvider } from "~/components/MobileShellContext";
import type { JSX } from "solid-js";

function renderReader(ui: () => JSX.Element) {
  return render(() => <MobileShellProvider>{ui()}</MobileShellProvider>);
}

let fetchMock: MockedFunction<typeof fetch>;

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

const SAMPLE_RANGE = {
  // `work_id` is the integer surrogate the reader uses to call
  // /api/works/:work_id/occurrence_map. Real responses always carry
  // it; mocks here include it so the parallel occurrence-map fetch
  // hits a real URL even if the test doesn't otherwise care.
  work_id: 999,
  corpus: "plato",
  author: "Plato",
  work: "Republic",
  lang: "grc",
  total: 2,
  offset: 0,
  limit: 200,
  chunks: [
    {
      chunk_id: "r-1",
      section: "509d",
      book: "6",
      page: null,
      speaker: null,
      text: "τοῦ πατρός",
      ord: 0,
    },
    {
      chunk_id: "r-2",
      section: "510a",
      book: "6",
      page: null,
      speaker: null,
      text: "τοῦ υἱοῦ",
      ord: 1,
    },
  ],
};

describe("<Reader />", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    // Default: an unmocked URL returns a benign 404. The Reader mounts
    // parallel fetches (work range, occurrence map, ConcordanceTabPanel
    // mini-leaderboard) — only the assertions exercising each call
    // bother with `.mockResolvedValueOnce`. Without a baseline the
    // ConcordanceTabPanel resource sees `undefined` and emits an
    // unhandled rejection vitest flags.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not mocked",
      json: () => Promise.resolve({}),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches the work range on mount and renders lines with section labels", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(SAMPLE_RANGE));
    const { container } = renderReader(() => <Reader workId="Republic" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelectorAll(".line").length).toBe(2);
    });
    expect(container.querySelectorAll(".line .num")[0]!.textContent).toBe("509d");
    expect(container.querySelectorAll(".line .num")[1]!.textContent).toBe("510a");
    // Greek chunks are tokenized into per-word .gw spans inside
    // HoverTips. Reading the line's textContent would pick up the
    // hidden tooltip bodies too, so assert against the visible word
    // spans directly. Each .gw also carries a sibling tooltip whose
    // .hovertip-text holds the romanization.
    const lines = container.querySelectorAll(".line");
    const words = lines[0]!.querySelectorAll(".gw");
    expect(Array.from(words, (w) => w.textContent)).toEqual(["τοῦ", "πατρός"]);
    const tips = lines[0]!.querySelectorAll(".hovertip-text");
    expect(Array.from(tips, (t) => t.textContent)).toEqual(["tou", "patros"]);
    // 'Plato' appears in both the chrome and the head — check via byline.
    expect(container.querySelector(".byline")?.textContent).toContain("Plato");
  });

  it("language pill defaults to EN active and switches on click", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(SAMPLE_RANGE));
    const { container } = renderReader(() => <Reader workId="Republic" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelectorAll(".line").length).toBe(2);
    });
    const buttons = container.querySelectorAll(".lang button");
    expect(buttons[0]!.classList.contains("on")).toBe(true);
    fireEvent.click(buttons[1]!); // FR
    expect(buttons[1]!.classList.contains("on")).toBe(true);
    expect(buttons[0]!.classList.contains("on")).toBe(false);
  });

  it("does not render the right rail until a translation is requested", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(SAMPLE_RANGE));
    const { container } = renderReader(() => <Reader workId="Republic" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelectorAll(".line").length).toBe(2);
    });
    // The .rail element is always mounted now (so the close
    // transition can play); `.open` is the user-visible signal.
    expect(container.querySelector(".rail.open")).toBeNull();
  });

  it("renders an error message when the work range request fails", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404 } as unknown as Response);
    const { container } = renderReader(() => <Reader workId="Nope" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.textContent).toMatch(/Could not load the source/);
    });
  });

  it("passes the correct source-language query string", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({ ...SAMPLE_RANGE, lang: "deu", work: "Phänomenologie" }),
    );
    renderReader(() => <Reader workId="Phänomenologie" sourceLang="deu" />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/lang=de/);
    expect(decodeURIComponent(url)).toContain("Phänomenologie");
  });

  it("renders .term-mark for words inside a term occurrence span", async () => {
    // Chunk text "ὁμώνυμα λόγος" → ὁμώνυμα is positions 0..7,
    // λόγος is positions 8..13. Occurrence map flags the first
    // word only; the second word should still render as a .gw word
    // with a romanization HoverTip.
    const chunkText = "ὁμώνυμα λόγος";
    const range = {
      ...SAMPLE_RANGE,
      work_id: 91,
      chunks: [
        {
          chunk_id: "cat-1",
          section: "1.¶1",
          book: null,
          page: null,
          speaker: null,
          text: chunkText,
          ord: 0,
        },
      ],
      total: 1,
    };
    const occMap = {
      work_id: 91,
      lang: "grc",
      from: 0,
      limit: 200,
      by_chunk: {
        "cat-1": [
          {
            id: 1,
            term_id: 7,
            source_start: 0,
            source_end: 7,
            source_form: "ὁμώνυμα",
            lemma: "ὁμώνυμα",
            transliteration: "homonyma",
            short_gloss: "homonyms",
          },
        ],
      },
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      // `input` from the production fetch helpers is always a string;
      // narrow defensively without going through Object.toString.
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (url.includes("/occurrence_map")) return Promise.resolve(okResponse(occMap));
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => <Reader workId="Categories" sourceLang="grc" />);
    await waitFor(() => {
      // .term-mark only appears once the occurrence_map fetch resolves
      // and the Reader re-renders. Wait for the marker.
      expect(container.querySelector(".term-mark")).not.toBeNull();
    });
    const marks = container.querySelectorAll(".term-mark");
    expect(Array.from(marks, (m) => m.textContent)).toEqual(["ὁμώνυμα"]);
    expect(marks[0]!.getAttribute("data-term-id")).toBe("7");
    // The second word stays as an ordinary .gw with its romanization.
    const greekWords = container.querySelectorAll(".gw");
    expect(Array.from(greekWords, (w) => w.textContent)).toEqual(["λόγος"]);
  });

  it("opens the TermCard on .term-mark click", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 91,
      chunks: [
        { chunk_id: "cat-1", section: "1.¶1", book: null, page: null,
          speaker: null, text: "ὁμώνυμα λόγος", ord: 0 },
      ],
      total: 1,
    };
    const occMap = {
      work_id: 91, lang: "grc", from: 0, limit: 200,
      by_chunk: { "cat-1": [
        { id: 1, term_id: 7, source_start: 0, source_end: 7,
          source_form: "ὁμώνυμα", lemma: "ὁμώνυμα",
          transliteration: "homonyma", short_gloss: "homonyms" },
      ] },
    };
    const termDetail = {
      id: 7,
      source_form: "ὁμώνυμα",
      source_language: "grc",
      transliteration: "homonyma",
      lemma: "ὁμώνυμα",
      short_gloss: "homonyms",
      long_description: "",
      renderings: [],
      occurrences_by_edition: [],
      related: [],
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) return Promise.resolve(okResponse(occMap));
      if (url.includes("/api/terms/7")) return Promise.resolve(okResponse(termDetail));
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => <Reader workId="Categories" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelector(".term-mark")).not.toBeNull();
    });
    const mark = container.querySelector(".term-mark");
    if (mark === null) throw new Error("term-mark not found");
    fireEvent.click(mark);
    // Card mounts and resolves.
    await waitFor(() => {
      expect(container.querySelector(".termcard-lemma")).not.toBeNull();
    });
    expect(container.querySelector(".termcard-lemma")?.textContent).toBe("ὁμώνυμα");
  });

  it("clicking the same term-mark a second time closes the open card", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 91,
      chunks: [
        { chunk_id: "cat-1", section: "1.¶1", book: null, page: null,
          speaker: null, text: "ὁμώνυμα λόγος", ord: 0 },
      ],
      total: 1,
    };
    const occMap = {
      work_id: 91, lang: "grc", from: 0, limit: 200,
      by_chunk: { "cat-1": [
        { id: 1, term_id: 7, source_start: 0, source_end: 7,
          source_form: "ὁμώνυμα", lemma: "ὁμώνυμα",
          transliteration: "homonyma", short_gloss: "homonyms" },
      ] },
    };
    const termDetail = {
      id: 7, source_form: "ὁμώνυμα", source_language: "grc",
      transliteration: "homonyma", lemma: "ὁμώνυμα",
      short_gloss: "homonyms", long_description: "",
      renderings: [], occurrences_by_edition: [], related: [],
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) return Promise.resolve(okResponse(occMap));
      if (url.includes("/api/terms/7")) return Promise.resolve(okResponse(termDetail));
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => <Reader workId="Categories" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelector(".term-mark")).not.toBeNull();
    });
    const mark = container.querySelector(".term-mark");
    if (mark === null) throw new Error("term-mark not found");
    // First click opens the card.
    fireEvent.click(mark);
    await waitFor(() => {
      expect(container.querySelector(".termcard-lemma")).not.toBeNull();
    });
    // Second click on the same mark dismisses it.
    fireEvent.click(mark);
    await waitFor(() => {
      expect(container.querySelector(".termcard")).toBeNull();
    });
  });

  it("clicking a non-term word fires /api/translate and opens the rail", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130,
      lang: "deu",
      work: "Phänomenologie des Geistes",
      author: "Hegel",
      corpus: "hegel",
      chunks: [
        { chunk_id: "ph-1", section: "¶1", book: null, page: null,
          speaker: null, text: "Der Geist erscheint.", ord: 0 },
      ],
      total: 1,
    };
    let translateBody: { source_text?: string; target_lang?: string } | null = null;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url === "/api/translate") {
        // `init.body` is a string in our client (chat.ts JSON-
        // serialises before fetching); coerce only when it's a
        // proper BodyInit string to avoid the `[object Object]`
        // stringification hazard ESLint flags.
        const body = init?.body;
        translateBody =
          typeof body === "string"
            ? (JSON.parse(body) as typeof translateBody)
            : null;
        return Promise.resolve(okResponse({
          translated_text: "the spirit", literal_text: "the spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    // Click the second word (Geist).
    const words = container.querySelectorAll(".gw");
    fireEvent.click(words[1]!);
    // Wait for translate fetch + rail render.
    await waitFor(() => {
      if (translateBody === null) throw new Error("not yet");
    });
    // waitFor narrows nothing for TS; cast once we know it's set.
    const body = translateBody as unknown as
      { source_text?: string; target_lang?: string };
    expect(body.source_text).toBe("Geist");
    // Rail opens with the translation.
    await waitFor(() => {
      expect(container.querySelector(".rail")).not.toBeNull();
    });
    // The rail must actually flip from "Translating" to the ready
    // state — a prior bug (early-capture of `const s = props.state`
    // in RailContent) left the loading spinner stuck forever.
    await waitFor(() => {
      const txt = container.querySelector(".rail .translation")?.textContent ?? "";
      expect(txt).toContain("the spirit");
    });
    expect(container.querySelector(".rail .translation")?.textContent).not.toContain(
      "Translating",
    );
  });

  it("Show more samples paginates word lookup", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130,
      lang: "deu",
      work: "Phänomenologie des Geistes",
      author: "Hegel",
      corpus: "hegel",
      chunks: [
        { chunk_id: "ph-1", section: "¶1", book: null, page: null,
          speaker: null, text: "Der Geist erscheint.", ord: 0 },
      ],
      total: 1,
    };
    const mkSample = (i: number) => ({
      chunk_id: `c${i}`, section: `¶${i}`, surface: "Geist",
      surface_start: 0, surface_end: 5, snippet: `... Geist ${i} ...`,
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        const u = new URL(url, "http://test");
        const off = Number(u.searchParams.get("samples_offset") ?? "0");
        // Total of 15 samples; pages of 10. Page 1: 0..10, page 2: 10..15.
        const limit = Math.min(10, 15 - off);
        const samples = Array.from({ length: limit }, (_, i) => mkSample(off + i));
        const next = off + samples.length < 15 ? off + samples.length : null;
        return Promise.resolve(okResponse({
          surface: "Geist", lemma: "Geist", lang: "deu", edition_id: 84,
          work_id: 130, work_title: "Phänomenologie des Geistes",
          occurrence_count: 15,
          samples_offset: off, next_samples_offset: next, samples,
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "spirit", literal_text: "spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    const geist = container.querySelectorAll(".gw")[1];
    fireEvent.click(geist!);
    // First page: 10 samples + a Show-more button.
    await waitFor(() => {
      expect(container.querySelectorAll(".wordinfo-samples li").length).toBe(10);
    });
    const more = container.querySelector(".wordinfo-more");
    if (more === null) throw new Error(".wordinfo-more not found");
    expect(more.textContent).toMatch(/Show 5 more/);
    fireEvent.click(more);
    // Page 2 appends the remaining 5 → 15 total, and the button
    // disappears (next_samples_offset is null).
    await waitFor(() => {
      const lookups = fetchMock.mock.calls.filter((c) => {
        const input = c[0];
        const u =
          typeof input === "string"
            ? input
            : input instanceof URL ? input.href : input.url;
        return u.includes("/api/words/lookup");
      });
      expect(lookups.length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(container.querySelectorAll(".wordinfo-samples li").length).toBe(15);
    });
    expect(container.querySelector(".wordinfo-more")).toBeNull();
  });

  it("closes the rail via the X button + clears the in-text highlight", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 86, lang: "grc", work: "Nicomachean Ethics",
      author: "Aristotle", corpus: "aristotle",
      chunks: [
        { chunk_id: "ne-1", section: "1094a", book: null, page: null,
          speaker: null, text: "λόγος ἐστὶν λόγος.", ord: 0 },
      ],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 86, lang: "grc", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "λόγος", lemma: "λόγος", lang: "grc", edition_id: 53,
          work_id: 86, work_title: "Nicomachean Ethics",
          occurrence_count: 2, samples_offset: 0, next_samples_offset: null,
          pos: "NOUN", gender: "Masc", number: "Sing",
          feats: "Case=Nom|Gender=Masc|Number=Sing",
          samples: [],
        }));
      }
      if (url.includes("/lemma_highlights")) {
        return Promise.resolve(okResponse({
          work_id: 86, lang: "grc", lemma: "λόγος", from: 0, limit: 200,
          by_chunk: { "ne-1": [{ start: 0, end: 5 }, { start: 12, end: 17 }] },
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "speech", literal_text: "speech (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => <Reader workId="Nicomachean Ethics" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    fireEvent.click(container.querySelectorAll(".gw")[0]!);
    // Rail opens and in-text highlights paint.
    await waitFor(() => {
      expect(container.querySelector(".rail.open")).not.toBeNull();
      expect(container.querySelectorAll(".gw.lemma-hl").length).toBe(2);
    });
    // The X button is always visible while the rail is open.
    const close = container.querySelector(".rail-close");
    if (close === null) throw new Error(".rail-close not found");
    fireEvent.click(close);
    // Rail loses `.open` (slides + fades away via CSS transition);
    // in-text highlights are cleared synchronously.
    await waitFor(() => {
      expect(container.querySelector(".rail.open")).toBeNull();
    });
    expect(container.querySelectorAll(".gw.lemma-hl").length).toBe(0);
  });

  it("closes the rail when Esc is pressed", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130, lang: "deu", work: "Phänomenologie des Geistes",
      author: "Hegel", corpus: "hegel",
      chunks: [{ chunk_id: "ph-1", section: "¶1", book: null, page: null,
                 speaker: null, text: "Der Geist erscheint.", ord: 0 }],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "Geist", lemma: "Geist", lang: "deu", edition_id: 84,
          work_id: 130, work_title: "Phänomenologie des Geistes",
          occurrence_count: 1, samples_offset: 0, next_samples_offset: null,
          pos: "NOUN", gender: "Masc", number: "Sing",
          feats: "Case=Nom|Gender=Masc|Number=Sing",
          samples: [],
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "spirit", literal_text: "spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    fireEvent.click(container.querySelectorAll(".gw")[1]!);
    await waitFor(() => {
      expect(container.querySelector(".rail.open")).not.toBeNull();
    });
    // Esc dismisses the rail.
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(container.querySelector(".rail.open")).toBeNull();
    });
  });

  it("highlights every site of the clicked lemma in the text + snippet match", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 86, lang: "grc", work: "Nicomachean Ethics",
      author: "Aristotle", corpus: "aristotle",
      chunks: [
        { chunk_id: "ne-1", section: "1094a", book: null, page: null,
          speaker: null, text: "λόγος ἐστὶν λόγος.", ord: 0 },
      ],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 86, lang: "grc", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "λόγος", lemma: "λόγος", lang: "grc", edition_id: 53,
          work_id: 86, work_title: "Nicomachean Ethics",
          occurrence_count: 2, samples_offset: 0, next_samples_offset: null,
          pos: "NOUN", gender: "Masc", number: "Sing",
          feats: "Case=Nom|Gender=Masc|Number=Sing",
          samples: [
            { chunk_id: "ne-1", section: "1094a", surface: "λόγος",
              surface_start: 0, surface_end: 5,
              snippet: "λόγος ἐστὶν λόγος.",
              match_start: 0, match_end: 5 },
          ],
        }));
      }
      if (url.includes("/lemma_highlights")) {
        return Promise.resolve(okResponse({
          work_id: 86, lang: "grc", lemma: "λόγος", from: 0, limit: 200,
          by_chunk: {
            "ne-1": [
              { start: 0, end: 5 },
              { start: 12, end: 17 },
            ],
          },
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "speech", literal_text: "speech (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => <Reader workId="Nicomachean Ethics" sourceLang="grc" />);
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    fireEvent.click(container.querySelectorAll(".gw")[0]!);
    // In-text: both λόγος sites get .lemma-hl after the fetch lands.
    await waitFor(() => {
      expect(container.querySelectorAll(".gw.lemma-hl").length).toBe(2);
    });
    // Snippet inside the rail wraps the match in .lemma-hl too.
    expect(container.querySelector(".wordinfo-snippet .lemma-hl")?.textContent).toBe(
      "λόγος",
    );
  });

  it("renders POS · gender · number chip when the lemma carries morph", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130, lang: "deu", work: "Phänomenologie des Geistes",
      author: "Hegel", corpus: "hegel",
      chunks: [{ chunk_id: "ph-1", section: "¶1", book: null, page: null,
                 speaker: null, text: "Der Geist erscheint.", ord: 0 }],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "Geist", lemma: "Geist", lang: "deu", edition_id: 84,
          work_id: 130, work_title: "Phänomenologie des Geistes",
          occurrence_count: 682,
          samples_offset: 0, next_samples_offset: null,
          pos: "NOUN", gender: "Masc", number: "Sing",
          feats: "Case=Nom|Gender=Masc|Number=Sing",
          samples: [],
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "spirit", literal_text: "spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    // Click "Geist" (second word).
    fireEvent.click(container.querySelectorAll(".gw")[1]!);
    await waitFor(() => {
      expect(container.querySelector(".wordinfo-morph")).not.toBeNull();
    });
    expect(container.querySelector(".wordinfo-morph")?.textContent).toBe(
      "noun · masc. · sing.",
    );
  });

  it("omits the morph chip when pos/gender/number are all null (legacy chunk)", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130, lang: "deu", work: "Phänomenologie des Geistes",
      author: "Hegel", corpus: "hegel",
      chunks: [{ chunk_id: "ph-1", section: "¶1", book: null, page: null,
                 speaker: null, text: "Der Geist erscheint.", ord: 0 }],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "Geist", lemma: "Geist", lang: "deu", edition_id: 84,
          work_id: 130, work_title: "Phänomenologie des Geistes",
          occurrence_count: 1,
          samples_offset: 0, next_samples_offset: null,
          pos: null, gender: null, number: null, feats: null,
          samples: [],
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "spirit", literal_text: "spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    fireEvent.click(container.querySelectorAll(".gw")[1]!);
    await waitFor(() => {
      expect(container.querySelector(".wordinfo-count")).not.toBeNull();
    });
    expect(container.querySelector(".wordinfo-morph")).toBeNull();
  });

  it("wraps each German word in .gw for the hover affordance (no HoverTip)", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130,
      lang: "deu",
      work: "Phänomenologie des Geistes",
      author: "Hegel",
      corpus: "hegel",
      chunks: [
        { chunk_id: "ph-1", section: "¶1", book: null, page: null,
          speaker: null, text: "Der Geist erscheint.", ord: 0 },
      ],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelector(".gw")).not.toBeNull();
    });
    // Each word becomes a .gw span; the chunk has 3 words.
    const words = Array.from(container.querySelectorAll(".gw"), (w) => w.textContent);
    expect(words).toEqual(["Der", "Geist", "erscheint"]);
    // No romanization tooltip for German — the HoverTip wrapper is
    // grc-only until the user clicks a word. Inspect the line's
    // hovertip-text count.
    const tips = container.querySelectorAll(".line .hovertip-text");
    expect(tips.length).toBe(0);
  });

  it("shows a cached translation on hover after a word click and rail dismiss", async () => {
    const range = {
      ...SAMPLE_RANGE,
      work_id: 130,
      lang: "deu",
      work: "Phänomenologie des Geistes",
      author: "Hegel",
      corpus: "hegel",
      chunks: [
        { chunk_id: "ph-1", section: "¶1", book: null, page: null,
          speaker: null, text: "Der Geist erscheint.", ord: 0 },
      ],
      total: 1,
    };
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL ? input.href : input.url;
      if (url.includes("/occurrence_map")) {
        return Promise.resolve(okResponse({
          work_id: 130, lang: "deu", from: 0, limit: 200, by_chunk: {},
        }));
      }
      if (url.startsWith("/api/words/lookup")) {
        return Promise.resolve(okResponse({
          surface: "Geist", lemma: "Geist", lang: "deu", edition_id: 84,
          work_id: 130, work_title: "Phänomenologie des Geistes",
          occurrence_count: 1, samples_offset: 0, next_samples_offset: null,
          pos: "NOUN", gender: "Masc", number: "Sing",
          feats: "Case=Nom|Gender=Masc|Number=Sing",
          samples: [],
        }));
      }
      if (url === "/api/translate") {
        return Promise.resolve(okResponse({
          translated_text: "spirit", literal_text: "spirit (lit)", model: "test", cached: false,
        }));
      }
      return Promise.resolve(okResponse(range));
    });
    const { container } = renderReader(() => (
      <Reader workId="Phänomenologie des Geistes" sourceLang="deu" />
    ));
    await waitFor(() => {
      expect(container.querySelectorAll(".gw").length).toBe(3);
    });
    fireEvent.click(container.querySelectorAll(".gw")[1]!);
    await waitFor(() => {
      expect(container.querySelector(".rail .translation")?.textContent).toContain(
        "spirit",
      );
    });
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(container.querySelector(".rail.open")).toBeNull();
    });
    const geist = container.querySelectorAll(".gw")[1]!;
    fireEvent.mouseEnter(geist);
    await waitFor(() => {
      const tip = geist.closest(".hovertip-wrap")?.querySelector(".hovertip-text");
      expect(tip?.textContent).toBe("spirit");
    });
  });
});
