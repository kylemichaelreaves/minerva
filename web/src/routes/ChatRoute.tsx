import { Show, createEffect, on, onCleanup } from "solid-js";
import Landing from "~/features/Landing";
import Composer from "~/features/Composer";
import WorkScopeControl from "~/features/Composer/WorkScopeControl";
import Thread from "~/Thread";
import Topbar from "~/components/shell/Topbar";
import { ThreadSearchSheet } from "~/Thread/components/ThreadSearchSheet";
import { useMobileShell } from "~/components/shell/MobileShellContext";
import type { RouteContextProps } from "~/routes/types";
import { createLandingTransition } from "~/features/LandingTransition/controller";

export function ChatRoute(props: RouteContextProps) {
  const shell = useMobileShell();
  // The landing → chat transition (docs/superpowers/specs/
  // 2026-11-06-landing-chat-transition-design.md). While it runs, the chat
  // is mounted and the landing stays mounted on top of it, fading out.
  const transition = createLandingTransition();
  const lifting = () => transition.phase() === "lift";
  // A plain flag, not a signal: the chat branch — and its Composer — is
  // created synchronously inside `startFromLanding`, so the Composer reads
  // `true` at creation on every path (lift, fade or cut), and `false` for a
  // sidebar pick or a direct load, which must not steal focus.
  let fromLanding = false;
  const beginFromLanding = (text: string) => {
    fromLanding = true;
    try {
      transition.begin(text, props.conversations.startFromLanding);
    } finally {
      fromLanding = false;
    }
  };
  // "New conversation" (or anything else that brings the landing back)
  // mid-flight: drop the flight and show an ordinary landing. `on` so this
  // tracks `showLanding` alone — `cancel()` reads the phase, and tracking it
  // would re-run this the moment a lift starts, while `showLanding` is still
  // true, and cancel the flight before the question was even sent.
  createEffect(
    on(
      () => props.conversations.showLanding(),
      (shown) => {
        if (shown) transition.cancel();
      },
    ),
  );
  onCleanup(() => transition.cancel());

  return (
    <>
      <Show when={!props.conversations.showLanding()}>
        <Topbar
          scrolled={props.scrolled()}
          sidebarCollapsed={props.sidebarCollapsed()}
          onToggleSidebar={() => props.setSidebarCollapsed(false)}
          theme={props.themeApi.theme()}
          onToggleTheme={props.themeApi.toggleTheme}
          conversationTitle={props.conversationTitle()}
          entering={lifting()}
        />
      </Show>
      <Show when={!props.conversations.showLanding()}>
        <div class="scroll" ref={props.scrollRef} onScroll={props.onScroll}>
          <Thread
            arriving={transition.phase()}
            messages={props.conversations.messages()}
            thinking={props.conversations.thinking()}
            hydrating={props.conversations.hydrating()}
            marginNotes={props.marginNotes}
            pinnedChunkIds={props.conversations.pinnedChunkIds()}
            onTogglePin={props.conversations.togglePin}
            onOpenReader={(workId, sourceLang, chunkId) => {
              props.reader.openAtChunk(workId, sourceLang, chunkId);
            }}
          />
        </div>
        <Composer
          onSend={props.conversations.sendMessage}
          focusOnMount={fromLanding}
          entering={lifting()}
          scopeChip={
            <WorkScopeControl
              scope={props.conversations.chatScope}
              works={props.reader.works}
              ensureWorks={props.reader.ensureWorks}
              onSet={props.conversations.setChatScope}
            />
          }
        />
        <ThreadSearchSheet
          open={shell.isMobile() && !props.conversations.showLanding() && shell.threadSearchOpen()}
          messages={props.conversations.messages()}
          onClose={() => shell.setThreadSearchOpen(false)}
        />
      </Show>
      {/* Second, so the leaving landing paints over the chat beneath it. */}
      <Show when={props.conversations.showLanding() || transition.phase() !== "idle"}>
        <Landing
          onSubmit={beginFromLanding}
          leaving={props.conversations.showLanding() ? undefined : transition.phase()}
          scopeChip={
            // Only when a scope is actually set (#350), so the cold landing
            // stays the uncluttered brand screen. `WorkScopeControl` is the
            // same dismissible chip the conversation composer uses above, so
            // a work carried out of the Reader is visible and droppable
            // rather than a hidden filter on the first question.
            <Show when={props.conversations.chatScope()}>
              <WorkScopeControl
                scope={props.conversations.chatScope}
                works={props.reader.works}
                ensureWorks={props.reader.ensureWorks}
                onSet={props.conversations.setChatScope}
              />
            </Show>
          }
          onOpenRead={() => {
            void props.reader.switchMode("reader");
          }}
          onOpenRefs={(sourceAuthor) => {
            props.routing.navigate(
              sourceAuthor ? { kind: "refs", sourceAuthor } : { kind: "refs" },
            );
          }}
          onOpenNetwork={() => {
            props.routing.navigate({ kind: "network" });
          }}
          onOpenConcordance={() => {
            props.routing.navigate({ kind: "concordance", lang: "deu" });
          }}
          onOpenMetrics={() => {
            props.routing.navigate({ kind: "metrics" });
          }}
          theme={props.themeApi.theme()}
          onToggleTheme={props.themeApi.toggleTheme}
        />
      </Show>
    </>
  );
}
