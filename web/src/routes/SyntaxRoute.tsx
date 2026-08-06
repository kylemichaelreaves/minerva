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
        // Pass the chunk id through as `focusChunkId`, NOT a `sourceLang`.
        // The reader route has no lang here, and defaulting one (as
        // `useWorkRange`/`work_range()` both do, to "grc") can resolve a
        // completely different edition than the one the overlay was opened
        // from — silently swapping the German text for e.g. the Greek
        // Septuagint on works that also have a `grc` edition. Passing the
        // chunk instead makes the server's `around=` path resolve the
        // work/lang/edition straight off that chunk row, so the Reader
        // reopens on the exact text the user left. Looks cosmetic; do not
        // drop it.
        props.routing.navigate(
          workId === undefined
            ? { kind: "landing" }
            : { kind: "reader", workId, focusChunkId: route().chunkId },
        );
      }}
    />
  );
}
