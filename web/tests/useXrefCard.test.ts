import { describe, it, expect } from "vitest";
import { createRoot, createSignal, flush } from "solid-js";
import { useXrefCard } from "~/Reader/useXrefCard";
import type { Reference, ReferencesMap } from "~/utils/types";

const REF: Reference = {
  id: 1,
  source_chunk_id: "rep-509d",
  source_span_start: null,
  source_span_end: null,
  source_form: null,
  quoted_phrase: null,
  target: {
    author: "Aristotle",
    work: "Ethics",
    in_corpus_work_id: 2,
    chunk_id: "ne-1",
    locator: "1097b",
    locator_payload: null,
    sort_key: null,
  },
  reference_type: "cites",
  confidence: 0.9,
  source_method: "rule",
  curator_status: "approved",
  curated_by: null,
  curated_at: null,
  note: null,
};

function refsMap(): ReferencesMap {
  return {
    work_id: 1,
    lang: "grc",
    from: 0,
    limit: 10,
    by_chunk: {
      "rep-509d": { count: 1, top: [REF] },
    },
  };
}

/** Build the hook under a root, then drive it from OUTSIDE that root: Solid 2
 *  forbids signal writes inside an owned scope, and the hook's handlers are
 *  event handlers in real use. Reads lag writes until `flush()`. */
function mount(initial: ReferencesMap | null) {
  return createRoot((dispose) => {
    const [map, setMap] = createSignal<ReferencesMap | null>(initial);
    return { api: useXrefCard({ refsMap: map }), setMap, dispose };
  });
}

describe("useXrefCard()", () => {
  it("opens a card from the first reference on a chunk", () => {
    const { api, setMap, dispose } = mount(null);
    setMap(refsMap());
    flush();
    const rect = new DOMRect(10, 20, 30, 40);
    api.onXrefOpen("rep-509d", rect);
    flush();
    const open = api.openRefCard();
    expect(open?.chunkId).toBe("rep-509d");
    expect(open?.reference.id).toBe(1);
    expect(open?.anchor).toBe(rect);
    dispose();
  });

  it("toggles closed when clicking the same chunk again", () => {
    const { api, dispose } = mount(refsMap());
    const rect = new DOMRect(0, 0, 1, 1);
    api.onXrefOpen("rep-509d", rect);
    flush();
    expect(api.openRefCard()).not.toBeNull();
    api.onXrefOpen("rep-509d", rect);
    flush();
    expect(api.openRefCard()).toBeNull();
    dispose();
  });

  it("no-ops when the chunk has no references", () => {
    const { api, dispose } = mount(refsMap());
    api.onXrefOpen("missing-chunk", new DOMRect(0, 0, 1, 1));
    flush();
    expect(api.openRefCard()).toBeNull();
    dispose();
  });

  it("close() clears open state", () => {
    const { api, dispose } = mount(refsMap());
    api.onXrefOpen("rep-509d", new DOMRect(0, 0, 1, 1));
    flush();
    expect(api.openRefCard()).not.toBeNull();
    api.close();
    flush();
    expect(api.openRefCard()).toBeNull();
    dispose();
  });
});
