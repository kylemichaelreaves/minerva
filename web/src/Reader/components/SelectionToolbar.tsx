// Floating action toolbar that appears after a text selection settles.
// Sits between the gesture (drag-select on .stage) and the rail-open
// commit — gives the user a chance to refine the selection without
// burning an LLM call on every intermediate pointerup.
//
// Shapes, driven by `singleWord` and by which optional handlers are given:
//   • multi-word:  [ Translate phrase · T ] [ Syntax · S ]? [Copy] [ <count> ]
//   • single-word: [ Look up · L ] [ Translate · T ] [ Syntax · S ]? [Copy] [ <count> ]
// `?` = rendered only when the corresponding handler is supplied.

import { Show, onCleanup, onMount } from "solid-js";

export interface ToolbarAnchor {
  /** Selection bounding rect in viewport coords. */
  rect: DOMRect;
}

export function SelectionToolbar(props: {
  anchor: ToolbarAnchor;
  /** Plain-language summary, e.g. "4 words · 22 chars". */
  count: string;
  /** When true, render the single-word fork (Look up + Translate). */
  singleWord: boolean;
  onTranslate: () => void;
  onLookup?: () => void;
  /** Supplied only when the syntax overlay is available for this
   *  selection — the Reader withholds it for non-German editions, since
   *  the dependency parser is German-only. Absent means no button. */
  onSyntax?: () => void;
  onCopy: () => void;
  onDismiss: () => void;
}) {
  let el: HTMLDivElement | undefined;

  // Position: prefer above the selection (matches design's .tp-toolbar
  // default). Flip below if there's <60px of headroom above. Clamp
  // horizontally to the viewport with an 8px margin.
  const place = () => {
    if (!el) return;
    const r = props.anchor.rect;
    const tbW = el.offsetWidth || 240;
    const tbH = el.offsetHeight || 40;
    const margin = 8;
    const vw = window.innerWidth;
    const above = r.top - tbH - 10;
    const below = r.bottom + 10;
    const flipBelow = above < 60;
    const top = flipBelow ? below : above;
    el.classList.toggle("below", flipBelow);
    // Horizontal anchor: align toolbar's caret (22px from left edge in
    // the design) under the selection's horizontal midpoint.
    const midX = r.left + r.width / 2;
    let left = midX - 22 - tbW / 2;
    if (left < margin) left = margin;
    if (left + tbW > vw - margin) left = vw - tbW - margin;
    el.style.top = `${Math.round(top)}px`;
    el.style.left = `${Math.round(left)}px`;
  };

  onMount(() => {
    place();
    const handler = () => { place(); };
    window.addEventListener("resize", handler);
    window.addEventListener("scroll", handler, true);
    onCleanup(() => {
      window.removeEventListener("resize", handler);
      window.removeEventListener("scroll", handler, true);
    });
  });

  // Mousedown handler stops native selection from clearing — without
  // preventDefault on mousedown, clicking the toolbar collapses the
  // selection before the click reaches our buttons.
  const swallow = (e: MouseEvent) => {
    e.preventDefault();
  };

  return (
    <div
      ref={el}
      class="selection-toolbar"
      role="toolbar"
      aria-label="Selection actions"
      onMouseDown={swallow}
    >
      <Show when={props.singleWord && props.onLookup}>
        <button
          type="button"
          class="st-btn"
          onClick={() => { props.onLookup!(); }}
          title="Look up (L)"
        >
          <span>Look up</span>
          <span class="kbd">L</span>
        </button>
        <div class="st-sep" />
      </Show>
      <button
        type="button"
        class="st-btn"
        onClick={() => { props.onTranslate(); }}
        title="Translate (T)"
      >
        <span>{props.singleWord ? "Translate" : "Translate phrase"}</span>
        <span class="kbd">T</span>
      </button>
      <Show when={props.onSyntax}>
        <div class="st-sep" />
        <button
          type="button"
          class="st-btn"
          onClick={() => { props.onSyntax!(); }}
          title="Syntax (S)"
        >
          <span>Syntax</span>
          <span class="kbd">S</span>
        </button>
      </Show>
      <div class="st-sep" />
      <button
        type="button"
        class="st-btn"
        onClick={() => { props.onCopy(); }}
        title="Copy selection"
      >
        <span>Copy</span>
      </button>
      <div class="st-sep" />
      <span class="st-count">{props.count}</span>
    </div>
  );
}
