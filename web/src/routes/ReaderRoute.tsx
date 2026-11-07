import { Show } from "solid-js";
import Reader from "~/Reader";
import type { RouteContextProps } from "~/routes/types";

/**
 * Solid components run their body once at mount; anything pulled out
 * of a reactive accessor with ``const x = sig()`` is captured as a
 * snapshot and never refreshes. The previous shape here was:
 *
 *     const work = props.reader.readerWork();
 *     return <Reader workId={work.workId} ... />;
 *
 * which mounted with the initial work and then never updated when
 * the sidebar fired ``openWork(newWork)`` — the URL changed but
 * the Reader kept receiving the original workId forever, so the
 * page looked stuck. (Same shape as the ConcordanceRoute bug
 * documented in ``routes/ConcordanceRoute.tsx``.)
 *
 * Fix: keep ``readerWork`` as an accessor (``work()``) and read it
 * inside each JSX expression. Solid wraps every attribute in an
 * effect, so each navigation re-evaluates the per-prop reads and
 * the Reader sees fresh workId / sourceLang values. ``<Show>``
 * (non-keyed) keeps the same Reader instance alive while its props
 * update, which preserves any internal state the Reader builds up
 * across navigations.
 */
export function ReaderRoute(props: RouteContextProps) {
  // Falls back to the retained location so the Reader keeps rendering the
  // passage while the route has stepped out to the concordance (#348).
  // `readerWork()` is null there — it is derived from the route — and reading
  // it alone would blank the Reader that `AppRoutes` went to the trouble of
  // keeping mounted. The retained value is the same object the reader route
  // last produced, so the props below do not change and `useWorkRange`'s
  // `windowKey` memo (PR #347) sees no reason to reload.
  const work = () => props.reader.readerWork() ?? props.reader.retainedWork();
  // Read off the route rather than through `readerWork()`: the syntax layer is
  // a modifier on the reader route (#342), not part of the reader LOCATION —
  // `readerCtrl` mirrors that location into localStorage, and "an overlay was
  // open" is not something Read should resume into.
  const syntaxOpen = () => {
    const r = props.routing.route();
    return r.kind === "reader" && r.syntaxChunkId !== undefined;
  };

  /** Seed the chat scope with the work being read, for either exit (#428).
   *
   *  Both exits used to do this synchronously off `currentWork()`, which reads
   *  the LAZILY-loaded `works()` list while the Reader renders straight off the
   *  route. Leaving inside the `/api/works` round-trip therefore seeded `null`
   *  and dropped the work with no sign it had happened.
   *
   *  So: seed now if the list can answer, and otherwise fall back to
   *  `resolveWork`, which awaits the list. Nothing here is awaited by the
   *  caller — the navigation happens immediately either way, and the chip
   *  appears a moment later in the cold case. An exit keypress must not wait on
   *  a network round-trip.
   *
   *  The late path only writes when the scope is *still* what this function
   *  left it. Between the two, the user has a landing (or a conversation) in
   *  front of them with a working scope control, and a late resolution that
   *  overwrote their choice would be a worse bug than the one being fixed. */
  const seedScopeFromReader = () => {
    const loc = props.reader.readerWork();
    const w = props.reader.currentWork();
    props.conversations.setChatScope(w ? { workId: w.work_id, title: w.display_title } : null);
    if (w || !loc) return;
    // Deliberately untracked: the late callback must read chatScope as it is when the list resolves, not subscribe to it
    void props.reader.resolveWork(loc).then((late) => {
      if (!late) return;
      if (props.conversations.chatScope() !== null) return;
      props.conversations.setChatScope({
        workId: late.work_id,
        title: late.display_title,
      });
    });
  };
  return (
    <Show when={work()}>
      {(w) => (
        <Reader
          workSlug={w().workSlug}
          sourceLang={w().sourceLang}
          authorSlug={w().authorSlug}
          focusChunkId={w().focusChunkId}
          openTermId={w().openTermId}
          onOpenTermIdChange={props.reader.setOpenTermId}
          onAuthorResolved={props.reader.growAuthorSlug}
          syntaxOpen={syntaxOpen()}
          suspended={props.reader.mode() !== "reader"}
          onExit={() => {
            // Escape leaves for the landing. Deliberately NOT `onClose`: the
            // back arrow resumes the last conversation, and "escape out of the
            // Reader" should not drop the user into a thread they did not ask
            // for. The passage is not lost either way; `minerva:last-reader`
            // brings Read back to it.
            //
            // The work IS carried over now, the same way `onClose` carries it
            // (#350). This used to clear the scope, and said so because the
            // landing had no chip to render one and `startFromLanding` cleared
            // it on submit anyway — both of which were true and are no longer:
            // `ChatRoute` passes `WorkScopeControl` to `<Landing>` when a scope
            // is set, and `startFromLanding` keeps it. So seeding here is now
            // visible and survives, which is what the agreed design asked for.
            seedScopeFromReader();
            props.routing.navigate({ kind: "landing" });
          }}
          onClose={() => {
            // Seed the chat scope with the work being read, so a question
            // asked right after closing the Reader is scoped to it. Shown
            // as a dismissible composer chip — never silent.
            seedScopeFromReader();
            void props.reader.switchMode("chat");
          }}
        />
      )}
    </Show>
  );
}
