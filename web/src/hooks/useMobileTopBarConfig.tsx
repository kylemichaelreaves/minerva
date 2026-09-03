import { createMemo, type JSX } from "solid-js";
import type { useConversations } from "~/features/conversations/conversationsCtrl";
import type { useReader } from "~/Reader/readerCtrl";
import type { useRouting } from "~/routing";
import { useMobileShell } from "~/components/shell/MobileShellContext";

export interface MobileTopBarConfigInput {
  routing: ReturnType<typeof useRouting>;
  reader: ReturnType<typeof useReader>;
  conversations: ReturnType<typeof useConversations>;
  conversationTitle: () => string | null;
  onRefs: () => boolean;
  onNetwork: () => boolean;
  onConcordance: () => boolean;
  readerWorkInfo: () => { author: string; title: string } | null;
}

export function useMobileTopBarConfig(input: MobileTopBarConfigInput): {
  title: JSX.Element;
  action: JSX.Element | undefined;
  onAction: (() => void) | undefined;
} {
  const shell = useMobileShell();

  const title = createMemo<JSX.Element>(() => {
    if (input.onConcordance()) {
      const r = input.routing.route();
      if (r.kind === "concordance-lemma") {
        return (
          <>
            <em>{r.lemma}</em> · concordance
          </>
        );
      }
      return "Concordance";
    }
    if (input.onNetwork()) return "Network";
    if (input.onRefs()) return "Cross-references";
    if (input.reader.mode() === "reader") {
      const info = input.readerWorkInfo();
      if (info) {
        return (
          <>
            {info.author} · <em>{info.title}</em>
          </>
        );
      }
      return <em>Reader</em>;
    }
    const chatTitle = input.conversationTitle();
    return chatTitle ?? <em>Chat</em>;
  });

  const action = createMemo<JSX.Element | undefined>(() => {
    if (input.onRefs() || input.onNetwork()) return <>Filters</>;
    if (input.reader.mode() === "reader") return <>Aa</>;
    if (input.conversations.showLanding()) return undefined;
    return <span aria-label="Search within conversation">⌕</span>;
  });

  const onAction = createMemo(() => {
    if (input.onRefs() || input.onNetwork()) {
      return () => shell.openMobilePanel("filters");
    }
    if (input.reader.mode() === "reader") {
      return () => shell.openMobilePanel("reader-settings");
    }
    if (!input.conversations.showLanding()) {
      return () => shell.openMobilePanel("thread-search");
    }
    return undefined;
  });

  return {
    get title() {
      return title();
    },
    get action() {
      return action();
    },
    get onAction() {
      return onAction();
    },
  };
}
