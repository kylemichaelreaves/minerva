// ReferenceCard — sibling of TermCard. The popover that opens when a
// reader clicks an inline gutter marker indicating "this passage
// references another author." Three variants, all derived from one
// data shape:
//
//   • IN-CORPUS — target.in_corpus_work_id is set; we can render a
//     preview and an "Open in reader →" affordance.
//   • OUT-OF-CORPUS — target.in_corpus_work_id is null (Cicero,
//     Plotinus, Vergil, …). No preview; an external-link row
//     replaces it.
//   • PENDING — `curator_status === 'auto'` and the row hasn't been
//     curator-approved. Overlay state on top of either variant
//     above: adds an "unverified · auto" pill in the top-right and
//     mutes the preview.
//
// Lifecycle mirrors TermCard.tsx:
//   - The caller passes the bounding rect of the gutter marker that
//     triggered the open. The card pins itself below the marker by
//     default; flips above when overflow would push it off-screen.
//   - Esc / outside-click dismisses (caller owns the open/closed
//     state; this component is presentation only). True of Esc since
//     the beginning and of outside-click only since #356 — the shell
//     wired it per-caller and this card was not one of the callers,
//     so this line described the intent rather than the behaviour for
//     as long as the card existed. There is no close button: the term
//     card's is error-state only, so the two cards match there too.
//
// The component is fully prop-driven — no internal fetch. The reader
// fetches `/api/works/:id/references_map` once per window
// (`fetchReferencesMap`), and `useXrefCard` passes the first of the
// clicked chunk's `top` references in. Preview text (the target chunk's
// body, when in-corpus) is similarly passed in by the caller via the
// optional `previewText` prop; an undefined `previewText` collapses
// the preview block.

import { For, Show } from "solid-js";
import PopoverCard from "~/components/primitives/PopoverCard";
import "~/components/cards/referencecard.css";
import { ExtLinkIcon } from "~/components/primitives/ExtLinkIcon";
import { referenceTypeLabel } from "~/utils/referenceTypes";
import {
  defaultExternalLinks,
  defaultOpenInReader,
  isGreekQuote,
  type ExternalLink,
} from "~/utils/referenceCardUtils";
import type {
  Reference,
  ReferenceTarget,
  ReferenceType,
} from "~/utils/types";
export type { Reference, ReferenceTarget, ReferenceType, ExternalLink };

export interface ReferenceCardProps {
  reference: Reference;
  /** Bounding rect of the gutter marker that triggered the open. */
  anchor: DOMRect;
  /** Optional snippet of the target chunk's body — typically the first
   *  ~120 chars. When omitted, the in-corpus preview block collapses
   *  (the card still renders the header, chip, and "Open in reader"). */
  previewText?: string;
  /** Hash-route to the reader when "Open in reader →" is clicked.
   *  Defaults to `#/r/<work>?focus=<chunk_id>`; pass a custom function
   *  to integrate with the app's routing module. */
  openInReader?: (target: ReferenceTarget) => string;
  /** External-link slots for out-of-corpus targets. Defaults to a
   *  Logeion/Perseus/archive.org triple derived from the target
   *  author/work. */
  externalLinks?: ExternalLink[];
  /** Called when the user dismisses the card — Esc, a click away (#356), or
   *  a second click on the gutter marker that opened it. There is no close
   *  button on this card. The reader uses this to clear its selection
   *  state. */
  onClose: () => void;
}

export default function ReferenceCard(props: ReferenceCardProps) {
  const isInCorpus = (): boolean =>
    props.reference.target.in_corpus_work_id !== null;
  const isPending = (): boolean => props.reference.curator_status === "auto";
  const greekQuote = (): boolean => isGreekQuote(props.reference.quoted_phrase);

  const openHref = (): string => {
    const fn = props.openInReader ?? defaultOpenInReader;
    return fn(props.reference.target);
  };
  const extLinks = (): ExternalLink[] =>
    props.externalLinks ?? defaultExternalLinks(props.reference.target);

  // Parse a citation header into author + work + locator. The design's
  // header renders as "Aristotle, *De anima* III.7" — author in upright
  // serif, work in italic, locator (when present) in upright.
  const targetCitation = (): import("@solidjs/web").JSX.Element => {
    const t = props.reference.target;
    return (
      <>
        {t.author}, <em>{t.work}</em>
        <Show when={t.locator}>{(loc) => <> {loc()}</>}</Show>
      </>
    );
  };

  return (
    <PopoverCard
      variant="refcard"
      anchor={props.anchor}
      ariaLabel="Cross-reference details"
      anchorSelector=".xref-pin"
      onClose={props.onClose}
      class={isPending() ? "is-pending" : undefined}
    >
      <Show when={isPending()}>
        <span class="refcard-unverified">unverified · auto</span>
      </Show>

      <div class="refcard-head">{targetCitation()}</div>

      <div class="refcard-chip">{referenceTypeLabel(props.reference.reference_type)}</div>

      <Show when={props.reference.quoted_phrase}>
        {(phrase) => (
          <div class={["refcard-quote", { "is-greek": greekQuote() }]}>
            {phrase()}
          </div>
        )}
      </Show>

      {/* In-corpus targets get a preview + "Open in reader →".
          Out-of-corpus targets get the external-link row instead.
          Pending state mutes the preview but keeps everything else. */}
      <Show when={isInCorpus()}>
        <Show when={props.previewText}>
          {(text) => (
            <div class={["refcard-preview", { "is-muted": isPending() }]}>
              {text()}
            </div>
          )}
        </Show>
        <a class="refcard-open" href={openHref()}>
          Open in reader →
        </a>
      </Show>

      <Show when={!isInCorpus()}>
        <div class="refcard-ext-links">
          <For each={extLinks()}>
            {(link, i) => (
              <>
                <Show when={i() > 0}>
                  <span class="refcard-ext-sep" aria-hidden="true" />
                </Show>
                <a href={link.href} target="_blank" rel="noopener noreferrer">
                  <ExtLinkIcon />
                  {link.label}
                </a>
              </>
            )}
          </For>
        </div>
      </Show>
    </PopoverCard>
  );
}
