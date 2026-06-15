import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  conversationToHistoryItem,
  persistedToTurn,
  relativeTime,
} from "~/conversations/conversationsHydrate";
import type { Conversation, PersistedMessage } from "~/utils/types";

describe("relativeTime()", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-05T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns Just now for timestamps within the last minute", () => {
    expect(relativeTime(Date.now() / 1000 - 30)).toBe("Just now");
  });

  it("returns minutes ago for timestamps within the last hour", () => {
    expect(relativeTime(Date.now() / 1000 - 5 * 60)).toBe("5m ago");
  });

  it("returns hours ago for timestamps within the last day", () => {
    expect(relativeTime(Date.now() / 1000 - 3 * 3600)).toBe("3h ago");
  });

  it("returns Yesterday for timestamps between 1 and 2 days ago", () => {
    expect(relativeTime(Date.now() / 1000 - 86400 - 60)).toBe("Yesterday");
  });

  it("returns days ago for timestamps within the last week", () => {
    expect(relativeTime(Date.now() / 1000 - 3 * 86400)).toBe("3d ago");
  });

  it("returns a short date for older timestamps", () => {
    const epoch = Date.now() / 1000 - 10 * 86400;
    expect(relativeTime(epoch)).toMatch(/\w{3} \d{1,2}/);
  });
});

describe("conversationToHistoryItem()", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-05T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("maps id, title, dominant, and relative meta", () => {
    const c: Conversation = {
      id: "abc-1",
      title: "On virtue",
      dominant: "A",
      created_at: 1,
      updated_at: Date.now() / 1000 - 120,
    };
    expect(conversationToHistoryItem(c)).toEqual({
      id: "abc-1",
      title: "On virtue",
      meta: "2m ago",
      dominant: "A",
    });
  });
});

describe("persistedToTurn()", () => {
  it("maps user messages to user turns with formatted time", () => {
    const m: PersistedMessage = {
      role: "user",
      content: "What is justice?",
      created_at: 1717593600,
      dominant: null,
      abstained: null,
      citations: [],
    };
    const turn = persistedToTurn(m);
    expect(turn.role).toBe("user");
    if (turn.role === "user") {
      expect(turn.text).toBe("What is justice?");
      expect(turn.time).toMatch(/\d/);
    }
  });

  it("maps assistant messages with renumbered citations", () => {
    const m: PersistedMessage = {
      role: "assistant",
      content: "Justice is knowledge [3].\n\nAlso habit [1].",
      created_at: 1717593600,
      dominant: "P",
      abstained: false,
      citations: [
        { n: 1, src: "Rep 441c", text: "habit" },
        { n: 3, src: "Rep 368d", text: "knowledge" },
      ],
    };
    const turn = persistedToTurn(m);
    expect(turn.role).toBe("minerva");
    if (turn.role === "minerva") {
      expect(turn.paragraphs[0]).toContain("[1]");
      expect(turn.citations.map((c) => c.n)).toEqual([1, 2]);
      expect(turn.abstained).toBe(false);
      expect(turn.dominant).toBe("P");
    }
  });
});
