// The cross-reference gutter marker in `<Lines>`.
//
// A row shows the marker only when the chunk has outgoing references AND the
// caller wired an open-handler; clicking it hands the handler the chunk it
// belongs to plus the marker's rect, which is what anchors the ReferenceCard.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@solidjs/testing-library";
import { Lines } from "~/Reader/components/Lines";
import type { SourceChunk } from "~/utils/types";
import { must } from "./helpers/must";

function chunk(id: string, ord: number): SourceChunk {
  return {
    chunk_id: id,
    section: `S${ord}`,
    book: null,
    page: null,
    speaker: null,
    text: `text ${ord}`,
    ord,
    block_type: null,
  };
}

const CHUNKS = [chunk("a", 0), chunk("b", 1)];

function renderLines(props: Partial<Parameters<typeof Lines>[0]> = {}) {
  return render(() => (
    <Lines
      chunks={CHUNKS}
      lang="deu"
      occMap={null}
      lemmaHighlights={null}
      onTermClick={vi.fn()}
      onWordClick={vi.fn()}
      {...props}
    />
  ));
}

describe("<Lines /> cross-reference marker", () => {
  it("renders the count on the chunk that has references and opens it on click", () => {
    const onXrefOpen = vi.fn();
    const { container } = renderLines({ xrefMap: { b: { count: 3 } }, onXrefOpen });

    const pins = container.querySelectorAll<HTMLButtonElement>(".xref-pin");
    expect(pins).toHaveLength(1);
    const pin = must(pins[0]);
    // It sits on row "b", not row "a".
    const lines = container.querySelectorAll(".line");
    expect(must(lines[1]).contains(pin)).toBe(true);
    expect(pin.textContent).toContain("³");

    // The marker's own rect is what anchors the card; pin it to a known one.
    const rect = { top: 40, left: 300, bottom: 56, right: 316, width: 16, height: 16 } as DOMRect;
    vi.spyOn(pin, "getBoundingClientRect").mockReturnValue(rect);

    fireEvent.click(pin);
    expect(onXrefOpen).toHaveBeenCalledTimes(1);
    expect(onXrefOpen).toHaveBeenCalledWith("b", rect);
  });

  it("marks the row whose reference card is open as active", () => {
    const { container } = renderLines({
      xrefMap: { a: { count: 1 }, b: { count: 2 } },
      onXrefOpen: vi.fn(),
      openRefChunkId: "a",
    });
    const pins = container.querySelectorAll(".xref-pin");
    expect(must(pins[0]).classList.contains("is-active")).toBe(true);
    expect(must(pins[1]).classList.contains("is-active")).toBe(false);
  });

  it("renders no marker without an open-handler, even when references exist", () => {
    const { container } = renderLines({ xrefMap: { b: { count: 3 } } });
    expect(container.querySelector(".xref-pin")).toBeNull();
  });
});
