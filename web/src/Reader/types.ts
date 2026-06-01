// Shared types within the Reader subpackage. Defined separately so
// the sibling files (Chrome.tsx, Lines.tsx, Rail.tsx, index.tsx) can
// import without a cycle through the orchestrator.

import type { TranslationResponse, WordLookup } from "~/api/types/reader";

/** Side-loaded word lookup. Decoupled from `RailState` because it
 *  comes from a different endpoint than translate and resolves at a
 *  different time — the rail renders whichever piece has arrived.
 *  `loadingMore` is the "Show more" button's in-flight gate. */
export type WordInfoState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; info: WordLookup; loadingMore: boolean }
  | { kind: "error"; message: string };

/** Translation-rail state machine. `awaiting` is the post-language-
 *  chip-tap state where the rail surfaces a hint but no fetch has
 *  fired yet. */
export type RailState =
  | { kind: "idle" }
  | { kind: "awaiting" }
  | { kind: "loading"; source: string; ref: string }
  | { kind: "ready"; source: string; ref: string; response: TranslationResponse }
  | { kind: "error"; source: string; ref: string; message: string };

/** Open-term-card state owned by the Reader. */
export interface OpenCard {
  termId: number;
  anchor: DOMRect;
}
