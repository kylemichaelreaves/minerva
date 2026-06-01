import { For, Show, createSignal, onCleanup } from "solid-js";
import { fetchChunkContext } from "~/api/readerApi";
import { apiError } from "~/utils/apiError";
import { dominantGlyph, dominantName } from "~/utils/dominantPhil";
import { renderParagraph } from "~/utils/renderMarkdown";
import type { ChunkContextResponse, Citation, MinervaTurn } from "~/utils/types";
import { classnames, errorMessage, isAbortError } from "~/utils/util";
import { CiteLocatorLink, PinButton } from "~/Thread/components/CiteControls";
import { MarginNote } from "~/Thread/components/MarginNote";

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
  const citationsByN = () => new Map(props.msg.citations.map((c) => [c.n, c]));

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
            {props.msg.streamText ?? ""}
            <span class="stream-cursor" aria-hidden="true" />
          </div>
        </Show>

        <Show when={!abstained() && props.marginNotes && props.msg.citations}>
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

        <Show when={!abstained() && !props.marginNotes && props.msg.citations}>
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
