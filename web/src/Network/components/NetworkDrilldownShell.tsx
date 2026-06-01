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
  type NetworkSummary,
} from "~/api/networkApi";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import "~/Network/network.css";

interface Props {
  /** Page title shown center-aligned in the top bar (design: "Chronological
   *  arc" / "Verification coverage"). */
  title: string;
  /** Fired when the user taps the back affordance — caller routes
   *  back to the parent Network surface. */
  onBack: () => void;
  /** Network filter params. Passed through to the fetcher so the
   *  drilldown sees the same slice the parent does. */
  minConfidence?: number;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
  /** Render-prop body: receives the resolved summary. Only invoked
   *  when fetch has settled successfully — otherwise the shell shows
   *  its own loading / error state. */
  children: (summary: NetworkSummary) => JSX.Element;
}

export function NetworkDrilldownShell(props: Props) {
  const { data, loading, error } = useAbortableFetch(
    () => ({
      minConfidence: props.minConfidence,
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
          onClick={props.onBack}
          aria-label="Back to Network"
        >
          <span class="arr">←</span> Network
        </button>
        <span class="mobile-topbar-title">{props.title}</span>
        <span class="mobile-topbar-action" aria-hidden="true" />
      </header>
      <Show
        when={data() && !error()}
        fallback={
          <div class={error() ? "net-error" : "net-loading"}>
            {error() ?? (loading() ? "Loading…" : "")}
          </div>
        }
      >
        {props.children(data()!)}
      </Show>
    </div>
  );
}
