/** Barrel re-exports — prefer `api/types/*` or `lib/uiTypes` for new code. */

export type {
  ChatHistoryMessage,
  ChatRequest,
  ChatResponse,
  ChatStreamDone,
  ChatStreamMeta,
  Citation,
  Conversation,
  ConversationDetail,
  Dominant,
  PersistedMessage,
  ReplyLang,
  Role,
} from "~/api/types/chat";

export type {
  ChunkContextResponse,
  LemmaHighlightSpan,
  LemmaHighlights,
  OccurrenceMap,
  SourceChunk,
  TargetLang,
  TermDetail,
  TermEditionCountRow,
  TermOccurrenceSpan,
  TermRelatedRow,
  TermRenderingRow,
  TranslationResponse,
  WordLookup,
  WordSample,
  Work,
  WorkRange,
} from "~/api/types/reader";

export type {
  Reference,
  ReferencesMap,
  ReferenceTarget,
  ReferenceType,
} from "~/api/types/refs";

export type {
  AccentDef,
  AccentKey,
  AccentPalette,
  CitationFragment,
  CiteFragment,
  HistoryItem,
  MinervaTurn,
  StarterPrompt,
  Theme,
  Turn,
  UserTurn,
} from "~/utils/uiTypes";

export { isCiteFragment } from "~/utils/uiTypes";
