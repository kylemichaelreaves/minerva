import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@solidjs/testing-library";
import { FreqRange } from "~/Concordance/components/FilterBar";

/** FreqRange stacks two native range inputs over a shared track.
 *  These tests exercise the clamping + undefined-edge logic, not the
 *  visual stacking. */
describe("<FreqRange />", () => {
  it("renders the active bounds on either edge of the track", () => {
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={vi.fn()} />
    ));
    const edges = container.querySelectorAll(".fbar-range .ed");
    expect(edges[0].textContent).toBe("100");
    expect(edges[1].textContent).toBe("5,000");
  });

  it("falls back to 1 (lo) and ceil (hi) when bounds are undefined", () => {
    const { container } = render(() => (
      <FreqRange
        min={undefined}
        max={undefined}
        ceil={10000}
        onChange={vi.fn()}
      />
    ));
    const edges = container.querySelectorAll(".fbar-range .ed");
    expect(edges[0].textContent).toBe("1");
    expect(edges[1].textContent).toBe("10,000");
  });

  it("dragging the upper knob below the ceiling reports the new max", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange
        min={undefined}
        max={undefined}
        ceil={10000}
        onChange={onChange}
      />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    // Two thumbs: index 0 = lower knob, index 1 = upper knob.
    fireEvent.input(thumbs[1], { target: { value: "5000" } });
    expect(onChange).toHaveBeenCalledWith(undefined, 5000);
  });

  it("dragging the upper knob to the ceiling clears the max bound", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.input(thumbs[1], { target: { value: "10000" } });
    expect(onChange).toHaveBeenCalledWith(100, undefined);
  });

  it("dragging the lower knob to 1 clears the min bound", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.input(thumbs[0], { target: { value: "1" } });
    expect(onChange).toHaveBeenCalledWith(undefined, 5000);
  });

  it("clamps the lower knob if the user drags it past the upper knob", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={500} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    // User drags lower knob to 800 — past the upper at 500. The
    // emitted value clamps to the upper bound so the slider can't
    // invert.
    fireEvent.input(thumbs[0], { target: { value: "800" } });
    expect(onChange).toHaveBeenCalledWith(500, 500);
  });

  it("clamps the upper knob if the user drags it below the lower knob", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={500} max={2000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.input(thumbs[1], { target: { value: "100" } });
    expect(onChange).toHaveBeenCalledWith(500, 500);
  });
});
