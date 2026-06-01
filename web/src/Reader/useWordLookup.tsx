// Word-lookup state machine. Single-click on a non-term word fires
// both the lemma-cache lookup (for the rail's "word info" panel) and a
// translation request through the supplied callback. The hook also
// owns the in-text lemma highlight set so a fast subsequent click
// cancels both fetches together.

import { createSignal, type Accessor } from "solid-js";
import { fetchLemmaHighlights, fetchWordLookup } from "~/api/readerApi";
import { errorMessage, isAbortError } from "~/utils/util";
import type { LemmaHighlights, WorkRange } from "~/utils/types";
import type { WordInfoState } from "~/Reader/types";

const SAMPLES_PAGE_SIZE = 10;

export interface WordLookupApi {
  wordInfo: () => WordInfoState;
  lemmaHighlights: () => LemmaHighlights | null;
  onWordClick: (
    word: string,
    chunkId: string,
    offset: number,
    lineEl: Element | null,
  ) => void;
  loadMoreSamples: () => void;
  /** Abort and reset to idle. */
  reset: () => void;
}

export interface WordLookupProps {
  range: Accessor<WorkRange | null>;
  /** Translate request fired in parallel with the lemma lookup. The
   *  rail surfaces whichever piece arrives first. */
  onTranslateRequest: (source: string, ref: string) => void;
}

export function useWordLookup(props: WordLookupProps): WordLookupApi {
  const [wordInfo, setWordInfo] = createSignal<WordInfoState>({ kind: "idle" });
  const [lemmaHighlights, setLemmaHighlights] = createSignal<LemmaHighlights | null>(null);
  let wordInfoController: AbortController | undefined;

  function onWordClick(
    word: string,
    chunkId: string,
    offset: number,
    lineEl: Element | null,
  ) {
    const numText = lineEl?.querySelector(".num")?.textContent ?? "";
    const ref = numText.trim() || "—";
    props.onTranslateRequest(word, ref);
    wordInfoController?.abort();
    const controller = new AbortController();
    wordInfoController = controller;
    setWordInfo({ kind: "loading" });
    setLemmaHighlights(null);
    void (async () => {
      try {
        const info = await fetchWordLookup(
          chunkId,
          offset,
          { samplesLimit: SAMPLES_PAGE_SIZE, samplesOffset: 0 },
          controller.signal,
        );
        if (wordInfoController === controller) {
          setWordInfo({ kind: "ready", info, loadingMore: false });
        }
        // Kick off the in-text highlight fetch once we know the
        // lemma. Same controller so a fast subsequent click cancels
        // both fetches together. The visible window must match
        // exactly the range loaded in the reader stage.
        const r = props.range();
        if (r && info.lemma && !controller.signal.aborted) {
          try {
            const hls = await fetchLemmaHighlights(
              r.work_id,
              {
                lang: r.lang,
                from: r.offset,
                limit: r.limit,
                lemma: info.lemma,
              },
              controller.signal,
            );
            // If the controller was aborted between the await
            // resolving and this assignment, the next click already
            // cleared lemmaHighlights — overwriting it with a stale
            // result is the only failure mode. Cheap to ignore.
            setLemmaHighlights(hls);
          } catch (err) {
            if (isAbortError(err)) return;
            // Highlight is best-effort: a failure here just leaves
            // the in-text highlight off. The rail still has the
            // primary word-info content.
          }
        }
      } catch (err) {
        if (isAbortError(err)) return;
        const message = errorMessage(err);
        if (wordInfoController === controller) {
          setWordInfo({ kind: "error", message });
        }
      }
    })();
  }

  async function loadMoreSamplesInternal() {
    const current = wordInfo();
    if (current.kind !== "ready") return;
    if (current.info.next_samples_offset === null) return;
    if (current.loadingMore) return;
    setWordInfo({ ...current, loadingMore: true });
    try {
      // No abort controller here — the user explicitly asked for
      // more; cancelling on a subsequent click is already handled by
      // the parent `wordInfoController` whose abort propagates out
      // of fetchWordLookup. We re-use the same chunk_id+offset the
      // initial click resolved against (the lemma is what we
      // actually filter on; the chunk+offset just anchors the lemma
      // lookup, and any sample's coords work for that).
      const sample = current.info.samples[0];
      const next = await fetchWordLookup(
        sample.chunk_id,
        sample.surface_start,
        {
          samplesLimit: SAMPLES_PAGE_SIZE,
          samplesOffset: current.info.next_samples_offset,
        },
      );
      const merged = wordInfo();
      // Guard against a fresh click clearing the panel between our
      // request firing and resolving.
      if (merged.kind !== "ready") return;
      setWordInfo({
        kind: "ready",
        loadingMore: false,
        info: {
          ...merged.info,
          samples: [...merged.info.samples, ...next.samples],
          next_samples_offset: next.next_samples_offset,
        },
      });
    } catch (err) {
      if (isAbortError(err)) return;
      const merged = wordInfo();
      if (merged.kind !== "ready") return;
      setWordInfo({ ...merged, loadingMore: false });
    }
  }

  function loadMoreSamples() {
    void loadMoreSamplesInternal();
  }

  function reset() {
    wordInfoController?.abort();
    wordInfoController = undefined;
    setWordInfo({ kind: "idle" });
    setLemmaHighlights(null);
  }

  return { wordInfo, lemmaHighlights, onWordClick, loadMoreSamples, reset };
}
