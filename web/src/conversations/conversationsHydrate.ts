// Persisted conversation → UI turn shapes and sidebar history labels.

import { renumberCitations } from "~/utils/renumber";
import type { Conversation, HistoryItem, PersistedMessage, Turn } from "~/utils/types";

export function relativeTime(epochSeconds: number): string {
  const now = Date.now() / 1000;
  const delta = now - epochSeconds;
  if (delta < 60) return "Just now";
  if (delta < 60 * 60) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 60 * 60 * 24) return `${Math.floor(delta / 3600)}h ago`;
  if (delta < 60 * 60 * 24 * 2) return "Yesterday";
  if (delta < 60 * 60 * 24 * 7) return `${Math.floor(delta / 86400)}d ago`;
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function conversationToHistoryItem(c: Conversation): HistoryItem {
  return {
    id: c.id,
    title: c.title,
    meta: relativeTime(c.updated_at),
    dominant: c.dominant ?? "P",
  };
}

export function persistedToTurn(m: PersistedMessage): Turn {
  const time = new Date(m.created_at * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (m.role === "user") {
    return { role: "user", text: m.content, time };
  }
  const renumbered = renumberCitations({
    paragraphs: m.content
      .split("\n\n")
      .map((p) => p.trim())
      .filter(Boolean),
    citations: m.citations,
  });
  return {
    role: "minerva",
    time,
    dominant: m.dominant ?? "P",
    paragraphs: renumbered.paragraphs,
    citations: renumbered.citations,
    abstained: m.abstained ?? false,
  };
}
