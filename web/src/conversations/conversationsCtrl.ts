// Chat conversation controller. Owns:
//   * messages / history / thinking / pinned signals,
//   * the in-flight `AbortController`,
//   * send / hydrate / delete flows + their server calls,
//   * delete-dialog target state.
//
// Bridges to the router via `route` + `navigate`: hydrates on route
// change to a conversation, navigates to the landing after delete, etc.
//
// `useConversations` must be called from inside a Solid reactive root.

import { createEffect, createSignal } from "solid-js";
import {
  deleteConversation,
  getConversation,
  listConversations,
  nowTime,
} from "~/api/chatApi";
import { apiError } from "~/utils/apiError";
import { isAbortError } from "~/utils/util";
import { askMinerva } from "~/conversations/conversationsSend";
import {
  conversationToHistoryItem,
  persistedToTurn,
} from "~/conversations/conversationsHydrate";
import type { Route, RoutingApi } from "~/routing";
import type { HistoryItem, Turn, UserTurn } from "~/utils/types";

/** Active chat retrieval scope — a single work the next turns are
 * restricted to. Seeded when leaving the Reader; shown as a dismissible
 * chip in the composer. */
export interface ChatScope {
  workId: number;
  title: string;
}

export interface ConversationsApi {
  messages: () => Turn[];
  history: () => HistoryItem[];
  /** Current work scope, or null when unscoped. */
  chatScope: () => ChatScope | null;
  /** Set (or replace) the work scope — e.g. on Reader → Chat. */
  setChatScope: (scope: ChatScope | null) => void;
  /** Clear the work scope (the chip's × button). */
  clearChatScope: () => void;
  thinking: () => boolean;
  pinnedChunkIds: () => string[];
  deleteTarget: () => HistoryItem | null;
  activeId: () => string | null;
  showLanding: () => boolean;
  hydrating: () => boolean;
  togglePin: (chunkId: string) => void;
  newConversation: () => void;
  pickHistory: (id: string) => void;
  startFromLanding: (text: string) => void;
  sendMessage: (text: string) => void;
  requestDelete: (item: HistoryItem) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
  abortInflight: () => void;
}

export function useConversations(routing: RoutingApi): ConversationsApi {
  const [messages, setMessages] = createSignal<Turn[]>([]);
  const [history, setHistory] = createSignal<HistoryItem[]>([]);
  const [thinking, setThinking] = createSignal(false);
  const [pinnedChunkIds, setPinnedChunkIds] = createSignal<string[]>([]);
  const [deleteTarget, setDeleteTarget] = createSignal<HistoryItem | null>(null);
  const [chatScope, setChatScope] = createSignal<ChatScope | null>(null);

  let inflightController: AbortController | undefined;

  function abortInflight() {
    inflightController?.abort();
    inflightController = undefined;
  }

  const activeId = (): string | null => {
    const r = routing.route();
    return r.kind === "conversation" ? r.id : null;
  };

  const showLanding = (): boolean => routing.route().kind === "landing" && messages().length === 0;

  const [hydrating, setHydrating] = createSignal(false);

  function togglePin(chunkId: string) {
    setPinnedChunkIds((ids) =>
      ids.includes(chunkId) ? ids.filter((x) => x !== chunkId) : [...ids, chunkId],
    );
  }

  let lastHydratedId: string | null = null;
  let hydrateController: AbortController | undefined;
  function abortHydrate(): void {
    hydrateController?.abort();
    hydrateController = undefined;
  }

  createEffect(() => {
    const r = routing.route();
    if (r.kind === "conversation") {
      if (lastHydratedId !== r.id) {
        lastHydratedId = r.id;
        abortInflight();
        abortHydrate();
        setMessages([]);
        setPinnedChunkIds([]);
        setThinking(false);
        void hydrate(r.id);
      }
    } else {
      if (lastHydratedId !== null) {
        lastHydratedId = null;
        abortInflight();
        abortHydrate();
        setMessages([]);
        setPinnedChunkIds([]);
        setThinking(false);
        setHydrating(false);
      }
    }
  });

  void refreshHistory();

  async function refreshHistory() {
    try {
      const list = await listConversations();
      setHistory(list.map(conversationToHistoryItem));
    } catch (err) {
      console.warn("failed to load conversations", err);
      apiError("Couldn't load conversation history.");
    }
  }

  async function hydrate(id: string) {
    const controller = new AbortController();
    hydrateController = controller;
    setHydrating(true);
    try {
      const detail = await getConversation(id, controller.signal);
      if (activeId() !== id) return;
      setMessages(detail.messages.map(persistedToTurn));
    } catch (err) {
      if (isAbortError(err)) return;
      console.warn(`failed to hydrate conversation ${id}`, err);
      apiError("That conversation is no longer available.");
      if (activeId() === id) routing.navigate({ kind: "landing" });
      void refreshHistory();
    } finally {
      if (hydrateController === controller) {
        hydrateController = undefined;
      }
      if (activeId() === id) setHydrating(false);
    }
  }

  function sendDeps() {
    return {
      messages,
      setMessages,
      setThinking,
      pinnedChunkIds,
      setPinnedChunkIds,
      activeId,
      workId: () => chatScope()?.workId,
      navigate: (cid: string) => routing.navigate({ kind: "conversation", id: cid }),
      onHydratedId: (cid: string) => {
        lastHydratedId = cid;
      },
      refreshHistory: () => void refreshHistory(),
      inflightController: () => inflightController,
      setInflightController: (c: AbortController | undefined) => {
        inflightController = c;
      },
      abortInflight,
    };
  }

  function newConversation() {
    // A fresh conversation starts unscoped.
    setChatScope(null);
    routing.navigate({ kind: "landing" });
  }

  function pickHistory(id: string) {
    // Scope is ephemeral session state, not persisted per conversation;
    // switching threads drops it to avoid a stale chip on an unrelated chat.
    setChatScope(null);
    routing.navigate({ kind: "conversation", id });
  }

  function startFromLanding(text: string) {
    // Landing is the global entry point — unscoped.
    setChatScope(null);
    const turn: UserTurn = { role: "user", text, time: nowTime() };
    setMessages([turn]);
    void askMinerva(text, sendDeps());
  }

  function sendMessage(text: string) {
    const turn: UserTurn = { role: "user", text, time: nowTime() };
    setMessages((m) => [...m, turn]);
    void askMinerva(text, sendDeps());
  }

  function requestDelete(item: HistoryItem) {
    setDeleteTarget(item);
  }

  function cancelDelete() {
    setDeleteTarget(null);
  }

  async function confirmDelete() {
    const target = deleteTarget();
    if (!target) return;
    setDeleteTarget(null);
    const wasActive = activeId() === target.id;
    if (wasActive) abortInflight();
    const original = history();
    const originalIndex = original.findIndex((h) => h.id === target.id);
    setHistory((hs) => hs.filter((h) => h.id !== target.id));
    if (localStorage.getItem("minerva:last-conversation") === target.id) {
      localStorage.removeItem("minerva:last-conversation");
    }
    if (wasActive) {
      routing.navigate({ kind: "landing" });
    }
    try {
      await deleteConversation(target.id);
    } catch (err) {
      console.warn(`failed to delete conversation ${target.id}`, err);
      apiError("Couldn't delete that conversation.");
      if (originalIndex >= 0) {
        setHistory((hs) => {
          if (hs.some((h) => h.id === target.id)) return hs;
          const next = [...hs];
          next.splice(Math.min(originalIndex, next.length), 0, target);
          return next;
        });
      }
      void refreshHistory();
      return;
    }
    void refreshHistory();
  }

  return {
    messages,
    history,
    chatScope,
    setChatScope,
    clearChatScope: () => setChatScope(null),
    thinking,
    pinnedChunkIds,
    deleteTarget,
    activeId,
    showLanding,
    hydrating,
    togglePin,
    newConversation,
    pickHistory,
    startFromLanding,
    sendMessage,
    requestDelete,
    cancelDelete,
    confirmDelete: () => void confirmDelete(),
    abortInflight,
  };
}

export {
  conversationToHistoryItem,
  persistedToTurn,
  relativeTime,
} from "~/conversations/conversationsHydrate";
export type { Route };
