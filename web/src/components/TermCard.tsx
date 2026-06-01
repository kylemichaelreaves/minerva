// Term card — the click-popover for marked Greek words in the
// Reader. Matches the structure of the term-wireframes design bundle
// (lemma / renderings grid / "why this rendering?" disclosure /
// occurrence count / related chips / external links) but uses the
// app's paper/ink tokens instead of the wireframe's grayscale palette.
//
// Single-translation case is the MVP (current data: Edghill, eng).
// The renderings grid is structured for multi-translator data so the
// three-pane variant from the wireframe drops in without rework.
//
// Lifecycle:
//   - The Reader passes a `termId` and an anchor rect (the clicked
//     word's bounding rect). TermCard fetches the full term record on
//     mount and positions itself near the anchor.
//   - Esc / outside-click dismisses (the Reader owns the open/closed
//     state; this component is presentation only).

import { Show, For, createResource, createSignal } from "solid-js";
import { fetchTermDetail } from "~/api/readerApi";
import PopoverCard from "~/components/PopoverCard";
import "~/components/termcard.css";
import type { TermDetail, TermRenderingRow } from "~/utils/types";

export interface TermCardProps {
  termId: number;
  /** Bounding rect of the word the user clicked. The card pins itself
   *  to this rect's bottom-left, falling back to viewport corners if
   *  it would overflow. */
  anchor: DOMRect;
  /** Called when the user dismisses the card (outside click / Esc /
   *  close button). The Reader uses this to clear its selection state. */
  onClose: () => void;
}

export default function TermCard(props: TermCardProps) {
  const [showNote, setShowNote] = createSignal(false);
  // No AbortSignal — Solid's createResource fetcher-info doesn't
  // expose one in this version. If the user reopens the card on a
  // different term while a prior fetch is in flight, Solid discards
  // the older response on the next resolve. For a short-lived card
  // this is fine; switching to manual AbortController would buy us
  // back the request cost on rapid term-flipping but isn't worth the
  // wiring at MVP scale.
  const [term] = createResource<TermDetail, number>(
    () => props.termId,
    (id) => fetchTermDetail(id),
  );

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
      ariaLabel="Term details"
      onClose={props.onClose}
    >
      <Show when={term.loading}>
        <div class="termcard-loading">Loading…</div>
      </Show>
      <Show when={Boolean(term.error)}>
        <div class="termcard-error">
          Could not load this term.
          <button
            class="termcard-close"
            onClick={() => {
              props.onClose();
            }}
          >
            Dismiss
          </button>
        </div>
      </Show>

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
            <Show when={greekRenderings().length === 1}>
              {(_unused) => {
                const r = greekRenderings()[0];
                return (
                  <div class="termcard-sec termcard-single-rendering">
                    <span class="termcard-single-label">{r.translator_name}</span>
                    <span class="termcard-single-word">{r.default_rendering}</span>
                  </div>
                );
              }}
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
                  aria-expanded={showNote()}
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
                <span class="termcard-see-all" aria-disabled>
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
