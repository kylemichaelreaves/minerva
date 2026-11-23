import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import Composer from "~/features/Composer";

function renderComposer() {
  const onSend = vi.fn();
  const utils = render(() => <Composer onSend={onSend} />);
  return { onSend, ...utils };
}

describe("<Composer />", () => {
  it("renders scope, hint and send in one footer, in tab order", () => {
    const { container } = render(() => (
      <Composer onSend={vi.fn()} scopeChip={<button>scope</button>} />
    ));
    const left = container.querySelector(".compose-foot__left");
    expect(left).not.toBeNull();
    const scope = screen.getByRole("button", { name: "scope" });
    expect(left?.contains(scope)).toBe(true);
    const order = Array.from(container.querySelectorAll("textarea, button"));
    expect(order).toEqual([
      container.querySelector("textarea"),
      scope,
      container.querySelector(".compose-foot .compose-send"),
    ]);
  });

  it("shows a disabled send while awaiting a reply", () => {
    const { container } = render(() => <Composer onSend={vi.fn()} disabled />);
    expect(container.querySelector(".compose-send")).toBeDisabled();
  });

  it("Enter sends the trimmed value and clears the input", () => {
    const { onSend } = renderComposer();
    const ta = screen.getByRole("textbox");
    fireEvent.input(ta, { target: { value: "  what is justice?  " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("what is justice?");
    expect((ta as HTMLTextAreaElement).value).toBe("");
  });

  it("Shift+Enter does NOT send (newline behavior)", () => {
    const { onSend } = renderComposer();
    const ta = screen.getByRole("textbox");
    fireEvent.input(ta, { target: { value: "line one" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("does not fire onSend for whitespace-only input", () => {
    const { onSend } = renderComposer();
    const ta = screen.getByRole("textbox");
    fireEvent.input(ta, { target: { value: "   \n  " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Send button is disabled when empty and active when filled", () => {
    renderComposer();
    const btn = screen.getByRole("button", { name: /send/i });
    expect(btn.classList.contains("disabled")).toBe(true);
    fireEvent.input(screen.getByRole("textbox"), { target: { value: "hi" } });
    expect(btn.classList.contains("disabled")).toBe(false);
  });

  it("Send button click triggers onSend", () => {
    const { onSend } = renderComposer();
    fireEvent.input(screen.getByRole("textbox"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalledWith("hi");
  });

  it("uses the standard placeholder when enabled", () => {
    renderComposer();
    expect(screen.getByPlaceholderText(/continue the enquiry/i)).toBeInTheDocument();
  });

  it("disabled prop blocks Enter and disables the controls", () => {
    const onSend = vi.fn();
    render(() => <Composer onSend={onSend} disabled={true} />);
    const ta = screen.getByRole("textbox");
    expect((ta as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.input(ta, { target: { value: "hi" } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    const btn = screen.getByRole("button", { name: /send/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(btn);
    expect(onSend).not.toHaveBeenCalled();
  });

  it("disabled placeholder advertises the in-flight state", () => {
    render(() => <Composer onSend={vi.fn()} disabled={true} />);
    expect(screen.getByPlaceholderText(/awaiting reply/i)).toBeInTheDocument();
  });

  it("focuses its textarea on mount when asked (landing → chat)", () => {
    render(() => <Composer onSend={vi.fn()} focusOnMount />);
    expect(document.activeElement).toBe(screen.getByRole("textbox"));
  });

  it("leaves focus alone by default (sidebar picks, direct loads)", () => {
    render(() => <Composer onSend={vi.fn()} />);
    expect(document.activeElement).not.toBe(screen.getByRole("textbox"));
  });

  it("marks its wrap as entering while the transition runs", () => {
    const { container } = render(() => <Composer onSend={vi.fn()} entering />);
    expect(container.querySelector(".composer-wrap")).toHaveClass("lt-entering");
  });
});
