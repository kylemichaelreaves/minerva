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

/** Consecutive runs of one block_type, so an apparatus run collapses as a
 *  single disclosure rather than one per chunk. */
function groupEditorialRuns<T extends { block_type?: string | null }>(
  chunks: T[],
): { editorial: boolean; items: T[] }[] {
  const out: { editorial: boolean; items: T[] }[] = [];
  for (const chunk of chunks) {
    const editorial = chunk.block_type === "editorial";
    const last = out[out.length - 1];
    if (last?.editorial === editorial) last.items.push(chunk);
    else out.push({ editorial, items: [chunk] });
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
  // Memoised so infinite-scroll appends (`useWorkRange`'s
  // `[...cur.chunks, ...next.chunks]`, which preserves each existing
  // chunk's identity on purpose) don't force `<For>` to rebuild every
  // already-rendered line. `<For>` reconciles on referential identity of
  // the array it's given; calling `groupEditorialRuns` directly in the
  // JSX rebuilt brand-new wrapper objects on every evaluation, defeating
  // that diff (#533 review finding 2).
  const editorialRuns = createMemo(() => groupEditorialRuns(props.chunks));
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
          <Show when={xref() && props.onXrefOpen}>
            <XrefMarker
              count={xref()!.count}
              active={props.openRefChunkId === chunk.chunk_id}
              onOpen={(rect) => {
                props.onXrefOpen!(chunk.chunk_id, rect);
              }}
            />
          </Show>
        </span>
      </div>
    );
  };
  return (
    <div class={classnames("lines", isLatin() && "latin", isRtl() && "rtl")}>
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
    </div>
  );
}
