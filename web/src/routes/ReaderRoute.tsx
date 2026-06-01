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
  const work = () => props.reader.readerWork();
  return (
    <Show when={props.reader.mode() === "reader" && work() !== null}>
      <Reader
        workId={work()!.workId}
        sourceLang={work()!.sourceLang}
        focusChunkId={work()!.focusChunkId}
        openTermId={work()!.openTermId}
        onOpenTermIdChange={props.reader.setOpenTermId}
        onClose={() => void props.reader.switchMode("chat")}
      />
    </Show>
  );
}
