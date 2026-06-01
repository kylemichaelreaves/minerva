/** Wire types for /api/chat and /api/conversations. */

export type Role = "user" | "assistant";

/** Single-letter dominant code from the API (see corpus_registry). */
export type Dominant = string;

export interface ChatHistoryMessage {
  role: Role;
  content: string;
}

export type ReplyLang = "auto" | "eng" | "grc" | "deu" | "lat" | "fra" | "heb" | "ara";

export interface ChatRequest {
  query: string;
  history?: ChatHistoryMessage[];
  reply_lang?: ReplyLang;
  speaker?: string | null;
  rewrite?: boolean;
  pinned_chunk_ids?: string[];
  conversation_id?: string;
  stream?: boolean;
}

export interface ChatStreamMeta {
  citations: Citation[];
  abstained: boolean;
  backend: string;
  conversation_id: string;
  title?: string;
  missing_pinned_ids?: string[];
}

export interface ChatStreamDone {
  response: string;
  paragraphs: string[];
  dominant: Dominant;
}

export interface Citation {
  n: number;
  src: string;
  text: string;
  chunk_id?: string;
  score?: number;
  speaker?: string | null;
  pinned?: boolean;
}

export interface ChatResponse {
  response: string;
  paragraphs: string[];
  citations: Citation[];
  dominant: Dominant;
  abstained: boolean;
  backend: string;
  conversation_id: string;
  title?: string;
  missing_pinned_ids?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  dominant: Dominant | null;
  created_at: number;
  updated_at: number;
}

export interface PersistedMessage {
  role: Role;
  content: string;
  created_at: number;
  dominant: Dominant | null;
  abstained: boolean | null;
  citations: Citation[];
}

export interface ConversationDetail extends Conversation {
  messages: PersistedMessage[];
}
