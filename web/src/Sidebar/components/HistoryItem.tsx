import { PHIL_DOMINANT_GLYPH } from "~/utils/dominantPhil";
import { TrashIcon } from "~/components/Icons";
import type { HistoryItem } from "~/utils/types";
import { SidebarNavRow } from "~/Sidebar/components/SidebarNavRow";

export function SidebarHistoryItem(props: {
  h: HistoryItem;
  active: boolean;
  onPick: (id: string) => void;
  onRequestDelete?: (item: HistoryItem) => void;
}) {
  return (
    <SidebarNavRow
      active={props.active}
      glyph={PHIL_DOMINANT_GLYPH[props.h.dominant] ?? "Π"}
      title={props.h.title}
      meta={props.h.meta}
      onPick={() => {
        props.onPick(props.h.id);
      }}
      onDelete={
        props.onRequestDelete
          ? () => {
              props.onRequestDelete?.(props.h);
            }
          : undefined
      }
      deleteLabel={`Delete conversation: ${props.h.title}`}
      deleteIcon={<TrashIcon />}
    />
  );
}
