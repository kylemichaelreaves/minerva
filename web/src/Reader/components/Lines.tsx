// Reader stage: one `.line` per source chunk (section label, word
// runs, optional cross-reference marker). Word-level tokenisation
// lives in WordRun.tsx.

import { createMemo, For, Show } from "solid-js";
import type { LemmaHighlights, OccurrenceMap, SourceChunk } from "~/utils/types";
import { XrefMarker } from "~/components/cards/XrefMarker";
import { classnames } from "~/utils/util";
import type { PinnedHighlight } from "~/Reader/utils";
import { WordRun } from "~/Reader/components/WordRun";
import { EditorialBlock } from "~/Reader/components/EditorialBlock";

interface EditorialRun<T> {
  editorial: boolean;
  items: T[];
}

/** True when every item of `a` is the same object (by `===`) as the
 *  corresponding item of `b`. Used to tell "this run's membership is
 *  unchanged" from "this run grew/shrank/reordered" without assuming
 *  anything about how the caller produced either array. */
function sameItemsByReference<T>(a: T[], b: T[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/** Consecutive runs of one block_type, so an apparatus run collapses as a
 *  single disclosure rather than one per chunk.
 *
 *  `cache` is an opaque, caller-owned Map that persists across calls (one
 *  per `Lines` instance). Each run is keyed by its first chunk's
 *  `chunk_id` plus its length and `editorial` flag — durable because
 *  `chunk_id` is stable for the life of a chunk and unique within a work,
 *  so two different runs can't collide on it. When a key's cached run has
 *  the exact same chunk objects in the exact same order, the cached
 *  wrapper object is reused rather than a fresh one allocated, so `<For>`
 *  sees the same reference for that run and does not tear its DOM down.
 *  Only a run whose membership actually changed (the growing tail run on
 *  an infinite-scroll append, or a genuinely new run) gets a new wrapper. */
function groupEditorialRuns<T extends { block_type?: string | null; chunk_id: string }>(
  chunks: T[],
  cache: Map<string, EditorialRun<T>>,
): EditorialRun<T>[] {
  const out: EditorialRun<T>[] = [];
  const liveKeys = new Set<string>();
  let i = 0;
  while (i < chunks.length) {
    const first = chunks[i];
    if (!first) break; // unreachable: i < chunks.length
    const editorial = first.block_type === "editorial";
    let j = i + 1;
    while (j < chunks.length && (chunks[j]?.block_type === "editorial") === editorial) {
      j++;
    }
    const items = chunks.slice(i, j);
    const key = `${first.chunk_id}:${items.length}:${editorial}`;
    const cached = cache.get(key);
    const run =
      cached?.editorial === editorial && sameItemsByReference(cached.items, items)
        ? cached
        : { editorial, items };
    cache.set(key, run);
    liveKeys.add(key);
    out.push(run);
    i = j;
  }
  // Drop entries no run resolved to this pass (e.g. a work switch that
  // replaces `chunks` wholesale) so the cache doesn't grow unboundedly.
  for (const key of cache.keys()) {
    if (!liveKeys.has(key)) cache.delete(key);
  }
  return out;
}

/** Per-chunk reference summary fed in from the references_map fetch.
 *  Lines only needs the count for rendering the marker; the full
 *  payload (target metadata, quoted phrase, etc.) is fetched by the
 *  caller on click and passed into a ReferenceCard. */
export interface XrefSummary {
  count: number;
}
export type XrefMap = Record<string, XrefSummary>;

export function Lines(props: {
  chunks: SourceChunk[];
  lang: string;
  occMap: OccurrenceMap | null;
  /** When non-null, the reader paints a highlight on every word
   *  whose offset matches a span in `by_chunk[chunkId]`. The lemma
   *  itself is in `lemmaHighlights.lemma` for css/aria use. */
  lemmaHighlights: LemmaHighlights | null;
  /** Selection-driven pinned highlights painted by the Reader after
   *  a translation commits. One entry per chunk the selection
   *  touched. `saved=true` means the rail has been dismissed; the
   *  marker drops to a hairline underline. */
  pinnedHighlights?: PinnedHighlight[];
  /** Click handler for a saved-underline marker — re-opens the
   *  rail with the cached translation. */
  onPinnedClick?: (chunkId: string, start: number, end: number) => void;
  /** Shift-click on a saved underline removes it. The handler signs
   *  off persisted state so the marker stays gone after reload. */
  onPinnedRemove?: (chunkId: string, start: number, end: number) => void;
  /** Optional map of chunk_id → outgoing-reference summary. When
   *  omitted (the common path until the Reader wires
   *  `/api/works/:id/references_map` in), no markers render and the
   *  24px gutter column stays empty — the page never shifts. */
  xrefMap?: XrefMap;
  /** chunk_id whose ReferenceCard is currently open. The marker on
   *  that row renders in active state (accent) while the card is
   *  anchored. */
  openRefChunkId?: string | null;
  /** Click handler for a marker. Receives the chunk_id and the
   *  marker's bounding rect so the caller can fetch the references
   *  for that chunk and anchor the ReferenceCard popover. */
  onXrefOpen?: (chunkId: string, anchor: DOMRect) => void;
  onTermClick: (termId: number, anchor: DOMRect, direction?: "ltr" | "rtl") => void;
  onWordClick: (word: string, chunkId: string, offset: number, lineEl: Element | null) => void;
  /** When set, returns a cached translation for a previously-clicked
   *  word at (chunkId, offset) in the current target language. */
  wordTranslation?: (chunkId: string, offset: number) => string | undefined;
}) {
  // Accessors, not consts — `props.lang` must stay a reactive read so
  // the script-family classes update if the Reader swaps editions
  // (e.g. grc → eng) without remounting Lines.
  const isGreek = () => props.lang === "grc";
  const isHebrew = () => props.lang === "heb";
  const isArabic = () => props.lang === "ara";
  const isRtl = () => isHebrew() || isArabic();
  // The pre-existing `.latin` class triggered the serif body font.
  // Now that we have three families (Greek default, Latin serif, RTL
  // Hebrew/Arabic), the LTR fallback is "everything that isn't Greek
  // and isn't RTL" — the same set that used to be flagged isLatin.
  const isLatin = () => !isGreek() && !isRtl();
  // `<For>` reconciles on referential identity of the *items* it's given,
  // not the array. `groupEditorialRuns` allocates a fresh `{ editorial,
  // items }` wrapper per run on every call, so wrapping it in a
  // `createMemo` keyed on `props.chunks` does NOT help: `props.chunks` is
  // itself a fresh array on every infinite-scroll append
  // (`useWorkRange`'s `[...cur.chunks, ...next.chunks]`, which preserves
  // each existing chunk's identity but not the array's), so the memo
  // recomputes and every wrapper is rebuilt anyway (#544).
  //
  // Two things actually keep old rows from being torn down:
  //
  // 1. `hasEditorial` skips the wrapper layer entirely for the common
  //    case — a work with no editorial chunks renders `props.chunks`
  //    straight into `<For>`, exactly as before #534, so those chunk
  //    objects (already stable across an append) are the `<For>` items.
  // 2. When there IS editorial material, `groupEditorialRuns` reuses a
  //    run's previous wrapper object out of `runCache` whenever that
  //    run's chunk objects are unchanged (same objects, same order), so
  //    `<For>` gets the same reference for every run except the growing
  //    tail run and any genuinely new run.
  const runCache = new Map<string, EditorialRun<SourceChunk>>();
  const hasEditorial = createMemo(() => props.chunks.some((c) => c.block_type === "editorial"));
  const editorialRuns = createMemo(() =>
    hasEditorial() ? groupEditorialRuns(props.chunks, runCache) : [],
  );
  const renderLine = (chunk: SourceChunk) => {
    const xref = (): XrefSummary | undefined => props.xrefMap?.[chunk.chunk_id];
    return (
      <div
        class={classnames(
          "line",
          isRtl() && "rtl",
          isHebrew() && "lang-heb",
          isArabic() && "lang-ara",
        )}
        data-chunk-id={chunk.chunk_id}
        // Structural role (Hegel Remark/Addition, etc.). Absent for
        // ordinary body prose; reader.css indents the set-apart blocks.
        data-block={chunk.block_type ?? undefined}
        // Objections carry the objector's name (Hobbes, Arnauld, …);
        // reader.css renders it as a small voice tag above the block.
        data-speaker={chunk.block_type === "objection" ? (chunk.speaker ?? undefined) : undefined}
      >
        <span class="num">{chunk.section ?? chunk.ord + 1}</span>
        <span class="text" dir={isRtl() ? "rtl" : undefined}>
          <WordRun
            text={chunk.text}
            lang={props.lang}
            chunkId={chunk.chunk_id}
            occurrences={props.occMap?.by_chunk[chunk.chunk_id] ?? []}
            highlights={props.lemmaHighlights?.by_chunk[chunk.chunk_id] ?? []}
            pinned={(props.pinnedHighlights ?? []).filter((p) => p.chunkId === chunk.chunk_id)}
            onPinnedClick={props.onPinnedClick}
            onPinnedRemove={props.onPinnedRemove}
            onTermClick={props.onTermClick}
            onWordClick={props.onWordClick}
            wordTranslation={props.wordTranslation}
          />
        </span>
        {/* The 24px right-gutter cell is always present (grid
            reserves the column) so the page never shifts as
            markers come and go. The marker itself only renders
            when this chunk has outgoing references AND the caller
            has wired an open-handler. */}
        <span class="line-marker">
          <Show when={xref()}>
            {(x) => (
              <Show when={props.onXrefOpen}>
                {(onXrefOpen) => (
                  <XrefMarker
                    count={x().count}
                    active={props.openRefChunkId === chunk.chunk_id}
                    onOpen={(rect) => {
                      onXrefOpen()(chunk.chunk_id, rect);
                    }}
                  />
                )}
              </Show>
            )}
          </Show>
        </span>
      </div>
    );
  };
  return (
    <div class={classnames("lines", isLatin() && "latin", isRtl() && "rtl")}>
      <Show when={hasEditorial()} fallback={<For each={props.chunks}>{renderLine}</For>}>
        <For each={editorialRuns()}>
          {(run) => (
            <Show when={run.editorial} fallback={<For each={run.items}>{renderLine}</For>}>
              <EditorialBlock
                label={run.items[0]?.section?.split(",")[0] ?? "Editorial material"}
                count={run.items.length}
              >
                <For each={run.items}>{renderLine}</For>
              </EditorialBlock>
            </Show>
          )}
        </For>
      </Show>
    </div>
  );
}
