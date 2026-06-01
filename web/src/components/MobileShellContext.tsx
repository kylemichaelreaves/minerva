import {
  createContext,
  createSignal,
  onCleanup,
  useContext,
  type Accessor,
  type JSX,
} from "solid-js";
import { useMobile } from "~/hooks/useMobile";

export type MobilePanel = "filters" | "reader-settings" | "thread-search";

export interface MobileSurfaceActions {
  openFilters?: () => void;
  openReaderSettings?: () => void;
  openThreadSearch?: () => void;
}

interface MobileShellContextValue {
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

const MobileShellContext = createContext<MobileShellContextValue>();

export function MobileShellProvider(props: { children: JSX.Element }) {
  const isMobile = useMobile();
  const [filtersSheetOpen, setFiltersSheetOpen] = createSignal(false);
  const [readerSettingsOpen, setReaderSettingsOpen] = createSignal(false);
  const [threadSearchOpen, setThreadSearchOpen] = createSignal(false);
  let surfaceActions: MobileSurfaceActions = {};

  function registerSurfaceActions(actions: MobileSurfaceActions) {
    surfaceActions = actions;
    onCleanup(() => {
      surfaceActions = {};
    });
  }

  function openMobilePanel(panel: MobilePanel) {
    if (panel === "filters") {
      if (surfaceActions.openFilters) surfaceActions.openFilters();
      else setFiltersSheetOpen(true);
    } else if (panel === "reader-settings") {
      if (surfaceActions.openReaderSettings) surfaceActions.openReaderSettings();
      else setReaderSettingsOpen(true);
    } else {
      // panel === "thread-search" — exhaustive after the union narrowing.
      if (surfaceActions.openThreadSearch) surfaceActions.openThreadSearch();
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

  return (
    <MobileShellContext.Provider value={value}>
      {props.children}
    </MobileShellContext.Provider>
  );
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
  return useContext(MobileShellContext);
}
