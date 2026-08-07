/** UI-only types (not API wire shapes). */

import type { Citation, Dominant } from "~/api/types/chat";

export type Theme = "light" | "dark";
export type AccentKey = "oxblood";

export interface UserTurn {
  role: "user";
  text: string;
  time: string;
}

export interface MinervaTurn {
  role: "minerva";
  time: string;
  dominant: Dominant;
  paragraphs: string[];
  citations: Citation[];
  abstained?: boolean;
  conversation_id?: string;
  title?: string;
  missing_pinned_ids?: string[];
  streaming?: boolean;
  streamText?: string;
}

export type Turn = UserTurn | MinervaTurn;

export interface HistoryItem {
  id: string;
  title: string;
  meta: string;
  dominant: Dominant;
}

export interface AccentPalette {
  accent: string;
  soft: string;
  selection: string;
}

export interface AccentDef {
  label: string;
  light: AccentPalette;
  dark: AccentPalette;
}

export interface CiteFragment {
  kind: "cite";
  n: number;
}
export type CitationFragment = string | CiteFragment;

export function isCiteFragment(x: CitationFragment): x is CiteFragment {
  return typeof x === "object";
}
