// Verification coverage drilldown — mobile design 6.
//
// Each author gets a full-width stacked bar split into three buckets:
// verified (manual + rule_strong + rule+embed+llm — high-confidence
// methods), unverified (rule+embed + rule_weak — auto methods still
// pending human review), and disputed (curator_status='rejected' —
// we don't currently expose this on the verification endpoint, so
// shown as 0 for now and called out in the legend regardless to keep
// the visual encoding stable across data updates).
//
// Fetch + topbar + loading shell live in `NetworkDrilldownShell`;
// this file owns the summary strip + per-author bar list.

import { For, Show } from "solid-js";
import type { NetworkFilterParams, VerificationRow } from "~/api/networkApi";
import { NetworkDrilldownShell } from "~/Network/components/NetworkDrilldownShell";

interface Props extends NetworkFilterParams {
  onBack: () => void;
}

interface Coverage {
  verified: number;
  unverified: number;
  disputed: number;
  total: number;
  pct: number;
}

function classifyRow(row: VerificationRow): Coverage {
  // "Verified" = methods that have either a curator stamp or a
  // multi-strategy consensus. "Unverified" = single weak strategy
  // still pending. Disputed is currently unmeasured on this endpoint
  // — surfaced as 0; will populate when the API exposes rejected
  // counts.
  const verified =
    row.parts.manual + row.parts.rule_strong + row.parts["rule+embed+llm"];
  const unverified = row.parts["rule+embed"] + row.parts.rule_weak;
  const disputed = 0;
  const total = row.total || 1;
  return { verified, unverified, disputed, total, pct: verified / total };
}

export function NetworkCoverage(props: Props) {
  return (
    <NetworkDrilldownShell
      title="Verification coverage"
      onBack={props.onBack}
      minConfidence={props.minConfidence}
      includeRejected={props.includeRejected}
      sourceAuthors={props.sourceAuthors}
      corpora={props.corpora}
      sourceMethods={props.sourceMethods}
    >
      {(summary) => (
        <>
          <div class="net-cov-summary">
            <span class="num">{summary.totals.xrefs.toLocaleString()}</span>{" "}
            refs · % <b class="cov-v">verified</b> ·{" "}
            <b class="cov-u">unverified</b> ·{" "}
            <b class="cov-x">disputed</b>
          </div>
          <div class="net-cov-list">
            <For each={summary.verification}>
              {(row) => {
                const cov = classifyRow(row);
                return (
                  <div class="net-cov">
                    <span class="net-cov-au">{row.author}</span>
                    <span class="net-cov-bar">
                      <span
                        class="v"
                        style={{
                          width: `${(cov.verified / cov.total) * 100}%`,
                        }}
                      />
                      <span
                        class="u"
                        style={{
                          width: `${(cov.unverified / cov.total) * 100}%`,
                        }}
                      />
                      <Show when={cov.disputed > 0}>
                        <span
                          class="x"
                          style={{
                            width: `${(cov.disputed / cov.total) * 100}%`,
                          }}
                        />
                      </Show>
                    </span>
                    <span class="net-cov-pct">
                      {Math.round(cov.pct * 100)}%
                    </span>
                  </div>
                );
              }}
            </For>
            <div class="net-cov-legend">
              <span>
                <span class="sw v" />
                verified
              </span>
              <span>
                <span class="sw u" />
                unverified
              </span>
              <span>
                <span class="sw x" />
                disputed
              </span>
            </div>
          </div>
        </>
      )}
    </NetworkDrilldownShell>
  );
}
