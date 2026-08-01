import { SyntaxOverlay } from "~/Syntax";
import { isSyntaxRoute } from "~/routes/routeUtils";
import type { RouteContextProps } from "~/routes/types";

/**
 * Full-bleed dependency-syntax overlay for one chunk.
 *
 * Reads `route()` inside the JSX prop expression so a navigation between
 * chunks re-fetches rather than re-mounting — same pattern as
 * `ConcordanceRoute` and `NetworkRoute`.
 */
export function SyntaxRoute(props: RouteContextProps) {
  const route = () => {
    const r = props.routing.route();
    if (!isSyntaxRoute(r)) throw new Error("expected syntax route");
    return r;
  };

  return (
    <SyntaxOverlay
      chunkId={route().chunkId}
      onClose={() => {
        const workId = route().workId;
        props.routing.navigate(
          workId === undefined ? { kind: "landing" } : { kind: "reader", workId },
        );
      }}
    />
  );
}
