import { describe, it, expect } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { useWordHoverTranslations } from "~/Reader/useWordHoverTranslations";
import type { RailState } from "~/Reader/types";
import type { TargetLang } from "~/utils/types";

// Mirrors HOVER_TRANSLATION_CACHE_MAX in useWordHoverTranslations.tsx.
const CACHE_MAX = 500;

function setup() {
  const [rail, setRail] = createSignal<RailState>({ kind: "idle" });
  const [target] = createSignal<TargetLang>("eng");
  let dispose: () => void = () => undefined;
  const api = createRoot((d) => {
    dispose = d;
    return useWordHoverTranslations({ rail, target });
  });
  /** Simulate a word click whose translate call then settles. */
  const translate = (chunkId: string, offset: number, text: string) => {
    const source = `${chunkId}@${offset}`;
    api.registerWordClick(chunkId, offset, source);
    setRail({
      kind: "ready",
      lang: "eng",
      source,
      ref: chunkId,
      response: { translated_text: text, literal_text: text, model: "m", cached: false },
    });
  };
  return { api, setRail, translate, dispose };
}

describe("useWordHoverTranslations", () => {
  it("caches a settled word-click translation, keyed by chunk and offset", () => {
    const { api, translate, dispose } = setup();
    translate("c1", 3, "man");
    expect(api.lookup("c1", 3)).toBe("man");
    expect(api.lookup("c1", 4)).toBeUndefined();
    expect(api.lookup("c2", 3)).toBeUndefined();
    dispose();
  });

  it("ignores a ready rail whose source is not the pending word, or after clearPending", () => {
    const { api, setRail, dispose } = setup();
    api.registerWordClick("c1", 0, "arma");
    setRail({
      kind: "ready",
      lang: "eng",
      source: "a whole passage",
      ref: "c1",
      response: { translated_text: "x", literal_text: "x", model: "m", cached: false },
    });
    expect(api.lookup("c1", 0)).toBeUndefined();
    api.clearPending();
    setRail({
      kind: "ready",
      lang: "eng",
      source: "arma",
      ref: "c1",
      response: { translated_text: "arms", literal_text: "arms", model: "m", cached: false },
    });
    expect(api.lookup("c1", 0)).toBeUndefined();
    dispose();
  });

  it("evicts the oldest entries once the cache exceeds its limit, keeping the newest", () => {
    const { api, translate, dispose } = setup();
    for (let i = 0; i < CACHE_MAX; i++) translate("c", i, `t${i}`);
    // Exactly at the limit: nothing dropped yet.
    expect(api.lookup("c", 0)).toBe("t0");

    translate("c", CACHE_MAX, `t${CACHE_MAX}`);
    translate("c", CACHE_MAX + 1, `t${CACHE_MAX + 1}`);

    expect(api.lookup("c", 0)).toBeUndefined();
    expect(api.lookup("c", 1)).toBeUndefined();
    expect(api.lookup("c", 2)).toBe("t2");
    expect(api.lookup("c", CACHE_MAX)).toBe(`t${CACHE_MAX}`);
    expect(api.lookup("c", CACHE_MAX + 1)).toBe(`t${CACHE_MAX + 1}`);
    dispose();
  });
});
