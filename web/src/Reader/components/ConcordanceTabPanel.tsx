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

import { For, Show } from "solid-js";
import { createAsyncState } from "~/hooks/createAsyncState";
import { fetchLemmaIndex, type LemmaIndexResponse, type LemmaIndexRow } from "~/api/concordanceApi";

interface Props {
  workTitle: string | null;
  lang: string;
  onOpenWorkScope: () => void;
  onOpenLemma: (lemma: string) => void;
}

function loadLemmaIndex(q: { work: string; lang: string }): Promise<LemmaIndexResponse> {
  return fetchLemmaIndex({
    lang: q.lang,
    scope: "work",
    works: [q.work],
    limit: 12,
    // sort=freq is default; default POS filter strips function words.
  });
}

export function ConcordanceTabPanel(props: Props) {
  /** Settled before the node sees it (see `createAsyncState`), so a failure
   *  is ordinary data. That is the #426 fix carried forward: under Solid 1's
   *  `createResource`, reading `data()` on an errored resource **threw**, the
   *  throw abandoned the update the rejection triggered, and this panel sat on
   *  "Loading lemma index…" forever — its remedy line (`minerva terms
   *  lemmatize`) never reached the screen. No work open asks nothing. */
  const data = createAsyncState(
    () => (props.workTitle ? { work: props.workTitle, lang: props.lang } : undefined),
    loadLemmaIndex,
  );
  /** First fetch in flight, or a refetch after a work/lang change. */
  const loading = () => data.firstLoad() || data.refreshing();
  const failed = () => data.error() !== undefined && !loading();
  /** The loaded index, or `undefined` while loading / on error. */
  const loaded = data.value;
  /** The loaded rows, or none while loading / on error. `?? []` also
   *  absorbs a malformed payload missing `rows`, which the response type
   *  claims is always present. */
  const rows = () => loaded()?.rows ?? [];

  return (
    <div class="rail-concord">
      <Show
        when={props.workTitle}
        fallback={<div class="rail-concord-empty">Open a work to see its top lemmas.</div>}
      >
        <button
          class="rail-concord-cta"
          onClick={() => props.onOpenWorkScope()}
          disabled={!props.workTitle}
        >
          Full concordance for this work <span class="rail-concord-arr">→</span>
        </button>

        <div class="rail-concord-head">Top lemmas · this work</div>

        <Show when={loading()}>
          <div class="rail-concord-loading">Loading lemma index…</div>
        </Show>

        <Show when={failed()}>
          <div class="rail-concord-empty">
            Lemma index unavailable. Has <code>minerva terms lemmatize --lang {props.lang}</code>{" "}
            been run for this edition?
          </div>
        </Show>

        <Show when={rows().length > 0}>
          <ul class="rail-concord-list">
            <For each={rows()}>
              {(row: LemmaIndexRow) => (
                <li>
                  <button
                    type="button"
                    class="rail-concord-row"
                    onClick={() => props.onOpenLemma(row.lemma)}
                  >
                    <span class="rail-concord-lem">{row.lemma}</span>
                    <span class="rail-concord-pos">{row.pos.toLowerCase()}</span>
                    <span class="rail-concord-ct">{row.count.toLocaleString()}</span>
                  </button>
                </li>
              )}
            </For>
          </ul>
        </Show>

        {/* Gated on `loaded()` rather than `data()` so a *failed* fetch does
            not claim the work has no lemmas — that is a different statement,
            and the error branch above is what should speak for it. */}
        {/* eslint-disable-next-line @typescript-eslint/no-unnecessary-condition */}
        <Show when={loaded() && (loaded()?.rows?.length ?? 0) === 0 && !loading()}>
          <div class="rail-concord-empty">No content lemmas in this work.</div>
        </Show>
      </Show>
    </div>
  );
}
