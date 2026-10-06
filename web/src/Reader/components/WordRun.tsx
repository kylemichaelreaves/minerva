// Per-chunk word tokenisation for the Reader stage. Each word either:
//   - falls inside a term-occurrence span → wrapped in a clickable
//     .term-mark with no hover tooltip (the click is the gesture);
//   - or is an ordinary word → wrapped in `<span class="gw">` for the
//     dashed-underline hover affordance. Greek / Hebrew / Arabic
//     words get a HoverTip with their respective romanization (Greek
//     via lib/greek.romanize, Hebrew via lib/hebrew.romanize, Arabic
//     via lib/arabic.romanize); any word the user has previously
//     clicked also gets a HoverTip carrying its cached translation.
// Selection still works across all spans, so the mouseUp → translate
// flow is unaffected.

import { For, Show, type JSX } from "solid-js";
import { HoverTip } from "~/components/primitives/HoverTip";
import { detectAnchorDirection } from "~/utils/popoverPosition";
import { romanize as romanizeArabic } from "~/utils/arabic";
import { romanize as romanizeGreek, tokenizeWords } from "~/utils/greek";
import { romanize as romanizeHebrew } from "~/utils/hebrew";
import type { TermOccurrenceSpan } from "~/utils/types";
import { occurrenceFor, type PinnedHighlight } from "~/Reader/utils";

function WordToken(props: {
  class: string;
  offset: number;
  title?: string;
  onClick: (e: MouseEvent & { currentTarget: HTMLSpanElement }) => void;
  dataTermId?: number;
  children: JSX.Element;
}) {
  return (
    <span
      class={props.class}
      data-offset={props.offset}
      data-term-id={props.dataTermId}
      title={props.title}
      // eslint-disable-next-line minerva/no-mouse-only-click -- one tab stop per word is unusable; needs a roving-tabindex design (#785)
      onClick={(e) => {
        props.onClick(e);
      }}
    >
      {props.children}
    </span>
  );
}

export function WordRun(props: {
  text: string;
  lang: string;
  occurrences: TermOccurrenceSpan[];
  /** When set, words whose offset falls inside one of these spans
   *  receive a `.lemma-hl` class so the user can see every site of
   *  the currently-open word's lemma on the page. Spans typically
   *  align with word boundaries (the lemmatizer cache stores
   *  surface_start/surface_end exactly), so an inclusive containment
   *  check is enough. */
  highlights: { start: number; end: number }[];
  pinned: PinnedHighlight[];
  chunkId: string;
  onTermClick: (termId: number, anchor: DOMRect, direction?: "ltr" | "rtl") => void;
  onWordClick: (word: string, chunkId: string, offset: number, lineEl: Element | null) => void;
  onPinnedClick?: (chunkId: string, start: number, end: number) => void;
  /** Shift-click on a saved underline removes it. The handler signs
   *  off persisted state so the marker stays gone after reload. */
  onPinnedRemove?: (chunkId: string, start: number, end: number) => void;
  wordTranslation?: (chunkId: string, offset: number) => string | undefined;
}) {
  // Per-lang transliteration dispatch. `null` means no hover-
  // romanization for this chunk's source language (e.g., German
  // Hegel, English Hume — already in Latin script, no help needed).
  // Accessor, not an IIFE-computed const: `props.lang` must stay a
  // reactive read so the dispatch follows an edition swap.
  const transliterate = () => {
    if (props.lang === "grc") return romanizeGreek;
    if (props.lang === "heb") return romanizeHebrew;
    if (props.lang === "ara") return romanizeArabic;
    return null;
  };
  const isHighlighted = (offset: number, length: number) => {
    for (const h of props.highlights) {
      if (h.start <= offset && offset + length <= h.end) return true;
    }
    return false;
  };
  const pinnedFor = (offset: number, length: number) => {
    for (const p of props.pinned) {
      if (p.start <= offset && offset + length <= p.end) return p;
    }
    return null;
  };
  const onPinnedClickInner = (
    e: MouseEvent & { currentTarget: HTMLElement },
    p: PinnedHighlight,
  ) => {
    e.stopPropagation();
    e.preventDefault();
    if (e.shiftKey) {
      props.onPinnedRemove?.(p.chunkId, p.start, p.end);
      return;
    }
    if (!props.onPinnedClick) return;
    props.onPinnedClick(p.chunkId, p.start, p.end);
  };
  const onClickWord = (e: MouseEvent & { currentTarget: HTMLSpanElement }) => {
    // Stop the document-level outside-click dismisser (registered
    // while a TermCard is open) from clearing the rail's signal —
    // and stop the .stage mouseUp path from racing this click via
    // a phantom collapsed selection.
    e.stopPropagation();
    const line = e.currentTarget.closest(".line");
    const offset = Number(e.currentTarget.dataset.offset ?? "0");
    const word = e.currentTarget.textContent;
    props.onWordClick(word, props.chunkId, offset, line);
  };
  return (
    <For each={tokenizeWords(props.text)}>
      {(t) => {
        if (!t.word) return <>{t.s}</>;
        // The occurrence test must be inside <Show> (not a plain
        // ternary) so it re-evaluates when props.occurrences arrives
        // from the async map fetch — otherwise the For closure runs
        // once with an empty occurrences array and never flips to
        // .term-mark when the data lands.
        const pin = () => pinnedFor(t.offset, t.s.length);
        const baseClass = (extra: string) => {
          const lemma = isHighlighted(t.offset, t.s.length) ? " lemma-hl" : "";
          const p = pin();
          const pCls = p ? (p.saved ? " pin-hl saved" : " pin-hl") : "";
          return `${extra}${lemma}${pCls}`;
        };
        const titleAttr = () => {
          const p = pin();
          if (!p?.saved) return undefined;
          return "Saved translation — click to reopen, ⇧-click to remove";
        };
        const handleClick = (e: MouseEvent & { currentTarget: HTMLSpanElement }) => {
          const p = pin();
          if (p?.saved) {
            onPinnedClickInner(e, p);
            return;
          }
          onClickWord(e);
        };
        const hoverTip = () => {
          const cached = props.wordTranslation?.(props.chunkId, t.offset);
          if (cached) return cached;
          const tr = transliterate();
          if (tr) {
            const r = tr(t.s);
            // Suppress empty / unchanged romanizations (e.g., a
            // single-letter Arabic alef with no consonants left)
            // so the tooltip doesn't flash an empty bubble.
            if (r && r !== t.s) return r;
          }
          return undefined;
        };
        return (
          <Show
            when={occurrenceFor(props.occurrences, t.offset, t.s.length)}
            fallback={
              <Show
                when={hoverTip()}
                fallback={
                  <WordToken
                    class={baseClass("gw")}
                    offset={t.offset}
                    title={titleAttr()}
                    onClick={handleClick}
                  >
                    {t.s}
                  </WordToken>
                }
              >
                {(body) => (
                  <HoverTip body={body()}>
                    <WordToken
                      class={baseClass("gw")}
                      offset={t.offset}
                      title={titleAttr()}
                      onClick={handleClick}
                    >
                      {t.s}
                    </WordToken>
                  </HoverTip>
                )}
              </Show>
            }
          >
            {(occ) => (
              <WordToken
                class={baseClass("term-mark")}
                offset={t.offset}
                dataTermId={occ().term_id}
                onClick={(e) => {
                  e.stopPropagation();
                  const rect = e.currentTarget.getBoundingClientRect();
                  props.onTermClick(occ().term_id, rect, detectAnchorDirection(e.currentTarget));
                }}
              >
                {t.s}
              </WordToken>
            )}
          </Show>
        );
      }}
    </For>
  );
}
