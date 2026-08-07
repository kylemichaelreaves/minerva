import { createSignal } from "solid-js";

// Per-chunk state, in an overlay that outlives the chunk.
//
// `SyntaxRoute` reads `route()` inside the JSX prop expression on purpose, so
// a navigation between chunks re-fetches rather than re-mounting — the same
// pattern as `ConcordanceRoute` and `NetworkRoute`. Nothing unmounts, so
// nothing is reinitialised, and every signal set on one passage is still set
// on the next one.
//
// The consequences were not small. The correction store posted to the chunk
// it was created on, so every later edit came back refused with a message
// about a token that plainly exists; and a sentence index kept from a longer
// chunk matched nothing in a shorter one, so the overlay reported "No syntax
// for this passage" over a chunk that had parsed perfectly well (#141).

type Update<T> = T | ((cur: T) => T);

/**
 * A signal whose value belongs to one chunk, and reads as *empty* from any
 * other.
 *
 * A `createEffect` on the chunk id would also clear it, but a beat late: the
 * effect runs after the update that changed the chunk, and for that beat the
 * old value is live over the new tree. Stamping the value with the chunk it
 * was written on moves the reset into the read, where there is no beat.
 */
export function createScopedSignal<T>(chunkId: () => string, empty: T) {
  const [raw, setRaw] = createSignal({ chunk: chunkId(), value: empty });

  const read = (): T => {
    const r = raw();
    return r.chunk === chunkId() ? r.value : empty;
  };

  const write = (next: Update<T>): void => {
    // An updater counts from `read()`, which is already *empty* on a new
    // chunk — so `setSentOrd((n) => n + 1)` after a navigation moves off the
    // first sentence of the new passage, not off wherever the reader was in
    // the old one.
    const value = typeof next === "function" ? (next as (cur: T) => T)(read()) : next;
    setRaw({ chunk: chunkId(), value });
  };

  return [read, write] as const;
}
