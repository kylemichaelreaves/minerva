import { SyntaxOverlay } from "~/Syntax";
import type { RoutingApi } from "~/routing";

/**
 * Full-bleed dependency-syntax overlay for one chunk, rendered as a LAYER over
 * the Reader rather than as a peer route (#342).
 *
 * It was a sibling `<Match>` of the Reader's own `<Switch>` branch, so opening
 * it unmounted the Reader — the window refetched, the stage blanked, and the
 * scroll position came back only as a deep-link jump. `.syn` is already
 * `position: fixed; inset: 0; z-index: 40` over an opaque background, so it
 * needed no styling to become the layer it looked like; what it needed was for
 * the reader location to stay resolved underneath it, which is what the
 * `syntax=<chunk>` modifier on the reader route does.
 *
 * `chunkId` arrives as a prop (narrowed by the `<Show>` in `App`) rather than
 * being read off the route here, so a navigation between chunks re-fetches
 * inside the overlay instead of re-mounting it — same property `SyntaxRoute`
 * had, without a route read that can outlive its own guard.
 */
export function SyntaxLayer(props: { routing: RoutingApi; chunkId: string }) {
  return (
    <SyntaxOverlay
      chunkId={props.chunkId}
      onClose={() => {
        const r = props.routing.route();
        if (r.kind !== "reader") return;
        // Drop the modifier and nothing else. The Reader never unmounted, so
        // there is no scroll position to restore and no `focus=` to add — the
        // old return trip passed the chunk as `focusChunkId` precisely because
        // the Reader was being rebuilt from the URL, and that is what turned a
        // step into a diagram and back into a deep-link jump with its
        // `.focused` highlight.
        const { syntaxChunkId: _dropped, ...rest } = r;
        props.routing.navigate(rest);
      }}
    />
  );
}
