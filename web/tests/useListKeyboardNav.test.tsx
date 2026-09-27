import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@solidjs/testing-library";
import {
  isEditableTarget,
  useListKeyboardNav,
  type ListKeyboardNavOpts,
} from "~/hooks/useListKeyboardNav";

function Harness(props: { opts: ListKeyboardNavOpts }) {
  // eslint-disable-next-line solid/reactivity -- the hook takes its options once at setup, as its real callers do; each test mounts a fresh harness
  useListKeyboardNav(props.opts);
  return <div data-testid="page" />;
}

function setup(opts: Partial<ListKeyboardNavOpts> = {}) {
  const onNext = vi.fn();
  const onPrev = vi.fn();
  const full: ListKeyboardNavOpts = { onNext, onPrev, ...opts };
  const utils = render(() => <Harness opts={full} />);
  return { onNext, onPrev, ...utils };
}

describe("useListKeyboardNav()", () => {
  it("maps j/ArrowDown to next and k/ArrowUp to prev", () => {
    const { onNext, onPrev } = setup();
    fireEvent.keyDown(document.body, { key: "j" });
    fireEvent.keyDown(document.body, { key: "ArrowDown" });
    fireEvent.keyDown(document.body, { key: "k" });
    fireEvent.keyDown(document.body, { key: "ArrowUp" });
    expect(onNext).toHaveBeenCalledTimes(2);
    expect(onPrev).toHaveBeenCalledTimes(2);
  });

  it("maps ArrowRight/ArrowLeft only when horizontal", () => {
    const a = setup();
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    expect(a.onNext).not.toHaveBeenCalled();
    expect(a.onPrev).not.toHaveBeenCalled();
    a.unmount();

    const b = setup({ horizontal: true });
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    expect(b.onNext).toHaveBeenCalledTimes(1);
    expect(b.onPrev).toHaveBeenCalledTimes(1);
  });

  it("fires Enter/Escape handlers only when provided", () => {
    const onSelect = vi.fn();
    const onEscape = vi.fn();
    const a = setup(); // no onSelect/onEscape — keys pass through
    fireEvent.keyDown(document.body, { key: "Enter" });
    fireEvent.keyDown(document.body, { key: "Escape" });
    a.unmount();

    setup({ onSelect, onEscape });
    fireEvent.keyDown(document.body, { key: "Enter" });
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("ignores keys originating in form elements", () => {
    const { onNext, container } = setup();
    for (const tag of ["input", "textarea", "select"] as const) {
      const el = document.createElement(tag);
      container.appendChild(el);
      fireEvent.keyDown(el, { key: "ArrowDown" });
    }
    expect(onNext).not.toHaveBeenCalled();
  });

  it("ignores keys originating in contenteditable regions", () => {
    const { onNext, container } = setup();
    const el = document.createElement("div");
    el.setAttribute("contenteditable", "true");
    // jsdom doesn't compute isContentEditable from the attribute.
    Object.defineProperty(el, "isContentEditable", { value: true });
    container.appendChild(el);
    fireEvent.keyDown(el, { key: "j" });
    expect(onNext).not.toHaveBeenCalled();
  });

  it("is fully muted while `enabled` returns false (modal/sheet open)", () => {
    const onEscape = vi.fn();
    const { onNext } = setup({ enabled: () => false, onEscape });
    fireEvent.keyDown(document.body, { key: "j" });
    // Escape must reach the sheet's own handler, not ours.
    const escEvent = new KeyboardEvent("keydown", { key: "Escape", cancelable: true });
    document.body.dispatchEvent(escEvent);
    expect(onNext).not.toHaveBeenCalled();
    expect(onEscape).not.toHaveBeenCalled();
    expect(escEvent.defaultPrevented).toBe(false);
  });

  it("ignores modified keystrokes unless the onKey pre-handler claims them", () => {
    const onKey = vi.fn((e: KeyboardEvent) => e.key === "ArrowUp" && e.metaKey);
    const { onNext, onPrev } = setup({ onKey });
    // Meta chord the pre-handler claims: default mapping skipped.
    fireEvent.keyDown(document.body, { key: "ArrowUp", metaKey: true });
    expect(onKey).toHaveBeenCalled();
    expect(onPrev).not.toHaveBeenCalled();
    // Unclaimed modified keystroke: nothing fires.
    fireEvent.keyDown(document.body, { key: "ArrowDown", ctrlKey: true });
    expect(onNext).not.toHaveBeenCalled();
    // Plain keystroke still maps normally.
    fireEvent.keyDown(document.body, { key: "ArrowDown" });
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("removes the window listener on unmount", () => {
    const { onNext, unmount } = setup();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(onNext).toHaveBeenCalledTimes(1);
    unmount();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});

describe("isEditableTarget()", () => {
  it("flags inputs, textareas, selects; not divs or buttons", () => {
    expect(isEditableTarget(document.createElement("input"))).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("select"))).toBe(true);
    expect(isEditableTarget(document.createElement("div"))).toBe(false);
    expect(isEditableTarget(document.createElement("button"))).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
});
