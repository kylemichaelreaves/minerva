import { For, Show, createMemo, createSignal } from "solid-js";
import { classnames } from "~/utils/util";
import { SidebarIcon, PlusIcon } from "~/components/Icons";
import type { HistoryItem, Work } from "~/utils/types";
import {
  loadCollapsedAuthors,
  saveCollapsedAuthors,
} from "~/Sidebar/collapsedAuthorsStorage";
import { SidebarHistorySection } from "~/Sidebar/components/SidebarHistorySection";
import { SidebarWorkItem } from "~/Sidebar/components/WorkItem";
import { ThemeToggle } from "~/components/ThemeToggle";
import "~/Sidebar/sidebar.css";

export type AppMode = "chat" | "reader";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  history: HistoryItem[];
  activeId: string | null;
  onPick: (id: string) => void;
  onNew: () => void;
  onRequestDelete?: (item: HistoryItem) => void;
  /** Drives which mode-specific section the sidebar shows (chat
   *  history vs. works tree). Mode SWITCHING happens via the landing
   *  page's mode entry row, not the sidebar — there are no longer
   *  Chat/Read/Refs/Network tabs here. */
  mode: AppMode;
  works?: Work[];
  activeWorkId?: string | null;
  activeWorkLang?: string;
  onPickWork?: (work: Work) => void;
  onGoLanding?: () => void;
  /** Mobile-only — fired when the drawer should close. Renders an
   *  ✕ button inside the sidebar header at ≤768px so the user can
   *  dismiss without tapping the scrim. */
  onCloseMobile?: () => void;
  /** Current theme + toggle. On mobile, surfaced as the ⚙ cog in the
   *  drawer footer (design 2b) — the topbar's right slot belongs to
   *  the surface action (search / Filters / Aa). On desktop these
   *  props are unused (the Topbar component owns the toggle). */
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
}

export default function Sidebar(props: SidebarProps) {
  const recent = () => props.history.slice(0, 4);
  const earlier = () => props.history.slice(4);

  const [collapsedAuthors, setCollapsedAuthors] = createSignal<Set<string>>(
    loadCollapsedAuthors(),
  );
  const toggleAuthor = (author: string) => {
    setCollapsedAuthors((prev) => {
      const next = new Set(prev);
      if (next.has(author)) next.delete(author);
      else next.add(author);
      saveCollapsedAuthors(next);
      return next;
    });
  };

  const worksByAuthor = createMemo(() => {
    const groups = new Map<string, Work[]>();
    for (const w of props.works ?? []) {
      const list = groups.get(w.author) ?? [];
      list.push(w);
      groups.set(w.author, list);
    }
    return Array.from(groups, ([author, works]) => ({ author, works }));
  });

  return (
    <aside class={classnames("sidebar", props.collapsed && "collapsed")}>
      <div class="sidebar-head">
        <div class="brand">
          <button
            class="brand-mark brand-link"
            onClick={() => props.onGoLanding?.()}
            aria-label="Go to landing"
            title="Home"
            type="button"
          >
            <span class="glyph">M</span>
            <Show when={!props.collapsed}>
              <span class="brand-text">inerva</span>
            </Show>
          </button>
        </div>
        <Show when={!props.collapsed}>
          <button
            class="icon-btn"
            onClick={props.onToggle}
            aria-label="Collapse sidebar"
            title="Collapse"
          >
            <SidebarIcon />
          </button>
        </Show>
        <Show when={props.onCloseMobile}>
          <button
            class="sidebar-close-mobile"
            onClick={props.onCloseMobile}
            aria-label="Close menu"
            title="Close"
            type="button"
          >
            ✕
          </button>
        </Show>
      </div>

      {/* Mode tab strip removed — Chat/Read/Refs/Network are now reached
          via the landing's mode entry row. The URL is the source of
          truth for which mode is active; clicking the brand logo above
          returns to the landing where a new mode can be picked. */}

      <Show when={props.mode === "chat"}>
        <button class="new-btn" onClick={props.onNew} title="New conversation">
          <PlusIcon />
          <Show when={!props.collapsed}>
            <span class="new-btn-label">New conversation</span>
          </Show>
        </button>
      </Show>

      <Show when={props.collapsed}>
        <button
          class="icon-btn"
          style={{ margin: "14px auto 0" }}
          onClick={props.onToggle}
          aria-label="Expand sidebar"
        >
          <SidebarIcon />
        </button>
      </Show>

      <div class="history-section">
        <Show when={props.mode === "chat"}>
          <Show when={recent().length > 0}>
            <SidebarHistorySection
              label="Recent"
              items={recent()}
              activeId={props.activeId}
              onPick={props.onPick}
              onRequestDelete={props.onRequestDelete}
            />
          </Show>

          <Show when={earlier().length > 0}>
            <SidebarHistorySection
              label="Earlier"
              items={earlier()}
              activeId={props.activeId}
              onPick={props.onPick}
              onRequestDelete={props.onRequestDelete}
            />
          </Show>
        </Show>

        <Show when={props.mode === "reader"}>
          <Show
            when={worksByAuthor().length > 0}
            fallback={
              <div class="history-label" style={{ color: "var(--ink-faint)" }}>
                Loading works…
              </div>
            }
          >
            <For each={worksByAuthor()}>
              {(group) => {
                const collapsed = () => collapsedAuthors().has(group.author);
                return (
                  <>
                    <button
                      type="button"
                      class="history-label history-label-toggle"
                      aria-expanded={!collapsed()}
                      onClick={() => {
                        toggleAuthor(group.author);
                      }}
                    >
                      <span class="history-label-caret" aria-hidden="true">
                        <svg viewBox="0 0 12 12" width="8" height="8">
                          <polyline points="3 2 8 6 3 10" />
                        </svg>
                      </span>
                      <span>{group.author}</span>
                      <span class="history-label-count">{group.works.length}</span>
                    </button>
                    <Show when={!collapsed()}>
                      <div class="history-list">
                        <For each={group.works}>
                          {(w) => (
                            <SidebarWorkItem
                              work={w}
                              active={
                                props.activeWorkId === w.work &&
                                (props.activeWorkLang ?? w.lang) === w.lang
                              }
                              onPick={(work) => props.onPickWork?.(work)}
                            />
                          )}
                        </For>
                      </div>
                    </Show>
                  </>
                );
              }}
            </For>
          </Show>
        </Show>
      </div>

      {/* Mobile drawer footer (design 2b/3e). Hidden on desktop via
          .sidebar-foot CSS — desktop's Topbar already carries the
          theme toggle. The user-dot is a placeholder until the app
          gains a real auth/profile concept. */}
      <Show when={props.onToggleTheme}>
        <div class="sidebar-foot">
          <span class="sidebar-foot-user">
            <span class="sidebar-foot-dot">·</span>
            <span class="sidebar-foot-name">minerva</span>
          </span>
          <ThemeToggle
            theme={props.theme ?? "light"}
            onToggle={() => props.onToggleTheme?.()}
            variant="cog"
          />
        </div>
      </Show>

    </aside>
  );
}
