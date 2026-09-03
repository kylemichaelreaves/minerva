import {
  Match,
  Show,
  Switch,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  onMount,
} from "solid-js";
import SurfaceErrorBoundary from "~/components/SurfaceErrorBoundary";
import { SuspendedSubtreeProvider } from "~/hooks/suspendedSubtree";
import { ChatRoute } from "~/routes/ChatRoute";
import { ConcordanceRoute } from "~/routes/ConcordanceRoute";
import { NetworkRoute } from "~/routes/NetworkRoute";
import { ReaderRoute } from "~/routes/ReaderRoute";
import { RefsRoute } from "~/routes/RefsRoute";
import type { RouteContextProps } from "~/routes/types";
import type { useConversations } from "~/features/conversations/conversationsCtrl";
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
  const [stickToBottom, setStickToBottom] = createSignal(true);
  const NEAR_BOTTOM_PX = 80;

  const streamTail = createMemo(() => {
    const msgs = props.conversations.messages();
    const last = msgs[msgs.length - 1];
    if (last?.role === "minerva" && last.streaming) return last.streamText ?? "";
    return "";
  });

  createEffect(() => {
    props.conversations.messages();
    props.conversations.thinking();
    streamTail();
    if (!stickToBottom() || !scrollEl) return;
    const el = scrollEl;
    queueMicrotask(() => {
      el.scrollTop = el.scrollHeight;
    });
  });

  onMount(() => {
    const el = scrollEl;
    if (!el) return;
    const onScroll = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      setStickToBottom(dist < NEAR_BOTTOM_PX);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    onCleanup(() => el.removeEventListener("scroll", onScroll));
  });

  // `ctx` copies stable controller bundles + functions (created once in
  // AppShell) into the route context; the reactive scalars are wrapped as
  // accessors below. The bundle/function/constant reads are stable
  // references, so the solid/reactivity warnings they trigger are false
  // positives — hence the block disable.
  /* eslint-disable solid/reactivity */
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
  /* eslint-enable solid/reactivity */

  // The Reader lives OUTSIDE the switch (#348). As a peer `<Match>` it was
  // destroyed by every side route that matched ahead of it, and #342 fixed
  // only the fourth such case, the syntax overlay — which is not a branch
  // here at all, but a layer `App` mounts outside `<main>` over whatever this
  // renders.
  //
  // `retainedWork` keeps a location to render while the route has stepped out
  // to a concordance; it is null on the destinations (network, refs) and on a
  // concordance reached cold, so those release the Reader as before. `hidden`
  // keeps the retained Reader off the screen and `inert` keeps it out of the
  // tab order — a mounted Reader under a full-page view is still focusable,
  // and before this it was unreachable only because it had been destroyed.
  // The wrapper is `display: contents` so `.main`'s flex column still sees
  // `.reader` as its own child.
  const readerShowing = () => props.reader.mode() === "reader";
  return (
    <>
      <Show when={props.reader.readerWork() ?? props.reader.retainedWork()}>
        {/* `attr:inert` because the plain prop compiles to `el.inert = …`, a
            no-op wherever the property is unimplemented; the attribute is
            what the browser's inert semantics key on. Same reason as
            `App.tsx`. `hidden` needs no such escape — Solid treats it as a
            boolean attribute — and `attr:hidden` is not in the JSX types. */}
        <div
          class="reader-keepalive"
          hidden={!readerShowing()}
          attr:inert={readerShowing() ? undefined : ""}
        >
          {/* Above `ReaderRoute`, not inside the Reader's JSX: hooks called in
              the Reader's own component body (`useTermCard`, its two
              `useEscape`s) resolve `useContext` against the provider that is
              already above them at that point, and a provider nested inside
              the Reader's returned tree would be invisible to them. Scoped to
              this wrapper so the concordance rendered in the sibling `<Switch>`
              below reads the default and stays live (#352). */}
          <SuspendedSubtreeProvider suspended={() => !readerShowing()}>
            {/* Per-surface boundaries (#426). Inside the provider, so a Reader
                failure does not tear down the suspended-subtree context the
                sibling concordance depends on (#352). */}
            <SurfaceErrorBoundary label="The reader">
              <ReaderRoute {...ctx} />
            </SurfaceErrorBoundary>
          </SuspendedSubtreeProvider>
        </div>
      </Show>
      {/* `mode()` is `readerWork() ? "reader" : "chat"`, so this is exactly the
          condition the removed `<Match>` used — without it the switch would
          fall through to `ChatRoute` and render the chat under the Reader. */}
      <Show when={!readerShowing()}>
        <Switch
          fallback={
            <SurfaceErrorBoundary label="Chat">
              <ChatRoute {...ctx} />
            </SurfaceErrorBoundary>
          }
        >
          <Match when={props.onConcordance()}>
            <SurfaceErrorBoundary label="The concordance">
              <ConcordanceRoute {...ctx} />
            </SurfaceErrorBoundary>
          </Match>
          <Match when={props.onNetwork()}>
            <SurfaceErrorBoundary label="The network view">
              <NetworkRoute {...ctx} />
            </SurfaceErrorBoundary>
          </Match>
          <Match when={props.onRefs()}>
            <SurfaceErrorBoundary label="Cross-references">
              <RefsRoute {...ctx} />
            </SurfaceErrorBoundary>
          </Match>
        </Switch>
      </Show>
    </>
  );
}
