/**
 * `<MobileSheet>` had no test file at all — 18 units at 50% coverage, the
 * second-worst in `components/` after `XrefMarker`. It gets one here because
 * the a11y repair below changes its markup, and #324 moves the file, which
 * puts its whole surface in front of SonarCloud's new-code coverage gate.
 *
 * The repair: the scrim was a bare `<div onClick>` (typescript:S6848 +
 * typescript:S1082) — dismissal reachable by mouse and by nothing else. It is
 * a real <button> now, which is focusable and Enter/Space-operable for free.
 * Escape already closed the sheet and still does; that path is pinned too, so
 * the two dismissals cannot drift apart.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library";
import { MobileSheet } from "~/components/MobileSheet";

afterEach(cleanup);

function renderSheet(open = true) {
  const onClose = vi.fn();
  const utils = render(() => (
    <MobileSheet open={open} title="Filters" onClose={onClose}>
      <p>sheet body</p>
    </MobileSheet>
  ));
  return { onClose, ...utils };
}

describe("<MobileSheet />", () => {
  it("renders nothing when closed", () => {
    renderSheet(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the title, the body and the Done control when open", () => {
    renderSheet();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByText("sheet body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("labels the dialog with its title", () => {
    renderSheet();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-label", "Filters");
  });

  it("puts the scrim dismissal on a keyboard-operable control (#324)", () => {
    renderSheet();
    const scrim = document.querySelector(".mobile-sheet-scrim");
    expect(scrim).not.toBeNull();
    expect(scrim!.tagName).toBe("BUTTON");
    expect(scrim!.getAttribute("aria-label")).toBe("Dismiss");
  });

  it("clicking the scrim closes the sheet", () => {
    const { onClose } = renderSheet();
    fireEvent.click(document.querySelector(".mobile-sheet-scrim")!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Done closes the sheet", () => {
    const { onClose } = renderSheet();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape closes the sheet", () => {
    const { onClose } = renderSheet();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape does nothing once the sheet is closed", () => {
    const { onClose } = renderSheet(false);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
