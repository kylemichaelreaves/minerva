import { createContext, createSignal, onCleanup, useContext, type Accessor } from "solid-js";
import type { JSX } from "@solidjs/web";
import { useMobile } from "~/hooks/useMobile";

export type MobilePanel = "filters" | "reader-settings" | "thread-search";

export interface MobileSurfaceActions {
  openFilters?: () => void;
  openReaderSettings?: () => void;
  openThreadSearch?: () => void;
}

export interface MobileShellContextValue {
  isMobile: Accessor<boolean>;
  openMobilePanel: (panel: MobilePanel) => void;
  registerSurfaceActions: (actions: MobileSurfaceActions) => void;
  filtersSheetOpen: Accessor<boolean>;
  setFiltersSheetOpen: (open: boolean) => void;
  readerSettingsOpen: Accessor<boolean>;
  setReaderSettingsOpen: (open: boolean) => void;
  threadSearchOpen: Accessor<boolean>;
  setThreadSearchOpen: (open: boolean) => void;
}

// `null` default, not default-less: in Solid 2 a default-less context throws
// `ContextNotFoundError` from `useContext` outside a provider, and
// `useMobileShellOptional` below exists precisely to answer "no provider"
// without throwing. `null` is the documented optional-context form.
const MobileShellContext = createContext<MobileShellContextValue | null>(null);

export function MobileShellProvider(props: { children: JSX.Element }) {
  const isMobile = useMobile();
  const [filtersSheetOpen, setFiltersSheetOpen] = createSignal(false);
  const [readerSettingsOpen, setReaderSettingsOpen] = createSignal(false);
  const [threadSearchOpen, setThreadSearchOpen] = createSignal(false);
  // A STACK of registrations, not one slot. With a single slot (#200):
  // a surface supplying only `openFilters` erased a live surface's
  // `openReaderSettings`, and the cleanup reset the slot to `{}`
  // unconditionally, so an unmounting surface could wipe a
  // still-mounted one's handlers.
  //
  // Innermost-last, and resolution walks from the end, so the
  // most-recently-registered surface still wins a genuine conflict —
  // the previous behaviour for two surfaces claiming the same panel —
  // while a surface that says nothing about a panel no longer hides
  // whoever does. Cleanup removes only that surface's own entry, so
  // unmounting reveals the one beneath rather than the fallback.
  const registrations: MobileSurfaceActions[] = [];

  function registerSurfaceActions(actions: MobileSurfaceActions) {
    registrations.push(actions);
    onCleanup(() => {
      const at = registrations.lastIndexOf(actions);
      if (at !== -1) registrations.splice(at, 1);
    });
  }

  function handlerFor(key: keyof MobileSurfaceActions): (() => void) | undefined {
    for (let i = registrations.length - 1; i >= 0; i--) {
      const handler = registrations[i]?.[key];
      if (handler) return handler;
    }
    return undefined;
  }

  function openMobilePanel(panel: MobilePanel) {
    if (panel === "filters") {
      const open = handlerFor("openFilters");
      if (open) open();
      else setFiltersSheetOpen(true);
    } else if (panel === "reader-settings") {
      const open = handlerFor("openReaderSettings");
      if (open) open();
      else setReaderSettingsOpen(true);
    } else {
      // panel === "thread-search" — exhaustive after the union narrowing.
      const open = handlerFor("openThreadSearch");
      if (open) open();
      else setThreadSearchOpen(true);
    }
  }

  const value: MobileShellContextValue = {
    isMobile,
    openMobilePanel,
    registerSurfaceActions,
    filtersSheetOpen,
    setFiltersSheetOpen,
    readerSettingsOpen,
    setReaderSettingsOpen,
    threadSearchOpen,
    setThreadSearchOpen,
  };

  return <MobileShellContext value={value}>{props.children}</MobileShellContext>;
}

export function useMobileShell(): MobileShellContextValue {
  const ctx = useContext(MobileShellContext);
  if (!ctx) {
    throw new Error("useMobileShell must be used within MobileShellProvider");
  }
  return ctx;
}

/** Optional hook — returns undefined outside provider (for ComposeField). */
export function useMobileShellOptional(): MobileShellContextValue | undefined {
  return useContext(MobileShellContext) ?? undefined;
}

/** The shell's mobile flag when inside the provider, else the viewport's
 *  own breakpoint — for components that also render outside the shell
 *  (tests, stories). Call once per component, in its body. */
export function useIsMobile(): Accessor<boolean> {
  const shell = useMobileShellOptional();
  const fallback = useMobile();
  return () => shell?.isMobile() ?? fallback();
}
