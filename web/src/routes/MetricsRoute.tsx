import { MetricsPanel } from "~/Metrics/MetricsPanel";
import { isMetricsRoute, type RouteMetrics } from "~/routes/routeUtils";
import type { RouteContextProps } from "~/routes/types";

/** Thin shell wiring the `#/metrics` route into `MetricsPanel` — same
 *  shape as `RefsRoute`/`NetworkRoute`: resolve the typed route, forward
 *  its fields as props, and turn the panel's `onNavigate` callback back
 *  into a `routing.navigate`. `SurfaceErrorBoundary` wraps this in
 *  `AppRoutes`, not here, matching the other route files. */
export function MetricsRoute(props: RouteContextProps) {
  const route = (): RouteMetrics => {
    const r = props.routing.route();
    if (!isMetricsRoute(r)) throw new Error("expected metrics route");
    return r;
  };
  return (
    <MetricsPanel
      window={route().window}
      label={route().label}
      onNavigate={(patch) => {
        props.routing.navigate({ kind: "metrics", ...patch });
      }}
    />
  );
}
