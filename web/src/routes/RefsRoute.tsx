import { Match, Switch } from "solid-js";

import Refs from "~/features/Refs";
import Review from "~/features/Refs/components/Review";
import type { RouteContextProps } from "~/routes/types";
import { isRefsReviewRoute, isRefsRoute, type RouteRefs, type RouteRefsReview } from "~/routes/routeUtils";

export function RefsRoute(props: RouteContextProps) {
  const route = () => props.routing.route();
  const refsRoute = (): RouteRefs => {
    const r = route();
    if (!isRefsRoute(r)) throw new Error("expected refs route");
    return r;
  };
  const reviewRoute = (): RouteRefsReview => {
    const r = route();
    if (!isRefsReviewRoute(r)) throw new Error("expected refs-review route");
    return r;
  };
  return (
    <Switch>
      <Match when={isRefsRoute(route())}>
        <Refs
          sourceAuthor={refsRoute().sourceAuthor}
          targetAuthor={refsRoute().targetAuthor}
          targetWork={refsRoute().targetWork}
          referenceType={refsRoute().referenceType}
          includeRejected={refsRoute().includeRejected}
          onNavigate={(patch) => {
            props.routing.navigate({ kind: "refs", ...patch });
          }}
          onOpenReview={() => {
            props.routing.navigate({ kind: "refs-review" });
          }}
          onOpenSource={props.openSourceInReader}
        />
      </Match>
      <Match when={isRefsReviewRoute(route())}>
        <Review
          sourceAuthor={reviewRoute().sourceAuthor}
          referenceType={reviewRoute().referenceType}
          referenceId={reviewRoute().referenceId}
          onNavigate={(patch) => {
            props.routing.navigate({ kind: "refs-review", ...patch });
          }}
          onNavigateToReference={(id) => {
            // `replace` (not `navigate`) — advancing through the queue
            // is fine-grained URL tracking, not a real navigation, so
            // we don't want each item to land in browser history.
            const r = route();
            if (r.kind !== "refs-review") return;
            props.routing.replace({
              kind: "refs-review",
              sourceAuthor: r.sourceAuthor,
              referenceType: r.referenceType,
              referenceId: id,
            });
          }}
          onOpenSource={props.openSourceInReader}
        />
      </Match>
    </Switch>
  );
}
