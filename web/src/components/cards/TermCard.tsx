// Term card — the click-popover for marked Greek words in the
// Reader. Matches the structure of a design bundle (lemma / renderings
// grid / "why this rendering?" disclosure / occurrence count / related
// chips / external links) but uses the app's paper/ink tokens instead of
// that bundle's grayscale palette. The bundle was a local scratch
// directory and never entered the repository; the design of record is the
// Storybook story `Reader/TermCard` (#360).
//
// Single-translation case is the MVP (current data: Edghill, eng).
// The renderings grid is structured for multi-translator data so the
// three-pane variant drops in without rework — which is why the grid
// exists at all while only one translator is loaded.
//
// Lifecycle:
//   - The Reader passes a `termId` and an anchor rect (the clicked
//     word's bounding rect). TermCard fetches the full term record on
//     mount and positions itself near the anchor.
//   - Esc / outside-click dismisses (the Reader owns the open/closed
//     state; this component is presentation only).

import { Show, For, createSignal } from "solid-js";
import { createAsyncState } from "~/hooks/createAsyncState";
import { fetchTermDetail } from "~/api/readerApi";
import PopoverCard from "~/components/primitives/PopoverCard";
import "~/components/cards/termcard.css";
import type { TermRenderingRow } from "~/utils/types";

export interface TermCardProps {
  termId: number;
  /** Bounding rect of the word the user clicked. The card pins itself
   *  to this rect's bottom-left, falling back to viewport corners if
   *  it would overflow. */
  anchor: DOMRect;
  direction?: "ltr" | "rtl";
  /** Called when the user dismisses the card — a click away, Esc, a second
   *  click on the marked word, or the shell's `×` (#358), which is the card's
   *  one visible exit in every state including the load error (#361). The
   *  Reader uses this to clear its selection state. */
  onClose: () => void;
}

export default function TermCard(props: TermCardProps) {
  const [showNote, setShowNote] = createSignal(false);
  // No AbortSignal. If the user reopens the card on a different term while
  // a prior fetch is in flight, the node discards the superseded answer. For
  // a short-lived card this is fine; aborting from an `onCleanup` in the
  // compute would buy back the request cost on rapid term-flipping but isn't
  // worth the wiring at MVP scale.
  //
  // `createAsyncState` settles the fetch before the node sees it, so a failure
  // is data rather than a throw (#361), and a term change keeps the previous
  // term readable while it refetches — the shape `createResource` gave this card.
  const termState = createAsyncState(() => props.termId, fetchTermDetail);
  const loading = () => termState.firstLoad() || termState.refreshing();
  const failed = () => termState.error() !== undefined && !loading();
  const term = termState.value;

  const total = () => {
    const t = term();
    if (!t) return 0;
    return t.occurrences_by_edition.reduce((sum, r) => sum + r.occurrences, 0);
  };

  const greekRenderings = () => {
    const t = term();
    if (!t) return [] as TermRenderingRow[];
    return t.renderings.filter((r) => r.language !== t.source_language);
  };

  return (
    <PopoverCard
      variant="termcard"
      anchor={props.anchor}
      direction={props.direction}
      ariaLabel="Term details"
      anchorSelector=".term-mark"
      onClose={props.onClose}
    >
      <Show when={loading()}>
        <div class="termcard-loading">Loading…</div>
      </Show>
      <Show when={failed()}>
        {/* One dismiss control, the shell's `×` (#361). This branch used to
            carry its own "Dismiss" button as well — written as a recovery
            affordance back when `PopoverCard` had no close control at all,
            and left redundant once #358 gave every popover one. Both called
            `props.onClose()` with nothing else, so the error state put two
            identical exits in `useDialogFocus`'s tab trap. */}
        <div class="termcard-error">Could not load this term.</div>
      </Show>

      {/* Gated on the settled value, not a raw rejection (#361). Under Solid
          1's `createResource`, reading an errored resource rethrew, so an
          unguarded `when={term()}` threw inside this update — which aborted
          it, left the card showing "Loading…" forever, and escaped as an
          uncaught error (the app mounts no error boundary). The branch above
          was therefore unreachable: a failed fetch never rendered the error
          state at all. `loadTerm` now settles the rejection into data before
          the node sees it, so `term()` is simply undefined on failure. */}
      <Show when={term()}>
        {(t) => (
          <>
            <div class="termcard-head">
              <div class="termcard-lemma">{t().source_form}</div>
              <div class="termcard-trans">
                <Show when={t().transliteration}>
                  {(translit) => <>{translit()}</>}
                </Show>
              </div>
              <div class="termcard-gloss">{t().short_gloss}</div>
            </div>

            {/* Renderings:
                  - 0 translators → hide entirely (Kant KrV case).
                  - 1 translator  → flat one-liner.
                  - 2+ translators → grid for side-by-side comparison.
                The grid only earns its space at 2+ rows; below that
                it looks like overdesign relative to the gloss above. */}
            <Show
              when={greekRenderings().length === 1 ? greekRenderings()[0] : undefined}
            >
              {(r) => (
                <div class="termcard-sec termcard-single-rendering">
                  <span class="termcard-single-label">{r().translator_name}</span>
                  <span class="termcard-single-word">{r().default_rendering}</span>
                </div>
              )}
            </Show>
            <Show when={greekRenderings().length >= 2}>
              <div class="termcard-sec">
                <div class="termcard-sec-label">
                  Renderings · across translations
                </div>
                <div class="termcard-renderings">
                  <For each={greekRenderings()}>
                    {(r) => (
                      <>
                        <div class="termcard-who">
                          {r.translator_name}
                          <Show when={r.translator_note}>
                            <span class="termcard-current">current</span>
                          </Show>
                        </div>
                        <div class="termcard-word">{r.default_rendering}</div>
                      </>
                    )}
                  </For>
                </div>
              </div>
            </Show>

            <Show when={greekRenderings().some((r) => r.translator_note)}>
              <div class="termcard-sec">
                <button
                  class="termcard-disclosure"
                  onClick={() => setShowNote(!showNote())}
                  aria-expanded={showNote() ? "true" : "false"}
                >
                  <span>Why this rendering?</span>
                  <span class="termcard-chev">{showNote() ? "▾" : "▸"}</span>
                </button>
                <Show when={showNote()}>
                  <For each={greekRenderings().filter((r) => r.translator_note)}>
                    {(r) => (
                      <div class="termcard-note">
                        <span class="termcard-note-who">{r.translator_name}</span>
                        {" — "}
                        {r.translator_note}
                      </div>
                    )}
                  </For>
                </Show>
              </div>
            </Show>

            <Show when={total() > 0}>
              <div class="termcard-sec termcard-occ-row">
                <span>
                  Appears <b>{total()}</b> times
                </span>
                <span class="termcard-see-all" aria-disabled="true">
                  See all occurrences →
                </span>
              </div>
            </Show>

            <Show when={t().related.length > 0}>
              <div class="termcard-sec">
                <div class="termcard-sec-label">Related terms</div>
                <div class="termcard-chips">
                  <For each={t().related}>
                    {(rel) => <span class="termcard-chip">{rel.source_form}</span>}
                  </For>
                </div>
              </div>
            </Show>

            <div class="termcard-sec termcard-ext">
              <a
                href={`https://logeion.uchicago.edu/${encodeURIComponent(
                  t().lemma ?? t().source_form,
                )}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Logeion
              </a>
              <a
                href={`https://www.perseus.tufts.edu/hopper/morph?l=${encodeURIComponent(
                  t().source_form,
                )}&la=greek`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Perseus
              </a>
            </div>
          </>
        )}
      </Show>
    </PopoverCard>
  );
}
