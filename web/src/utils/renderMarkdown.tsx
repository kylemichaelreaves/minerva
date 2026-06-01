// JSX renderer for the markdown fragment tree produced by
// `./markdown.ts` (`parseRichText` / `parseBlocks`). Kept separate
// from `Thread.tsx` so the chat-turn component stays focused on
// layout and the rendering pipeline stays focused on output shape.
//
// Inline cite markers become focusable `<sup>` elements that reveal
// a tooltip with the locator + passage text on hover/focus.
// Adjacent list-item blocks are grouped into a single `<ul>` so the
// resulting HTML is semantically correct.

import { type JSX } from "solid-js";
import { type Block, parseBlocks, parseRichText, type RichFragment } from "~/utils/markdown";
import { HoverTip } from "~/components/HoverTip";
import type { Citation } from "~/utils/types";

export function renderRich(
  fragments: RichFragment[],
  citations: Map<number, Citation>,
): JSX.Element {
  return fragments.map((f) => {
    if (typeof f === "string") return f;
    if (f.kind === "cite") {
      const c = citations.get(f.n);
      const ariaLabel = c ? `Citation ${f.n}: ${c.src}` : `Citation ${f.n}`;
      // Two children stamped into the same .cite-mark trigger:
      //  - .cite-mark-n is the [N] superscript that desktop reads as
      //    a footnote pointer (hover reveals the locator via HoverTip)
      //  - .cite-mark-chip is the inline chip mobile shows in place of
      //    the superscript — "Aug. civ. Dei XIV.13" — source author in
      //    oxblood, locator in mono. Visibility is CSS-driven by
      //    viewport width (see mobile.css).
      const sup = (
        <sup class="cite-mark" tabindex="0" role="button" aria-label={ariaLabel}>
          <span class="cite-mark-n">[{f.n}]</span>
          {c && (
            <span class="cite-mark-chip">
              {c.speaker && <span class="cite-mark-src">{c.speaker}</span>}
              <span class="cite-mark-loc">{c.src}</span>
            </span>
          )}
        </sup>
      );
      // No citation metadata loaded yet → render just the trigger,
      // skipping the tooltip body (matches the previous behavior).
      if (!c) return sup;
      const srcLabel = c.speaker ? `${c.speaker} · ${c.src}` : c.src;
      return (
        <HoverTip label={srcLabel} body={c.text}>
          {sup}
        </HoverTip>
      );
    }
    if (f.kind === "bold") return <strong>{renderRich(f.children, citations)}</strong>;
    if (f.kind === "italic") return <em>{renderRich(f.children, citations)}</em>;
    // `f.kind === "code"` is implied by the exhaustive prior branches; the
    // explicit check would be flagged as always-true.
    return <code class="inline-code">{f.text}</code>;
  });
}

// Render a single block into JSX. Lists are wrapped at the caller
// level (see `renderParagraph`) so consecutive list-items can land
// inside one <ul>.
export function renderBlock(block: Block, citations: Map<number, Citation>): JSX.Element {
  if (block.kind === "hr") return <hr class="md-hr" />;
  const inline = renderRich(parseRichText(block.body), citations);
  switch (block.kind) {
    case "h1":
      return <h2 class="md-h1">{inline}</h2>;
    case "h2":
      return <h3 class="md-h2">{inline}</h3>;
    case "h3":
      return <h4 class="md-h3">{inline}</h4>;
    case "list-item":
      return <li>{inline}</li>;
    default:
      return <p>{inline}</p>;
  }
}

// A paragraph from the server may decompose into multiple blocks
// (e.g. `**Sources**\n- a\n- b` becomes one bold paragraph + two
// list items). Group consecutive list-item blocks into a single
// <ul> so the bullets share semantic context and CSS can space
// them as a list.
export function renderParagraph(p: string, citations: Map<number, Citation>): JSX.Element {
  const blocks = parseBlocks(p);
  const out: JSX.Element[] = [];
  let listBuffer: Block[] = [];
  const flushList = () => {
    if (listBuffer.length === 0) return;
    const items = listBuffer.map((b) => renderBlock(b, citations));
    listBuffer = [];
    out.push(<ul class="md-list">{items}</ul>);
  };
  for (const block of blocks) {
    if (block.kind === "list-item") {
      listBuffer.push(block);
    } else {
      flushList();
      out.push(renderBlock(block, citations));
    }
  }
  flushList();
  return out;
}
