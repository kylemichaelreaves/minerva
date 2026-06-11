// F3 — Reader-rail Concordance tab.
//
// A work-scoped mini-leaderboard: the top 12 lemmas of the currently-
// open work, each a tappable row that opens the corpus concordance
// at that lemma. The tab header carries a "full concordance for this
// work →" CTA that takes the user out to the F2 KWIC at work scope.
//
// Scoped to the current work because that's the in-context view a
// reader actually wants — the same lemma in *this* book — while the
// top-nav entry is what they reach for the corpus-wide view.

import { For, Show, createResource } from "solid-js";
import {
  fetchLemmaIndex,
  type LemmaIndexRow,
} from "~/api/concordanceApi";

interface Props {
  workTitle: string | null;
  lang: string;
  onOpenWorkScope: () => void;
  onOpenLemma: (lemma: string) => void;
}

export function ConcordanceTabPanel(props: Props) {
  const [data] = createResource(
    () => ({ work: props.workTitle, lang: props.lang }),
    async (args) => {
      if (!args.work) return null;
      return fetchLemmaIndex({
        lang: args.lang,
        scope: "work",
        work: args.work,
        limit: 12,
        // sort=freq is default; default POS filter strips function words.
      });
    },
  );

  return (
    <div class="rail-concord">
      <Show when={props.workTitle} fallback={
        <div class="rail-concord-empty">
          Open a work to see its top lemmas.
        </div>
      }>
        <button
          class="rail-concord-cta"
          onClick={props.onOpenWorkScope}
          disabled={!props.workTitle}
        >
          Full concordance for this work{" "}
          <span class="rail-concord-arr">→</span>
        </button>

        <div class="rail-concord-head">
          Top lemmas · this work
        </div>

        <Show when={data.loading}>
          <div class="rail-concord-loading">Loading lemma index…</div>
        </Show>

        <Show when={!!data.error}>
          <div class="rail-concord-empty">
            Lemma index unavailable. Has{" "}
            <code>minerva terms lemmatize --lang {props.lang}</code>{" "}
            been run for this edition?
          </div>
        </Show>

        {/* `rows?.` is defensive against a malformed server payload —
            the response type claims it's always present. */}
        {/* eslint-disable-next-line @typescript-eslint/no-unnecessary-condition */}
        <Show when={data() && !data.error && (data()?.rows?.length ?? 0) > 0}>
          <ul class="rail-concord-list">
            <For each={data()!.rows}>
              {(row: LemmaIndexRow) => (
                <li
                  class="rail-concord-row"
                  onClick={() => props.onOpenLemma(row.lemma)}
                >
                  <span class="rail-concord-lem">{row.lemma}</span>
                  <span class="rail-concord-pos">{row.pos.toLowerCase()}</span>
                  <span class="rail-concord-ct">
                    {row.count.toLocaleString()}
                  </span>
                </li>
              )}
            </For>
          </ul>
        </Show>

        {/* eslint-disable-next-line @typescript-eslint/no-unnecessary-condition */}
        <Show when={data() && (data()?.rows?.length ?? 0) === 0 && !data.loading}>
          <div class="rail-concord-empty">
            No content lemmas in this work.
          </div>
        </Show>
      </Show>
    </div>
  );
}
