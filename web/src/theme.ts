// Theme + accent composable. Owns:
//   * the active light/dark signal,
//   * the OS `prefers-color-scheme` listener (only active until the
//     user explicitly toggles — see `userOverrode`),
//   * `localStorage` persistence,
//   * applying the accent palette to CSS custom properties.
//
// `useTheme` must be called from inside a Solid reactive root (i.e.
// `App()`).

import { createEffect, createSignal, onCleanup, onMount } from "solid-js";
import { ACCENTS } from "~/data";
import type { AccentKey, Theme } from "~/utils/types";

const STORAGE_KEY = "minerva:theme";

function readInitialTheme(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readInitialOverride(): boolean {
  // Track whether the user has explicitly toggled the theme. Without
  // this flag, the OS-preference listener would stop firing after the
  // initial `createEffect` writes a value to localStorage. Only the two
  // valid theme strings count as a real override; an empty / corrupted
  // entry is treated as "no preference" so OS-theme changes propagate.
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === "light" || saved === "dark";
}

export function applyAccent(theme: Theme, accentKey: AccentKey): void {
  const palette = ACCENTS[accentKey][theme];
  document.documentElement.style.setProperty("--accent", palette.accent);
  document.documentElement.style.setProperty("--accent-soft", palette.soft);
  document.documentElement.style.setProperty("--selection", palette.selection);
}

export interface ThemeApi {
  theme: () => Theme;
  toggleTheme: () => void;
}

export function useTheme(accentKey: AccentKey): ThemeApi {
  const [theme, setTheme] = createSignal<Theme>(readInitialTheme());
  const [userOverrode, setUserOverrode] = createSignal(readInitialOverride());

  // Apply theme + accent whenever they change. Persist only when the
  // user has explicitly toggled, so the OS-preference listener stays
  // effective for sessions where the theme was inferred rather than
  // chosen.
  createEffect(() => {
    const t = theme();
    document.documentElement.setAttribute("data-theme", t);
    if (userOverrode()) localStorage.setItem(STORAGE_KEY, t);
    applyAccent(t, accentKey);
  });

  // Follow OS theme changes only when the user hasn't explicitly chosen one.
  onMount(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      if (!userOverrode()) setTheme(e.matches ? "dark" : "light");
    };
    mq.addEventListener("change", handler);
    onCleanup(() => {
      mq.removeEventListener("change", handler);
    });
  });

  function toggleTheme() {
    setUserOverrode(true);
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  return { theme, toggleTheme };
}
