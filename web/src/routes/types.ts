import type { useConversations } from "~/conversations/conversationsCtrl";
import type { useReader } from "~/Reader/readerCtrl";
import type { useRouting } from "~/routing";
import type { useTheme } from "~/theme";

export interface RouteContextProps {
  routing: ReturnType<typeof useRouting>;
  conversations: ReturnType<typeof useConversations>;
  reader: ReturnType<typeof useReader>;
  themeApi: ReturnType<typeof useTheme>;
  scrolled: boolean;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean | ((c: boolean) => boolean)) => void;
  conversationTitle: () => string | null;
  openSourceInReader: (workTitle: string, chunkId: string) => void;
  onScrollChange: (scrolled: boolean) => void;
  marginNotes: boolean;
  scrollRef?: (el: HTMLDivElement) => void;
  onScroll?: (e: Event & { currentTarget: HTMLDivElement }) => void;
}
