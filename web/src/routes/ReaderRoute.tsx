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
  return (
    <Show when={work() !== null}>
      <Reader
        workId={work()!.workId}
        sourceLang={work()!.sourceLang}
        author={work()!.author}
        focusChunkId={work()!.focusChunkId}
        openTermId={work()!.openTermId}
        onOpenTermIdChange={props.reader.setOpenTermId}
        syntaxOpen={syntaxOpen()}
        suspended={props.reader.mode() !== "reader"}
        onExit={() => {
          // Escape leaves for the landing, unscoped — the same state
          // `newConversation` produces. Deliberately NOT `onClose`: the back
          // arrow resumes the last conversation, and "escape out of the
          // Reader" should not drop the user into a thread they did not ask
          // for. The passage is not lost either way; `minerva:last-reader`
          // brings Read back to it.
          //
          // No chat scope is seeded here, unlike `onClose`. The landing has
          // no scope chip to show one — `WorkScopeControl` lives in
          // `ChatRoute`'s conversation branch — and `startFromLanding`
          // clears the scope on submit by design ("the global entry point —
          // unscoped"), so seeding it would be invisible and then discarded.
          props.conversations.setChatScope(null);
          props.routing.navigate({ kind: "landing" });
        }}
        onClose={() => {
          // Seed the chat scope with the work being read, so a question
          // asked right after closing the Reader is scoped to it. Shown
          // as a dismissible composer chip — never silent.
          const w = props.reader.currentWork();
          props.conversations.setChatScope(
            w ? { workId: w.work_id, title: w.display_title } : null,
          );
          void props.reader.switchMode("chat");
        }}
      />
    </Show>
  );
}
