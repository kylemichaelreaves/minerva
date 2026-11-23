// In-memory cache of per-word hover translations. When the user
// single-clicks a word, the Reader fires /api/translate and shows
// the result in the rail; once that fetch settles, the translated
// text is keyed by (chunk_id, offset, target_lang) so a later
// hover can surface it without re-opening the rail.
//
// Only word-click translations are cached here — drag-selection
// commits clear the pending anchor so a multi-word passage
// translation can't attach to the last clicked word.

import { createEffect, createSignal, type Accessor } from "solid-js";
import type { TargetLang } from "~/utils/types";
import type { RailState } from "~/Reader/types";

function cacheKey(
  chunkId: string,
  offset: number,
  lang: TargetLang,
): string {
  return `${chunkId}:${offset}:${lang}`;
}

export interface WordHoverTranslationsApi {
  /** Register the word the user just clicked before translate fires. */
  registerWordClick: (chunkId: string, offset: number, source: string) => void;
  /** Drop the pending anchor (selection translate, saved-marker re-open). */
  clearPending: () => void;
  /** Cached translation for hover, if any, in the current target lang. */
  lookup: (chunkId: string, offset: number) => string | undefined;
}

export interface WordHoverTranslationsProps {
  rail: Accessor<RailState>;
  target: Accessor<TargetLang>;
}

const HOVER_TRANSLATION_CACHE_MAX = 500;

export function useWordHoverTranslations(
  props: WordHoverTranslationsProps,
): WordHoverTranslationsApi {
  const [translations, setTranslations] = createSignal<Record<string, string>>(
    {},
  );
  let pending: { chunkId: string; offset: number; source: string } | null =
    null;

  createEffect(() => props.rail(), (r) => {
    if (r.kind !== "ready" || pending === null) return;
    if (r.source !== pending.source) return;
    // Key on the language the response was produced for, not the current
    // target: setTargetLang flips the target while the old response is
    // still on the rail (#690).
    const key = cacheKey(pending.chunkId, pending.offset, r.lang);
    setTranslations((prev) => {
      const next = { ...prev, [key]: r.response.translated_text };
      const entries = Object.entries(next);
      if (entries.length <= HOVER_TRANSLATION_CACHE_MAX) return next;
      const drop = entries.length - HOVER_TRANSLATION_CACHE_MAX;
      return Object.fromEntries(entries.slice(drop));
    });
  });

  function registerWordClick(
    chunkId: string,
    offset: number,
    source: string,
  ): void {
    pending = { chunkId, offset, source };
  }

  function clearPending(): void {
    pending = null;
  }

  function lookup(chunkId: string, offset: number): string | undefined {
    return translations()[cacheKey(chunkId, offset, props.target())];
  }

  return { registerWordClick, clearPending, lookup };
}
