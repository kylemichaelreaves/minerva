import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import { flush } from "solid-js";
import WorkScopeControl from "~/features/Composer/WorkScopeControl";

function mount() {
  render(() => (
    <WorkScopeControl
      scope={() => null}
      works={() => []}
      ensureWorks={() => Promise.resolve()}
      onSet={vi.fn()}
    />
  ));
}

const escape = () => {
  const e = new KeyboardEvent("keydown", { key: "Escape", cancelable: true });
  window.dispatchEvent(e);
  // Settled like `fireEvent`: the close is a signal write Solid 2 commits at
  // the next flush.
  flush();
  return e;
};

describe("<WorkScopeControl /> and Escape", () => {
  it("leaves Escape alone while its picker is closed", () => {
    // Claiming it closed made every Escape in the chat look taken, so the
    // chat's Escape-to-landing never fired.
    mount();
    expect(escape().defaultPrevented).toBe(false);
  });

  it("claims Escape to close an open picker", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Scope: All works" }));
    expect(screen.getByRole("dialog", { name: /scope chat to a work/i })).toBeInTheDocument();

    expect(escape().defaultPrevented).toBe(true);
    expect(screen.queryByRole("dialog", { name: /scope chat to a work/i })).toBeNull();
  });
});
