import { describe, it, expect, vi } from "vitest";
import { render } from "@solidjs/testing-library";
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
