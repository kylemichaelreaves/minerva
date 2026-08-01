import {
  For,
  Match,
  Show,
  Switch,
  createMemo,
  createResource,
  createSignal,
  onCleanup,
  onMount,
} from "solid-js";
import { fetchChunkSyntax } from "~/api/syntaxApi";
import { ArcDiagram } from "~/Syntax/components/ArcDiagram";
import { RefusalPanel } from "~/Syntax/components/RefusalPanel";
import { RelationPicker } from "~/Syntax/components/RelationPicker";
import { SentenceList } from "~/Syntax/components/SentenceList";
import { TokenInspector } from "~/Syntax/components/TokenInspector";
import { exportConllu, exportFilename, exportPatch } from "~/Syntax/corrections/export";
import { fromApi } from "~/Syntax/corrections/apply";
import { createCorrectionStore, httpTransport } from "~/Syntax/corrections/store";
import "~/Syntax/syntax.css";

// The close-reading overlay: one chunk's syntax, full-bleed off the Reader,
// following the `#/network/arc` drilldown pattern.
//
// Correcting the parse is the primary activity, not viewing it — no gold
// German treebank exists for philosophical prose, and statistical parsers
// fail precisely where the syntax is doing interpretive work. So this phase
// adds the relabel loop: pick a token, press L, filter a closed inventory,
// commit. Reattachment by drag is the next one; the machinery underneath it
// (validation, the optimistic queue, undo) is already here and under test.

/** A bracket in the legend, drawn the same way the arcs are. */
function Swatch(props: { kind: "corr" | "mach" | "oxide" }) {
  const stroke = () =>
    props.kind === "corr"
      ? "var(--syn-corr)"
      : props.kind === "oxide"
        ? "var(--syn-oxide)"
        : "var(--syn-mach)";
  return (
    <svg width="26" height="9" aria-hidden="true">
      <path
        d="M1 8 L1 3 Q1 1 3 1 L23 1 Q25 1 25 3 L25 8"
        fill="none"
        stroke={stroke()}
        stroke-width={props.kind === "corr" ? 1.9 : 1.4}
        stroke-dasharray={props.kind === "oxide" ? "3 3" : undefined}
      />
    </svg>
  );
}

/** Hand the browser a file without a round trip through the server. */
function download(filename: string, contents: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export interface SyntaxOverlayProps {
  chunkId: string;
  /** Citation line for the top bar, when the caller knows it. */
  cite?: string;
  onClose: () => void;
}

export function SyntaxOverlay(props: SyntaxOverlayProps) {
  const [doc] = createResource(
    () => props.chunkId,
    (id: string) => fetchChunkSyntax(id),
  );
  const [sentOrd, setSentOrd] = createSignal(0);
  const [hovered, setHovered] = createSignal<number | null>(null);
  const [selected, setSelected] = createSignal<number | null>(null);
  const [picking, setPicking] = createSignal(false);

  // The GET answers with the pristine machine parse and the correction log
  // side by side; the store replays one over the other. Seeding it with the
  // saved log is what makes Revert work on a correction from an earlier
  // session — otherwise the button is there and points at nothing.
  const store = createCorrectionStore(
    props.chunkId,
    () => doc()?.sentences ?? [],
    httpTransport,
    () => (doc()?.corrections ?? []).map(fromApi),
  );

  const sentences = () => store.sentences();
  const current = createMemo(() => sentences().find((s) => s.sent_ord === sentOrd()));
  const tokens = () => current()?.tokens ?? [];

  const selectedToken = createMemo(() => {
    const id = selected();
    return id === null ? undefined : tokens().find((t) => t.id === id);
  });
  const headOfSelected = createMemo(() => {
    const t = selectedToken();
    if (t?.head == null || t.head === 0) return undefined;
    return tokens().find((x) => x.id === t.head);
  });

  /** The correction on the selected token, if this session made one. */
  const correctionOnSelected = createMemo(() => {
    const id = selected();
    if (id === null) return undefined;
    return store
      .corrections()
      .filter((c) => c.sentOrd === sentOrd() && c.tokId === id && c.kind === "deprel")
      .at(-1);
  });

  const correctedCount = createMemo(() => tokens().filter((t) => t.corrected).length);

  const openPicker = () => {
    if (selected() !== null) setPicking(true);
  };

  // Esc closes; ←/→ move between sentences; L relabels the selected token.
  // The picker swallows these while it is open.
  onMount(() => {
    const onKey = (e: KeyboardEvent) => {
      if (picking()) return;
      if (e.key === "Escape") {
        if (store.refusal() !== null) store.clearRefusal();
        else if (selected() !== null) setSelected(null);
        else props.onClose();
      }
      if (e.key === "ArrowRight") setSentOrd((n) => Math.min(n + 1, sentences().length - 1));
      if (e.key === "ArrowLeft") setSentOrd((n) => Math.max(n - 1, 0));
      if ((e.key === "l" || e.key === "L") && selected() !== null) {
        e.preventDefault();
        openPicker();
      }
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => {
      window.removeEventListener("keydown", onKey);
    });
  });

  return (
    <div class="syn">
      <header class="syn-top">
        <div class="l">
          <button type="button" class="syn-back" onClick={() => props.onClose()}>
            ← Reader
          </button>
          <span class="syn-vr" />
          <span class="syn-mode">Syntax</span>
          <Show when={props.cite}>{(cite) => <span class="syn-cite">{cite()}</span>}</Show>
        </div>
        <div class="r">
          <Show when={sentences().length > 1}>
            <span class="syn-status">
              <b>{sentOrd() + 1}</b> of {sentences().length}
            </span>
            <span class="syn-vr" />
          </Show>
          <button
            type="button"
            class="syn-ctl"
            disabled={tokens().length === 0}
            onClick={() => {
              download(
                exportFilename(props.chunkId, "conllu"),
                exportConllu(props.chunkId, sentences()),
                "text/plain;charset=utf-8",
              );
            }}
          >
            Export CoNLL-U
          </button>
          <button
            type="button"
            class="syn-ctl"
            disabled={store.corrections().length === 0}
            onClick={() => {
              download(
                exportFilename(props.chunkId, "json"),
                JSON.stringify(exportPatch(props.chunkId, store.corrections()), null, 2),
                "application/json",
              );
            }}
          >
            Export patch
          </button>
          <span class="syn-vr" />
          <span class="syn-kbd">Esc</span>
        </div>
      </header>

      <div class="syn-body">
        <Show when={sentences().length > 1}>
          <SentenceList
            sentences={sentences()}
            current={sentOrd()}
            onPick={(n) => {
              setSentOrd(n);
              setSelected(null);
              setPicking(false);
            }}
          />
        </Show>

        <main class="syn-stage">
          <Switch>
            <Match when={doc.loading}>
              <div class="syn-empty">Parsing…</div>
            </Match>
            <Match when={doc.error !== undefined}>
              <div class="syn-empty">Could not load syntax for this passage.</div>
            </Match>
            <Match when={tokens().length > 0}>
              <ArcDiagram
                tokens={tokens()}
                hovered={hovered()}
                onHover={setHovered}
                selected={selected()}
                onSelect={(id) => {
                  setSelected((cur) => (cur === id ? null : id));
                  setPicking(false);
                }}
              />
              <p class="syn-hint">
                Hover a token to isolate the subtree it governs · click to inspect ·{" "}
                <span class="syn-kbd">L</span> relabel · <span class="syn-kbd">←</span>{" "}
                <span class="syn-kbd">→</span> between sentences
              </p>
            </Match>
            <Match when={true}>
              <div class="syn-empty">No syntax for this passage.</div>
            </Match>
          </Switch>
        </main>
      </div>

      <Show when={store.refusal()}>
        {(refusal) => (
          <RefusalPanel refusal={refusal()} onDismiss={() => store.clearRefusal()} />
        )}
      </Show>

      <Show when={selectedToken()}>
        {(tok) => (
          <Show
            when={picking()}
            fallback={
              <TokenInspector
                token={tok()}
                head={headOfSelected()}
                wasDeprel={correctionOnSelected()?.fromVal}
                onClose={() => setSelected(null)}
                onRelabel={openPicker}
                onRevert={() => {
                  const c = correctionOnSelected();
                  if (c !== undefined) void store.undo(c.id);
                }}
              />
            }
          >
            <RelationPicker
              form={tok().form}
              tokenId={tok().id}
              headForm={headOfSelected()?.form}
              headId={headOfSelected()?.id}
              current={tok().deprel}
              onCancel={() => setPicking(false)}
              onCommit={(relation) => {
                setPicking(false);
                void store.relabel(sentOrd(), tok().id, relation);
              }}
            />
          </Show>
        )}
      </Show>

      <footer class="syn-foot">
        <div class="syn-legend">
          <For
            each={
              [
                ["corr", "hand-corrected"],
                ["mach", "machine-parsed"],
              ] as const
            }
          >
            {([kind, label]) => (
              <span class="syn-lg">
                <Swatch kind={kind} />
                {label}
              </span>
            )}
          </For>
          <span class="syn-lg">below the row · discontinuous</span>
        </div>
        <div class="syn-status">
          <Show when={store.pending() > 0}>
            <span class="syn-saving">saving…</span>
            <span class="syn-vr" />
          </Show>
          <Show when={tokens().length > 0}>
            <span>{tokens().length} tokens</span>
            <span class="syn-vr" />
            <span>
              <b>{correctedCount()}</b> hand-corrected
            </span>
          </Show>
        </div>
      </footer>
    </div>
  );
}
