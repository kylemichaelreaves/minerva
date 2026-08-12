// Reader mode controller. Two responsibilities:
//
//   1. Derive `readerWork` from the route (when `route.kind === 'reader'`).
//   2. Drive `switchMode('chat' | 'reader')` from the sidebar tabs —
//      remember the last-opened work in localStorage so Chat → Read
//      returns to the same passage, or fall back to the first work
//      from `/api/works`.

import { createEffect, createSignal } from "solid-js";
import { listWorks } from "~/api/readerApi";
import { keepsReaderAlive } from "~/routes/routeUtils";
import { apiError } from "~/utils/apiError";
import type { RoutingApi } from "~/routing";
import type { AppMode } from "~/Sidebar";
import type { Work } from "~/utils/types";

interface ReaderLocation {
  workId: string;
  sourceLang?: string;
  /** Disambiguates same-titled works (Luther 1912 vs 1545). */
  author?: string;
  focusChunkId?: string;
  /** Term-card open state mirrored from the URL (`?term=<id>`). When
   *  set, the Reader resumes the popover on next paint. */
  openTermId?: number;
}

const STORAGE_KEY = "minerva:last-reader";
// Remember the most recently active chat conversation so `switchMode("chat")`
// from Reader can drop the user back into the thread they were in. Without
// this, every Reader → Chat round-trip would dump the user onto the
// landing screen even though they came from a specific conversation.
const CONV_STORAGE_KEY = "minerva:last-conversation";

export interface ReaderApi {
  /** Current reader location from the route, or null when in chat. */
  readerWork: () => ReaderLocation | null;
  /** The reader location to keep RENDERING while the route has stepped out
   *  to a side route that should not tear the Reader down (#348) — the
   *  concordance today. Equal to `readerWork()` on a reader route, holds the
   *  last one while `keepsReaderAlive` is true, and null everywhere else.
   *
   *  Deliberately in memory only, and deliberately NOT sourced from the
   *  `minerva:last-reader` key `switchMode` reads. That key is a session-long
   *  bookmark; this is "the passage you are standing in right now". Sourcing
   *  it from storage would mount a hidden Reader — and refetch its window —
   *  behind a concordance opened cold from the top nav, which is an entry
   *  point with nothing to come back to. */
  retainedWork: () => ReaderLocation | null;
  /** "chat" / "reader" derived from the route — used by the sidebar tabs. */
  mode: () => AppMode;
  /** Switch view. Reads `localStorage` for the last reader location;
   *  falls back to the first work returned by `/api/works`.  */
  switchMode: (target: AppMode) => Promise<void>;
  /** Open the reader directly at a specific chunk — used when the user
   *  clicks a citation locator in marginalia. */
  openAtChunk: (workId: string, sourceLang: string | undefined, chunkId: string) => void;
  /** All available works from `/api/works`. Populated lazily the first
   *  time Reader mode is entered. */
  works: () => Work[];
  /** Trigger the lazy single-flight `/api/works` load (no-op once
   *  populated). Lets the chat scope picker fill the works list without
   *  entering Reader mode. */
  ensureWorks: () => Promise<void>;
  /** The full Work for the current reader location, or null. Resolves
   *  the route's work string + lang against the `works()` list — used to
   *  seed the chat scope chip when leaving the Reader. */
  currentWork: () => Work | null;
  /** Navigate to a specific work in Reader mode. */
  openWork: (work: Work) => void;
  /** Open / close the term-card for the current reader URL. Writing
   *  null clears `?term=…`; writing an id sets it. The Reader's local
   *  open-card signal is driven from this URL state on next paint. */
  setOpenTermId: (id: number | null) => void;
}

export function useReader(routing: RoutingApi, abortChat: () => void): ReaderApi {
  const [works, setWorks] = createSignal<Work[]>([]);
  let worksFetchInflight: Promise<void> | null = null;

  const readerWork = (): ReaderLocation | null => {
    const r = routing.route();
    return r.kind === "reader"
      ? {
          workId: r.workId,
          sourceLang: r.sourceLang,
          author: r.author,
          focusChunkId: r.focusChunkId,
          openTermId: r.openTermId,
        }
      : null;
  };

  const mode = (): AppMode => (readerWork() ? "reader" : "chat");

  // Hold the reader location across a step-out, drop it on anything else.
  // A signal rather than a derivation because the whole point is to remember
  // a value the route no longer carries.
  const [retainedWork, setRetainedWork] = createSignal<ReaderLocation | null>(null);
  createEffect(() => {
    const loc = readerWork();
    if (loc) {
      setRetainedWork(loc);
      return;
    }
    if (!keepsReaderAlive(routing.route())) setRetainedWork(null);
  });

  const currentWork = (): Work | null => {
    const loc = readerWork();
    if (!loc) return null;
    return (
      works().find(
        (w) =>
          w.work === loc.workId &&
          (loc.sourceLang == null || w.lang === loc.sourceLang) &&
          (loc.author == null || w.author === loc.author),
      ) ?? null
    );
  };

  function openAtChunk(workId: string, sourceLang: string | undefined, chunkId: string) {
    abortChat();
    routing.navigate({ kind: "reader", workId, sourceLang, focusChunkId: chunkId });
  }

  function openWork(work: Work) {
    abortChat();
    routing.navigate({
      kind: "reader",
      workId: work.work,
      sourceLang: work.lang,
      author: work.author,
    });
  }

  // Lazy single-flight loader. Avoid hammering `/api/works` on every
  // sidebar render — only fetch the first time the user enters Reader.
  function ensureWorks() {
    if (works().length > 0 || worksFetchInflight) return worksFetchInflight ?? Promise.resolve();
    worksFetchInflight = (async () => {
      try {
        setWorks(await listWorks());
      } catch (err) {
        console.warn("failed to load works for reader", err);
        apiError("Couldn't load the works list. Is the server running?");
      } finally {
        worksFetchInflight = null;
      }
    })();
    return worksFetchInflight;
  }
  createEffect(() => {
    if (mode() === "reader") void ensureWorks();
  });

  async function switchMode(target: AppMode) {
    if (target === mode()) return;
    abortChat();
    if (target === "chat") {
      // Restore the last conversation if we have one. If the stored id
      // points at a deleted conversation, the hydration path in
      // `conversationsCtrl` falls back gracefully (404 → landing).
      const lastConv = localStorage.getItem(CONV_STORAGE_KEY);
      if (lastConv) {
        routing.navigate({ kind: "conversation", id: lastConv });
        return;
      }
      routing.navigate({ kind: "landing" });
      return;
    }
    // target === 'reader': open the most recently visited work, or
    // pick a sensible default (first Greek-language work; fall back to
    // the first listed work; fail loudly only if there are no works).
    const remembered = localStorage.getItem(STORAGE_KEY);
    if (remembered) {
      try {
        const { workId, sourceLang, author } = JSON.parse(remembered) as ReaderLocation;
        if (workId) {
          routing.navigate({ kind: "reader", workId, sourceLang, author });
          return;
        }
      } catch (_) {
        // bad JSON in localStorage — ignore and fall through
      }
    }
    try {
      await ensureWorks();
      const all = works();
      if (all.length === 0) {
        console.warn("No works available — corpus index may be empty.");
        apiError("No works in the corpus index yet.");
        return;
      }
      const greek = all.find((w) => w.lang === "grc");
      const pick = greek ?? all[0];
      if (pick === undefined) return;
      routing.navigate({
        kind: "reader",
        workId: pick.work,
        sourceLang: pick.lang,
        author: pick.author,
      });
    } catch (err) {
      console.warn("failed to fetch works for reader", err);
      apiError("Couldn't load the works list.");
    }
  }

  // Remember the last reader location so Read → Chat → Read returns
  // to the same passage. Cleared only by explicit user navigation.
  createEffect(() => {
    const r = readerWork();
    if (r) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(r));
      } catch (_) {
        // localStorage quota — non-fatal
      }
    }
  });

  // Mirror the last-conversation id whenever the route lands on one,
  // so Reader → Chat can return to it. Deletions in `conversationsCtrl`
  // also clear this key (see `deleteConversation` handler there).
  createEffect(() => {
    const r = routing.route();
    if (r.kind === "conversation") {
      try {
        localStorage.setItem(CONV_STORAGE_KEY, r.id);
      } catch (_) {
        // localStorage quota — non-fatal
      }
    }
  });

  function setOpenTermId(id: number | null) {
    const r = routing.route();
    if (r.kind !== "reader") return;
    // Build the next route by spreading the current reader fields and
    // overwriting openTermId. Using `undefined` (not 0) tells
    // routeHash to omit the param entirely.
    routing.navigate({
      ...r,
      openTermId: id ?? undefined,
    });
  }

  return {
    readerWork,
    retainedWork,
    mode,
    currentWork,
    switchMode,
    openAtChunk,
    works,
    ensureWorks,
    openWork,
    setOpenTermId,
  };
}
