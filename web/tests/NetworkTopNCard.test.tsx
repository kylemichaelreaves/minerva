import { fireEvent, render, screen } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { describe, expect, it, vi } from "vitest";
import { NetworkTopNCard } from "~/Network/components/NetworkTopNCard";

interface Row {
  name: string;
}

const a: Row = { name: "Plato" };
const b: Row = { name: "Kant" };
const c: Row = { name: "Hegel" };

function rowTexts(): string[] {
  return screen.getAllByTestId("row").map((el) => el.textContent);
}

describe("<NetworkTopNCard />", () => {
  it("renders title, meta, and only the first `limit` rows with their index", () => {
    const onShowAll = vi.fn();
    render(() => (
      <NetworkTopNCard
        title="Top author pairs"
        meta="2 of 3"
        items={[a, b, c]}
        limit={2}
        dataPanel="toppairs"
        onShowAll={onShowAll}
        renderRow={(item, i) => <div data-testid="row">{`${i}:${item.name}`}</div>}
      />
    ));
    expect(screen.getByText("Top author pairs")).toBeTruthy();
    expect(screen.getByText("2 of 3")).toBeTruthy();
    expect(rowTexts()).toEqual(["0:Plato", "1:Kant"]);
    fireEvent.click(screen.getByRole("button", { name: "Show all 3 →" }));
    expect(onShowAll).toHaveBeenCalledTimes(1);
  });

  // Regression: the row body used to call `renderRow(item, i())` directly
  // inside <For>'s untracked mapper, so a row kept the index it was first
  // built with after the same object moved to a new position.
  it("re-renders a moved row with its NEW index", () => {
    const [items, setItems] = createSignal<Row[]>([a, b, c]);
    render(() => (
      <NetworkTopNCard
        title="t"
        meta="m"
        items={items()}
        limit={10}
        dataPanel="toppairs"
        renderRow={(item, i) => <div data-testid="row">{`${i}:${item.name}`}</div>}
      />
    ));
    expect(rowTexts()).toEqual(["0:Plato", "1:Kant", "2:Hegel"]);

    setItems([c, a, b]);
    expect(rowTexts()).toEqual(["0:Hegel", "1:Plato", "2:Kant"]);
    // No "Show all" affordance without an onShowAll handler.
    expect(screen.queryByRole("button")).toBeNull();
  });
});
