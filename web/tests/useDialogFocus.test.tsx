import { describe, it, expect } from "vitest";
import { createSignal } from "solid-js";
import { render, fireEvent, screen } from "@solidjs/testing-library";
import { useDialogFocus } from "~/hooks/useDialogFocus";

function Dialog(props: { withButtons: boolean }) {
  const [root, setRoot] = createSignal<HTMLDivElement>();
  useDialogFocus(root, () => true);
  return (
    <div ref={setRoot} role="dialog">
      {props.withButtons ? (
        <>
          <button type="button">first</button>
          <button type="button" disabled>
            skipped
          </button>
          <button type="button">middle</button>
          <button type="button">last</button>
          <button type="button" disabled>
            disabled-last
          </button>
        </>
      ) : (
        <p>nothing focusable</p>
      )}
    </div>
  );
}

const flush = () => new Promise<void>((r) => queueMicrotask(r));

describe("useDialogFocus Tab trap", () => {
  it("focuses the first focusable on open", async () => {
    render(() => <Dialog withButtons />);
    await flush();
    expect(document.activeElement).toBe(screen.getByText("first"));
  });

  it("wraps Tab from the last enabled focusable to the first", async () => {
    render(() => <Dialog withButtons />);
    await flush();
    screen.getByText("last").focus();
    const ev = fireEvent.keyDown(document, { key: "Tab" });
    expect(ev).toBe(false); // default prevented
    expect(document.activeElement).toBe(screen.getByText("first"));
  });

  it("wraps Shift+Tab from the first focusable to the last enabled one", async () => {
    render(() => <Dialog withButtons />);
    await flush();
    screen.getByText("first").focus();
    const ev = fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(ev).toBe(false);
    expect(document.activeElement).toBe(screen.getByText("last"));
  });

  it("pulls Shift+Tab back into the dialog when focus is outside it", async () => {
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    render(() => <Dialog withButtons />);
    await flush();
    outside.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("last"));
    outside.remove();
  });

  it("leaves Tab alone in the middle of the list and ignores other keys", async () => {
    render(() => <Dialog withButtons />);
    await flush();
    screen.getByText("middle").focus();
    expect(fireEvent.keyDown(document, { key: "Tab" })).toBe(true);
    expect(fireEvent.keyDown(document, { key: "Tab", shiftKey: true })).toBe(true);
    screen.getByText("last").focus();
    expect(fireEvent.keyDown(document, { key: "Enter" })).toBe(true);
    expect(document.activeElement).toBe(screen.getByText("last"));
  });

  it("does nothing, and does not throw, when the dialog has no focusables", async () => {
    render(() => <Dialog withButtons={false} />);
    await flush();
    const before = document.activeElement;
    expect(() => fireEvent.keyDown(document, { key: "Tab" })).not.toThrow();
    expect(fireEvent.keyDown(document, { key: "Tab", shiftKey: true })).toBe(true);
    expect(document.activeElement).toBe(before);
  });
});
