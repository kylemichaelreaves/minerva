import { Show } from "solid-js";
import Landing from "~/Landing";
import Composer from "~/Composer";
import WorkScopeControl from "~/Composer/WorkScopeControl";
import Thread from "~/Thread";
import Topbar from "~/components/Topbar";
import { ThreadSearchSheet } from "~/Thread/components/ThreadSearchSheet";
import { useMobileShell } from "~/components/MobileShellContext";
import type { RouteContextProps } from "~/routes/types";

export function ChatRoute(props: RouteContextProps) {
  const shell = useMobileShell();

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
        />
      </Show>
      <Show
        when={props.conversations.showLanding()}
        fallback={
          <>
            <div class="scroll" ref={props.scrollRef} onScroll={props.onScroll}>
              <Thread
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
              open={
                shell.isMobile() &&
                !props.conversations.showLanding() &&
                shell.threadSearchOpen()
              }
              messages={props.conversations.messages()}
              onClose={() => shell.setThreadSearchOpen(false)}
            />
          </>
        }
      >
        <Landing
          onSubmit={props.conversations.startFromLanding}
          onPickPrompt={props.conversations.startFromLanding}
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
          theme={props.themeApi.theme()}
          onToggleTheme={props.themeApi.toggleTheme}
        />
      </Show>
    </>
  );
}
