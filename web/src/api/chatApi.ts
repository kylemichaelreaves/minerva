// Chat + conversations API. Streams `{query, history, stream: true}`
// to POST /api/chat over SSE and maps the events into the shape
// Thread/Turn components expect; conversation CRUD lives here too.
// (A non-streaming `chat()` used to live here as well — it was dead
// production code that had drifted from the streaming path.)
//
// In dev, Vite proxies /api → http://localhost:8000 (see vite.config.ts).
// In prod, the same Python process serves both /api and the static
// bundle, so /api works without a proxy.

import type {
  ChatHistoryMessage,
  ChatStreamDone,
  ChatStreamMeta,
  Conversation,
  ConversationDetail,
  Dominant,
  ReplyLang,
} from "~/api/types/chat";
import type { MinervaTurn } from "~/utils/uiTypes";
import { readErrorDetail } from "~/api/client";
import { renumberCitations } from "~/utils/renumber";
import { errorMessage, isAbortError } from "~/utils/util";
import { apiDelete, apiGet } from "~/api/client";

// Dominant codes come from the server's corpus_registry; any single
// character is a valid code (dominantGlyph falls back to rendering the
// code itself for ones without a bespoke glyph). A hand-synced
// allowlist here silently re-mapped newer corpora to Plato.
function asDominant(raw: unknown): Dominant {
  if (typeof raw === "string" && raw.length === 1) {
    return raw;
  }
  return "P";
}

export interface ChatStreamHandlers {
  onMeta: (meta: ChatStreamMeta) => void;
  onDelta: (text: string) => void;
  onDone: (turn: MinervaTurn) => void;
  onError: (message: string) => void;
}

export interface ChatArgs {
  query: string;
  history?: ChatHistoryMessage[];
  /** Optional per-request speaker override; the server defaults to its
   * startup `--speaker` when omitted. */
  speaker?: string | null;
  /** Ask the LLM to rewrite the follow-up into a standalone retrieval query. */
  rewrite?: boolean;
  /** Chunk IDs to anchor as pinned context for this turn. */
  pinnedChunkIds?: string[];
  /** Existing conversation to append to. Omit to create a new one. */
  conversationId?: string;
  /** Hard-scope retrieval to one work (works.id). Set from the UI scope
   * chip; the server otherwise auto-detects a work named in the query. */
  workId?: number | null;
  /** Answer language; omit or `auto` to match the question. */
  replyLang?: ReplyLang;
  /**
   * AbortSignal so callers can cancel an in-flight request — e.g. when
   * the user clicks "New conversation" while a slow LLM call is pending.
   * If aborted, this function rethrows the AbortError instead of
   * returning an errorTurn so the caller can drop the result silently.
   */
  signal?: AbortSignal;
}

export function buildChatBody(args: ChatArgs & { stream?: boolean }): Record<string, unknown> {
  const body: Record<string, unknown> = {
    query: args.query,
    history: args.history ?? [],
  };
  if (args.stream) body.stream = true;
  if (args.speaker) body.speaker = args.speaker;
  if (args.rewrite) body.rewrite = true;
  if (args.pinnedChunkIds?.length) body.pinned_chunk_ids = args.pinnedChunkIds;
  if (args.conversationId) body.conversation_id = args.conversationId;
  if (typeof args.workId === "number") body.work_id = args.workId;
  if (args.replyLang && args.replyLang !== "auto") body.reply_lang = args.replyLang;
  return body;
}

/** Parse accumulated SSE bytes into discrete events. Returns unconsumed tail.
 *  Splits on blank lines with optional carriage returns — proxies that
 *  normalize the stream to CRLF would otherwise never produce a block
 *  boundary and the buffer would grow forever. */
export function parseSseBuffer(
  buffer: string,
): { events: { name: string; data: string }[]; rest: string } {
  const events: { name: string; data: string }[] = [];
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    if (!block.trim()) continue;
    let name = "message";
    const dataLines: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) {
        name = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length) {
      events.push({ name, data: dataLines.join("\n") });
    }
  }
  return { events, rest };
}

export async function chatStream(
  args: ChatArgs,
  handlers: ChatStreamHandlers,
): Promise<void> {
  let r: Response;
  try {
    const body = buildChatBody({ ...args, stream: true });
    r = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: args.signal,
    });
  } catch (err) {
    // Propagate abort up so the caller can drop the result rather than
    // rendering a stale error message for a request the user cancelled.
    if (isAbortError(err)) throw err;
    const msg = errorMessage(err);
    // Same-origin in prod, Vite proxy in dev — either way the request
    // didn't reach the Minerva server, so keep the copy generic.
    handlers.onError(`Network error: ${msg}. The Minerva server may be unreachable.`);
    return;
  }
  if (!r.ok) {
    handlers.onError(await readErrorDetail(r));
    return;
  }
  const reader = r.body?.getReader();
  if (!reader) {
    handlers.onError("Server returned an empty streaming body.");
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let meta: ChatStreamMeta | undefined;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseBuffer(buffer);
      buffer = parsed.rest;
      for (const ev of parsed.events) {
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(ev.data) as Record<string, unknown>;
        } catch {
          handlers.onError("Server returned invalid SSE JSON.");
          return;
        }
        if (ev.name === "meta") {
          // Defensive normalization — mirror the guards the JSON
          // hydrate path applies. A malformed meta payload shouldn't
          // poison every downstream `meta?.…` read.
          const rawMeta = payload as Partial<ChatStreamMeta>;
          meta = {
            citations: Array.isArray(rawMeta.citations) ? rawMeta.citations : [],
            abstained: rawMeta.abstained ?? false,
            backend: typeof rawMeta.backend === "string" ? rawMeta.backend : "",
            conversation_id:
              typeof rawMeta.conversation_id === "string" ? rawMeta.conversation_id : "",
            title: rawMeta.title,
            missing_pinned_ids: Array.isArray(rawMeta.missing_pinned_ids)
              ? rawMeta.missing_pinned_ids
              : undefined,
          };
          handlers.onMeta(meta);
        } else if (ev.name === "delta") {
          const text = payload.text;
          if (typeof text === "string" && text) handlers.onDelta(text);
        } else if (ev.name === "done") {
          const doneEv = payload as Partial<ChatStreamDone>;
          // A done event whose paragraphs is present but not an array
          // is malformed — surface it as a stream error instead of
          // letting renumberCitations throw mid-handler.
          if (doneEv.paragraphs !== undefined && !Array.isArray(doneEv.paragraphs)) {
            handlers.onError("Server sent a malformed done event.");
            return;
          }
          const renumbered = renumberCitations({
            paragraphs: doneEv.paragraphs ?? [],
            citations: meta?.citations ?? [],
          });
          handlers.onDone({
            role: "minerva",
            time: nowTime(),
            dominant: asDominant(doneEv.dominant),
            paragraphs: renumbered.paragraphs,
            citations: renumbered.citations,
            abstained: meta?.abstained ?? false,
            conversation_id: meta?.conversation_id,
            title: meta?.title,
            missing_pinned_ids: meta?.missing_pinned_ids,
          });
          return;
        } else if (ev.name === "error") {
          const errMsg = typeof payload.error === "string" ? payload.error : "Unknown error";
          handlers.onError(errMsg);
          return;
        }
      }
    }
    if (!meta) {
      handlers.onError("Stream ended before any data arrived.");
    }
  } catch (err) {
    if (isAbortError(err)) throw err;
    const msg = errorMessage(err);
    handlers.onError(`Unexpected error: ${msg}`);
  } finally {
    reader.releaseLock();
  }
}

export async function listConversations(signal?: AbortSignal): Promise<Conversation[]> {
  const body = await apiGet<{ conversations?: Conversation[] }>("/api/conversations", signal);
  return body.conversations ?? [];
}

export async function getConversation(
  id: string,
  signal?: AbortSignal,
): Promise<ConversationDetail> {
  return apiGet<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`, signal);
}

export async function deleteConversation(id: string, signal?: AbortSignal): Promise<void> {
  await apiDelete(`/api/conversations/${encodeURIComponent(id)}`, signal);
}

export function errorTurn(message: string): MinervaTurn {
  return {
    role: "minerva",
    time: nowTime(),
    dominant: "P",
    paragraphs: [`(I couldn't reach the corpus.) ${message}`],
    citations: [],
  };
}

export function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
