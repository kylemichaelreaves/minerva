import { Show } from "solid-js";
import { classnames } from "~/utils/util";
import { SidebarIcon } from "~/components/Icons";
import { ThemeToggle } from "~/components/ThemeToggle";
import type { Theme } from "~/utils/types";
import { smallCapsLabel } from "~/components/topbarStyles";

interface TopbarProps {
  scrolled: boolean;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  conversationTitle: string | null | false;
}

export default function Topbar(props: TopbarProps) {
  return (
    <div class={classnames("topbar", props.scrolled && "scrolled")}>
      <div class="topbar-left">
        <Show when={props.sidebarCollapsed}>
          <button class="icon-btn" onClick={props.onToggleSidebar} aria-label="Show sidebar">
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
        <ThemeToggle
          theme={props.theme}
          onToggle={props.onToggleTheme}
          variant="icon"
        />
      </div>
    </div>
  );
}
