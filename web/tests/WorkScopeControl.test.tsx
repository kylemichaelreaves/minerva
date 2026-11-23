import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import WorkScopeControl from "~/features/Composer/WorkScopeControl";
import type { Work } from "~/utils/types";

const ethica = { work_id: 1, author: "Spinoza", display_title: "Ethica" } as Work;

function mount(scope: { workId: number; title: string } | null, onSet = vi.fn()) {
  render(() => (
    <WorkScopeControl
      scope={() => scope}
      works={() => [ethica]}
      ensureWorks={() => Promise.resolve()}
      onSet={onSet}
    />
  ));
  return onSet;
}

describe("<WorkScopeControl /> pill", () => {
  it("offers 'All works' when unscoped", () => {
    mount(null);
    expect(screen.getByRole("button", { name: "Scope: All works" })).toBeInTheDocument();
  });

  it("names the work when scoped and can clear it", () => {
    const onSet = mount({ workId: 1, title: "Ethica" });
    expect(screen.getByRole("button", { name: "Scope: Ethica" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /clear scope/i }));
    expect(onSet).toHaveBeenCalledWith(null);
  });

  it("shows the work's full title on hover, for a pill that truncates it", () => {
    mount({ workId: 1, title: "Ethica ordine geometrico demonstrata" });
    expect(
      screen.getByRole("button", { name: "Scope: Ethica ordine geometrico demonstrata" }),
    ).toHaveAttribute("title", "Ethica ordine geometrico demonstrata");
  });

  it("opens the picker from the pill", () => {
    mount(null);
    fireEvent.click(screen.getByRole("button", { name: "Scope: All works" }));
    expect(screen.getByPlaceholderText(/filter works/i)).toBeInTheDocument();
  });
});
