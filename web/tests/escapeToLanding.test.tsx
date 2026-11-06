import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@solidjs/testing-library";
import type { Turn } from "~/utils/uiTypes";
import {
  chatIsSettled,
  isPlainEscape,
  useUnclaimedEscape,
  wouldDropInput,
} from "~/features/LandingTransition/escapeToLanding";

const key = (init: KeyboardEventInit) =>
  new KeyboardEvent("keydown", { key: "Escape", cancelable: true, ...init });

describe("isPlainEscape", () => {
  it("is a bare Escape only", () => {
    expect(isPlainEscape(key({}))).toBe(true);
    expect(isPlainEscape(key({ key: "Enter" }))).toBe(false);
    expect(isPlainEscape(key({ repeat: true }))).toBe(false);
    expect(isPlainEscape(key({ isComposing: true }))).toBe(false);
    for (const mod of ["altKey", "ctrlKey", "metaKey", "shiftKey"] as const) {
      expect(isPlainEscape(key({ [mod]: true }))).toBe(false);
    }
  });
});

describe("wouldDropInput", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function chatComposer(value = "") {
    document.body.innerHTML =
      '<div class="composer"><textarea class="composer-input"></textarea></div><input id="other" /><div id="edit" contenteditable="true"></div><button id="btn"></button>';
    const ta = document.querySelector<HTMLTextAreaElement>(".composer-input");
    if (!ta) throw new Error("no composer");
    ta.value = value;
    return ta;
  }

  it("is false for an empty composer, focused or not", () => {
    const ta = chatComposer();
    expect(wouldDropInput()).toBe(false);
    ta.focus();
    expect(wouldDropInput()).toBe(false);
    document.getElementById("btn")?.focus();
    expect(wouldDropInput()).toBe(false);
  });

  it("is true over a draft, even a blurred one", () => {
    chatComposer("and Kant?");
    expect(wouldDropInput()).toBe(true);
  });

  it("ignores a whitespace-only draft", () => {
    chatComposer("   \n");
    expect(wouldDropInput()).toBe(false);
  });

  it("is true while another field has focus", () => {
    chatComposer();
    document.getElementById("other")?.focus();
    expect(wouldDropInput()).toBe(true);
  });

  it("is true while a contenteditable has focus", () => {
    chatComposer();
    const el = document.getElementById("edit");
    // jsdom does not implement isContentEditable.
    if (el) Object.defineProperty(el, "isContentEditable", { value: true });
    el?.focus();
    expect(wouldDropInput()).toBe(true);
  });

  it("is false with no composer and nothing focused", () => {
    expect(wouldDropInput()).toBe(false);
  });
});

describe("useUnclaimedEscape", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function mount() {
    const onEscape = vi.fn();
    const utils = render(() => {
      useUnclaimedEscape(onEscape);
      return null;
    });
    return { onEscape, ...utils };
  }

  it("fires for an Escape nobody claimed, after dispatch", () => {
    const { onEscape } = mount();
    window.dispatchEvent(key({}));
    expect(onEscape).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(onEscape).toHaveBeenCalledOnce();
  });

  it("stays out of an Escape a later listener claimed", () => {
    const { onEscape } = mount();
    // Registered after the hook, as a popover's would be.
    const claim = (e: KeyboardEvent) => e.preventDefault();
    window.addEventListener("keydown", claim);
    window.dispatchEvent(key({}));
    vi.runAllTimers();
    window.removeEventListener("keydown", claim);
    expect(onEscape).not.toHaveBeenCalled();
  });

  it("ignores other keys", () => {
    const { onEscape } = mount();
    window.dispatchEvent(key({ key: "a" }));
    vi.runAllTimers();
    expect(onEscape).not.toHaveBeenCalled();
  });

  it("stops listening on unmount, a pending press included", () => {
    const { onEscape, unmount } = mount();
    window.dispatchEvent(key({}));
    unmount();
    vi.runAllTimers();
    window.dispatchEvent(key({}));
    vi.runAllTimers();
    expect(onEscape).not.toHaveBeenCalled();
  });
});

describe("chatIsSettled", () => {
  const answered = { role: "minerva", streaming: false } as Turn;
  const base = {
    onLanding: false,
    thinking: false,
    hydrating: false,
    transitioning: false,
    last: answered,
  };

  it("is settled once a reply has finished", () => {
    expect(chatIsSettled(base)).toBe(true);
    expect(chatIsSettled({ ...base, last: undefined })).toBe(true);
    expect(chatIsSettled({ ...base, last: { role: "user" } as Turn })).toBe(true);
  });

  it.each([
    ["on the landing already", { onLanding: true }],
    ["considering", { thinking: true }],
    ["loading a conversation", { hydrating: true }],
    ["mid-transition", { transitioning: true }],
    ["streaming a reply", { last: { role: "minerva", streaming: true } as Turn }],
  ])("is not settled while %s", (_, over) => {
    expect(chatIsSettled({ ...base, ...over })).toBe(false);
  });
});
