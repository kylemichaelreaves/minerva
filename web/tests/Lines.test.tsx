import { describe, it, expect, vi } from "vitest";
import { render } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { Lines } from "~/Reader/components/Lines";
import type { SourceChunk } from "~/utils/types";

const CHUNKS: SourceChunk[] = [
  {
    chunk_id: "a",
    section: "§4",
    book: null,
    page: null,
    speaker: null,
    text: "main prose",
    ord: 0,
    block_type: null,
  },
  {
    chunk_id: "b",
    section: "§4 Remark",
    book: null,
    page: null,
    speaker: null,
    text: "the remark",
    ord: 1,
    block_type: "remark",
  },
  {
    chunk_id: "c",
    section: "§4 Addition",
    book: null,
    page: null,
    speaker: null,
    text: "the addition",
    ord: 2,
    block_type: "addition",
  },
];

describe("<Lines /> structural blocks", () => {
  it("tags set-apart blocks with data-block and leaves body prose untagged", () => {
    const { container } = render(() => (
      <Lines
        chunks={CHUNKS}
        lang="eng"
        occMap={null}
        lemmaHighlights={null}
        onTermClick={vi.fn()}
        onWordClick={vi.fn()}
      />
    ));
    const lines = [...container.querySelectorAll(".line")];
    expect(lines).toHaveLength(3);
    // Body prose carries no data-block (renders as ordinary text).
    expect(lines[0]!.getAttribute("data-block")).toBeNull();
    // Remark / Addition are tagged so reader.css can indent them.
    expect(lines[1]!.getAttribute("data-block")).toBe("remark");
    expect(lines[2]!.getAttribute("data-block")).toBe("addition");
  });
});

// Coverage for `groupEditorialRuns` and its render wiring in Lines.tsx.
// The function itself isn't exported — these tests exercise it through
// the rendered output, which also proves the `<EditorialBlock>` wiring
// (Step 5 of the editorial-apparatus plan, #534) is correct end to end.

function chunk(ord: number, overrides: Partial<SourceChunk> = {}): SourceChunk {
  return {
    chunk_id: `c-${ord}`,
    section: `S${ord}`,
    book: null,
    page: null,
    speaker: null,
    text: `text ${ord}`,
    ord,
    ...overrides,
  };
}

function renderLines(chunks: SourceChunk[]) {
  return render(() => (
    <Lines
      chunks={chunks}
      lang="eng"
      occMap={null}
      lemmaHighlights={null}
      onTermClick={vi.fn()}
      onWordClick={vi.fn()}
    />
  ));
}

const editorial = (ord: number) => chunk(ord, { block_type: "editorial" });
const body = (ord: number) => chunk(ord);

describe("Lines — editorial run grouping", () => {
  it("(a) collapses a run at the START into one disclosure, body chunks stay visible", () => {
    const { container } = renderLines([editorial(0), editorial(1), editorial(2), body(3), body(4)]);
    expect(container.querySelectorAll(".editorial-block")).toHaveLength(1);
    // The collapsed run's chunks are unmounted (Show), not just hidden.
    expect(container.querySelector('[data-chunk-id="c-0"]')).toBeNull();
    expect(container.querySelector('[data-chunk-id="c-1"]')).toBeNull();
    expect(container.querySelector('[data-chunk-id="c-2"]')).toBeNull();
    // Body chunks after the run render normally, outside any disclosure.
    const line3 = container.querySelector('[data-chunk-id="c-3"]');
    const line4 = container.querySelector('[data-chunk-id="c-4"]');
    expect(line3).not.toBeNull();
    expect(line4).not.toBeNull();
    expect(line3?.closest(".editorial-block")).toBeNull();
    expect(line4?.closest(".editorial-block")).toBeNull();
  });

  it("(b) collapses a run at the END into one disclosure", () => {
    const { container } = renderLines([body(0), body(1), editorial(2), editorial(3), editorial(4)]);
    expect(container.querySelectorAll(".editorial-block")).toHaveLength(1);
    expect(container.querySelector('[data-chunk-id="c-0"]')).not.toBeNull();
    expect(container.querySelector('[data-chunk-id="c-1"]')).not.toBeNull();
    expect(container.querySelector('[data-chunk-id="c-2"]')).toBeNull();
    expect(container.querySelector('[data-chunk-id="c-3"]')).toBeNull();
    expect(container.querySelector('[data-chunk-id="c-4"]')).toBeNull();
    // The single disclosure reports all three hidden chunks.
    const summary = container.querySelector(".editorial-block-summary");
    expect(summary?.textContent).toContain("3");
  });

  it("(c) two editorial runs separated by body chunks stay SEPARATE disclosures", () => {
    // This is the case that would fail if grouping merged non-adjacent
    // editorial runs (e.g. partitioning by block_type instead of walking
    // consecutive chunks): a buggy implementation would fold ords 0-1 and
    // 4-5 into a single disclosure of count 4, or reorder the body chunk
    // to the end. Neither may happen.
    const chunks = [editorial(0), editorial(1), body(2), body(3), editorial(4), editorial(5)];
    const { container } = renderLines(chunks);
    const blocks = container.querySelectorAll(".editorial-block");
    expect(blocks).toHaveLength(2);
    // Each disclosure hides exactly 2 chunks, not 4.
    for (const block of blocks) {
      expect(block.querySelector(".editorial-block-summary")?.textContent).toContain("2");
    }
    // The body run in between is visible and sits, in document order,
    // after the first disclosure and before the second.
    const line2 = container.querySelector('[data-chunk-id="c-2"]');
    expect(line2).not.toBeNull();
    expect(line2?.closest(".editorial-block")).toBeNull();
    const allNodes = Array.from(container.querySelectorAll(".editorial-block, [data-chunk-id]"));
    const positionOf = (el: Element | null | undefined) => (el ? allNodes.indexOf(el) : -1);
    expect(positionOf(blocks[0])).toBeLessThan(positionOf(line2));
    expect(positionOf(line2)).toBeLessThan(positionOf(blocks[1]));
  });

  it("(d) an all-editorial list collapses into a single disclosure covering every chunk", () => {
    const { container } = renderLines([editorial(0), editorial(1), editorial(2)]);
    const blocks = container.querySelectorAll(".editorial-block");
    expect(blocks).toHaveLength(1);
    expect(container.querySelectorAll("[data-chunk-id]")).toHaveLength(0);
    expect(blocks[0]?.querySelector(".editorial-block-summary")?.textContent).toContain("3");
  });
});

// #544: <For> reconciles on the referential identity of its ITEMS, not the
// array. `useWorkRange.tsx:296` appends via `[...cur.chunks, ...next.chunks]`
// — a new array wrapping the SAME chunk objects — specifically so that a
// `<For>` reading the chunks directly does not tear down and rebuild rows
// that didn't change. The editorial-run grouping interposed a fresh
// `{ editorial, items }` wrapper per run on every evaluation, which broke
// that: every row got rebuilt on every append regardless of whether its
// underlying chunk objects changed. A `createMemo` around the grouping call
// does NOT fix this because its only dependency, `props.chunks`, is exactly
// the array that changes on every append.
//
// These tests assert DOM node identity survives an append — the thing the
// bug actually breaks. Both were confirmed to FAIL against the pre-fix
// code (plain `groupEditorialRuns(props.chunks)` behind a `createMemo`,
// with no `hasEditorial` fast path) and PASS against the fix.
describe("Lines — reconciliation survives an infinite-scroll append (#544)", () => {
  it("keeps the same DOM node for an existing chunk when chunks grows with a new array (no editorial material)", () => {
    const [chunks, setChunks] = createSignal<SourceChunk[]>([body(0), body(1)]);
    const { container } = render(() => (
      <Lines
        chunks={chunks()}
        lang="eng"
        occMap={null}
        lemmaHighlights={null}
        onTermClick={vi.fn()}
        onWordClick={vi.fn()}
      />
    ));
    const captured = container.querySelector('[data-chunk-id="c-0"]');
    expect(captured).not.toBeNull();

    // Mirrors useWorkRange.tsx:296 exactly: a NEW array, the SAME chunk
    // objects, plus newly-appended ones.
    setChunks((cur) => [...cur, body(2), body(3)]);

    expect(container.querySelector('[data-chunk-id="c-0"]')).toBe(captured);
  });

  it("keeps the same DOM node inside an untouched editorial run when chunks grows with a new array", () => {
    const [chunks, setChunks] = createSignal<SourceChunk[]>([
      editorial(0),
      editorial(1),
      body(2),
      body(3),
    ]);
    const { container } = render(() => (
      <Lines
        chunks={chunks()}
        lang="eng"
        occMap={null}
        lemmaHighlights={null}
        onTermClick={vi.fn()}
        onWordClick={vi.fn()}
      />
    ));
    // The disclosure element for the untouched leading run...
    const capturedBlock = container.querySelector(".editorial-block");
    expect(capturedBlock).not.toBeNull();
    // ...and a rendered line inside the trailing body run, which is the
    // run that actually grows on this append.
    const capturedLine = container.querySelector('[data-chunk-id="c-2"]');
    expect(capturedLine).not.toBeNull();

    setChunks((cur) => [...cur, body(4), body(5)]);

    // The run that didn't change (editorial(0), editorial(1)) reconciles:
    // same disclosure element.
    expect(container.querySelector(".editorial-block")).toBe(capturedBlock);
    // The trailing body run grew, so its own rows are allowed to be
    // rebuilt — c-2 stays present but reconciliation of THAT run isn't
    // asserted here.
    expect(container.querySelector('[data-chunk-id="c-2"]')).not.toBeNull();
  });
});
