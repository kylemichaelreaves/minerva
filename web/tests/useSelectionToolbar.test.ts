// Lifecycle tests for useSelectionToolbar — the persistent-highlight
// load/save behavior. We drive the hook directly via Solid's
// createRoot so we don't have to mount a full Reader (which would
// need a real DOM, a fetch mock, and the entire range-fetch chain).
//
// The Selection API helpers (onMouseUp) need a real DOM Range, so we
// don't exercise them here — we drive commitTranslate /
// markAllPinnedSaved / removeSavedHighlight directly with a hand-built
// SelToolbar payload.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRoot, createSignal } from "solid-js";
import {
  useSelectionToolbar,
  type SelToolbar,
} from "~/Reader/useSelectionToolbar";

/** Flush one microtask tick so Solid's createEffect callbacks
 *  (scheduled on next-tick) have a chance to run before we assert.
 *  See the useAbortableFetch tests for the same pattern. */
const flush = (): Promise<void> => Promise.resolve();

function buildToolbar(
  text: string,
  ref: string,
  pinned: { chunkId: string; start: number; end: number }[],
): SelToolbar {
  return {
    rect: new DOMRect(0, 0, 1, 1),
    text,
    ref,
    pinned: pinned.map((p) => ({ ...p, saved: false })),
    summary: `${text.split(/\s+/).length} words`,
    singleWord: false,
  };
}

describe("useSelectionToolbar persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("markAllPinnedSaved persists saved highlights to localStorage", () => {
    createRoot((dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      // Simulate the user committing a translation on "divided line"
      // spanning offsets 5..17 in chunk rep-509d.
      const toolbar = buildToolbar("divided line", "509d", [
        { chunkId: "rep-509d", start: 5, end: 17 },
      ]);
      api.commitTranslate(toolbar);
      // After commit but before dismiss: highlight is active
      // (saved=false), nothing written yet.
      expect(api.pinnedHighlights()[0].saved).toBe(false);
      expect(localStorage.getItem("minerva:highlights:Republic")).toBeNull();

      // Dismiss → markAllPinnedSaved fires → localStorage written.
      api.markAllPinnedSaved();
      expect(api.pinnedHighlights()[0].saved).toBe(true);
      const raw = localStorage.getItem("minerva:highlights:Republic");
      expect(raw).not.toBeNull();
      const parsed = JSON.parse(raw ?? "") as unknown[];
      expect(parsed).toEqual([
        {
          chunkId: "rep-509d",
          start: 5,
          end: 17,
          source: "divided line",
          ref: "509d",
        },
      ]);
      dispose();
    });
  });

  it("loads existing highlights from storage on mount", async () => {
    // Seed storage as if a prior session saved one highlight.
    localStorage.setItem(
      "minerva:highlights:Republic",
      JSON.stringify([
        {
          chunkId: "rep-509d",
          start: 5,
          end: 17,
          source: "divided line",
          ref: "509d",
        },
      ]),
    );
    await createRoot(async (dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      // createEffect runs on the next microtask — flush before
      // asserting on the loaded state.
      await flush();
      const loaded = api.pinnedHighlights();
      expect(loaded).toEqual([
        { chunkId: "rep-509d", start: 5, end: 17, saved: true },
      ]);
      dispose();
    });
  });

  it("reloads when workId changes (switching philosophers)", async () => {
    localStorage.setItem(
      "minerva:highlights:Republic",
      JSON.stringify([
        {
          chunkId: "rep-509d",
          start: 5,
          end: 17,
          source: "divided line",
          ref: "509d",
        },
      ]),
    );
    localStorage.setItem(
      "minerva:highlights:Phaedo",
      JSON.stringify([
        {
          chunkId: "phaedo-72e",
          start: 0,
          end: 11,
          source: "Recollection",
          ref: "72e",
        },
      ]),
    );
    await createRoot(async (dispose) => {
      const [workId, setWorkId] = createSignal("Republic");
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId,
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      await flush();
      expect(api.pinnedHighlights()[0].chunkId).toBe("rep-509d");
      // Switch work — the effect re-runs and loads Phaedo's set.
      setWorkId("Phaedo");
      await flush();
      expect(api.pinnedHighlights()[0].chunkId).toBe("phaedo-72e");
      dispose();
    });
  });

  it("removeSavedHighlight strips from in-memory state AND storage", () => {
    createRoot((dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      api.commitTranslate(
        buildToolbar("divided line", "509d", [
          { chunkId: "rep-509d", start: 5, end: 17 },
        ]),
      );
      api.markAllPinnedSaved();
      expect(api.pinnedHighlights().length).toBe(1);

      api.removeSavedHighlight("rep-509d", 5, 17);
      expect(api.pinnedHighlights().length).toBe(0);
      // Empty list deletes the key entirely (see highlightStorage).
      expect(localStorage.getItem("minerva:highlights:Republic")).toBeNull();
      dispose();
    });
  });

  it("commit + dismiss + commit accumulates across multiple selections", () => {
    createRoot((dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      // First selection.
      api.commitTranslate(
        buildToolbar("divided line", "509d", [
          { chunkId: "rep-509d", start: 5, end: 17 },
        ]),
      );
      api.markAllPinnedSaved();
      // Second selection on a different chunk.
      api.commitTranslate(
        buildToolbar("cave", "514a", [
          { chunkId: "rep-514a", start: 0, end: 4 },
        ]),
      );
      api.markAllPinnedSaved();

      const raw = localStorage.getItem("minerva:highlights:Republic");
      expect(raw).not.toBeNull();
      const stored = JSON.parse(raw ?? "") as { chunkId: string }[];
      expect(stored.length).toBe(2);
      const ids = stored.map((h) => h.chunkId).sort();
      expect(ids).toEqual(["rep-509d", "rep-514a"]);
      dispose();
    });
  });
});
