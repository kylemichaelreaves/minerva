import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { FilterChipGroup } from "~/Concordance/components/FilterChipGroup";

const BUCKETS = [
  { value: "Nom", count: 10 },
  { value: "Acc", count: 4 },
];

function renderGroup(props: { applied?: string; onClear?: () => void; selected?: string }) {
  const onToggle = vi.fn();
  const utils = render(() => (
    <FilterChipGroup
      label="Case"
      applied={props.applied}
      onClear={props.onClear}
      selected={props.selected}
      buckets={BUCKETS}
      labelFor={(v) => v.toUpperCase()}
      titleFor={(b) => `${b.count} hits`}
      onToggle={onToggle}
    />
  ));
  return { ...utils, onToggle };
}

describe("<FilterChipGroup /> clear control", () => {
  it("shows no badge and no clear link when nothing is applied, even with onClear", () => {
    const { container } = renderGroup({ onClear: vi.fn() });
    expect(container.querySelector(".applied")).toBeNull();
    expect(screen.queryByText("clear")).toBeNull();
  });

  it("shows the badge but no clear link when applied without onClear", () => {
    const { container } = renderGroup({ applied: "Accusative" });
    expect(container.querySelector(".applied")?.textContent).toBe("· Accusative");
    expect(screen.queryByText("clear")).toBeNull();
  });

  it("shows the clear link when applied with onClear, and clicking it calls onClear", () => {
    const onClear = vi.fn();
    renderGroup({ applied: "Accusative", onClear });
    // A real button, so it is reachable and operable from the keyboard.
    const clear = screen.getByRole("button", { name: "clear" });
    expect(clear).toHaveAttribute("type", "button");
    fireEvent.click(clear);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

describe("<FilterChipGroup /> chips", () => {
  it("labels chips, marks the selected one, and toggles on click", () => {
    const { onToggle } = renderGroup({ selected: "Acc" });
    const acc = screen.getByText("ACC");
    const nom = screen.getByText("NOM");
    expect(acc).toHaveClass("on");
    expect(nom).not.toHaveClass("on");
    expect(nom).toHaveAttribute("title", "10 hits");
    fireEvent.click(nom);
    expect(onToggle).toHaveBeenLastCalledWith("Nom");
    fireEvent.click(acc);
    expect(onToggle).toHaveBeenLastCalledWith(undefined);
  });
});
