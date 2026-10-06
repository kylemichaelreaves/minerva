// @vitest-environment node
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
  type MockedFunction,
} from "vitest";
import {
  buildChatBody,
  chatStream,
  deleteConversation,
  getConversation,
  listConversations,
  parseSseBuffer,
  type ChatStreamHandlers,
} from "~/api/chatApi";
import type { MinervaTurn } from "~/utils/uiTypes";
import { getWorkRange, listWorks, translate } from "~/api/readerApi";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

function errorResponse(status: number, statusText: string, body?: unknown): Response {
  // readErrorDetail reads the body via .text() (so non-JSON proxy bodies
  // aren't lost); mirror a real Response by serialising the body to text.
  return {
    ok: false,
    status,
    statusText,
    text: () => Promise.resolve(body === undefined ? "" : JSON.stringify(body)),
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
    expect((JSON.parse(must(events[1]).data) as { text: string }).text).toBe("Hi");
  });

  it("keeps an incomplete trailing block in rest", () => {
    const { events, rest } = parseSseBuffer('event: meta\ndata: {"a":1}');
    expect(events).toHaveLength(0);
    expect(rest).toContain("event: meta");
  });

  it("parses CRLF-delimited blocks (proxy-normalized streams)", () => {
    const raw =
      'event: meta\r\ndata: {"citations":[]}\r\n\r\n' +
      'event: delta\r\ndata: {"text":"Hi"}\r\n\r\n';
    const { events, rest } = parseSseBuffer(raw);
    expect(rest).toBe("");
    expect(events.map((e) => e.name)).toEqual(["meta", "delta"]);
    expect((JSON.parse(must(events[1]).data) as { text: string }).text).toBe("Hi");
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
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    const error = vi.fn();

    await chatStream(
      { query: "q" },
      { onMeta: meta, onDelta: delta, onDone: done, onError: error },
    );

    expect(meta).toHaveBeenCalledTimes(1);
    expect(delta).toHaveBeenCalledTimes(2);
    expect(done).toHaveBeenCalledTimes(1);
    expect(error).not.toHaveBeenCalled();
    const doneTurn = must(done.mock.calls[0])[0];
    expect(doneTurn.paragraphs).toEqual(["Hello"]);
    expect(doneTurn.role).toBe("minerva");
  });

  it("calls onError for non-OK responses", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(502, "Bad Gateway", { error: "LLM backend error" }),
    );
    const error = vi.fn();
    await chatStream(
      { query: "q" },
      {
        onMeta: () => undefined,
        onDelta: () => undefined,
        onDone: () => undefined,
        onError: error,
      },
    );
    expect(error).toHaveBeenCalledWith("LLM backend error");
  });

  it("rethrows AbortError", async () => {
    fetchMock.mockRejectedValueOnce(Object.assign(new DOMException("aborted", "AbortError")));
    await expect(
      chatStream(
        { query: "q" },
        {
          onMeta: () => undefined,
          onDelta: () => undefined,
          onDone: () => undefined,
          onError: () => undefined,
        },
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  const noopHandlers = {
    onMeta: () => undefined,
    onDelta: () => undefined,
    onDone: () => undefined,
    onError: () => undefined,
  };
  const doneSse = 'event: done\ndata: {"response":"x","paragraphs":["x"],"dominant":"P"}\n\n';

  function sentBody(): Record<string, unknown> {
    return JSON.parse(must(must(fetchMock.mock.calls[0])[1]).body as string) as Record<
      string,
      unknown
    >;
  }

  it("sends work_id when the turn is work-scoped", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([doneSse]));
    await chatStream({ query: "q", workId: 792 }, noopHandlers);
    expect(sentBody().work_id).toBe(792);
  });

  it("omits work_id when unscoped", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([doneSse]));
    await chatStream({ query: "q" }, noopHandlers);
    expect(sentBody()).not.toHaveProperty("work_id");
  });

  function doneTurnOf(done: Mock<ChatStreamHandlers["onDone"]>): MinervaTurn {
    return must(done.mock.calls[0])[0];
  }

  it("accepts any single-character dominant verbatim; falls back to P on garbage", async () => {
    for (const [code, expected] of [
      ["X", "X"],
      ["Ω", "Ω"],
      ["plato", "P"],
      ["", "P"],
    ] as const) {
      fetchMock.mockResolvedValueOnce(
        sseResponse([
          `event: done\ndata: {"response":"x","paragraphs":["x"],"dominant":${JSON.stringify(code)}}\n\n`,
        ]),
      );
      const done = vi.fn<ChatStreamHandlers["onDone"]>();
      await chatStream({ query: "q" }, { ...noopHandlers, onDone: done });
      expect(doneTurnOf(done).dominant).toBe(expected);
      fetchMock.mockReset();
    }
  });

  it("propagates abstained from meta onto the finished turn", async () => {
    const sse =
      'event: meta\ndata: {"citations":[],"abstained":true,"backend":"none","conversation_id":"c1"}\n\n' +
      'event: done\ndata: {"response":"x","paragraphs":["x"],"dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    await chatStream({ query: "q" }, { ...noopHandlers, onDone: done });
    expect(doneTurnOf(done).abstained).toBe(true);
  });

  it("renumbers citations into order of first appearance in the prose", async () => {
    const meta = {
      citations: [
        { n: 1, src: "s1", text: "t1" },
        { n: 2, src: "s2", text: "t2" },
        { n: 3, src: "s3", text: "t3" },
      ],
      abstained: false,
      backend: "stub",
      conversation_id: "c1",
    };
    const sse =
      `event: meta\ndata: ${JSON.stringify(meta)}\n\n` +
      'event: done\ndata: {"response":"x","paragraphs":["Open with [3] then [1] and [2]."],"dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    await chatStream({ query: "q" }, { ...noopHandlers, onDone: done });
    const turn = doneTurnOf(done);
    expect(turn.paragraphs).toEqual(["Open with [1] then [2] and [3]."]);
    expect(turn.citations.map((c) => c.n)).toEqual([1, 2, 3]);
    expect(turn.citations.map((c) => c.src)).toEqual(["s3", "s1", "s2"]);
  });

  it("normalizes a malformed meta payload instead of poisoning the stream", async () => {
    const sse =
      'event: meta\ndata: {"citations":"oops","abstained":null}\n\n' +
      'event: done\ndata: {"response":"x","paragraphs":["x"],"dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const onMeta = vi.fn();
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    const error = vi.fn();
    await chatStream({ query: "q" }, { ...noopHandlers, onMeta, onDone: done, onError: error });
    expect(error).not.toHaveBeenCalled();
    expect(must(onMeta.mock.calls[0])[0]).toMatchObject({ citations: [], abstained: false });
    expect(doneTurnOf(done).citations).toEqual([]);
  });

  it("routes a malformed done event (non-array paragraphs) to onError", async () => {
    const sse = 'event: done\ndata: {"response":"x","paragraphs":"x","dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    const error = vi.fn();
    await chatStream({ query: "q" }, { ...noopHandlers, onDone: done, onError: error });
    expect(done).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith("Server sent a malformed done event.");
  });

  it("tolerates a done event with missing paragraphs (defaults to [])", async () => {
    const sse = 'event: done\ndata: {"response":"x","dominant":"P"}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    const error = vi.fn();
    await chatStream({ query: "q" }, { ...noopHandlers, onDone: done, onError: error });
    expect(error).not.toHaveBeenCalled();
    expect(doneTurnOf(done).paragraphs).toEqual([]);
  });

  it("reports network failures without the dev-only ':8000' copy", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const error = vi.fn();
    await chatStream({ query: "q" }, { ...noopHandlers, onError: error });
    expect(error).toHaveBeenCalledTimes(1);
    const msg = must(error.mock.calls[0])[0] as string;
    expect(msg).toMatch(/Network error: Failed to fetch/);
    expect(msg).not.toMatch(/:8000/);
  });
});

// `buildChatBody` is the request-shape contract shared by every chat
// call. (The non-streaming `chat()` wrapper these assertions used to
// run through was deleted as dead production code — the body-shape
// rules live on here.)
describe("buildChatBody()", () => {
  it("keeps query + history and defaults history to []", () => {
    expect(
      buildChatBody({ query: "what is justice?", history: [{ role: "user", content: "hi" }] }),
    ).toEqual({
      query: "what is justice?",
      history: [{ role: "user", content: "hi" }],
    });
    expect(buildChatBody({ query: "q" })).toEqual({ query: "q", history: [] });
  });

  it("includes `stream: true` only when requested", () => {
    expect(buildChatBody({ query: "q", stream: true }).stream).toBe(true);
    expect("stream" in buildChatBody({ query: "q" })).toBe(false);
  });

  it("includes `speaker` when provided and omits it otherwise", () => {
    expect(buildChatBody({ query: "q", speaker: "Socrates" }).speaker).toBe("Socrates");
    expect("speaker" in buildChatBody({ query: "q" })).toBe(false);
    expect("speaker" in buildChatBody({ query: "q", speaker: null })).toBe(false);
  });

  it("includes `rewrite: true` when requested", () => {
    expect(buildChatBody({ query: "q", rewrite: true }).rewrite).toBe(true);
    expect("rewrite" in buildChatBody({ query: "q" })).toBe(false);
  });

  it("includes `pinned_chunk_ids` only when non-empty", () => {
    expect(buildChatBody({ query: "q", pinnedChunkIds: ["abc", "def"] }).pinned_chunk_ids).toEqual([
      "abc",
      "def",
    ]);
    expect("pinned_chunk_ids" in buildChatBody({ query: "q", pinnedChunkIds: [] })).toBe(false);
  });

  it("forwards conversationId as `conversation_id` and omits when absent", () => {
    expect(buildChatBody({ query: "q", conversationId: "abc12345" }).conversation_id).toBe(
      "abc12345",
    );
    expect("conversation_id" in buildChatBody({ query: "q" })).toBe(false);
  });

  it("includes `work_id` only for numeric workId", () => {
    expect(buildChatBody({ query: "q", workId: 792 }).work_id).toBe(792);
    expect("work_id" in buildChatBody({ query: "q", workId: null })).toBe(false);
    expect("work_id" in buildChatBody({ query: "q" })).toBe(false);
  });

  it("includes `reply_lang` unless it is 'auto' or absent", () => {
    expect(buildChatBody({ query: "q", replyLang: "deu" }).reply_lang).toBe("deu");
    expect("reply_lang" in buildChatBody({ query: "q", replyLang: "auto" })).toBe(false);
    expect("reply_lang" in buildChatBody({ query: "q" })).toBe(false);
  });
});

describe("chat request plumbing (via chatStream)", () => {
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

  const doneSse = 'event: done\ndata: {"response":"x","paragraphs":["x"],"dominant":"P"}\n\n';
  const noopHandlers = {
    onMeta: () => undefined,
    onDelta: () => undefined,
    onDone: () => undefined,
    onError: () => undefined,
  };

  it("POSTs JSON to /api/chat with content-type and the built body", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([doneSse]));
    await chatStream(
      { query: "what is justice?", history: [{ role: "user", content: "hi" }] },
      noopHandlers,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      query: "what is justice?",
      history: [{ role: "user", content: "hi" }],
      stream: true,
    });
  });

  it("forwards an AbortSignal to fetch", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse([doneSse]));
    const ac = new AbortController();
    await chatStream({ query: "q", signal: ac.signal }, noopHandlers);
    const init = must(must(fetchMock.mock.calls[0])[1]);
    expect(init.signal).toBe(ac.signal);
  });

  it("returns the server-minted conversation_id and title on the turn", async () => {
    const sse =
      'event: meta\ndata: {"citations":[],"abstained":false,"backend":"stub","conversation_id":"srv-id-1","title":"On the divided line"}\n\n' +
      doneSse;
    fetchMock.mockResolvedValueOnce(sseResponse([sse]));
    const done = vi.fn<ChatStreamHandlers["onDone"]>();
    await chatStream({ query: "What is the divided line?" }, { ...noopHandlers, onDone: done });
    const turn = must(done.mock.calls[0])[0] as { conversation_id?: string; title?: string };
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
    expect(must(out[0]).id).toBe("a");
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
    expect(must(out[0]).work).toBe("Republic");
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
      text: () =>
        Promise.resolve(JSON.stringify({ error: 'target_lang must be one of ["de", "en", "fr"]' })),
    } as unknown as Response);
    await expect(translate("x", "eng")).rejects.toThrow(/target_lang must be one of/);
  });

  it("falls back to status text when the body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      text: () => Promise.resolve("<html>error</html>"),
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
    const init = must(must(fetchMock.mock.calls[0])[1]);
    expect(init.signal).toBe(ac.signal);
  });
});
