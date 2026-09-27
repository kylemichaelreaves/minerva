import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import ConfirmDialog from "~/components/primitives/ConfirmDialog";
import { must } from "./helpers/must";

function renderDialog(overrides: Partial<{ open: boolean }> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const utils = render(() => (
    <ConfirmDialog
      open={overrides.open ?? true}
      title="Delete this conversation?"
      message="This can't be undone."
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  ));
  return { onConfirm, onCancel, ...utils };
}

describe("<ConfirmDialog />", () => {
  it("renders nothing when closed", () => {
    renderDialog({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders title, message, and the two action buttons when open", () => {
    renderDialog();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Delete this conversation?")).toBeInTheDocument();
    expect(screen.getByText("This can't be undone.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("Esc cancels", () => {
    const { onCancel, onConfirm } = renderDialog();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter confirms when focus is inside the dialog", () => {
    const { onCancel, onConfirm } = renderDialog();
    // Focus trap keeps focus inside the dialog; simulate that.
    screen.getByRole("button", { name: "Delete" }).focus();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("Enter does NOT confirm when focus is outside the dialog", () => {
    // A stray Enter while the user is typing in a background field must
    // not delete the conversation (issue #60).
    const outside = document.createElement("input");
    document.body.appendChild(outside);
    const { onConfirm } = renderDialog();
    outside.focus();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onConfirm).not.toHaveBeenCalled();
    outside.remove();
  });

  // The scrim used to be a bare `<div onClick>` wrapping the dialog, which
  // reached a mouse and nothing else (typescript:S6848 + typescript:S1082).
  // The dismissal now lives on a real <button> laid over the scrim, so it is
  // focusable and Enter/Space-operable for free — and because the dialog is a
  // sibling rather than a child, the `stopPropagation` shim that used to sit
  // on it (typescript:S6847 + typescript:S1082) is gone too.
  it("puts the outside-click cancel on a keyboard-operable control (#324)", () => {
    renderDialog();
    const hit = document.querySelector(".dialog-scrim-hit");
    expect(hit).not.toBeNull();
    expect(must(hit).tagName).toBe("BUTTON");
    // Named distinctly from the visible ghost button, so `getByRole("button",
    // { name: "Cancel" })` still resolves to exactly one element.
    expect(must(hit).getAttribute("aria-label")).toBe("Dismiss");
  });

  it("clicking the scrim cancels", () => {
    const { onCancel } = renderDialog();
    const scrim = must(document.querySelector(".dialog-scrim-hit"));
    fireEvent.click(scrim);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("the scrim control carries no click handler on the scrim itself", () => {
    // Pins the structure the a11y fix depends on: clicking the scrim element
    // does nothing, because the handler is on the button layered over it.
    const { onCancel } = renderDialog();
    fireEvent.click(must(document.querySelector(".dialog-scrim")));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("clicking inside the dialog does not cancel", () => {
    const { onCancel } = renderDialog();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("clicking Cancel and Delete buttons dispatches the right callbacks", () => {
    const { onCancel, onConfirm } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("keyboard handler stops firing once the dialog closes", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const [open, setOpen] = createSignal(true);
    render(() => (
      <ConfirmDialog
        open={open()}
        title="t"
        message="m"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    ));
    setOpen(false);
    fireEvent.keyDown(window, { key: "Enter" });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("uses custom labels when supplied", () => {
    render(() => (
      <ConfirmDialog
        open={true}
        title="t"
        message="m"
        confirmLabel="Erase"
        cancelLabel="Keep"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    ));
    expect(screen.getByRole("button", { name: "Erase" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep" })).toBeInTheDocument();
    cleanup();
  });
});
