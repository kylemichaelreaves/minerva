import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import { UserTurnView } from "~/Thread/components/UserTurnView";

describe("<UserTurnView />", () => {
  // `.turn-user-inner` is the column wrapper that thread.css caps at `--col`
  // on wide screens so the question lines up with the composer below it.
  // The turn's own border stays full-width; only meta + body sit inside.
  it("wraps meta and body in .turn-user-inner", () => {
    const { container } = render(() => (
      <UserTurnView msg={{ role: "user", text: "What is Geist?", time: "10:00" }} />
    ));
    const inner = container.querySelector(".turn.turn-user > .turn-user-inner");
    expect(inner).not.toBeNull();
    expect(inner?.querySelector(".turn-meta")?.textContent).toBe("You · 10:00");
    expect(inner?.querySelector(".turn-body")?.textContent).toBe("What is Geist?");
  });
});
