import { For, Show } from "solid-js";
import type { WordInfoState } from "~/Reader/types";
import { formatMorphChip } from "~/Reader/wordInfoMorph";

/** Block-level word lookup. Renders surface + lemma + occurrence
 *  count + currently-loaded sample sites above the translation in
 *  the rail. Includes a "Show more" button that paginates samples
 *  via /api/words/lookup. Hidden entirely until a word click
 *  resolves; degrades to a small inline error if the lookup fails
 *  (most likely cause: the edition hasn't been lemmatised yet). */
export function WordInfoBlock(props: {
  state: WordInfoState;
  onLoadMore: () => void;
  /** Navigate to the corpus concordance for this lemma. Optional — when
   *  absent, the "See all in concordance" CTA is hidden. */
  onOpenConcordance?: (lemma: string, lang: string) => void;
}) {
  return (
    <Show when={props.state.kind !== "idle"}>
      <div class="wordinfo">
        <Show when={props.state.kind === "loading"}>
          <div class="wordinfo-loading">Looking up word…</div>
        </Show>
        <Show when={props.state.kind === "error"}>
          {(_) => {
            const e = props.state as Extract<WordInfoState, { kind: "error" }>;
            return <div class="wordinfo-error">No word info: {e.message}</div>;
          }}
        </Show>
        <Show when={props.state.kind === "ready"}>
          {(_) => {
            const ready = () =>
              props.state as Extract<WordInfoState, { kind: "ready" }>;
            const info = () => ready().info;
            const remaining = () =>
              info().occurrence_count - info().samples.length;
            return (
              <>
                <div class="wordinfo-head">
                  <span class="wordinfo-surface">{info().surface}</span>
                  <Show when={info().lemma !== info().surface}>
                    <span class="wordinfo-lemma">
                      <span class="wordinfo-arrow">→</span> {info().lemma}
                    </span>
                  </Show>
                </div>
                <Show when={formatMorphChip(info())}>
                  {(chip) => <div class="wordinfo-morph">{chip()}</div>}
                </Show>
                <div class="wordinfo-count">
                  Appears <b>{info().occurrence_count}</b>{" "}
                  {info().occurrence_count === 1 ? "time" : "times"} in this work
                </div>
                <Show when={props.onOpenConcordance}>
                  <button
                    class="wordinfo-concordance"
                    onClick={() =>
                      props.onOpenConcordance?.(info().lemma, info().lang)
                    }
                  >
                    See all occurrences in the corpus{" "}
                    <span class="wordinfo-concordance-arr">→</span>
                  </button>
                </Show>
                <Show when={info().samples.length > 0}>
                  <ul class="wordinfo-samples">
                    <For each={info().samples}>
                      {(s) => (
                        <li>
                          <span class="wordinfo-loc">{s.section ?? "—"}</span>
                          <span class="wordinfo-snippet">
                            {s.snippet.slice(0, s.match_start)}
                            <span class="lemma-hl">
                              {s.snippet.slice(s.match_start, s.match_end)}
                            </span>
                            {s.snippet.slice(s.match_end)}
                          </span>
                        </li>
                      )}
                    </For>
                  </ul>
                </Show>
                <Show when={info().next_samples_offset !== null}>
                  <button
                    class="wordinfo-more"
                    disabled={ready().loadingMore}
                    onClick={() => {
                      props.onLoadMore();
                    }}
                  >
                    <Show
                      when={ready().loadingMore}
                      fallback={
                        <>
                          Show {Math.min(10, remaining())} more
                          <span class="wordinfo-more-tail">
                            {" "}
                            ({remaining()} remaining)
                          </span>
                        </>
                      }
                    >
                      Loading…
                    </Show>
                  </button>
                </Show>
              </>
            );
          }}
        </Show>
      </div>
    </Show>
  );
}
