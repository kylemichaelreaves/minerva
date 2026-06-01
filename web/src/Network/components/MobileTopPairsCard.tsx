// Top author pairs card — mobile design 5a.
//
// Renders the top 5 author→author citation pairs as a stacked list
// with a mini bar normalized to the leader's count. Tap a row →
// /refs filtered to that pair. Card chrome (title + meta + slice +
// "Show all 10 →") lives in `NetworkTopNCard`; this file just defines
// the row.

import type { AuthorPair } from "~/api/networkApi";
import { NetworkTopNCard } from "~/Network/components/NetworkTopNCard";

interface Props {
  pairs: AuthorPair[];
  onOpenPair: (source: string, target: string) => void;
}

const LIMIT = 5;

export function MobileTopPairsCard(props: Props) {
  // Bar widths are normalized against the leader's count — a
  // log-scale would dampen the gap between Vulgate-class scripture
  // pairs and everything else, but the design specifies a linear bar
  // so the visual asymmetry is the point.
  const max = (): number => props.pairs[0]?.n ?? 1;

  return (
    <NetworkTopNCard
      title="Top author pairs"
      meta={`${Math.min(10, props.pairs.length)} of ${props.pairs.length}`}
      items={props.pairs}
      limit={LIMIT}
      dataPanel="top-pairs"
      renderRow={(pair, i) => (
        <button
          type="button"
          class="nw-pair"
          onClick={() => props.onOpenPair(pair.src, pair.tgt)}
        >
          <span class="rk">{i + 1}</span>
          <span class="pair">
            {pair.src} <span class="arr">→</span> {pair.tgt}
          </span>
          <span class="ct">{pair.n.toLocaleString()}</span>
          <div class="barwrap">
            <div
              class="fill"
              style={{ width: `${Math.round((pair.n / max()) * 100)}%` }}
            />
          </div>
        </button>
      )}
    />
  );
}
