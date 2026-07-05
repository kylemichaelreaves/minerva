import type { Turn } from "~/utils/types";

// Stable DOM id for a conversation turn. Shared by Thread (which stamps
// the ids onto the rendered turns) and ThreadSearchSheet (which
// scroll-targets them) — they MUST agree, so this lives in one place
// rather than being duplicated in both (issue #66).
export function turnId(msg: Turn, index: number): string {
  return msg.role === "user" ? `user-${index}` : `minerva-${index}`;
}
