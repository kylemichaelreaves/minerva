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
import { legalHeads } from "~/Syntax/corrections/validate";
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
  const [focused, setFocused] = createSignal<number | null>(null);
  /** The token being reattached, or null when not in reattach mode. */
  const [lifted, setLifted] = createSignal<number | null>(null);
  /** Which legal head the reattachment is currently aimed at. */
  const [proposed, setProposed] = createSignal<number | null>(null);
  /** A target that was just refused, so the diagram can mark it. */
  const [refused, setRefused] = createSignal<number | null>(null);

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

  /** The heads the lifted token may take, root slot included. */
  const candidates = createMemo(() => {
    const id = lifted();
    return id === null ? [] : legalHeads(tokens(), id);
  });

  /** Enter reattach mode on *id*, aimed at where it already hangs. */
  const lift = (id: number): void => {
    const legal = legalHeads(tokens(), id);
    if (legal.length === 0) return;
    store.clearRefusal();
    setRefused(null);
    setLifted(id);
    const here = tokens().find((t) => t.id === id)?.head ?? null;
    setProposed(here !== null && legal.includes(here) ? here : (legal[0] ?? null));
  };

  const cancelReattach = (): void => {
    setLifted(null);
    setProposed(null);
    setRefused(null);
  };

  /** Move the aim to the next legal head, wrapping. */
  const aim = (delta: number): void => {
    const legal = candidates();
    if (legal.length === 0) return;
    const at = legal.indexOf(proposed() ?? -1);
    setProposed(legal[(at + delta + legal.length) % legal.length] ?? null);
  };

  /**
   * Commit the lift onto *head*, or onto whatever is currently aimed at.
   *
   * The head is *not* checked against `candidates()` first. A drag can be
   * released over any token, legal or not, and running the illegal ones
   * through `store.reattach` is what produces the refusal with its reason —
   * silently ignoring the drop would leave the user with no idea why nothing
   * happened.
   */
  const commitReattach = async (head?: number): Promise<void> => {
    const id = lifted();
    const target = head ?? proposed();
    if (id === null || target == null) return;
    const ok = await store.reattach(sentOrd(), id, target);
    if (ok) {
      cancelReattach();
      setFocused(id);
    } else {
      // Keep the lift alive so the user can aim somewhere else without
      // starting over; mark what was refused.
      setProposed(null);
      setRefused(target);
    }
  };

  // ---- drag ----
  //
  // Pointer position is tracked on `window` and the drop target resolved with
  // `elementFromPoint` rather than with per-token pointerenter handlers. Two
  // reasons: the ghost sits under the cursor (and is `pointer-events: none`,
  // so it does not shadow the tokens), and a release that lands on empty
  // space has to be distinguishable from one that lands on a token.
  const [ghost, setGhost] = createSignal<{ x: number; y: number; form: string } | null>(null);

  /** The token id under the pointer, or null over anything else. */
  const tokenUnder = (x: number, y: number): number | null => {
    const el = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-tok]");
    const raw = el?.dataset.tok;
    return raw === undefined ? null : Number(raw);
  };

  const beginDrag = (id: number, e: PointerEvent): void => {
    // Only the primary button, and never over the picker.
    if (e.button !== 0 || picking()) return;
    const form = tokens().find((t) => t.id === id)?.form ?? "";
    let dragging = false;
    const startX = e.clientX;
    const startY = e.clientY;

    const move = (ev: PointerEvent) => {
      if (!dragging) {
        // A 4px threshold, so a click is still a click.
        if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < 4) return;
        dragging = true;
        lift(id);
      }
      setGhost({ x: ev.clientX, y: ev.clientY, form });
      const over = tokenUnder(ev.clientX, ev.clientY);
      // Aim only at legal heads while moving; an illegal one stays unaimed so
      // the preview never suggests a drop that will be refused.
      setProposed(over !== null && candidates().includes(over) ? over : null);
    };

    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setGhost(null);
      if (!dragging) return;
      const over = tokenUnder(ev.clientX, ev.clientY);
      if (over === null || over === id) {
        // Released on empty space, or back where it started. Not an edit and
        // not an error.
        cancelReattach();
        return;
      }
      // Illegal targets go through too — the refusal is the point.
      void commitReattach(over);
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  /** Move token focus by *delta* within the sentence, clamped. */
  const moveFocus = (delta: number): void => {
    const ids = tokens().map((t) => t.id);
    if (ids.length === 0) return;
    const at = ids.indexOf(focused() ?? -1);
    const next = at === -1 ? (delta > 0 ? 0 : ids.length - 1) : at + delta;
    setFocused(ids[Math.min(Math.max(next, 0), ids.length - 1)] ?? null);
  };

  // ←/→ move token focus, which is what the acceptance criterion asks for and
  // what keyboard reattach needs. Sentence navigation moved to ↑/↓ — with 53
  // tokens in a row and rarely more than a handful of sentences, the arrows
  // that matter should drive the thing you use constantly.
  //
  // While a token is lifted the same arrows aim the reattachment instead: the
  // gesture is modal, and the status bar says so.
  onMount(() => {
    const onKey = (e: KeyboardEvent) => {
      if (picking()) return;

      if (e.key === "Escape") {
        if (lifted() !== null) cancelReattach();
        else if (store.refusal() !== null) store.clearRefusal();
        else if (selected() !== null) setSelected(null);
        else props.onClose();
        return;
      }

      if (lifted() !== null) {
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          aim(1);
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          aim(-1);
        } else if (e.key === "Enter") {
          e.preventDefault();
          void commitReattach();
        } else if ((e.key === "r" || e.key === "R") && (e.altKey || e.metaKey)) {
          // ⌥R — straight to the root, the one target that is nowhere on the
          // row and would otherwise need arrowing past every token.
          e.preventDefault();
          setProposed(0);
          void commitReattach();
        }
        return;
      }

      if (e.key === "ArrowRight") {
        e.preventDefault();
        moveFocus(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        moveFocus(-1);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSentOrd((n) => Math.min(n + 1, sentences().length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSentOrd((n) => Math.max(n - 1, 0));
      } else if (e.key === "l" || e.key === "L") {
        const id = selected() ?? focused();
        if (id !== null) {
          e.preventDefault();
          setSelected(id);
          setPicking(true);
        }
      } else if (e.key === "r" || e.key === "R") {
        const id = selected() ?? focused();
        if (id !== null) {
          e.preventDefault();
          lift(id);
        }
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
              {/* Frame 06's drop bar. The root is the one target that is
                  nowhere on the row, so it needs somewhere to be. */}
              {/* Not offered to the token that is already the root: `0` is a
                  legal head for it, but only because it is where it already
                  sits, and a drop zone that does nothing is worse than none. */}
              <Show
                when={
                  lifted() !== null &&
                  candidates().includes(0) &&
                  tokens().find((t) => t.id === lifted())?.head !== 0
                }
              >
                <button
                  type="button"
                  class={`syn-rootbar${proposed() === 0 ? " on" : ""}`}
                  onMouseEnter={() => setProposed(0)}
                  onClick={() => void commitReattach()}
                >
                  <span>Attach to root</span>
                  <span class="syn-kbd">⌥R</span>
                </button>
              </Show>

              <ArcDiagram
                tokens={tokens()}
                hovered={hovered()}
                onHover={setHovered}
                selected={selected()}
                focused={focused()}
                lifted={lifted()}
                candidates={candidates()}
                proposed={proposed()}
                refused={refused()}
                onDragStart={beginDrag}
                onSelect={(id) => {
                  if (lifted() !== null) {
                    // Mid-reattachment a click is a drop, not a selection.
                    if (candidates().includes(id)) {
                      setProposed(id);
                      void commitReattach();
                    }
                    return;
                  }
                  setFocused(id);
                  setSelected((cur) => (cur === id ? null : id));
                  setPicking(false);
                }}
              />

              <Show
                when={lifted() === null}
                fallback={
                  <p class="syn-hint">
                    Reattaching <b>{tokens().find((t) => t.id === lifted())?.form}</b> —{" "}
                    <span class="syn-kbd">←</span> <span class="syn-kbd">→</span> choose a head ·{" "}
                    <span class="syn-kbd">↵</span> commit · <span class="syn-kbd">⌥R</span> root ·{" "}
                    <span class="syn-kbd">Esc</span> cancel
                  </p>
                }
              >
                <p class="syn-hint">
                  Hover a token to isolate the subtree it governs · click to inspect ·{" "}
                  <span class="syn-kbd">L</span> relabel · <span class="syn-kbd">R</span> reattach ·{" "}
                  <span class="syn-kbd">←</span> <span class="syn-kbd">→</span> tokens ·{" "}
                  <span class="syn-kbd">↑</span> <span class="syn-kbd">↓</span> sentences
                </p>
              </Show>
            </Match>
            <Match when={true}>
              <div class="syn-empty">No syntax for this passage.</div>
            </Match>
          </Switch>
        </main>
      </div>

      <Show when={ghost()}>
        {(g) => (
          <div
            class="syn-ghost"
            aria-hidden="true"
            style={{ left: `${String(g().x)}px`, top: `${String(g().y)}px` }}
          >
            {g().form}
          </div>
        )}
      </Show>

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
                onReattach={() => {
                  lift(tok().id);
                }}
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
