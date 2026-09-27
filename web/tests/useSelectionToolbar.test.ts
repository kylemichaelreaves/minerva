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
  toolbarKeyAction,
  type SelToolbar,
} from "~/Reader/useSelectionToolbar";
import { must } from "./helpers/must";

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
      expect(must(api.pinnedHighlights()[0]).saved).toBe(false);
      expect(localStorage.getItem("minerva:highlights:Republic")).toBeNull();

      // Dismiss → markAllPinnedSaved fires → localStorage written.
      api.markAllPinnedSaved();
      expect(must(api.pinnedHighlights()[0]).saved).toBe(true);
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
      expect(loaded).toEqual([{ chunkId: "rep-509d", start: 5, end: 17, saved: true }]);
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
      expect(must(api.pinnedHighlights()[0]).chunkId).toBe("rep-509d");
      // Switch work — the effect re-runs and loads Phaedo's set.
      setWorkId("Phaedo");
      await flush();
      expect(must(api.pinnedHighlights()[0]).chunkId).toBe("phaedo-72e");
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
        buildToolbar("divided line", "509d", [{ chunkId: "rep-509d", start: 5, end: 17 }]),
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

  it("cleans up the document keydown listener when the toolbar closes", async () => {
    // Regression: the cleanup used to be RETURNED from createEffect,
    // which Solid ignores — every toolbar open leaked one permanent
    // document keydown listener with a stale toolbar closure.
    await createRoot(async (dispose) => {
      const onTranslate = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: onTranslate,
        onLookupRequest: vi.fn(),
      });
      // Fake a non-collapsed selection so onMouseUp opens the toolbar.
      const textNode = document.createTextNode("divided line");
      document.body.appendChild(textNode);
      const fakeRange = {
        startContainer: textNode,
        endContainer: textNode,
        getBoundingClientRect: () => new DOMRect(0, 0, 1, 1),
      } as unknown as Range;
      const fakeSel = {
        isCollapsed: false,
        rangeCount: 1,
        toString: () => "divided line",
        getRangeAt: () => fakeRange,
        removeAllRanges: () => undefined,
      } as unknown as Selection;
      const selSpy = vi.spyOn(window, "getSelection").mockReturnValue(fakeSel);

      api.onMouseUp({ target: null } as unknown as MouseEvent);
      await flush();
      expect(api.selToolbar()).not.toBeNull();

      // Escape closes the toolbar via the document listener…
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      expect(api.selToolbar()).toBeNull();
      await flush();

      // …and the listener must be GONE: a later "t" keypress must not
      // commit a translate from the stale closure.
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
      expect(onTranslate).not.toHaveBeenCalled();

      // Re-open and confirm T still works through a fresh listener.
      api.onMouseUp({ target: null } as unknown as MouseEvent);
      await flush();
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
      expect(onTranslate).toHaveBeenCalledTimes(1);

      selSpy.mockRestore();
      textNode.remove();
      dispose();
    });
  });

  it("registers no keydown listener while the Reader is suspended", async () => {
    // The Reader now survives a step-out to the concordance instead of being
    // destroyed (#348), so its `document`-level shortcuts outlive the
    // navigation. `hidden` and `inert` on the Reader do not reach a listener
    // bound to `document` — without this gate, T on the concordance would
    // commit a translate from a toolbar nobody can see.
    await createRoot(async (dispose) => {
      const onTranslate = vi.fn();
      const [suspended, setSuspended] = createSignal(true);
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: onTranslate,
        onLookupRequest: vi.fn(),
        suspended,
      });
      const textNode = document.createTextNode("divided line");
      document.body.appendChild(textNode);
      const fakeRange = {
        startContainer: textNode,
        endContainer: textNode,
        getBoundingClientRect: () => new DOMRect(0, 0, 1, 1),
      } as unknown as Range;
      const fakeSel = {
        isCollapsed: false,
        rangeCount: 1,
        toString: () => "divided line",
        getRangeAt: () => fakeRange,
        removeAllRanges: () => undefined,
      } as unknown as Selection;
      const selSpy = vi.spyOn(window, "getSelection").mockReturnValue(fakeSel);

      api.onMouseUp({ target: null } as unknown as MouseEvent);
      await flush();
      // The toolbar STATE is open — that is the point of retaining the
      // Reader. Only the key binding is withheld.
      expect(api.selToolbar()).not.toBeNull();

      document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
      expect(onTranslate).not.toHaveBeenCalled();

      // Coming back to the Reader re-arms it against the same open toolbar.
      setSuspended(false);
      await flush();
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
      expect(onTranslate).toHaveBeenCalledTimes(1);

      selSpy.mockRestore();
      textNode.remove();
      dispose();
    });
  });

  it("ignores toolbar shortcuts while typing in a form field", async () => {
    await createRoot(async (dispose) => {
      const onTranslate = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Republic",
        onTranslateRequest: onTranslate,
        onLookupRequest: vi.fn(),
      });
      const textNode = document.createTextNode("divided line");
      document.body.appendChild(textNode);
      const fakeRange = {
        startContainer: textNode,
        endContainer: textNode,
        getBoundingClientRect: () => new DOMRect(0, 0, 1, 1),
      } as unknown as Range;
      const fakeSel = {
        isCollapsed: false,
        rangeCount: 1,
        toString: () => "divided line",
        getRangeAt: () => fakeRange,
        removeAllRanges: () => undefined,
      } as unknown as Selection;
      const selSpy = vi.spyOn(window, "getSelection").mockReturnValue(fakeSel);

      api.onMouseUp({ target: null } as unknown as MouseEvent);
      await flush();
      expect(api.selToolbar()).not.toBeNull();

      // A "t" typed inside an <input> must neither commit a translate
      // nor steal the keystroke.
      const input = document.createElement("input");
      document.body.appendChild(input);
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
      expect(onTranslate).not.toHaveBeenCalled();
      expect(api.selToolbar()).not.toBeNull();

      input.remove();
      selSpy.mockRestore();
      textNode.remove();
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
        buildToolbar("divided line", "509d", [{ chunkId: "rep-509d", start: 5, end: 17 }]),
      );
      api.markAllPinnedSaved();
      // Second selection on a different chunk.
      api.commitTranslate(
        buildToolbar("cave", "514a", [{ chunkId: "rep-514a", start: 0, end: 4 }]),
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

describe("useSelectionToolbar syntax action", () => {
  it("commitSyntax reports the chunk of the first pinned span", () => {
    createRoot((dispose) => {
      const onSyntaxRequest = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
        syntaxEnabled: () => true,
        onSyntaxRequest,
      });
      const toolbar = buildToolbar("Der Geist", "¶17", [
        { chunkId: "hegel-p17", start: 0, end: 9 },
      ]);

      api.commitSyntax(toolbar);

      expect(onSyntaxRequest).toHaveBeenCalledWith("hegel-p17");
      dispose();
    });
  });

  it("commitSyntax is inert when the selection has no pinned span", () => {
    createRoot((dispose) => {
      const onSyntaxRequest = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
        syntaxEnabled: () => true,
        onSyntaxRequest,
      });
      const toolbar = buildToolbar("Der Geist", "¶17", []);

      api.commitSyntax(toolbar);

      expect(onSyntaxRequest).not.toHaveBeenCalled();
      dispose();
    });
  });

  it("commitSyntax does nothing when no handler is supplied", () => {
    createRoot((dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      const toolbar = buildToolbar("Der Geist", "¶17", [
        { chunkId: "hegel-p17", start: 0, end: 9 },
      ]);

      // Must not throw — `onSyntaxRequest` is optional.
      expect(() => {
        api.commitSyntax(toolbar);
      }).not.toThrow();
      dispose();
    });
  });
});

describe("toolbarKeyAction", () => {
  const ev = (key: string, target?: EventTarget) => {
    const e = new KeyboardEvent("keydown", { key });
    if (target) Object.defineProperty(e, "target", { value: target });
    return e;
  };
  const opts = (over: Partial<{ singleWord: boolean; syntaxEnabled: boolean }> = {}) => ({
    singleWord: over.singleWord ?? false,
    syntaxEnabled: over.syntaxEnabled ?? false,
  });

  it("maps S to syntax only when syntax is enabled", () => {
    expect(toolbarKeyAction(ev("s"), opts({ syntaxEnabled: true }))).toBe("syntax");
    expect(toolbarKeyAction(ev("S"), opts({ syntaxEnabled: true }))).toBe("syntax");
    expect(toolbarKeyAction(ev("s"), opts({ syntaxEnabled: false }))).toBeNull();
  });

  it("maps L to lookup only for a single-word selection", () => {
    expect(toolbarKeyAction(ev("l"), opts({ singleWord: true }))).toBe("lookup");
    expect(toolbarKeyAction(ev("l"), opts({ singleWord: false }))).toBeNull();
  });

  it("maps T to translate and Escape to dismiss", () => {
    expect(toolbarKeyAction(ev("t"), opts())).toBe("translate");
    expect(toolbarKeyAction(ev("T"), opts())).toBe("translate");
    expect(toolbarKeyAction(ev("Escape"), opts())).toBe("dismiss");
  });

  it("yields to form fields and editable regions", () => {
    for (const tag of ["input", "textarea", "select"]) {
      const el = document.createElement(tag);
      expect(toolbarKeyAction(ev("t", el), opts())).toBeNull();
    }
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    // jsdom does not derive isContentEditable from the attribute.
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(toolbarKeyAction(ev("t", editable), opts())).toBeNull();
  });

  it("ignores unrelated keys", () => {
    expect(toolbarKeyAction(ev("x"), opts({ singleWord: true, syntaxEnabled: true }))).toBeNull();
  });
});

describe("useSelectionToolbar onMouseUp target handling", () => {
  /** A non-collapsed selection, as a drag leaves behind. */
  function fakeDragSelection(text: string) {
    const node = document.createTextNode(text);
    document.body.appendChild(node);
    const range = {
      startContainer: node,
      endContainer: node,
      getBoundingClientRect: () => new DOMRect(0, 0, 1, 1),
    } as unknown as Range;
    const sel = {
      isCollapsed: false,
      rangeCount: 1,
      toString: () => text,
      getRangeAt: () => range,
      removeAllRanges: () => undefined,
    } as unknown as Selection;
    return vi.spyOn(window, "getSelection").mockReturnValue(sel);
  }

  function api() {
    return useSelectionToolbar({
      getStage: () => undefined,
      workId: () => "Fragments",
      onTranslateRequest: vi.fn(),
      onLookupRequest: vi.fn(),
    });
  }

  it("opens for a drag released over a word", async () => {
    // The ordinary case, and the one that was broken: a drag-selection
    // ends with the pointer on a word, and every word is wrapped in
    // `<span class="gw">` by WordRun. The handler used to return early
    // on `target.closest(".gw")`, so the toolbar never appeared unless
    // you happened to release on a space or past the end of the line.
    // Measured in Chrome: released over .gw -> no toolbar; over the
    // surrounding .text or .line -> toolbar.
    await createRoot(async (dispose) => {
      const a = api();
      fakeDragSelection("Das sich zusammenziehende");
      const word = document.createElement("span");
      word.className = "gw";
      document.body.appendChild(word);

      a.onMouseUp({ target: word } as unknown as MouseEvent);
      await flush();
      expect(a.selToolbar()).not.toBeNull();
      dispose();
    });
  });

  it("still opens for a drag released between words", async () => {
    await createRoot(async (dispose) => {
      const a = api();
      fakeDragSelection("Das sich zusammenziehende");
      const run = document.createElement("span");
      run.className = "text";
      document.body.appendChild(run);

      a.onMouseUp({ target: run } as unknown as MouseEvent);
      await flush();
      expect(a.selToolbar()).not.toBeNull();
      dispose();
    });
  });

  it("stays shut for a plain word click, which leaves a collapsed selection", async () => {
    // The condition the removed guard was reaching for. A click collapses
    // the selection; a drag does not. That is the real click-vs-drag test.
    await createRoot(async (dispose) => {
      const a = api();
      const sel = {
        isCollapsed: true,
        rangeCount: 0,
        toString: () => "",
        removeAllRanges: () => undefined,
      } as unknown as Selection;
      vi.spyOn(window, "getSelection").mockReturnValue(sel);
      const word = document.createElement("span");
      word.className = "gw";
      document.body.appendChild(word);

      a.onMouseUp({ target: word } as unknown as MouseEvent);
      await flush();
      expect(a.selToolbar()).toBeNull();
      dispose();
    });
  });
});
