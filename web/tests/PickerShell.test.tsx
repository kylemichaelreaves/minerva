/**
 * The filter-and-commit picker shell, shared by the relation and
 * part-of-speech pickers (#253).
 *
 * The invariant worth a test is the one both pickers depend on: THE FIELD
 * FILTERS, IT NEVER ACCEPTS. A mistyped relation or a pasted TIGER tag
 * validates, exports, and is wrong, and nothing downstream reports it — so
 * committing must be impossible unless a row is highlighted, whatever is in
 * the input.
 */
import { fireEvent, render, screen, cleanup } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PickerShell, type PickerGroup } from "~/Syntax/components/PickerShell";

afterEach(cleanup);

const INVENTORY: PickerGroup[] = [
  {
    title: "Open class",
    rows: [
      { name: "NOUN", gloss: "noun" },
      { name: "VERB", gloss: "verb" },
    ],
  },
  {
    title: "Closed class",
    rows: [
      { name: "DET", gloss: "determiner" },
      { name: "ADP", gloss: "preposition or postposition" },
    ],
  },
];

const filter = (query: string): PickerGroup[] => {
  const q = query.trim().toLowerCase();
  if (q === "") return INVENTORY;
  return INVENTORY.map((g) => ({
    title: g.title,
    rows: g.rows.filter((r) => r.name.toLowerCase().includes(q) || r.gloss.includes(q)),
  })).filter((g) => g.rows.length > 0);
};

function mount(overrides: Partial<Parameters<typeof PickerShell>[0]> = {}) {
  const onCommit = vi.fn();
  const onCancel = vi.fn();
  render(() => (
    <PickerShell
      label="Part of speech"
      dialogLabel="Retag hinweg"
      filterLabel="Filter parts of speech"
      listLabel="Parts of speech"
      groups={filter}
      current="ADV"
      currentGloss="adverb"
      total={4}
      footNote="UD v2"
      emptyHint={(q) => <>Nothing matches “{q}”.</>}
      onCommit={onCommit}
      onCancel={onCancel}
      {...overrides}
    />
  ));
  const input = () => screen.getByLabelText("Filter parts of speech");
  return { onCommit, onCancel, input };
}

describe("<PickerShell />", () => {
  it("renders every group and row, with the current value pinned above", () => {
    mount();
    expect(screen.getByText("Open class")).toBeTruthy();
    expect(screen.getByText("Closed class")).toBeTruthy();
    expect(screen.getAllByText("NOUN").length).toBeGreaterThan(0);
    // The pinned current row shows the value and its gloss.
    expect(screen.getByText("adverb")).toBeTruthy();
  });

  it("focuses the filter input on mount, so typing narrows immediately", () => {
    const { input } = mount();
    expect(document.activeElement).toBe(input());
  });

  it("commits the highlighted row on Enter", () => {
    const { onCommit, input } = mount();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("NOUN");
  });

  it("moves the highlight with the arrow keys and wraps around", () => {
    const { onCommit, input } = mount();
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("VERB");

    cleanup();
    const second = mount();
    // Up from the first row wraps to the last.
    fireEvent.keyDown(second.input(), { key: "ArrowUp" });
    fireEvent.keyDown(second.input(), { key: "Enter" });
    expect(second.onCommit).toHaveBeenCalledWith("ADP");
  });

  it("commits the row that is left highlighted after filtering", () => {
    const { onCommit, input } = mount();
    fireEvent.input(input(), { target: { value: "adp" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("ADP");
  });

  it("NEVER commits the raw text when nothing matches", () => {
    // The whole point. `NN` is a TIGER tag: shaped like a UD tag, absent from
    // the inventory, and silent corruption if it were ever written.
    const { onCommit, input } = mount();
    fireEvent.input(input(), { target: { value: "NN" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("says what cannot be written when the filter matches nothing", () => {
    const { input } = mount();
    fireEvent.input(input(), { target: { value: "zzz" } });
    expect(screen.getByText(/Nothing matches/)).toBeTruthy();
  });

  it("commits on click", () => {
    const { onCommit } = mount();
    fireEvent.click(screen.getByText("determiner"));
    expect(onCommit).toHaveBeenCalledWith("DET");
  });

  it("commits on Enter against a focused row, for keyboard-only list users", () => {
    const { onCommit } = mount();
    const row = screen.getByText("ADP").closest('[role="option"]');
    fireEvent.keyDown(row!, { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("ADP");
  });

  it("cancels on Escape", () => {
    const { onCancel, input } = mount();
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });

  it("counts matches against the whole inventory in the footer", () => {
    const { input } = mount();
    expect(screen.getByText(/4 of 4/)).toBeTruthy();
    fireEvent.input(input(), { target: { value: "adp" } });
    expect(screen.getByText(/1 of 4/)).toBeTruthy();
  });

  it("is a real dialog with focusable options", () => {
    // `role="dialog"` on an <aside> is not honoured by every screen reader,
    // and an `option` that cannot take focus is unreachable to one driving
    // the list directly.
    mount();
    const dialog = screen.getByLabelText("Retag hinweg");
    expect(dialog.tagName).toBe("DIALOG");
    for (const opt of screen.getAllByRole("option")) {
      expect(opt.getAttribute("tabindex")).toBe("-1");
    }
  });

  it("omits the pinned row when there is no current value", () => {
    mount({ current: null, currentGloss: undefined });
    expect(screen.queryByText("adverb")).toBeNull();
  });
});
