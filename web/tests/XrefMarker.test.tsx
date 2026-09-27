import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { XrefMarker } from "~/components/cards/XrefMarker";

describe("<XrefMarker /> superscript count", () => {
  it("renders the bare glyph with no superscript when count is omitted", () => {
    const { container } = render(() => <XrefMarker onOpen={() => undefined} />);
    expect(container.querySelector(".xref-count")).toBeNull();
    expect(screen.getByRole("button")).toHaveAccessibleName("Cross-reference on this passage");
  });

  it("renders no superscript for a single reference", () => {
    const { container } = render(() => <XrefMarker count={1} onOpen={() => undefined} />);
    expect(container.querySelector(".xref-count")).toBeNull();
    expect(screen.getByRole("button").textContent).toBe("▸");
  });

  it("renders the count as a superscript digit when count ≥ 2", () => {
    const { container } = render(() => <XrefMarker count={3} onOpen={() => undefined} />);
    const sup = container.querySelector(".xref-count");
    expect(sup?.textContent).toBe("³");
    expect(sup).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("button")).toHaveAccessibleName("3 cross-references on this passage");
  });

  it("marks itself active and hands its bounding rect to onOpen", () => {
    const onOpen = vi.fn();
    render(() => <XrefMarker count={2} active onOpen={onOpen} />);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("is-active");
    fireEvent.click(btn);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen.mock.calls[0]?.[0]).toEqual(btn.getBoundingClientRect());
  });
});
