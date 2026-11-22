import { describe, expect, it } from "vitest";
import { render } from "@solidjs/testing-library";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import { useMobileTopBarConfig } from "~/hooks/useMobileTopBarConfig";

function mockRouting(kind: string) {
  return {
    route: () => ({ kind }),
  } as ReturnType<typeof import("~/routing").useRouting>;
}

function mockReader(mode: "chat" | "reader") {
  return {
    mode: () => mode,
    readerWork: () => null,
  } as ReturnType<typeof import("~/Reader/readerCtrl").useReader>;
}

function mockConversations(showLanding: boolean, _title: string | null = null) {
  return {
    showLanding: () => showLanding,
  } as ReturnType<typeof import("~/features/conversations/conversationsCtrl").useConversations>;
}

// Mounted for real rather than built inside a bare createRoot: a Solid 2
// context provider evaluates its children lazily, when its output is read,
// so an unrendered tree never ran the hook and `config` stayed unset.
function runConfig(input: Parameters<typeof useMobileTopBarConfig>[0]) {
  let config!: ReturnType<typeof useMobileTopBarConfig>;
  function Probe() {
    config = useMobileTopBarConfig(input);
    return null;
  }
  const { unmount } = render(() => (
    <MobileShellProvider>
      <Probe />
    </MobileShellProvider>
  ));
  return { config, dispose: unmount };
}

describe("useMobileTopBarConfig", () => {
  it("returns Cross-references title on refs route", () => {
    const { config, dispose } = runConfig({
      routing: mockRouting("refs"),
      reader: mockReader("chat"),
      conversations: mockConversations(false),
      conversationTitle: () => null,
      onRefs: () => true,
      onNetwork: () => false,
      onConcordance: () => false,
      onMetrics: () => false,
      readerWorkInfo: () => null,
    });

    expect(config.title).toBe("Cross-references");
    expect(config.onAction).toBeTypeOf("function");
    dispose();
  });

  it("returns conversation title and search action on chat route", () => {
    const { config, dispose } = runConfig({
      routing: mockRouting("chat"),
      reader: mockReader("chat"),
      conversations: mockConversations(false),
      conversationTitle: () => "Virtue and habit",
      onRefs: () => false,
      onNetwork: () => false,
      onConcordance: () => false,
      onMetrics: () => false,
      readerWorkInfo: () => null,
    });

    expect(config.title).toBe("Virtue and habit");
    expect(config.onAction).toBeTypeOf("function");
    dispose();
  });

  it("returns Observability title and no action on the metrics route", () => {
    // Without an `onMetrics` branch, `#/metrics` used to fall through to
    // the chat case below and show the active conversation's title plus
    // a "Search within conversation" action over the metrics page —
    // caught in review by actually running the mobile shell against
    // `#/metrics`, not by reading the hook.
    const { config, dispose } = runConfig({
      routing: mockRouting("metrics"),
      reader: mockReader("chat"),
      conversations: mockConversations(false, "Virtue and habit"),
      conversationTitle: () => "Virtue and habit",
      onRefs: () => false,
      onNetwork: () => false,
      onConcordance: () => false,
      onMetrics: () => true,
      readerWorkInfo: () => null,
    });

    expect(config.title).toBe("Observability");
    expect(config.action).toBeUndefined();
    expect(config.onAction).toBeUndefined();
    dispose();
  });

  it("omits action on landing", () => {
    const { config, dispose } = runConfig({
      routing: mockRouting("landing"),
      reader: mockReader("chat"),
      conversations: mockConversations(true),
      conversationTitle: () => null,
      onRefs: () => false,
      onNetwork: () => false,
      onConcordance: () => false,
      onMetrics: () => false,
      readerWorkInfo: () => null,
    });

    expect(config.action).toBeUndefined();
    expect(config.onAction).toBeUndefined();
    dispose();
  });
});
