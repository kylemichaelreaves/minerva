/**
 * `registerSurfaceActions` must not let one surface wipe another's
 * handlers (#200, item 3).
 *
 * The provider kept a single `MobileSurfaceActions` slot. Two
 * consequences, both real:
 *
 *   1. whichever surface registered last won outright — a surface that
 *      only supplies `openFilters` erased a live surface's
 *      `openReaderSettings`;
 *   2. the `onCleanup` reset to `{}` unconditionally, so an *unmounting*
 *      surface cleared the slot even when a different, still-mounted
 *      surface owned it.
 *
 * (The issue calls the slot module-scoped; it is provider-scoped —
 * declared inside `MobileShellProvider`. Same defect either way, since
 * there is one provider, but that is where to look.)
 *
 * Fallback behaviour is the contract these tests protect: with no
 * registered handler, `openMobilePanel` opens the provider's own sheet
 * signal, so a lost registration degrades to "the wrong sheet opens"
 * rather than to a visible error.
 */
import { describe, it, expect } from "vitest";
import { createRoot, flush } from "solid-js";
import {
  MobileShellProvider,
  useMobileShell,
  type MobileShellContextValue,
} from "~/components/shell/MobileShellContext";
import { render, cleanup } from "@solidjs/testing-library";
import { must } from "./helpers/must";

/** Render the provider and hand back its context value. */
function withShell(fn: (shell: MobileShellContextValue) => void) {
  let shell: MobileShellContextValue | undefined;
  function Probe() {
    shell = useMobileShell();
    return null;
  }
  render(() => (
    <MobileShellProvider>
      <Probe />
    </MobileShellProvider>
  ));
  try {
    fn(must(shell));
  } finally {
    cleanup();
  }
}

describe("registerSurfaceActions", () => {
  it("routes a panel request to the registered handler", () => {
    withShell((shell) => {
      const calls: string[] = [];
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("filters") }));

      shell.openMobilePanel("filters");

      expect(calls).toEqual(["filters"]);
      // The provider's own sheet stays closed — the surface handled it.
      expect(shell.filtersSheetOpen()).toBe(false);
    });
  });

  it("falls back to the provider's sheet when nothing is registered", () => {
    withShell((shell) => {
      // flush(): a Solid 2 signal read shows the write once it is applied.
      shell.openMobilePanel("filters");
      flush();
      expect(shell.filtersSheetOpen()).toBe(true);

      shell.openMobilePanel("reader-settings");
      flush();
      expect(shell.readerSettingsOpen()).toBe(true);

      shell.openMobilePanel("thread-search");
      flush();
      expect(shell.threadSearchOpen()).toBe(true);
    });
  });

  it("keeps a second surface's handler when a third registers a different one", () => {
    withShell((shell) => {
      const calls: string[] = [];
      createRoot(() =>
        shell.registerSurfaceActions({
          openReaderSettings: () => calls.push("reader"),
        }),
      );
      // A second surface registers, supplying only `openFilters`. It must
      // not erase the reader-settings handler above.
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("filters") }));

      shell.openMobilePanel("filters");
      shell.openMobilePanel("reader-settings");

      expect(calls).toEqual(["filters", "reader"]);
      expect(shell.readerSettingsOpen()).toBe(false);
    });
  });

  it("does not let an unmounting surface clear a still-mounted one's handler", () => {
    withShell((shell) => {
      const calls: string[] = [];
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("live") }));
      // A transient surface registers and then unmounts.
      const disposeTransient = createRoot((dispose) => {
        shell.registerSurfaceActions({ openThreadSearch: () => calls.push("gone") });
        return dispose;
      });
      disposeTransient();

      shell.openMobilePanel("filters");

      expect(calls).toEqual(["live"]);
      // Not the fallback — the live surface still owns the panel.
      expect(shell.filtersSheetOpen()).toBe(false);
    });
  });

  it("returns to the fallback once every surface has unmounted", () => {
    withShell((shell) => {
      const calls: string[] = [];
      const dispose = createRoot((d) => {
        shell.registerSurfaceActions({ openFilters: () => calls.push("filters") });
        return d;
      });
      dispose();

      shell.openMobilePanel("filters");
      flush();

      expect(calls).toEqual([]);
      expect(shell.filtersSheetOpen()).toBe(true);
    });
  });

  it("prefers the most recently registered handler for the same panel", () => {
    withShell((shell) => {
      const calls: string[] = [];
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("first") }));
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("second") }));

      shell.openMobilePanel("filters");

      // Last-registered wins, which is the existing behaviour for a
      // genuine conflict — two surfaces claiming the same panel.
      expect(calls).toEqual(["second"]);
    });
  });

  it("falls back to the earlier surface when the later one unmounts", () => {
    withShell((shell) => {
      const calls: string[] = [];
      createRoot(() => shell.registerSurfaceActions({ openFilters: () => calls.push("first") }));
      const dispose = createRoot((d) => {
        shell.registerSurfaceActions({ openFilters: () => calls.push("second") });
        return d;
      });
      dispose();

      shell.openMobilePanel("filters");

      expect(calls).toEqual(["first"]);
    });
  });
});
