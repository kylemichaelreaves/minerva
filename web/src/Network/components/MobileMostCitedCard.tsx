// Most-cited works leaderboard — mobile design 5a.
//
// Renders the top 4 works with rank, work title (serif italic), author
// byline (mono), and citation count. The design also shows a year
// next to the author ("Aristotle · −340"), but the network API
// doesn't currently expose work-year on top_works — that's a follow-up.
// Tap a row → /refs filtered to that work.
//
// Card chrome lives in `NetworkTopNCard`; this file just defines the row.

import type { TopWorkRow } from "~/api/networkApi";
import { NetworkTopNCard } from "~/Network/components/NetworkTopNCard";

interface Props {
  works: TopWorkRow[];
  onOpen: (author: string, work: string) => void;
}

const LIMIT = 4;

export function MobileMostCitedCard(props: Props) {
  return (
    <NetworkTopNCard
      title="Most-cited works"
      meta="leaderboard"
      items={props.works}
      limit={LIMIT}
      dataPanel="most-cited"
      renderRow={(work, i) => (
        <button
          type="button"
          class="nw-work"
          onClick={() => props.onOpen(work.author, work.work)}
        >
          <span class="rk">{i + 1}</span>
          <span class="nw-work-body">
            <span class="ttl">{work.work}</span>
            <span class="au">{work.author}</span>
          </span>
          <span class="ct">{work.n.toLocaleString()}</span>
        </button>
      )}
    />
  );
}
