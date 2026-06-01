import { For } from "solid-js";
import type { HistoryItem } from "~/utils/types";
import { SidebarHistoryItem } from "~/Sidebar/components/HistoryItem";

export function SidebarHistorySection(props: {
  label: string;
  items: HistoryItem[];
  activeId: string | null;
  onPick: (id: string) => void;
  onRequestDelete?: (item: HistoryItem) => void;
}) {
  return (
    <>
      <div class="history-label">{props.label}</div>
      <div class="history-list">
        <For each={props.items}>
          {(h) => (
            <SidebarHistoryItem
              h={h}
              active={props.activeId === h.id}
              onPick={props.onPick}
              onRequestDelete={props.onRequestDelete}
            />
          )}
        </For>
      </div>
    </>
  );
}
