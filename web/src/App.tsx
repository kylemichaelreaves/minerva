// App composition root. Wires composables into layout; routes live in AppRoutes.

import { createEffect, createMemo, createSignal, on, Show } from "solid-js";
import Sidebar from "~/Sidebar";
import ConfirmDialog from "~/components/ConfirmDialog";
import MobileTopBar from "~/components/MobileTopBar";
import { AppRoutes } from "~/AppRoutes";
import { MobileShellProvider, useMobileShell } from "~/components/MobileShellContext";
import { useMobileTopBarConfig } from "~/hooks/useMobileTopBarConfig";
import "~/styles/mobile.css";
import "~/styles/mobile-sheet.css";
import Toasts from "~/components/Toasts";
import { useTheme } from "~/theme";
import { useRouting } from "~/routing";
import { useConversations } from "~/conversations/conversationsCtrl";
import { useReader } from "~/Reader/readerCtrl";
import type { AccentKey } from "~/utils/types";

const ACCENT_KEY: AccentKey = "oxblood";
const MARGIN_NOTES = true;

export default function App() {
  return (
    <MobileShellProvider>
      <AppShell />
    </MobileShellProvider>
  );
}

function AppShell() {
  const themeApi = useTheme(ACCENT_KEY);
  const routing = useRouting();
  const conversations = useConversations(routing);
  const reader = useReader(routing, conversations.abortInflight);
  const { isMobile } = useMobileShell();

  const openSourceInReader = (workTitle: string, chunkId: string) => {
    reader.openAtChunk(workTitle, undefined, chunkId);
  };

  const [sidebarCollapsed, setSidebarCollapsed] = createSignal(false);
  const [scrolled, setScrolled] = createSignal(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = createSignal(false);

  createEffect(() => {
    if (isMobile() && mobileDrawerOpen()) {
      document.body.dataset.mobileDrawer = "open";
    } else {
      delete document.body.dataset.mobileDrawer;
    }
  });

  createEffect(
    on(
      () => routing.route(),
      () => { setMobileDrawerOpen(false); },
      { defer: true },
    ),
  );

  const conversationTitle = createMemo<string | null>(() => {
    const id = conversations.activeId();
    if (!id) return null;
    const h = conversations.history().find((x) => x.id === id);
    return h ? h.title : null;
  });

  const onRefs = createMemo(() => {
    const k = routing.route().kind;
    return k === "refs" || k === "refs-review";
  });
  // `onNetwork` covers the main network view + its two drilldown
  // routes (chronological arc + verification coverage) so they share
  // a Show-branch in AppRoutes. The MobileTopBar suppresses itself on
  // these routes — each drilldown carries its own back-bar.
  const onNetwork = createMemo(() => {
    const k = routing.route().kind;
    return k === "network" || k === "network-arc" || k === "network-coverage";
  });
  // Full-bleed like the network drilldowns: it renders its own back bar, so
  // the mobile chrome steps aside the same way.
  const onSyntax = createMemo(() => routing.route().kind === "syntax");
  const onConcordance = createMemo(() => {
    const k = routing.route().kind;
    return k === "concordance" || k === "concordance-lemma";
  });

  const readerWorkInfo = createMemo<{ author: string; title: string } | null>(
    () => {
      const loc = reader.readerWork();
      if (!loc) return null;
      const w = reader
        .works()
        .find(
          (x) =>
            x.work === loc.workId &&
            (loc.sourceLang == null || x.lang === loc.sourceLang),
        );
      if (w) return { author: w.author, title: w.display_title };
      return { author: "", title: loc.workId };
    },
  );

  const topBar = useMobileTopBarConfig({
    routing,
    reader,
    conversations,
    conversationTitle: () => conversationTitle(),
    onRefs: () => onRefs(),
    onNetwork: () => onNetwork(),
    onConcordance: () => onConcordance(),
    readerWorkInfo: () => readerWorkInfo(),
  });

  return (
    <div class="app">
      <Sidebar
        collapsed={sidebarCollapsed()}
        onToggle={() => setSidebarCollapsed((c) => !c)}
        history={conversations.history()}
        activeId={conversations.activeId()}
        onPick={conversations.pickHistory}
        onNew={conversations.newConversation}
        onRequestDelete={conversations.requestDelete}
        mode={reader.mode()}
        works={reader.works()}
        activeWorkId={reader.readerWork()?.workId ?? null}
        activeWorkLang={reader.readerWork()?.sourceLang}
        onPickWork={reader.openWork}
        onGoLanding={() => { routing.navigate({ kind: "landing" }); }}
        onCloseMobile={
          isMobile() ? () => setMobileDrawerOpen(false) : undefined
        }
        theme={isMobile() ? themeApi.theme() : undefined}
        onToggleTheme={
          isMobile() ? () => { themeApi.toggleTheme(); } : undefined
        }
      />
      <Show when={isMobile() && mobileDrawerOpen()}>
        <button
          class="mobile-scrim"
          onClick={() => setMobileDrawerOpen(false)}
        />
      </Show>
      <main class="main">
        <Show
          when={
            isMobile() &&
            !conversations.showLanding() &&
            routing.route().kind !== "network-arc" &&
            routing.route().kind !== "network-coverage" &&
            routing.route().kind !== "syntax"
          }
        >
          {/* MobileTopBar is suppressed on the two Network drilldown
              routes — each renders its own "← Network" back bar. */}
          <MobileTopBar
            onOpenDrawer={() => setMobileDrawerOpen(true)}
            title={topBar.title}
            action={topBar.action}
            onAction={topBar.onAction}
          />
        </Show>
        <AppRoutes
          routing={routing}
          conversations={conversations}
          reader={reader}
          themeApi={themeApi}
          scrolled={scrolled()}
          sidebarCollapsed={sidebarCollapsed()}
          setSidebarCollapsed={setSidebarCollapsed}
          conversationTitle={conversationTitle}
          onRefs={onRefs}
          onNetwork={onNetwork}
          onSyntax={onSyntax}
          onConcordance={onConcordance}
          openSourceInReader={openSourceInReader}
          onScrollChange={setScrolled}
          marginNotes={MARGIN_NOTES}
        />
      </main>

      <ConfirmDialog
        open={conversations.deleteTarget() !== null}
        title="Delete this conversation?"
        message="This can't be undone."
        confirmLabel="Delete"
        onConfirm={conversations.confirmDelete}
        onCancel={conversations.cancelDelete}
      />

      <Toasts />
    </div>
  );
}
