import { fireEvent, render, screen } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { describe, expect, it, vi } from "vitest";
import { FilterMenuChip } from "~/Network/components/FilterMenuChip";

const options = [
  { key: "class", label: "Classical" },
  { key: "scrip", label: "Scripture" },
];

function mount(selected: string[]) {
  const onToggle = vi.fn();
  const onClear = vi.fn();
  render(() => (
    <FilterMenuChip
      label="Corpus"
      value={selected.length ? `${selected.length}` : "all"}
      active={selected.length > 0}
      options={options}
      selected={selected}
      onToggle={onToggle}
      onClear={onClear}
    />
  ));
  fireEvent.click(screen.getByTitle("Corpus filter"));
  flush();
  return { onToggle, onClear };
}

describe("<FilterMenuChip />", () => {
  it("Clear calls onClear when something is selected", () => {
    const { onClear, onToggle } = mount(["scrip"]);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    flush();
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("hides Clear when nothing is selected, and toggles an option by key", () => {
    const { onToggle } = mount([]);
    expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Classical/ }));
    flush();
    expect(onToggle).toHaveBeenCalledWith("class");
  });
});
