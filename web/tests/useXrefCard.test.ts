import { describe, it, expect } from "vitest";
import { createRoot, createSignal } from "solid-js";
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

describe("useXrefCard()", () => {
  it("opens a card from the first reference on a chunk", () => {
    createRoot((dispose) => {
      const [map, setMap] = createSignal<ReferencesMap | null>(null);
      const api = useXrefCard({ refsMap: map });
      setMap(refsMap());
      const rect = new DOMRect(10, 20, 30, 40);
      api.onXrefOpen("rep-509d", rect);
      const open = api.openRefCard();
      expect(open?.chunkId).toBe("rep-509d");
      expect(open?.reference.id).toBe(1);
      expect(open?.anchor).toBe(rect);
      dispose();
    });
  });

  it("toggles closed when clicking the same chunk again", () => {
    createRoot((dispose) => {
      const api = useXrefCard({ refsMap: () => refsMap() });
      const rect = new DOMRect(0, 0, 1, 1);
      api.onXrefOpen("rep-509d", rect);
      expect(api.openRefCard()).not.toBeNull();
      api.onXrefOpen("rep-509d", rect);
      expect(api.openRefCard()).toBeNull();
      dispose();
    });
  });

  it("no-ops when the chunk has no references", () => {
    createRoot((dispose) => {
      const api = useXrefCard({ refsMap: () => refsMap() });
      api.onXrefOpen("missing-chunk", new DOMRect(0, 0, 1, 1));
      expect(api.openRefCard()).toBeNull();
      dispose();
    });
  });

  it("close() clears open state", () => {
    createRoot((dispose) => {
      const api = useXrefCard({ refsMap: () => refsMap() });
      api.onXrefOpen("rep-509d", new DOMRect(0, 0, 1, 1));
      api.close();
      expect(api.openRefCard()).toBeNull();
      dispose();
    });
  });
});
