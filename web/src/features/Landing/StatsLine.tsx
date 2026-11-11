// One line of corpus stats under the composer. Decorative: it fetches its
// own numbers and shows "—" until (or unless) they arrive.

import { For, Show, createSignal, onMount } from "solid-js";
import { fetchLandingStats, type LandingStats } from "~/api/landingApi";

// In order: field, then its noun.
const STATS = [
  ["authors", "authors"],
  ["works", "works"],
  ["xrefs", "cross-references"],
] as const satisfies readonly (readonly [keyof LandingStats, string])[];

// The last stats any landing fetched. A landing mounted again — New
// conversation, or Escape from a chat — renders with them at once and
// refreshes behind. The stats line is reserved a line's height either way, so
// its arriving late cannot re-centre the column and move the composer box
// after the return transition has measured where to land.
let lastStats: LandingStats | null = null;

const fmtNum = (n: number | undefined) => (n === undefined ? "—" : n.toLocaleString());

export default function StatsLine() {
  const [stats, setStats] = createSignal<LandingStats | null>(lastStats);
  onMount(() => {
    void fetchLandingStats()
      .then((s) => {
        lastStats = s;
        setStats(s);
      })
      .catch(() => {
        // Stats are decorative — silent on failure.
      });
  });

  return (
    <p class="landing-stats">
      <For each={STATS}>
        {([key, label], i) => (
          <>
            <Show when={i() > 0}>
              <span class="sep">·</span>
            </Show>
            <span class="num">{fmtNum(stats()?.[key])}</span> {label}
          </>
        )}
      </For>
    </p>
  );
}
