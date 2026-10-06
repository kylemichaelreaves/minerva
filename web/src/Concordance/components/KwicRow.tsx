import { Show, createMemo } from "solid-js";
import type { KwicRow } from "~/api/concordanceApi";
import { abbrevWork } from "~/Concordance/constants";
import { Romanizable } from "~/Concordance/components/Romanizable";

export function KwicRowEl(props: {
  row: KwicRow;
  cur: boolean;
  onClick: () => void;
  onHover: () => void;
}) {
  const sectionParts = createMemo(() => {
    const sec = props.row.section || "";
    const m = /^(.*?)(?:,\s*¶(\d+))?$/.exec(sec);
    if (m) {
      // `??` alone would let an empty group-1 match through; the
      // intended fallback is "whole section" for BOTH undefined and "".
      return { path: (m[1] ?? "") || sec, para: m[2] ? `¶${m[2]}` : "" };
    }
    return { path: sec, para: "" };
  });
  return (
    <div
      class={"kwic-row" + (props.cur ? " cur" : "")}
      // eslint-disable-next-line minerva/no-mouse-only-click -- keyboard path is LemmaDetail's j/k cursor + Enter, which opens the same chunk
      onClick={() => props.onClick()}
      onMouseEnter={() => props.onHover()}
    >
      <span class="loc">
        <b>{abbrevWork(props.row.work)}</b>
        {sectionParts().path}
        <Show when={sectionParts().para}>
          <br />
          {sectionParts().para}
        </Show>
      </span>
      <span class="left">{props.row.kwic_left}</span>
      <span class="match">
        <Romanizable text={props.row.kwic_match} />
      </span>
      <span class="right">{props.row.kwic_right}</span>
      <span class="meta">
        <span class="surf">
          <Romanizable text={props.row.surface} />
        </span>
        <span>{props.row.morph_str}</span>
      </span>
    </div>
  );
}
