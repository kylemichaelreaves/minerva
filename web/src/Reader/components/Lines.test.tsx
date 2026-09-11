// Coverage for `groupEditorialRuns` and its render wiring in Lines.tsx.
// The function itself isn't exported — these tests exercise it through
// the rendered output, which also proves the `<EditorialBlock>` wiring
// (Step 5 of the editorial-apparatus plan, #534) is correct end to end.

import { render } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import type { SourceChunk } from "~/utils/types";
import { Lines } from "./Lines";

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
