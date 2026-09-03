import { describe, expect, it } from "vitest";
import { createRoot } from "solid-js";
import { MobileShellProvider } from "~/components/MobileShellContext";
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

function runConfig(input: Parameters<typeof useMobileTopBarConfig>[0]) {
  let config!: ReturnType<typeof useMobileTopBarConfig>;
  const dispose = createRoot((d) => {
    createRoot(() => (
      <MobileShellProvider>
        {(() => {
          config = useMobileTopBarConfig(input);
          return null;
        })()}
      </MobileShellProvider>
    ));
    return d;
  });
  return { config, dispose };
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
      readerWorkInfo: () => null,
    });

    expect(config.title).toBe("Virtue and habit");
    expect(config.onAction).toBeTypeOf("function");
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
      readerWorkInfo: () => null,
    });

    expect(config.action).toBeUndefined();
    expect(config.onAction).toBeUndefined();
    dispose();
  });
});
