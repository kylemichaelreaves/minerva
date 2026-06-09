import { Match, Switch } from "solid-js";

import Network from "~/Network";
import { NetworkArc } from "~/Network/components/NetworkArc";
import { NetworkCoverage } from "~/Network/components/NetworkCoverage";
import {
  isNetworkArcRoute,
  isNetworkCoverageRoute,
  isNetworkRoute,
  networkFiltersFromRoute,
  networkRouteFromFilters,
  type RouteNetwork,
  type RouteNetworkArc,
  type RouteNetworkCoverage,
} from "~/routes/routeUtils";
import type { RouteContextProps } from "~/routes/types";

/**
 * Read route() inside JSX prop expressions so filter params stay reactive
 * across navigations — same pattern as ConcordanceRoute.
 */
export function NetworkRoute(props: RouteContextProps) {
  const route = () => props.routing.route();
  const arcRoute = (): RouteNetworkArc => {
    const r = route();
    if (!isNetworkArcRoute(r)) throw new Error("expected network-arc route");
    return r;
  };
  const coverageRoute = (): RouteNetworkCoverage => {
    const r = route();
    if (!isNetworkCoverageRoute(r)) throw new Error("expected network-coverage route");
    return r;
  };
  const mainRoute = (): RouteNetwork => {
    const r = route();
    if (!isNetworkRoute(r)) throw new Error("expected network route");
    return r;
  };
  return (
    <Switch>
      <Match when={isNetworkArcRoute(route())}>
        <NetworkArc
          {...networkFiltersFromRoute(arcRoute())}
          onBack={() => {
            const filters = networkFiltersFromRoute(arcRoute());
            props.routing.navigate(networkRouteFromFilters("network", filters));
          }}
          onOpenAuthor={(name) => {
            props.routing.navigate({ kind: "refs", sourceAuthor: name });
          }}
        />
      </Match>
      <Match when={isNetworkCoverageRoute(route())}>
        <NetworkCoverage
          {...networkFiltersFromRoute(coverageRoute())}
          onBack={() => {
            const filters = networkFiltersFromRoute(coverageRoute());
            props.routing.navigate(networkRouteFromFilters("network", filters));
          }}
        />
      </Match>
      <Match when={isNetworkRoute(route())}>
        <Network
          minConfidence={mainRoute().minConfidence}
          includeRejected={mainRoute().includeRejected}
          sourceAuthors={mainRoute().sourceAuthors}
          corpora={mainRoute().corpora}
          sourceMethods={mainRoute().sourceMethods}
          onNavigate={(patch) => {
            props.routing.navigate({ kind: "network", ...patch });
          }}
          onOpenPair={(source, target) => {
            props.routing.navigate({
              kind: "refs",
              sourceAuthor: source,
              targetAuthor: target,
            });
          }}
          onOpenTargetWork={(author, work) => {
            props.routing.navigate({
              kind: "refs",
              targetAuthor: author,
              targetWork: work,
            });
          }}
          onOpenArc={() => {
            const filters = networkFiltersFromRoute(mainRoute());
            props.routing.navigate(networkRouteFromFilters("network-arc", filters));
          }}
          onOpenCoverage={() => {
            const filters = networkFiltersFromRoute(mainRoute());
            props.routing.navigate(networkRouteFromFilters("network-coverage", filters));
          }}
        />
      </Match>
    </Switch>
  );
}
