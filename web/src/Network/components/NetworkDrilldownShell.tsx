// Shell for full-screen Network drilldowns — design 5b (chronological
// arc) and 6 (verification coverage). Both routes share the same
// scaffolding:
//
//   ┌──────────────────────────────┐
//   │ ← Network    Title       Aa  │  back-bar (this file)
//   ├──────────────────────────────┤
//   │ <caller-rendered body>       │  meta strip + visualization,
//   │                              │  composed inside the render-prop
//   └──────────────────────────────┘
//
// Both drilldowns also fetch the same `NetworkSummary` payload with
// the same arg shape, so the shell runs the fetch itself and passes
// the resolved summary into a render-prop child. The shell takes
// care of loading/error envelopes; the caller composes the body
// (meta strip + chart) so it can lay out summary-dependent text
// alongside the visualization.

import { Show, type JSX } from "solid-js";
import {
  fetchNetworkSummary,
  type NetworkFilterParams,
  type NetworkSummary,
} from "~/api/networkApi";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import "~/Network/network.css";

interface Props extends NetworkFilterParams {
  /** Page title shown center-aligned in the top bar (design: "Chronological
   *  arc" / "Verification coverage"). */
  title: string;
  /** Fired when the user taps the back affordance — caller routes
   *  back to the parent Network surface. */
  onBack: () => void;
  // The filter params (from NetworkFilterParams) pass through to the
  // fetcher so the drilldown sees the same slice the parent does.
  /** Render-prop body: receives the resolved summary. Only invoked
   *  when fetch has settled successfully — otherwise the shell shows
   *  its own loading / error state. */
  children: (summary: NetworkSummary) => JSX.Element;
}

export function NetworkDrilldownShell(props: Props) {
  const { data, loading, error } = useAbortableFetch(
    () => ({
      minConfidence: props.minConfidence,
      includeRejected: props.includeRejected,
      sourceAuthors: props.sourceAuthors,
      corpora: props.corpora,
      sourceMethods: props.sourceMethods,
    }),
    fetchNetworkSummary,
  );

  return (
    <div class="net-drilldown">
      <header class="mobile-topbar net-arc-topbar">
        <button
          type="button"
          class="net-arc-back"
          onClick={() => props.onBack()}
          aria-label="Back to Network"
        >
          <span class="arr">←</span> Network
        </button>
        <span class="mobile-topbar-title">{props.title}</span>
        <span class="mobile-topbar-action" aria-hidden="true" />
      </header>
      <Show
        when={!error() && data()}
        fallback={
          <div class={error() ? "net-error" : "net-loading"}>
            {error() ?? (loading() ? "Loading…" : "")}
          </div>
        }
      >
        {/* The fragment keeps the call tracked, so a refetch re-renders
            the body with the new summary as it did before. */}
        {(summary) => <>{props.children(summary())}</>}
      </Show>
    </div>
  );
}
