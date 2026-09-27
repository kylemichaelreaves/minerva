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
        works: [args.work],
        limit: 12,
        // sort=freq is default; default POS filter strips function words.
      });
    },
  );

  /** The resource's value, or `undefined` when it failed.
   *
   *  Reading `data()` on an errored resource **throws** — Solid rethrows so an
   *  `ErrorBoundary` can catch it. Every read below went through the raw
   *  accessor, so on a failed fetch the throw escaped the update the rejection
   *  triggered, abandoned it, and left this panel on "Loading lemma index…"
   *  forever: the error branch beneath it never mounted, and its remedy line
   *  (`minerva terms lemmatize`) never reached the screen (#426).
   *
   *  The guard at the old `:75` looked like it covered this —
   *  `data() && !data.error && …` — but `&&` evaluates left to right, so
   *  `data()` threw before `!data.error` was ever reached. Order was the whole
   *  bug.
   *
   *  Same shape as `Syntax/index.tsx`'s `loaded()`, which fixed the identical
   *  defect in the syntax overlay under #235 — deliberately the same spelling
   *  rather than a third one. */
  const loaded = () => (data.error === undefined ? data() : undefined);
  /** The loaded rows, or none while loading / on error. `?? []` also
   *  absorbs a malformed payload missing `rows`, which the response type
   *  claims is always present. */
  const rows = () => loaded()?.rows ?? [];

  return (
    <div class="rail-concord">
      <Show when={props.workTitle} fallback={
        <div class="rail-concord-empty">
          Open a work to see its top lemmas.
        </div>
      }>
        <button
          class="rail-concord-cta"
          onClick={() => props.onOpenWorkScope()}
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

        <Show when={rows().length > 0}>
          <ul class="rail-concord-list">
            <For each={rows()}>
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

        {/* Gated on `loaded()` rather than `data()` so a *failed* fetch does
            not claim the work has no lemmas — that is a different statement,
            and the error branch above is what should speak for it. */}
        {/* eslint-disable-next-line @typescript-eslint/no-unnecessary-condition */}
        <Show when={loaded() && (loaded()?.rows?.length ?? 0) === 0 && !data.loading}>
          <div class="rail-concord-empty">
            No content lemmas in this work.
          </div>
        </Show>
      </Show>
    </div>
  );
}
