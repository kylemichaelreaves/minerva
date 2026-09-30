import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@solidjs/testing-library";
import {
  isActivatableTarget,
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

  it("leaves Enter to activatable controls (#702), but still navigates from them", () => {
    const onSelect = vi.fn();
    const { onNext, container } = setup({ onSelect });
    const make = (html: string): HTMLElement => {
      const wrap = document.createElement("div");
      wrap.innerHTML = html;
      container.appendChild(wrap);
      const el = wrap.querySelector<HTMLElement>("[data-t]");
      if (!el) throw new Error("fixture has no [data-t]");
      return el;
    };
    const chip = make('<button data-t type="button">chip</button>');
    const controls = [
      chip,
      make('<a data-t href="#/x">link</a>'),
      make('<div data-t role="button" tabindex="0">r</div>'),
      make('<span data-t role="link" tabindex="0">r</span>'),
      make('<li data-t role="option">o</li>'),
      make("<details><summary data-t>s</summary></details>"),
      // A child of a button (icon span) is still inside the control.
      make('<button type="button"><span data-t>icon</span></button>'),
    ];
    for (const el of controls) {
      const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
      el.dispatchEvent(enter);
      expect(enter.defaultPrevented, el.outerHTML).toBe(false);
    }
    expect(onSelect).not.toHaveBeenCalled();
    // Arrow/j navigation from a focused chip keeps working.
    fireEvent.keyDown(chip, { key: "j" });
    expect(onNext).toHaveBeenCalledTimes(1);
    // A plain anchor with no href is not a link; Enter still selects.
    const bare = make("<a data-t>back</a>");
    fireEvent.keyDown(bare, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(1);
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

describe("isActivatableTarget()", () => {
  it("is false for non-elements and plain containers", () => {
    expect(isActivatableTarget(null)).toBe(false);
    expect(isActivatableTarget(window)).toBe(false);
    expect(isActivatableTarget(document.createElement("div"))).toBe(false);
    expect(isActivatableTarget(document.createElement("button"))).toBe(true);
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
