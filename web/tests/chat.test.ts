import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import {
  chat,
  chatStream,
  deleteConversation,
  getConversation,
  listConversations,
  parseSseBuffer,
} from "~/api/chatApi";
import {
  getWorkRange,
  listWorks,
  translate,
} from "~/api/readerApi";

let fetchMock: MockedFunction<typeof fetch>;

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

function errorResponse(status: number, statusText: string, body?: unknown): Response {
  return {
    ok: false,
    status,
    statusText,
    json: () =>
      body === undefined ? Promise.reject(new Error("not json")) : Promise.resolve(body),
  } as unknown as Response;
}

describe("parseSseBuffer()", () => {
  it("parses event and data lines from SSE blocks", () => {
    const raw =
      'event: meta\ndata: {"citations":[]}\n\n' +
      'event: delta\ndata: {"text":"Hi"}\n\n' +
      'event: done\ndata: {"paragraphs":["Hi"],"dominant":"P","response":"Hi"}\n\n';
    const { events, rest } = parseSseBuffer(raw);
    expect(rest).toBe("");
    expect(events.map((e) => e.name)).toEqual(["meta", "delta", "done"]);
    expect((JSON.parse(events[1].data) as { text: string }).text).toBe("Hi");
  });

  it("keeps an incomplete trailing block in rest", () => {
    const { events, rest } = parseSseBuffer('event: meta\ndata: {"a":1}');
    expect(events).toHaveLength(0);
    expect(rest).toContain("event: meta");
  });
});

describe("chatStream()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function sseResponse(chunks: string[]): Response {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        for (const c of chunks) {
          controller.enqueue(encoder.encode(c));
        }
        controller.close();
      },
    });
    return { ok: true, body: stream } as unknown as Response;
  }

  it("invokes handlers for meta, delta, and done", async () => {
    const sse =
      'event: meta\ndata: {"citations":[{"n":1,"src":"s","text":"t"}],"abstained":false,"backend":"stub","conversation_id":"cid1"}\n\n' +
      'event: delta\ndata: {"text":"Hel"}\n\n' +
      'event: delta\ndata: {"text":"lo"}\n\n' +
      'event: done\ndata: {"response":"Hello","paragraphs":["Hello"],"dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));

    const meta = vi.fn();
    const delta = vi.fn();
    const done = vi.fn();
    const error = vi.fn();

    await chatStream({ query: "q" }, { onMeta: meta, onDelta: delta, onDone: done, onError: error });

    expect(meta).toHaveBeenCalledTimes(1);
    expect(delta).toHaveBeenCalledTimes(2);
    expect(done).toHaveBeenCalledTimes(1);
    expect(error).not.toHaveBeenCalled();
    const doneTurn = done.mock.calls[0][0] as {
      paragraphs: string[];
      role: string;
    };
    expect(doneTurn.paragraphs).toEqual(["Hello"]);
    expect(doneTurn.role).toBe("minerva");
  });

  it("calls onError for non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(502, "Bad Gateway", { error: "LLM backend error" }),
    );
    const error = vi.fn();
    await chatStream({ query: "q" }, {
      onMeta: () => undefined,
      onDelta: () => undefined,
      onDone: () => undefined,
      onError: error,
    });
    expect(error).toHaveBeenCalledWith("LLM backend error");
  });

  it("rethrows AbortError", async () => {
    fetchMock.mockRejectedValueOnce(Object.assign(new DOMException("aborted", "AbortError")));
    await expect(
      chatStream({ query: "q" }, {
        onMeta: () => undefined,
        onDelta: () => undefined,
        onDone: () => undefined,
        onError: () => undefined,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("chat()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("POSTs JSON to /api/chat with the right body shape", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        response: "r",
        paragraphs: ["p"],
        citations: [],
        dominant: "P",
        abstained: false,
        backend: "none",
      }),
    );
    await chat({ query: "what is justice?", history: [{ role: "user", content: "hi" }] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      query: "what is justice?",
      history: [{ role: "user", content: "hi" }],
    });
  });

  it("maps a successful response to a minerva turn", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        response: "Republic 509d [1].",
        paragraphs: ["Republic 509d [1].", "Then the divided line."],
        citations: [{ n: 1, src: "Plato, Republic 509d", text: "Conceive then...", score: 0.9 }],
        dominant: "P",
        abstained: false,
        backend: "anthropic",
      }),
    );
    const turn = await chat({ query: "q" });
    expect(turn.role).toBe("minerva");
    expect(turn.dominant).toBe("P");
    expect(turn.paragraphs).toEqual(["Republic 509d [1].", "Then the divided line."]);
    expect(turn.citations).toHaveLength(1);
    expect(turn.citations[0].src).toBe("Plato, Republic 509d");
    expect(typeof turn.time).toBe("string");
  });

  it("defaults to dominant=P when the server omits the field", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [] }));
    const turn = await chat({ query: "q" });
    expect(turn.dominant).toBe("P");
    expect(turn.paragraphs).toEqual([]);
    expect(turn.citations).toEqual([]);
  });

  it("defaults history to [] when the caller omits it", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({ paragraphs: ["ok"], citations: [], dominant: "A" }),
    );
    await chat({ query: "q" });
    const init = fetchMock.mock.calls[0][1]!;
    expect(JSON.parse(init.body as string)).toEqual({ query: "q", history: [] });
  });

  it("returns an error turn (does NOT throw) on a network failure", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const turn = await chat({ query: "q" });
    expect(turn.role).toBe("minerva");
    expect(turn.citations).toEqual([]);
    expect(turn.paragraphs[0]).toMatch(/couldn't reach the corpus/i);
    expect(turn.paragraphs[0]).toMatch(/Network error: Failed to fetch/);
  });

  it("uses the server-provided error message on a non-OK response", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(502, "Bad Gateway", {
        error: "LLM error: Anthropic HTTP 401: invalid key",
      }),
    );
    const turn = await chat({ query: "q" });
    expect(turn.paragraphs[0]).toMatch(/LLM error: Anthropic HTTP 401/);
  });

  it("falls back to status text when the error body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(500, "Internal Server Error"));
    const turn = await chat({ query: "q" });
    expect(turn.paragraphs[0]).toMatch(/500 Internal Server Error/);
  });

  it("includes a `speaker` field in the request body when one is provided", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    await chat({ query: "q", speaker: "Socrates" });
    const init = fetchMock.mock.calls[0][1]!;
    expect(JSON.parse(init.body as string)).toMatchObject({ query: "q", speaker: "Socrates" });
  });

  it("omits `speaker` from the body when not provided", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    await chat({ query: "q" });
    const init = fetchMock.mock.calls[0][1]!;
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect("speaker" in body).toBe(false);
  });

  it("propagates the abstained flag from the server", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        response: "I could not find enough evidence...",
        paragraphs: ["I could not find enough evidence..."],
        citations: [],
        dominant: "P",
        abstained: true,
        backend: "none",
      }),
    );
    const turn = await chat({ query: "zxqv asdfgh" });
    expect(turn.abstained).toBe(true);
  });

  it("defaults abstained to false when the server omits it", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({ paragraphs: ["ok"], citations: [], dominant: "P" }),
    );
    const turn = await chat({ query: "q" });
    expect(turn.abstained).toBe(false);
  });

  it("returns an error turn when the server sends invalid JSON", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.reject(new SyntaxError("Unexpected token < in JSON")),
    } as unknown as Response);
    const turn = await chat({ query: "q" });
    expect(turn.role).toBe("minerva");
    expect(turn.paragraphs[0]).toMatch(/Server returned invalid JSON/);
    expect(turn.paragraphs[0]).toMatch(/Unexpected token/);
  });

  it("includes `rewrite: true` when requested", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    await chat({ query: "q", rewrite: true });
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string) as Record<string, unknown>;
    expect(body.rewrite).toBe(true);
  });

  it("includes `pinned_chunk_ids` when set", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    await chat({ query: "q", pinnedChunkIds: ["abc", "def"] });
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string) as Record<string, unknown>;
    expect(body.pinned_chunk_ids).toEqual(["abc", "def"]);
  });

  it("omits `pinned_chunk_ids` when the array is empty", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    await chat({ query: "q", pinnedChunkIds: [] });
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string) as Record<string, unknown>;
    expect("pinned_chunk_ids" in body).toBe(false);
  });

  it("accepts the four valid `dominant` codes (P/A/H/K) verbatim", async () => {
    for (const code of ["P", "A", "H", "K"]) {
      fetchMock.mockResolvedValueOnce(
        okResponse({
          paragraphs: ["ok"],
          citations: [],
          dominant: code,
        }),
      );
      const turn = await chat({ query: "q" });
      expect(turn.dominant).toBe(code);
    }
  });

  it("falls back to P for unknown / malformed `dominant` values", async () => {
    for (const bad of ["X", "plato", "", 42, null, undefined, { code: "P" }]) {
      fetchMock.mockResolvedValueOnce(
        okResponse({
          paragraphs: ["ok"],
          citations: [],
          dominant: bad,
        }),
      );
      const turn = await chat({ query: "q" });
      expect(turn.dominant).toBe("P");
    }
  });

  it("forwards an AbortSignal to fetch", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ paragraphs: [], citations: [], dominant: "P" }));
    const ac = new AbortController();
    await chat({ query: "q", signal: ac.signal });
    const init = fetchMock.mock.calls[0][1]!;
    expect(init.signal).toBe(ac.signal);
  });

  it("rethrows AbortError instead of returning an errorTurn", async () => {
    // Simulate an aborted fetch.
    fetchMock.mockRejectedValueOnce(Object.assign(new DOMException("aborted", "AbortError")));
    await expect(chat({ query: "q" })).rejects.toMatchObject({ name: "AbortError" });
  });

  it("still returns an errorTurn for non-abort network errors", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const turn = await chat({ query: "q" });
    expect(turn.paragraphs[0]).toMatch(/Network error/);
  });

  it("forwards conversationId as `conversation_id` in the request body", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        paragraphs: ["ok"],
        citations: [],
        dominant: "P",
      }),
    );
    await chat({ query: "q", conversationId: "abc12345" });
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string) as Record<string, unknown>;
    expect(body.conversation_id).toBe("abc12345");
  });

  it("omits conversation_id when not provided", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        paragraphs: ["ok"],
        citations: [],
        dominant: "P",
      }),
    );
    await chat({ query: "q" });
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string) as Record<string, unknown>;
    expect("conversation_id" in body).toBe(false);
  });

  it("renumbers citations into order of first appearance in the prose", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        paragraphs: ["Open with [3] then [1] and [2]."],
        citations: [
          { n: 1, src: "s1", text: "t1" },
          { n: 2, src: "s2", text: "t2" },
          { n: 3, src: "s3", text: "t3" },
        ],
        dominant: "P",
      }),
    );
    const turn = await chat({ query: "q" });
    expect(turn.paragraphs).toEqual(["Open with [1] then [2] and [3]."]);
    // Citations are reordered to match: [3]→[1], [1]→[2], [2]→[3].
    expect(turn.citations.map((c) => c.n)).toEqual([1, 2, 3]);
    expect(turn.citations.map((c) => c.src)).toEqual(["s3", "s1", "s2"]);
  });

  it("returns the server-minted conversation_id and title on the turn", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        paragraphs: ["ok"],
        citations: [],
        dominant: "P",
        conversation_id: "srv-id-1",
        title: "On the divided line",
      }),
    );
    const turn = await chat({ query: "What is the divided line?" });
    expect(turn.conversation_id).toBe("srv-id-1");
    expect(turn.title).toBe("On the divided line");
  });
});

// ---------- listConversations ----------

describe("listConversations()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function okResponse(body: unknown): Response {
    return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
  }

  it("GETs /api/conversations and returns the conversations array", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        conversations: [
          { id: "a", title: "A", dominant: "P", created_at: 1, updated_at: 2 },
          { id: "b", title: "B", dominant: null, created_at: 0, updated_at: 0 },
        ],
      }),
    );
    const out = await listConversations();
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations", { signal: undefined });
    expect(out).toHaveLength(2);
    expect(out[0].id).toBe("a");
  });

  it("returns an empty array when the server omits the field", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({}));
    expect(await listConversations()).toEqual([]);
  });

  it("throws on non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "oops",
    } as unknown as Response);
    await expect(listConversations()).rejects.toThrow(/500/);
  });
});

// ---------- getConversation ----------

describe("getConversation()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function okResponse(body: unknown): Response {
    return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
  }

  it("GETs /api/conversations/:id with the encoded id and returns the JSON body", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        id: "abc",
        title: "t",
        dominant: "A",
        created_at: 0,
        updated_at: 0,
        messages: [],
      }),
    );
    const out = await getConversation("abc");
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations/abc", { signal: undefined });
    expect(out.id).toBe("abc");
    expect(out.messages).toEqual([]);
  });

  it("URL-encodes the id", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        id: "a/b",
        title: "t",
        dominant: null,
        created_at: 0,
        updated_at: 0,
        messages: [],
      }),
    );
    await getConversation("a/b");
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations/a%2Fb", { signal: undefined });
  });

  it("throws on non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "not found",
    } as unknown as Response);
    await expect(getConversation("missing")).rejects.toThrow(/404/);
  });
});

// ---------- deleteConversation ----------

describe("deleteConversation()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("issues DELETE to the conversation URL", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204 } as unknown as Response);
    await deleteConversation("xyz");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/conversations/xyz");
    expect(init.method).toBe("DELETE");
  });

  it("treats 204 as success", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 204 } as unknown as Response);
    await expect(deleteConversation("xyz")).resolves.toBeUndefined();
  });

  it("throws on real failures", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500 } as unknown as Response);
    await expect(deleteConversation("xyz")).rejects.toThrow(/500/);
  });
});

// ---------- listWorks ----------

describe("listWorks()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function okResponse(body: unknown): Response {
    return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
  }

  it("GETs /api/works and returns the array", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        works: [{ corpus: "plato", author: "Plato", work: "Republic", lang: "grc", chunks: 540 }],
      }),
    );
    const out = await listWorks();
    expect(fetchMock).toHaveBeenCalledWith("/api/works", { signal: undefined });
    expect(out).toHaveLength(1);
    expect(out[0].work).toBe("Republic");
  });

  it("returns [] when the server omits works", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({}));
    expect(await listWorks()).toEqual([]);
  });

  it("throws on non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500 } as unknown as Response);
    await expect(listWorks()).rejects.toThrow(/500/);
  });
});

// ---------- getWorkRange ----------

describe("getWorkRange()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function okResponse(body: unknown): Response {
    return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
  }

  it("encodes the work id and appends query params", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        corpus: "plato",
        author: "Plato",
        work: "Republic",
        lang: "grc",
        total: 1,
        offset: 0,
        limit: 200,
        chunks: [],
      }),
    );
    await getWorkRange("Republic", { lang: "grc", from: 0, limit: 50 });
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/works/Republic?lang=grc&from=0&limit=50");
  });

  it("encodes spaces and punctuation in the work id", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        corpus: "hegel",
        author: "Hegel",
        work: "Phenomenology of Spirit",
        lang: "deu",
        total: 0,
        offset: 0,
        limit: 200,
        chunks: [],
      }),
    );
    await getWorkRange("Phenomenology of Spirit", { lang: "deu" });
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/works/Phenomenology%20of%20Spirit?lang=deu");
  });

  it("throws on non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404 } as unknown as Response);
    await expect(getWorkRange("Nope", {})).rejects.toThrow(/404/);
  });
});

// ---------- translate ----------

describe("translate()", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function okResponse(body: unknown): Response {
    return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
  }

  it("POSTs source_text and target_lang as JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        translated_text: "Sing, goddess",
        literal_text: "Wrath sing, goddess",
        model: "anthropic",
        cached: false,
      }),
    );
    const out = await translate("Μῆνιν", "eng");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/translate");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ source_text: "Μῆνιν", target_lang: "eng" });
    expect(out.translated_text).toBe("Sing, goddess");
    expect(out.literal_text).toBe("Wrath sing, goddess");
    expect(out.cached).toBe(false);
  });

  it("passes through the cached flag", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        translated_text: "Sing, goddess",
        literal_text: "Wrath sing, goddess",
        model: "anthropic",
        cached: true,
      }),
    );
    const out = await translate("Μῆνιν", "eng");
    expect(out.cached).toBe(true);
  });

  it("surfaces the server-provided error message", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ error: 'target_lang must be one of ["de", "en", "fr"]' }),
    } as unknown as Response);
    await expect(translate("x", "eng")).rejects.toThrow(/target_lang must be one of/);
  });

  it("falls back to status text when the body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    } as unknown as Response);
    await expect(translate("x", "eng")).rejects.toThrow(/500 Internal Server Error/);
  });

  it("forwards an AbortSignal", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        translated_text: "t",
        literal_text: "t-lit",
        model: "m",
        cached: false,
      }),
    );
    const ac = new AbortController();
    await translate("x", "eng", ac.signal);
    const init = fetchMock.mock.calls[0][1]!;
    expect(init.signal).toBe(ac.signal);
  });
});
