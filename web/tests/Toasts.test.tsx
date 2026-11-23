import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import Toasts from "~/components/primitives/Toasts";
import { _resetToastsForTesting, apiError } from "~/utils/apiError";

describe("<Toasts />", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    _resetToastsForTesting();
  });
  afterEach(() => {
    vi.useRealTimers();
    _resetToastsForTesting();
  });

  it("renders pushed toasts with accessible status region", () => {
    apiError("Couldn't load works.");
    render(() => <Toasts />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Couldn't load works.")).toBeInTheDocument();
  });

  it("dismisses a toast when the close button is clicked", () => {
    apiError("first");
    render(() => <Toasts />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("first")).toBeNull();
  });

  it("renders multiple toasts in insertion order", () => {
    apiError("alpha");
    apiError("beta");
    render(() => <Toasts />);
    const messages = screen.getAllByText(/alpha|beta/).map((el) => el.textContent);
    expect(messages).toEqual(["alpha", "beta"]);
  });
});
