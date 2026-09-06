import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createRoot } from "solid-js";
import { ACCENTS, applyAccent, useTheme } from "~/theme";
import { flush } from "./helpers/testRouting";

/** A `matchMedia` that reports `matches` for the dark-scheme query.
 *
 *  The listener hooks are inert on purpose: nothing here fires a change
 *  event, and these tests only read the initial value. It used to take
 *  an `onChange` callback and an `addEventListener` that looked like it
 *  registered a handler, but no caller ever passed one and the mock
 *  never invoked it — the handler was discarded down both branches. */
function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("prefers-color-scheme: dark") ? matches : false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }));
}

describe("applyAccent()", () => {
  it("sets CSS custom properties from the accent palette", () => {
    applyAccent("light", "oxblood");
    const palette = ACCENTS.oxblood.light;
    expect(document.documentElement.style.getPropertyValue("--accent")).toBe(palette.accent);
    expect(document.documentElement.style.getPropertyValue("--accent-soft")).toBe(palette.soft);
    expect(document.documentElement.style.getPropertyValue("--selection")).toBe(
      palette.selection,
    );
  });
});

describe("useTheme()", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.removeProperty("--accent");
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("reads saved theme from localStorage", async () => {
    localStorage.setItem("minerva:theme", "dark");
    mockMatchMedia(false);
    await createRoot(async (dispose) => {
      const api = useTheme("oxblood");
      await flush();
      expect(api.theme()).toBe("dark");
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
      dispose();
    });
  });

  it("falls back to OS dark preference when nothing is saved", async () => {
    mockMatchMedia(true);
    await createRoot(async (dispose) => {
      const api = useTheme("oxblood");
      await flush();
      expect(api.theme()).toBe("dark");
      dispose();
    });
  });

  it("toggleTheme persists and flips light/dark", async () => {
    localStorage.setItem("minerva:theme", "light");
    mockMatchMedia(false);
    await createRoot(async (dispose) => {
      const api = useTheme("oxblood");
      await flush();
      expect(api.theme()).toBe("light");
      api.toggleTheme();
      await flush();
      expect(api.theme()).toBe("dark");
      expect(localStorage.getItem("minerva:theme")).toBe("dark");
      dispose();
    });
  });

  it("follows OS changes only before the user explicitly toggles", async () => {
    let changeHandler: ((e: MediaQueryListEvent) => void) | undefined;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: (_: string, handler: (e: MediaQueryListEvent) => void) => {
        if (query.includes("prefers-color-scheme")) changeHandler = handler;
      },
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));

    await createRoot(async (dispose) => {
      const api = useTheme("oxblood");
      await flush();
      expect(api.theme()).toBe("light");

      changeHandler?.({ matches: true } as MediaQueryListEvent);
      await flush();
      expect(api.theme()).toBe("dark");

      api.toggleTheme();
      await flush();
      changeHandler?.({ matches: false } as MediaQueryListEvent);
      await flush();
      expect(api.theme()).toBe("light");
      dispose();
    });
  });
});
