import { For, Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { fetchChunkContext } from "~/api/readerApi";
import { apiError } from "~/utils/apiError";
import { dominantGlyph, dominantName } from "~/utils/dominantPhil";
import { renderParagraph } from "~/utils/renderMarkdown";
import type { ChunkContextResponse, Citation, MinervaTurn } from "~/utils/types";
import { classnames, errorMessage, isAbortError } from "~/utils/util";
import { CiteLocatorLink, PinButton } from "~/Thread/components/CiteControls";
import { MarginNote } from "~/Thread/components/MarginNote";

// Grapheme-aware character splitter for the token-stream reveal. Splitting
// per user-perceived character keeps the glow granular while never tearing
// a combining mark off its base letter (Greek breathings/accents, Hebrew
// niqqud, Arabic harakat) — code-point or naive splitting would. Falls back
// to code points if Intl.Segmenter is unavailable.
const graphemeSegmenter =
  typeof Intl !== "undefined" && "Segmenter" in Intl
    ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
    : null;

function splitGraphemes(text: string): string[] {
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(text), (s) => s.segment);
  }
  return Array.from(text);
}

export type ExpandedState =
  | { status: "loading" }
  | { status: "ready"; context: ChunkContextResponse }
  | { status: "error"; message: string };

export type ExpandedStateValue = ExpandedState | undefined;

export function useCitationExpand(
  onOpenReader?: (workId: string, sourceLang: string | undefined, chunkId: string) => void,
) {
  const [expanded, setExpanded] = createSignal<Record<string, ExpandedState>>({});
  const inflight = new Map<string, AbortController>();

  function cancelInflight(id: string): void {
    const c = inflight.get(id);
    if (c) {
      c.abort();
      inflight.delete(id);
    }
  }

  onCleanup(() => {
    for (const c of inflight.values()) c.abort();
    inflight.clear();
  });

  const anyExpanded = () =>
    Object.values(expanded()).some((s) => s.status === "ready" || s.status === "loading");

  async function toggleExpand(citation: Citation) {
    const id = citation.chunk_id;
    if (!id) return;
    if (id in expanded()) {
      cancelInflight(id);
      setExpanded((m) => {
        const { [id]: _drop, ...rest } = m;
        return rest;
      });
      return;
    }
    setExpanded((m) => ({ ...m, [id]: { status: "loading" } }));
    const controller = new AbortController();
    inflight.set(id, controller);
    try {
      const context = await fetchChunkContext(id, 1, controller.signal);
      setExpanded((m) => ({ ...m, [id]: { status: "ready", context } }));
    } catch (err) {
      if (isAbortError(err)) return;
      const message = errorMessage(err);
      setExpanded((m) => ({ ...m, [id]: { status: "error", message } }));
    } finally {
      if (inflight.get(id) === controller) inflight.delete(id);
    }
  }

  function openInReader(citation: Citation) {
    const id = citation.chunk_id;
    if (!id || !onOpenReader) return;
    const cur = expanded()[id] as
      | { status: "ready"; context: { work: string; lang: string } }
      | undefined;
    if (cur?.status === "ready") {
      onOpenReader(cur.context.work, cur.context.lang, id);
      return;
    }
    void fetchChunkContext(id, 0)
      .then((ctx) => {
        onOpenReader(ctx.work, ctx.lang, id);
      })
      .catch((err: unknown) => {
        console.warn("failed to resolve work for citation", err);
        apiError("Couldn't open that citation in the reader.");
      });
  }

  return { expanded, anyExpanded, toggleExpand, openInReader };
}

export function MinervaTurnView(props: {
  msg: MinervaTurn;
  marginNotes: boolean;
  pinnedChunkIds?: string[];
  onTogglePin?: (chunkId: string) => void;
  onOpenReader?: (workId: string, sourceLang: string | undefined, chunkId: string) => void;
}) {
  const streaming = () => Boolean(props.msg.streaming);
  const philName = () => dominantName(props.msg.dominant);
  const philGlyph = () => dominantGlyph(props.msg.dominant);
  const abstained = () => Boolean(props.msg.abstained);

  // Token-stream reveal — a steady-cadence "typewriter" that decouples how
  // fast characters appear from how fast they arrive over SSE. Anthropic
  // streams tiny, bursty token deltas (often 1-3 chars) and the abstain /
  // retrieval-only paths emit the whole body in one chunk, so staggering
  // *within* a delta is invisible. Instead the network delta is the
  // producer — it pushes graphemes into a queue — and a fixed-interval
  // consumer reveals them a few at a time, giving a smooth left-to-right
  // glow cascade regardless of arrival pattern. Mirrors the producer/
  // consumer split in the "Token Stream" design. Each revealed character
  // is its own <For> row, so only new characters mount and run the glow;
  // earlier ones keep their DOM and never re-fire. Closure state is
  // per-turn (one component instance per Minerva turn).
  const REVEAL_INTERVAL_MS = 16;
  const [revealed, setRevealed] = createSignal<{ text: string; id: number }[]>([]);
  let queue: string[] = [];
  let consumedLen = 0;
  let pieceSeq = 0;
  let revealTimer: ReturnType<typeof setInterval> | undefined;

  const stopConsumer = () => {
    if (revealTimer !== undefined) {
      clearInterval(revealTimer);
      revealTimer = undefined;
    }
  };
  onCleanup(stopConsumer);

  const startConsumer = () => {
    if (revealTimer !== undefined) return;
    revealTimer = setInterval(() => {
      if (queue.length === 0) {
        // Nothing left to type. Keep ticking while the stream is live (more
        // may arrive); stop once it has finished.
        if (!streaming()) stopConsumer();
        return;
      }
      // Reveal more per tick as the backlog grows, so a fast stream — or a
      // single whole-body chunk — can't fall far behind, while a trickle
      // still types one character at a time.
      const backlog = queue.length;
      const batch =
        backlog > 600 ? 20 : backlog > 240 ? 8 : backlog > 100 ? 4 : backlog > 32 ? 2 : 1;
      const next = queue.splice(0, batch).map((text) => ({ text, id: pieceSeq++ }));
      setRevealed((r) => [...r, ...next]);
    }, REVEAL_INTERVAL_MS);
  };

  createEffect(() => {
    const full = streaming() ? (props.msg.streamText ?? "") : "";
    if (full.length < consumedLen) {
      // Stream reset (defensive — a fresh stream on a reused node).
      queue = [];
      consumedLen = 0;
      setRevealed([]);
    }
    if (full.length > consumedLen) {
      queue.push(...splitGraphemes(full.slice(consumedLen)));
      consumedLen = full.length;
      startConsumer();
    }
  });
  // Memo — the For row below calls this once per paragraph; without
  // the memo each call rebuilt the Map from scratch.
  const citationsByN = createMemo(() => new Map(props.msg.citations.map((c) => [c.n, c])));

  const { expanded, anyExpanded, toggleExpand, openInReader } = useCitationExpand(
    props.onOpenReader,
  );

  return (
    <div
      class={classnames(
        "turn",
        "turn-minerva",
        !streaming() && "fade-in",
        streaming() && "turn-streaming",
        abstained() && "turn-abstain",
        anyExpanded() && "has-expanded",
      )}
    >
      <div class="turn-meta">
        <span>Minerva · {props.msg.time}</span>
        <Show when={!abstained() && !streaming()}>
          <span class="dot-sep" />
          <span class="turn-philosopher">
            <span class="glyph">{philGlyph()}</span>
            {philName()}
          </span>
        </Show>
        <Show when={!abstained() && streaming()}>
          <span class="dot-sep" />
          <span class="turn-philosopher" style={{ color: "var(--ink-faint)" }}>
            <span class="glyph">M</span>…
          </span>
        </Show>
        <Show when={abstained()}>
          <span class="dot-sep" />
          <span class="turn-philosopher" style={{ color: "var(--ink-faint)" }}>
            no evidence in corpus
          </span>
        </Show>
      </div>
      <div class="turn-inner">
        <Show
          when={streaming()}
          fallback={
            <div class="turn-body">
              <For each={props.msg.paragraphs}>{(p) => renderParagraph(p, citationsByN())}</For>
            </div>
          }
        >
          <div class="turn-body turn-body-streaming">
            <For each={revealed()}>{(ch) => <span class="tok-reveal">{ch.text}</span>}</For>
            <span class="stream-cursor" aria-hidden="true" />
          </div>
        </Show>

        <Show when={!abstained() && props.marginNotes && props.msg.citations.length > 0}>
          <div class="margin-notes">
            <For each={props.msg.citations}>
              {(c) => (
                <MarginNote
                  citation={c}
                  state={c.chunk_id ? expanded()[c.chunk_id] : undefined}
                  onToggleExpand={() => void toggleExpand(c)}
                  onOpenReader={() => {
                    openInReader(c);
                  }}
                  onTogglePin={props.onTogglePin}
                  pinnedChunkIds={props.pinnedChunkIds}
                />
              )}
            </For>
          </div>
        </Show>

        <Show when={!abstained() && !props.marginNotes && props.msg.citations.length > 0}>
          <For each={props.msg.citations}>
            {(c) => (
              <div class={classnames("pull-quote", c.pinned && "is-pinned")}>
                {c.text}
                <span class="src">
                  [{c.n}] {c.speaker ? `${c.speaker} · ` : ""}
                  <CiteLocatorLink
                    citation={c}
                    enabled={Boolean(props.onOpenReader)}
                    onOpen={() => {
                      openInReader(c);
                    }}
                  />
                  <PinButton
                    citation={c}
                    onTogglePin={props.onTogglePin}
                    pinnedChunkIds={props.pinnedChunkIds}
                  />
                </span>
              </div>
            )}
          </For>
        </Show>
      </div>
    </div>
  );
}
