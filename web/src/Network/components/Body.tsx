import { Show } from "solid-js";
import type { NetworkSummary } from "~/api/networkApi";
import { useMobileShellOptional } from "~/components/MobileShellContext";
import { ArcPanel } from "~/Network/components/ArcPanel";
import { HeatmapPanel } from "~/Network/components/HeatmapPanel";
import { LeaderboardPanel } from "~/Network/components/LeaderboardPanel";
import { MatrixPanel } from "~/Network/components/MatrixPanel";
import { VerificationPanel } from "~/Network/components/VerificationPanel";
import { MobileTopPairsCard } from "~/Network/components/MobileTopPairsCard";
import { MobileMostCitedCard } from "~/Network/components/MobileMostCitedCard";
import { MobileFooterLinks } from "~/Network/components/MobileFooterLinks";

export function NetworkBody(props: {
  summary: NetworkSummary;
  onOpenPair: (source: string, target: string) => void;
  onOpenTargetWork: (author: string, work: string) => void;
  onOpenArc: () => void;
  onOpenCoverage: () => void;
  onOpenMore?: () => void;
}) {
  const shell = useMobileShellOptional();
  const isMobile = () => shell?.isMobile() ?? false;

  return (
    <Show
      when={isMobile()}
      fallback={
        // Desktop: five-panel grid (matrix · arc · heatmap · coverage·leaderboard).
        <div class="net-body">
          <MatrixPanel
            authors={props.summary.matrix.authors}
            cells={props.summary.matrix.cells}
            onOpenPair={props.onOpenPair}
          />
          <ArcPanel
            authors={props.summary.matrix.authors}
            matrixCells={props.summary.matrix.cells}
            topPairsAll={props.summary.top_pairs.all}
            topPairsNonScrip={props.summary.top_pairs.non_scrip}
            topPairsPerAuthor={props.summary.top_pairs.per_author_top}
            onOpenPair={props.onOpenPair}
          />
          <HeatmapPanel
            authors={props.summary.scripture_heatmap.authors}
            sections={props.summary.scripture_heatmap.sections}
            cells={props.summary.scripture_heatmap.cells}
          />
          <section class="net-panel" data-panel="lists">
            <div class="net-bottomright">
              <VerificationPanel rows={props.summary.verification} />
              <LeaderboardPanel
                rows={props.summary.top_works}
                onOpen={props.onOpenTargetWork}
              />
            </div>
          </section>
        </div>
      }
    >
      {/* Mobile design 5a: hero already lives in NetworkHeader; here
          we render the two Top-N cards and the drilldown footer.
          Matrix / Heatmap / Verification / Arc are replaced (not
          shrunk) — see design notes 5a/5b/6. */}
      <div class="net-body net-body-mobile">
        <MobileTopPairsCard
          pairs={props.summary.top_pairs.all}
          onOpenPair={props.onOpenPair}
        />
        <MobileMostCitedCard
          works={props.summary.top_works}
          onOpen={props.onOpenTargetWork}
        />
        <MobileFooterLinks
          onOpenArc={props.onOpenArc}
          onOpenCoverage={props.onOpenCoverage}
          onOpenMore={props.onOpenMore ?? (() => undefined)}
        />
      </div>
    </Show>
  );
}
