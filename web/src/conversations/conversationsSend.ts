// Chat send / SSE streaming helpers for the conversation controller.

import { chatStream, errorTurn, nowTime } from "~/api/chatApi";
import { errorMessage, isAbortError } from "~/utils/util";
import type {
  ChatHistoryMessage,
  ChatStreamMeta,
  MinervaTurn,
  Turn,
} from "~/utils/types";

export interface AskMinervaDeps {
  messages: () => Turn[];
  setMessages: (fn: (m: Turn[]) => Turn[]) => void;
  setThinking: (v: boolean) => void;
  pinnedChunkIds: () => string[];
  setPinnedChunkIds: (fn: (ids: string[]) => string[]) => void;
  activeId: () => string | null;
  workId: () => number | undefined;
  navigate: (id: string) => void;
  onHydratedId: (id: string) => void;
  refreshHistory: () => void;
  inflightController: () => AbortController | undefined;
  setInflightController: (c: AbortController | undefined) => void;
  abortInflight: () => void;
}

export async function askMinerva(text: string, deps: AskMinervaDeps): Promise<void> {
  const history: ChatHistoryMessage[] = deps
    .messages()
    .map(
      (m): ChatHistoryMessage =>
        m.role === "user"
          ? { role: "user", content: m.text }
          : { role: "assistant", content: m.paragraphs.join("\n\n") },
    )
    .filter((m) => m.content);
  const priorHistory = history.slice(0, -1);

  deps.abortInflight();
  const controller = new AbortController();
  deps.setInflightController(controller);
  deps.setThinking(true);

  function applyStreamMeta(meta: ChatStreamMeta) {
    const placeholder: MinervaTurn = {
      role: "minerva",
      time: nowTime(),
      streaming: true,
      streamText: "",
      paragraphs: [],
      citations: meta.citations,
      abstained: meta.abstained,
      dominant: "P",
      conversation_id: meta.conversation_id,
      title: meta.title,
      missing_pinned_ids: meta.missing_pinned_ids,
    };
    deps.setMessages((m) => [...m, placeholder]);
    deps.setThinking(false);
    if (meta.conversation_id && !deps.activeId()) {
      deps.onHydratedId(meta.conversation_id);
      deps.navigate(meta.conversation_id);
    }
  }

  function applyStreamDelta(delta: string) {
    deps.setMessages((m) => {
      const last = m[m.length - 1];
      if (last?.role !== "minerva" || !last.streaming) return m;
      return [
        ...m.slice(0, -1),
        { ...last, streamText: (last.streamText ?? "") + delta },
      ];
    });
  }

  function finalizeStreamTurn(reply: MinervaTurn) {
    deps.setMessages((m) => {
      const last = m[m.length - 1];
      if (last?.role === "minerva" && last.streaming) {
        return [...m.slice(0, -1), { ...reply, streaming: false }];
      }
      return [...m, { ...reply, streaming: false }];
    });
    if (reply.missing_pinned_ids?.length) {
      const stale = new Set(reply.missing_pinned_ids);
      deps.setPinnedChunkIds((ids) => ids.filter((id) => !stale.has(id)));
    }
    deps.refreshHistory();
  }

  function dropPartialStreamTurn() {
    deps.setMessages((m) => {
      const last = m[m.length - 1];
      if (last?.role === "minerva" && last.streaming) return m.slice(0, -1);
      return m;
    });
  }

  const isCurrent = () => deps.inflightController() === controller;

  try {
    await chatStream(
      {
        query: text,
        history: priorHistory,
        pinnedChunkIds: deps.pinnedChunkIds().length ? deps.pinnedChunkIds() : undefined,
        conversationId: deps.activeId() ?? undefined,
        workId: deps.workId(),
        signal: controller.signal,
      },
      {
        onMeta: (meta) => {
          if (!isCurrent()) return;
          applyStreamMeta(meta);
        },
        onDelta: (delta) => {
          if (!isCurrent()) return;
          applyStreamDelta(delta);
        },
        onDone: (reply) => {
          if (!isCurrent()) return;
          finalizeStreamTurn(reply);
        },
        onError: (message) => {
          if (!isCurrent()) return;
          deps.setThinking(false);
          dropPartialStreamTurn();
          deps.setMessages((m) => [...m, errorTurn(message)]);
        },
      },
    );
  } catch (err) {
    if (isAbortError(err)) {
      if (isCurrent()) {
        deps.setThinking(false);
        dropPartialStreamTurn();
      }
      return;
    }
    const msg = errorMessage(err);
    console.error("askMinerva: unexpected error", err);
    if (isCurrent()) {
      deps.setThinking(false);
      dropPartialStreamTurn();
      deps.setMessages((m) => [...m, errorTurn(`Unexpected error: ${msg}`)]);
    }
  } finally {
    if (isCurrent()) {
      deps.setInflightController(undefined);
      deps.setThinking(false);
    }
  }
}
