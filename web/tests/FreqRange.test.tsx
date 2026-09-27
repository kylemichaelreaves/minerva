import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@solidjs/testing-library";
import { FilterBar, FreqRange, SEARCH_DEBOUNCE_MS } from "~/Concordance/components/FilterBar";
import { must } from "./helpers/must";

/** FreqRange stacks two native range inputs over a shared track.
 *  These tests exercise the clamping + undefined-edge logic, not the
 *  visual stacking. */
describe("<FreqRange />", () => {
  it("renders the active bounds on either edge of the track", () => {
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={vi.fn()} />
    ));
    const edges = container.querySelectorAll(".fbar-range .ed");
    expect(must(edges[0]).textContent).toBe("100");
    expect(must(edges[1]).textContent).toBe("5,000");
  });

  it("falls back to 1 (lo) and ceil (hi) when bounds are undefined", () => {
    const { container } = render(() => (
      <FreqRange min={undefined} max={undefined} ceil={10000} onChange={vi.fn()} />
    ));
    const edges = container.querySelectorAll(".fbar-range .ed");
    expect(must(edges[0]).textContent).toBe("1");
    expect(must(edges[1]).textContent).toBe("10,000");
  });

  it("releasing the upper knob below the ceiling reports the new max", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={undefined} max={undefined} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    // Two thumbs: index 0 = lower knob, index 1 = upper knob.
    fireEvent.change(must(thumbs[1]), { target: { value: "5000" } });
    expect(onChange).toHaveBeenCalledWith(undefined, 5000);
  });

  it("does NOT commit while dragging — input updates the labels only", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={undefined} max={undefined} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    // Mid-drag `input` events give live visual feedback without a
    // commit (each commit = URL patch + refetch).
    fireEvent.input(must(thumbs[1]), { target: { value: "7000" } });
    fireEvent.input(must(thumbs[1]), { target: { value: "5000" } });
    expect(onChange).not.toHaveBeenCalled();
    const edges = container.querySelectorAll(".fbar-range .ed");
    expect(must(edges[1]).textContent).toBe("5,000");
    // Release commits exactly once.
    fireEvent.change(must(thumbs[1]), { target: { value: "5000" } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(undefined, 5000);
  });

  it("releasing the upper knob at the ceiling clears the max bound", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.change(must(thumbs[1]), { target: { value: "10000" } });
    expect(onChange).toHaveBeenCalledWith(100, undefined);
  });

  it("releasing the lower knob at 1 clears the min bound", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={5000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.change(must(thumbs[0]), { target: { value: "1" } });
    expect(onChange).toHaveBeenCalledWith(undefined, 5000);
  });

  it("clamps the lower knob if the user drags it past the upper knob", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={100} max={500} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    // User releases the lower knob at 800 — past the upper at 500. The
    // emitted value clamps to the upper bound so the slider can't
    // invert.
    fireEvent.change(must(thumbs[0]), { target: { value: "800" } });
    expect(onChange).toHaveBeenCalledWith(500, 500);
  });

  it("clamps the upper knob if the user drags it below the lower knob", () => {
    const onChange = vi.fn();
    const { container } = render(() => (
      <FreqRange min={500} max={2000} ceil={10000} onChange={onChange} />
    ));
    const thumbs = container.querySelectorAll(".fbar-range .thumb");
    fireEvent.change(must(thumbs[1]), { target: { value: "100" } });
    expect(onChange).toHaveBeenCalledWith(500, 500);
  });
});

/** The lemma search box debounces its URL/refetch commit while keeping
 *  the typed value live in the input. */
describe("<FilterBar /> search debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function renderBar(onSetQ: (v: string | undefined) => void, q?: string) {
    return render(() => (
      <FilterBar
        lang="deu"
        sort="freq"
        freqCeil={10000}
        q={q}
        scope="corpus"
        authorOptions={[]}
        workOptions={[]}
        onPickAuthor={vi.fn()}
        onPickWork={vi.fn()}
        onSetLang={vi.fn()}
        onSetSort={vi.fn()}
        onSetPos={vi.fn()}
        onSetFreqRange={vi.fn()}
        onSetQ={onSetQ}
      />
    ));
  }

  function searchInput(container: HTMLElement): HTMLInputElement {
    return must(container.querySelector<HTMLInputElement>(".fbar-search input"));
  }

  it("keeps the input live but commits only after the debounce window", () => {
    const onSetQ = vi.fn();
    const { container } = renderBar(onSetQ);
    const input = searchInput(container);
    fireEvent.input(input, { target: { value: "G" } });
    fireEvent.input(input, { target: { value: "Ge" } });
    fireEvent.input(input, { target: { value: "Geist" } });
    // No commit per keystroke — but the input shows what was typed.
    expect(onSetQ).not.toHaveBeenCalled();
    expect(input.value).toBe("Geist");
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    expect(onSetQ).toHaveBeenCalledTimes(1);
    expect(onSetQ).toHaveBeenCalledWith("Geist");
  });

  it("restarts the debounce window on every keystroke", () => {
    const onSetQ = vi.fn();
    const { container } = renderBar(onSetQ);
    const input = searchInput(container);
    fireEvent.input(input, { target: { value: "G" } });
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50);
    fireEvent.input(input, { target: { value: "Ge" } });
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50);
    expect(onSetQ).not.toHaveBeenCalled();
    vi.advanceTimersByTime(50);
    expect(onSetQ).toHaveBeenCalledTimes(1);
    expect(onSetQ).toHaveBeenCalledWith("Ge");
  });

  it("Enter flushes immediately (no second commit when the timer lapses)", () => {
    const onSetQ = vi.fn();
    const { container } = renderBar(onSetQ);
    const input = searchInput(container);
    fireEvent.input(input, { target: { value: "Geist" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSetQ).toHaveBeenCalledTimes(1);
    expect(onSetQ).toHaveBeenCalledWith("Geist");
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 2);
    expect(onSetQ).toHaveBeenCalledTimes(1);
  });

  it("blur flushes immediately and clears to undefined on empty", () => {
    const onSetQ = vi.fn();
    const { container } = renderBar(onSetQ, "Geist");
    const input = searchInput(container);
    expect(input.value).toBe("Geist");
    fireEvent.input(input, { target: { value: "  " } });
    fireEvent.blur(input);
    expect(onSetQ).toHaveBeenCalledTimes(1);
    expect(onSetQ).toHaveBeenCalledWith(undefined);
  });

  it("does not commit when the value matches the URL-bound q", () => {
    const onSetQ = vi.fn();
    const { container } = renderBar(onSetQ, "Geist");
    const input = searchInput(container);
    fireEvent.input(input, { target: { value: "Geis" } });
    fireEvent.input(input, { target: { value: "Geist" } });
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    expect(onSetQ).not.toHaveBeenCalled();
  });
});
