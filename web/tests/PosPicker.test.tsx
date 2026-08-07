/**
 * The part-of-speech picker as wired to the real inventory (#253).
 *
 * `PickerShell.test.tsx` covers the interaction against a fake inventory;
 * this covers the adapter — that the real 17 tags reach the list, that the
 * current tag's gloss is looked up, and that the empty state names the mistake
 * it exists to prevent.
 */
import { fireEvent, render, screen, cleanup } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PosPicker } from "~/Syntax/components/PosPicker";

afterEach(cleanup);

function mount(current: string | null = "ADV") {
  const onCommit = vi.fn();
  const onCancel = vi.fn();
  render(() => (
    <PosPicker
      form="hinweg"
      tokenId={20}
      current={current}
      onCommit={onCommit}
      onCancel={onCancel}
    />
  ));
  return { onCommit, onCancel, input: () => screen.getByLabelText("Filter parts of speech") };
}

describe("<PosPicker />", () => {
  it("offers the real UD inventory, grouped", () => {
    mount();
    expect(screen.getByText("Open class")).toBeTruthy();
    expect(screen.getByText("Closed class")).toBeTruthy();
    expect(screen.getByText("Other")).toBeTruthy();
    // Including the three the reader's POS_LABEL map omits.
    expect(screen.getByText("PUNCT")).toBeTruthy();
    expect(screen.getByText("SYM")).toBeTruthy();
    expect(screen.getByText("X")).toBeTruthy();
    expect(screen.getByText(/17 of 17/)).toBeTruthy();
  });

  it("names the token it is retagging", () => {
    mount();
    expect(screen.getByLabelText("Retag hinweg")).toBeTruthy();
  });

  it("glosses the current tag from the inventory", () => {
    mount("ADV");
    // "adverb" appears twice — the pinned current row and ADV's own list row —
    // so scope to the pinned one, which is what the lookup feeds.
    const pinned = document.querySelector(".syn-prow.syn-cur");
    expect(pinned?.textContent).toContain("ADV");
    expect(pinned?.textContent).toContain("adverb");
  });

  it("commits the canonical upper-case tag", () => {
    const { onCommit, input } = mount();
    fireEvent.input(input(), { target: { value: "adp" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("ADP");
  });

  it("refuses a TIGER tag by having nothing to commit, and says so", () => {
    const { onCommit, input } = mount();
    fireEvent.input(input(), { target: { value: "NN" } });

    expect(onCommit).not.toHaveBeenCalled();
    expect(screen.getByText(/cannot be written here/)).toBeTruthy();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("works with no current tag", () => {
    mount(null);
    expect(screen.getByText(/17 of 17/)).toBeTruthy();
  });
});
