// Cross-reference card open/close state. The Reader's references_map
// fetch (in useWorkRange) already pre-loaded the chunk's top
// references, so opening the card needs no second round trip — we
// resolve the first reference from `by_chunk[chunkId].top[0]` and
// pin it to the marker's anchor rect.

import { createSignal, type Accessor } from "solid-js";
import type { Reference, ReferencesMap } from "~/utils/types";

export interface OpenRefCard {
  chunkId: string;
  anchor: DOMRect;
  reference: Reference;
}

export interface XrefCardApi {
  openRefCard: () => OpenRefCard | null;
  /** Toggle: a second click on the same row's marker dismisses; a
   *  click on a different row replaces. */
  onXrefOpen: (chunkId: string, anchor: DOMRect) => void;
  close: () => void;
}

export interface XrefCardProps {
  refsMap: Accessor<ReferencesMap | null>;
}

export function useXrefCard(props: XrefCardProps): XrefCardApi {
  const [openRefCard, setOpenRefCard] = createSignal<OpenRefCard | null>(null);

  function onXrefOpen(chunkId: string, anchor: DOMRect) {
    if (openRefCard()?.chunkId === chunkId) {
      setOpenRefCard(null);
      return;
    }
    const entry = props.refsMap()?.by_chunk[chunkId];
    const first = entry?.top[0];
    if (!first) return;
    setOpenRefCard({ chunkId, anchor, reference: first });
  }

  function close() {
    setOpenRefCard(null);
  }

  return { openRefCard, onXrefOpen, close };
}
