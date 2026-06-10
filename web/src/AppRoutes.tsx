import { Show, createEffect, createMemo } from "solid-js";
import { ChatRoute } from "~/routes/ChatRoute";
import { ConcordanceRoute } from "~/routes/ConcordanceRoute";
import { NetworkRoute } from "~/routes/NetworkRoute";
import { ReaderRoute } from "~/routes/ReaderRoute";
import { RefsRoute } from "~/routes/RefsRoute";
import type { RouteContextProps } from "~/routes/types";
import type { useConversations } from "~/conversations/conversationsCtrl";
import type { useReader } from "~/Reader/readerCtrl";
import type { useRouting } from "~/routing";
import type { useTheme } from "~/theme";

export interface AppRoutesProps {
  routing: ReturnType<typeof useRouting>;
  conversations: ReturnType<typeof useConversations>;
  reader: ReturnType<typeof useReader>;
  themeApi: ReturnType<typeof useTheme>;
  scrolled: boolean;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean | ((c: boolean) => boolean)) => void;
  conversationTitle: () => string | null;
  onRefs: () => boolean;
  onNetwork: () => boolean;
  onConcordance: () => boolean;
  openSourceInReader: (workTitle: string, chunkId: string) => void;
  onScrollChange: (scrolled: boolean) => void;
  marginNotes: boolean;
}

export function AppRoutes(props: AppRoutesProps) {
  let scrollEl: HTMLDivElement | undefined;

  const streamTail = createMemo(() => {
    const msgs = props.conversations.messages();
    const last = msgs[msgs.length - 1];
    // Array index access can return undefined at runtime when msgs is
    // empty — TS doesn't model this without noUncheckedIndexedAccess.
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (last?.role === "minerva" && last.streaming) return last.streamText ?? "";
    return "";
  });

  createEffect(() => {
    props.conversations.messages();
    props.conversations.thinking();
    streamTail();
    if (scrollEl) {
      const el = scrollEl;
      queueMicrotask(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  });

  const ctx: RouteContextProps = {
    routing: props.routing,
    conversations: props.conversations,
    reader: props.reader,
    themeApi: props.themeApi,
    // Accessor functions, not plain booleans — reading `props.scrolled`
    // here would freeze the value at mount (ctx is built once), so
    // consumers call these to stay reactive. Same pattern as
    // `conversationTitle` below.
    scrolled: () => props.scrolled,
    sidebarCollapsed: () => props.sidebarCollapsed,
    setSidebarCollapsed: props.setSidebarCollapsed,
    conversationTitle: props.conversationTitle,
    openSourceInReader: props.openSourceInReader,
    onScrollChange: props.onScrollChange,
    marginNotes: props.marginNotes,
    scrollRef: (el) => {
      scrollEl = el;
    },
    onScroll: (e) => props.onScrollChange(e.currentTarget.scrollTop > 4),
  };

  return (
    <Show when={props.onConcordance()} fallback={
      <Show when={props.onNetwork()} fallback={
        <Show when={props.onRefs()} fallback={
          <Show
            when={props.reader.mode() === "reader" && props.reader.readerWork()}
            fallback={<ChatRoute {...ctx} />}
          >
            <ReaderRoute {...ctx} />
          </Show>
        }>
          <RefsRoute {...ctx} />
        </Show>
      }>
        <NetworkRoute {...ctx} />
      </Show>
    }>
      <ConcordanceRoute {...ctx} />
    </Show>
  );
}
