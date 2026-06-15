import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createSignal } from "solid-js";
import { askMinerva, type AskMinervaDeps } from "~/conversations/conversationsSend";
import type { ChatStreamMeta, MinervaTurn, Turn, UserTurn } from "~/utils/types";

const chatStreamMock = vi.fn();

vi.mock("~/api/chatApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("~/api/chatApi")>();
  return {
    ...actual,
    chatStream: (...args: unknown[]) => chatStreamMock(...args),
  };
});

function buildDeps(overrides: Partial<AskMinervaDeps> = {}): AskMinervaDeps {
  const [messages, setMessages] = createSignal<Turn[]>([
    { role: "user", text: "hello", time: "12:00" } satisfies UserTurn,
  ]);
  const [pinnedChunkIds, setPinnedChunkIds] = createSignal<string[]>([]);
  let inflight: AbortController | undefined;
  return {
    messages,
    setMessages,
    setThinking: vi.fn(),
    pinnedChunkIds,
    setPinnedChunkIds,
    activeId: () => null,
    workId: () => undefined,
    navigate: vi.fn(),
    onHydratedId: vi.fn(),
    refreshHistory: vi.fn(),
    inflightController: () => inflight,
    setInflightController: (c) => {
      inflight = c;
    },
    abortInflight: () => {
      inflight?.abort();
      inflight = undefined;
    },
    ...overrides,
  };
}

describe("askMinerva()", () => {
  beforeEach(() => {
    chatStreamMock.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("streams meta, delta, and done; calls refreshHistory", async () => {
    chatStreamMock.mockImplementation(async (_args, handlers) => {
      handlers.onMeta({
        citations: [{ n: 1, src: "s", text: "t" }],
        abstained: false,
        backend: "stub",
        conversation_id: "existing",
      } satisfies ChatStreamMeta);
      handlers.onDelta("Hel");
      handlers.onDelta("lo");
      handlers.onDone({
        role: "minerva",
        time: "12:01",
        dominant: "P",
        paragraphs: ["Hello"],
        citations: [{ n: 1, src: "s", text: "t" }],
      } satisfies MinervaTurn);
    });

    const deps = buildDeps();
    await askMinerva("hello", deps);

    expect(chatStreamMock).toHaveBeenCalledWith(
      expect.objectContaining({ query: "hello", history: [] }),
      expect.any(Object),
    );
    const msgs = deps.messages();
    expect(msgs).toHaveLength(2);
    expect(msgs[1]!.role).toBe("minerva");
    if (msgs[1]!.role === "minerva") {
      expect(msgs[1]!.streaming).toBe(false);
      expect(msgs[1]!.paragraphs).toEqual(["Hello"]);
    }
    expect(deps.refreshHistory).toHaveBeenCalled();
  });

  it("navigates on meta when starting a new conversation", async () => {
    chatStreamMock.mockImplementation(async (_args, handlers) => {
      handlers.onMeta({
        citations: [],
        abstained: false,
        backend: "stub",
        conversation_id: "new-id",
        title: "New chat",
      } satisfies ChatStreamMeta);
      handlers.onDone({
        role: "minerva",
        time: "12:01",
        dominant: "P",
        paragraphs: ["ok"],
        citations: [],
      });
    });

    const deps = buildDeps();
    await askMinerva("hello", deps);

    expect(deps.onHydratedId).toHaveBeenCalledWith("new-id");
    expect(deps.navigate).toHaveBeenCalledWith("new-id");
  });

  it("passes pinned chunk ids and prunes stale pins from done payload", async () => {
    chatStreamMock.mockImplementation(async (args, handlers) => {
      expect(args.pinnedChunkIds).toEqual(["pin-1", "pin-2"]);
      handlers.onMeta({
        citations: [],
        abstained: false,
        backend: "stub",
        conversation_id: "x",
      });
      handlers.onDone({
        role: "minerva",
        time: "12:01",
        dominant: "P",
        paragraphs: ["ok"],
        citations: [],
        missing_pinned_ids: ["pin-2"],
      });
    });

    const [pinnedChunkIds, setPinnedChunkIds] = createSignal(["pin-1", "pin-2"]);
    const deps = buildDeps({ pinnedChunkIds, setPinnedChunkIds });
    await askMinerva("hello", deps);
    expect(deps.pinnedChunkIds()).toEqual(["pin-1"]);
  });

  it("onError drops partial stream and appends error turn", async () => {
    chatStreamMock.mockImplementation(async (_args, handlers) => {
      handlers.onMeta({
        citations: [],
        abstained: false,
        backend: "stub",
        conversation_id: "x",
      });
      handlers.onError("upstream failed");
    });

    const deps = buildDeps();
    await askMinerva("hello", deps);

    const msgs = deps.messages();
    expect(msgs).toHaveLength(2);
    expect(msgs[1]!.role).toBe("minerva");
    if (msgs[1]!.role === "minerva") {
      expect(msgs[1]!.paragraphs[0]).toContain("upstream failed");
    }
  });

  it("AbortError clears thinking without adding error turn", async () => {
    chatStreamMock.mockImplementation(async () => {
      throw new DOMException("aborted", "AbortError");
    });

    const setThinking = vi.fn();
    const deps = buildDeps({ setThinking });
    await askMinerva("hello", deps);

    expect(deps.messages()).toHaveLength(1);
    expect(setThinking).toHaveBeenCalledWith(false);
  });

  it("ignores callbacks from a superseded controller", async () => {
    // Holder object — TS doesn't flow-track assignments made inside
    // the mockImplementation closure on a bare `let`, so a property
    // write keeps the union type intact at the call sites below.
    const stale: {
      handlers: {
        onMeta: (m: ChatStreamMeta) => void;
        onDelta: (d: string) => void;
      } | null;
    } = { handlers: null };

    chatStreamMock.mockImplementation(async (_args, handlers) => {
      stale.handlers = handlers;
    });

    const deps = buildDeps();
    await askMinerva("hello", deps);
    await Promise.resolve();

    const controller2 = new AbortController();
    deps.setInflightController(controller2);

    stale.handlers?.onMeta({
      citations: [],
      abstained: false,
      backend: "stub",
      conversation_id: "stale",
    });
    stale.handlers?.onDelta("stale");

    expect(deps.messages()).toHaveLength(1);
  });
});
