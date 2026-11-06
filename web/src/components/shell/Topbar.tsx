import { Show } from "solid-js";
import { classnames } from "~/utils/util";
import { SidebarIcon } from "~/components/primitives/Icons";
import { ThemeToggle } from "~/components/shell/ThemeToggle";
import type { Theme } from "~/utils/types";
import { smallCapsLabel } from "~/components/shell/topbarStyles";

interface TopbarProps {
  scrolled: boolean;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  conversationTitle: string | null | false;
  /** True while the landing → chat transition runs: the bar fades in late
   *  (landingTransition.css). */
  entering?: boolean;
}

export default function Topbar(props: TopbarProps) {
  return (
    <div
      class={classnames("topbar", props.scrolled && "scrolled", props.entering && "lt-entering")}
    >
      <div class="topbar-left">
        <Show when={props.sidebarCollapsed}>
          <button
            class="icon-btn"
            onClick={() => props.onToggleSidebar()}
            aria-label="Show sidebar"
          >
            <SidebarIcon />
          </button>
        </Show>
        <div class="topbar-title">
          <Show
            when={props.conversationTitle}
            fallback={<span style={smallCapsLabel("0.18em")}>An untitled enquiry</span>}
          >
            <>
              {props.conversationTitle} <em>·</em>
              <span style={smallCapsLabel("0.14em")}> vol. iii</span>
            </>
          </Show>
        </div>
      </div>
      <div class="topbar-right">
        <ThemeToggle theme={props.theme} onToggle={props.onToggleTheme} variant="icon" />
      </div>
    </div>
  );
}
