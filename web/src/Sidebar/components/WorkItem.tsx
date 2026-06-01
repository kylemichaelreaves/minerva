import { PHIL_DOMINANT_GLYPH } from "~/utils/dominantPhil";
import type { Work } from "~/utils/types";
import { SidebarNavRow } from "~/Sidebar/components/SidebarNavRow";

export function SidebarWorkItem(props: {
  work: Work;
  active: boolean;
  onPick: (w: Work) => void;
}) {
  const w = () => props.work;
  const label = () => w().display_title || w().work;
  return (
    <SidebarNavRow
      active={props.active}
      glyph={PHIL_DOMINANT_GLYPH[w().author[0].toUpperCase()] ?? "Π"}
      title={label()}
      titleAttr={`${label()} · ${w().lang.toUpperCase()}`}
      trailing={<span class="work-lang-chip">{w().lang}</span>}
      onPick={() => {
        props.onPick(w());
      }}
    />
  );
}
