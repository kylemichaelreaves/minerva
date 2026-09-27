// The collapsed sidebar's expand button — the only way back to the full
// sidebar once it has been collapsed.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@solidjs/testing-library";
import Sidebar from "~/features/Sidebar";

describe("<Sidebar /> collapsed", () => {
  it("offers an Expand button that calls onToggle, and hides the New label", () => {
    const onToggle = vi.fn();
    render(() => (
      <Sidebar
        collapsed
        onToggle={onToggle}
        history={[]}
        activeId={null}
        onPick={vi.fn()}
        onNew={vi.fn()}
        mode="chat"
      />
    ));

    // The New-conversation button stays, icon-only.
    expect(screen.getByTitle("New conversation")).toBeInTheDocument();
    expect(screen.queryByText("New conversation")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("has no Expand button while expanded", () => {
    render(() => (
      <Sidebar
        collapsed={false}
        onToggle={vi.fn()}
        history={[]}
        activeId={null}
        onPick={vi.fn()}
        onNew={vi.fn()}
        mode="chat"
      />
    ));
    expect(screen.queryByRole("button", { name: "Expand sidebar" })).toBeNull();
  });
});
