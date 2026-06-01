import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library";
import MobileTopBar from "~/components/MobileTopBar";

// MobileTopBar is a thin presentational shell — the value of these
// tests is pinning the prop wiring (hamburger fires, action renders
// the right element kind, title accepts JSX) so a future refactor
// of App.tsx's mobile-action dispatch doesn't silently drop a
// callback. Visual layout is verified in Storybook via the iphone14
// viewport.

describe("<MobileTopBar />", () => {
  it("fires onOpenDrawer when the hamburger is clicked", () => {
    const onOpenDrawer = vi.fn();
    render(() => <MobileTopBar onOpenDrawer={onOpenDrawer} title="Reader" />);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(onOpenDrawer).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("renders a plain string title", () => {
    render(() => (
      <MobileTopBar onOpenDrawer={vi.fn()} title="Cross-references" />
    ));
    expect(screen.getByText("Cross-references")).toBeInTheDocument();
    cleanup();
  });

  it("renders a JSX title (so italic accents work)", () => {
    render(() => (
      <MobileTopBar
        onOpenDrawer={vi.fn()}
        title={
          <>
            Plato · <em>Republic</em>
          </>
        }
      />
    ));
    // The italicized work title must be its own <em> so the design's
    // serif-italic accent picks it up. If a future refactor flattens
    // the title to a string the visual rhythm breaks.
    expect(screen.getByText("Republic").tagName).toBe("EM");
    cleanup();
  });

  it("renders the action as a button when onAction is provided", () => {
    const onAction = vi.fn();
    render(() => (
      <MobileTopBar
        onOpenDrawer={vi.fn()}
        title="Chat"
        action="Theme"
        onAction={onAction}
      />
    ));
    // There should be two buttons: hamburger + action.
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(2);
    fireEvent.click(screen.getByText("Theme"));
    expect(onAction).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("renders the action as a non-interactive span when onAction is omitted", () => {
    // Refs/Network pass `action=\"Filters\"` without an onAction —
    // the chip strip below carries the real affordance. Render it as
    // a span so screen readers don't announce a phantom button.
    render(() => (
      <MobileTopBar
        onOpenDrawer={vi.fn()}
        title="Refs"
        action="Filters"
      />
    ));
    expect(screen.queryAllByRole("button").length).toBe(1); // just the ham
    const el = screen.getByText("Filters");
    expect(el.tagName).toBe("SPAN");
    cleanup();
  });

  it("renders an empty action slot when no action is provided", () => {
    // The placeholder span keeps the 56/1fr/56 grid balanced so the
    // title stays optically centered even when there's nothing on
    // the right. Without this, the title drifts right.
    render(() => <MobileTopBar onOpenDrawer={vi.fn()} title="Chat" />);
    const placeholder = document.querySelector(".mobile-topbar-action");
    expect(placeholder).not.toBeNull();
    expect(placeholder?.getAttribute("aria-hidden")).toBe("true");
    cleanup();
  });
});
