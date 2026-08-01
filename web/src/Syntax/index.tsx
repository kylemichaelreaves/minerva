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
import { SentenceList } from "~/Syntax/components/SentenceList";
import { TokenInspector } from "~/Syntax/components/TokenInspector";
import "~/Syntax/syntax.css";

// The close-reading overlay: one chunk's syntax, full-bleed off the Reader,
// following the `#/network/arc` drilldown pattern.
//
// Read-only for now. Reattachment, relabelling and the refusal states need the
// correction POST endpoint, which is the next phase.

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

  const sentences = () => doc()?.sentences ?? [];
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

  const correctedCount = createMemo(() => tokens().filter((t) => t.corrected).length);

  // Esc closes; ←/→ move between sentences. The brief's quality floor asks for
  // keyboard navigation, and this is the cheapest half of it.
  onMount(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (selected() !== null) setSelected(null);
        else props.onClose();
      }
      if (e.key === "ArrowRight") setSentOrd((n) => Math.min(n + 1, sentences().length - 1));
      if (e.key === "ArrowLeft") setSentOrd((n) => Math.max(n - 1, 0));
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
          </Show>
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
                onSelect={(id) => setSelected((cur) => (cur === id ? null : id))}
              />
              <p class="syn-hint">
                Hover a token to isolate the subtree it governs · click to inspect ·{" "}
                <span class="syn-kbd">←</span> <span class="syn-kbd">→</span> between sentences
              </p>
            </Match>
            <Match when={true}>
              <div class="syn-empty">No syntax for this passage.</div>
            </Match>
          </Switch>
        </main>
      </div>

      <Show when={selectedToken()}>
        {(tok) => (
          <TokenInspector token={tok()} head={headOfSelected()} onClose={() => setSelected(null)} />
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
