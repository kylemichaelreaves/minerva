import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createRoot } from "solid-js";
import { ApiError } from "~/api/client";
import { useConversations } from "~/features/conversations/conversationsCtrl";
import type { askMinerva } from "~/features/conversations/conversationsSend";
import type { listConversations, getConversation, deleteConversation } from "~/api/chatApi";
import type { Conversation, ConversationDetail } from "~/utils/types";
import { _resetToastsForTesting, useToasts } from "~/utils/apiError";
import { createTestRouting, flush } from "./helpers/testRouting";
import { must } from "./helpers/must";

const askMinervaMock = vi.fn<typeof askMinerva>();
const listConversationsMock = vi.fn<typeof listConversations>();
const getConversationMock = vi.fn<typeof getConversation>();
const deleteConversationMock = vi.fn<typeof deleteConversation>();

vi.mock("~/features/conversations/conversationsSend", () => ({
  askMinerva: (...args: Parameters<typeof askMinerva>) => askMinervaMock(...args),
}));

vi.mock("~/api/chatApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("~/api/chatApi")>();
  return {
    ...actual,
    listConversations: (...args: Parameters<typeof listConversations>) =>
      listConversationsMock(...args),
    getConversation: (...args: Parameters<typeof getConversation>) => getConversationMock(...args),
    deleteConversation: (...args: Parameters<typeof deleteConversation>) =>
      deleteConversationMock(...args),
  };
});

function runConversations(initial = createTestRouting()) {
  let api!: ReturnType<typeof useConversations>;
  const dispose = createRoot((d) => {
    api = useConversations(initial);
    return d;
  });
  return { api, routing: initial, dispose };
}

const LIST: Conversation[] = [
  {
    id: "abc",
    title: "First chat",
    dominant: "P",
    created_at: 1,
    updated_at: 100,
  },
  {
    id: "def",
    title: "Second chat",
    dominant: "A",
    created_at: 2,
    updated_at: 200,
  },
];

async function waitForHistory(api: ReturnType<typeof useConversations>) {
  await vi.waitFor(() => {
    expect(api.history().length).toBeGreaterThan(0);
  });
}

describe("useConversations()", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    askMinervaMock.mockReset();
    listConversationsMock.mockReset();
    getConversationMock.mockReset();
    deleteConversationMock.mockReset();
    listConversationsMock.mockResolvedValue(LIST);
    getConversationMock.mockResolvedValue({
      ...must(LIST[0]),
      messages: [],
    } satisfies ConversationDetail);
    deleteConversationMock.mockResolvedValue(undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("derives activeId and showLanding from the route", async () => {
    const routing = createTestRouting({ kind: "landing" });
    const { api, dispose } = runConversations(routing);
    await flush();
    expect(api.activeId()).toBeNull();
    expect(api.showLanding()).toBe(true);
    dispose();
  });

  it("showLanding is false after startFromLanding adds a message", async () => {
    const routing = createTestRouting({ kind: "landing" });
    const { api, dispose } = runConversations(routing);
    await flush();
    api.startFromLanding("hello");
    expect(api.showLanding()).toBe(false);
    expect(api.messages()).toHaveLength(1);
    expect(askMinervaMock).toHaveBeenCalledWith("hello", expect.any(Object));
    dispose();
  });

  it("hydrates messages when navigating to a conversation", async () => {
    getConversationMock.mockResolvedValue({
      ...must(LIST[0]),
      messages: [
        {
          role: "user",
          content: "Question?",
          created_at: 100,
          dominant: null,
          abstained: null,
          citations: [],
        },
      ],
    } satisfies ConversationDetail);

    const routing = createTestRouting({ kind: "conversation", id: "abc" });
    const { api, dispose } = runConversations(routing);
    await vi.waitFor(() => {
      expect(api.messages()).toHaveLength(1);
    });
    expect(api.activeId()).toBe("abc");
    const first = must(api.messages()[0]);
    if (first.role === "user") {
      expect(first.text).toBe("Question?");
    }
    expect(getConversationMock).toHaveBeenCalledWith("abc", expect.any(AbortSignal));
    dispose();
  });

  it("hydrate 404 navigates to landing and surfaces a toast", async () => {
    getConversationMock.mockRejectedValue(new ApiError("not found", 404));

    const routing = createTestRouting({ kind: "conversation", id: "missing" });
    const { api, routing: r, dispose } = runConversations(routing);
    await vi.waitFor(() => {
      expect(r.navigateSpy).toHaveBeenCalledWith({ kind: "landing" });
    });
    expect(useToasts()().some((t) => t.message.includes("no longer available"))).toBe(true);
    expect(api.messages()).toHaveLength(0);
    dispose();
  });

  it("transient hydrate failure (500 / network) keeps the user's place", async () => {
    getConversationMock.mockRejectedValue(new ApiError("boom", 500));

    const routing = createTestRouting({ kind: "conversation", id: "abc" });
    const { api, routing: r, dispose } = runConversations(routing);
    await vi.waitFor(() => {
      expect(useToasts()().some((t) => t.message.includes("Couldn't load"))).toBe(true);
    });
    // No navigation away — the conversation still exists server-side.
    expect(r.navigateSpy).not.toHaveBeenCalledWith({ kind: "landing" });
    expect(api.activeId()).toBe("abc");
    dispose();
  });

  it("re-picking the thread after a transient failure retries the hydrate", async () => {
    getConversationMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const routing = createTestRouting({ kind: "conversation", id: "abc" });
    const { api, dispose } = runConversations(routing);
    await vi.waitFor(() => {
      expect(useToasts()().some((t) => t.message.includes("Couldn't load"))).toBe(true);
    });
    expect(getConversationMock).toHaveBeenCalledTimes(1);
    // Picking the same conversation again re-attempts the hydrate
    // (lastHydratedId was cleared on the transient failure).
    api.pickHistory("abc");
    await vi.waitFor(() => {
      expect(getConversationMock).toHaveBeenCalledTimes(2);
    });
    dispose();
  });

  it("togglePin adds and removes chunk ids", async () => {
    const { api, dispose } = runConversations();
    await flush();
    api.togglePin("chunk-a");
    expect(api.pinnedChunkIds()).toEqual(["chunk-a"]);
    api.togglePin("chunk-b");
    expect(api.pinnedChunkIds()).toEqual(["chunk-a", "chunk-b"]);
    api.togglePin("chunk-a");
    expect(api.pinnedChunkIds()).toEqual(["chunk-b"]);
    dispose();
  });

  it("newConversation clears chat scope and navigates to landing", async () => {
    const routing = createTestRouting({ kind: "conversation", id: "abc" });
    const { api, routing: r, dispose } = runConversations(routing);
    await flush();
    api.setChatScope({ workId: 1, title: "Republic" });
    api.newConversation();
    expect(api.chatScope()).toBeNull();
    expect(r.navigateSpy).toHaveBeenCalledWith({ kind: "landing" });
    dispose();
  });

  it("pickHistory clears chat scope and navigates to the thread", async () => {
    const routing = createTestRouting({ kind: "landing" });
    const { api, routing: r, dispose } = runConversations(routing);
    await flush();
    api.setChatScope({ workId: 2, title: "Ethics" });
    api.pickHistory("def");
    expect(api.chatScope()).toBeNull();
    expect(r.navigateSpy).toHaveBeenCalledWith({ kind: "conversation", id: "def" });
    dispose();
  });

  it("startFromLanding KEEPS a scope that was seeded before submit (#350)", async () => {
    // The half of "leaving the Reader for the landing" that was
    // unbuildable: the back arrow could hand the work to a conversation,
    // and the landing could not receive it, because this cleared the scope
    // unconditionally ("Landing is the global entry point — unscoped").
    //
    // Now the landing renders the same dismissible `WorkScopeControl` chip
    // when a scope is set, so keeping it is visible rather than silent —
    // which is what makes carrying it honest.
    const routing = createTestRouting({ kind: "landing" });
    const { api, dispose } = runConversations(routing);
    await flush();
    api.setChatScope({ workId: 781, title: "Das Kapital, Band I" });
    api.startFromLanding("what is the commodity form?");
    expect(api.chatScope()).toEqual({ workId: 781, title: "Das Kapital, Band I" });
    dispose();
  });

  it("startFromLanding stays unscoped when no scope was seeded (#350)", async () => {
    // The cold landing — app start, or "New question" — is still the
    // global unscoped entry point. Nothing to keep, nothing to clear.
    const routing = createTestRouting({ kind: "landing" });
    const { api, dispose } = runConversations(routing);
    await flush();
    expect(api.chatScope()).toBeNull();
    api.startFromLanding("hello");
    expect(api.chatScope()).toBeNull();
    dispose();
  });

  it("sendMessage appends a user turn and calls askMinerva", async () => {
    const routing = createTestRouting({ kind: "conversation", id: "abc" });
    const { api, dispose } = runConversations(routing);
    await flush();
    api.sendMessage("follow up");
    expect(api.messages().some((m) => m.role === "user" && m.text === "follow up")).toBe(true);
    expect(askMinervaMock).toHaveBeenCalledWith("follow up", expect.any(Object));
    dispose();
  });

  it("requestDelete and cancelDelete manage dialog state", async () => {
    const { api, dispose } = runConversations();
    await flush();
    const item = { id: "abc", title: "t", meta: "m", dominant: "P" as const };
    api.requestDelete(item);
    expect(api.deleteTarget()).toEqual(item);
    api.cancelDelete();
    expect(api.deleteTarget()).toBeNull();
    dispose();
  });

  it("confirmDelete optimistically removes history and clears last-conversation key", async () => {
    localStorage.setItem("minerva:last-conversation", "abc");
    const routing = createTestRouting({ kind: "landing" });
    const { api, dispose } = runConversations(routing);
    await waitForHistory(api);
    const item = must(api.history().find((h) => h.id === "abc"));
    api.requestDelete(item);
    api.confirmDelete();
    await vi.waitFor(() => {
      expect(api.history().some((h) => h.id === "abc")).toBe(false);
    });
    expect(localStorage.getItem("minerva:last-conversation")).toBeNull();
    expect(deleteConversationMock).toHaveBeenCalledWith("abc");
    dispose();
  });

  it("confirmDelete restores history when delete fails", async () => {
    deleteConversationMock.mockRejectedValue(new Error("fail"));
    const { api, dispose } = runConversations();
    await waitForHistory(api);
    const item = must(api.history().find((h) => h.id === "abc"));
    api.requestDelete(item);
    api.confirmDelete();
    await vi.waitFor(() => {
      expect(useToasts()().some((t) => t.message.includes("Couldn't delete"))).toBe(true);
    });
    expect(api.history().some((h) => h.id === "abc")).toBe(true);
    dispose();
  });
});
