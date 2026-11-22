// @vitest-environment node
import { createRoot, createSignal, flush } from "solid-js";
import { describe, expect, it } from "vitest";
import { createScopedSignal } from "~/Syntax/chunkScoped";

// State that belongs to one chunk, in an overlay that outlives the chunk.
//
// `SyntaxRoute` re-fetches rather than re-mounting on a chunk change, so
// nothing unmounts and nothing is reinitialised. Clearing it with an effect
// would work a beat late, and for that beat the previous chunk's state is
// live over the new tree. Stamping the value with its chunk moves the reset
// into the read, where there is no beat (#141).

/** Create the scoped signal inside a Solid root, then run *body* against it
 *  outside the root's body (Solid 2 refuses writes inside an owned scope),
 *  disposing after. `goTo` and `write` are flushed at once, so a read
 *  straight after either sees the committed value — the same flush the
 *  overlay re-renders in. */
function withRoot<T>(
  empty: T,
  body: (
    read: () => T,
    write: (next: T | ((cur: T) => T)) => void,
    goTo: (id: string) => void,
  ) => void,
): void {
  const [chunkId, setChunkId] = createSignal("abc");
  let dispose = () => {
    /* replaced below */
  };
  const [read, rawWrite] = createRoot((d) => {
    dispose = d;
    return createScopedSignal(chunkId, empty);
  });
  try {
    body(
      read,
      (next) => {
        rawWrite(next);
        flush();
      },
      (id) => {
        setChunkId(id);
        flush();
      },
    );
  } finally {
    dispose();
  }
}

describe("createScopedSignal", () => {
  it("holds a value while the chunk is unchanged", () => {
    withRoot(0, (read, write) => {
      write(7);
      expect(read()).toBe(7);
    });
  });

  it("reads as empty on a different chunk", () => {
    withRoot(0, (read, write, goTo) => {
      write(7);
      goTo("xyz");
      expect(read()).toBe(0);
    });
  });

  it("resets immediately, not on a later tick", () => {
    // The distinction that rules an effect out: an effect would leave the old
    // value readable in the flush that commits the chunk change, which is
    // exactly when the overlay re-renders against the new tree.
    withRoot(null as number | null, (read, write, goTo) => {
      write(3);
      goTo("xyz");
      expect(read()).toBeNull();
    });
  });

  it("does not resurrect the old value when the chunk comes back", () => {
    withRoot(0, (read, write, goTo) => {
      write(7);
      goTo("xyz");
      write(0);
      goTo("abc");
      expect(read()).toBe(0);
    });
  });

  it("takes an updater, applied to the value on the current chunk", () => {
    withRoot(0, (read, write) => {
      write(2);
      write((n) => n + 3);
      expect(read()).toBe(5);
    });
  });

  it("applies an updater to empty after a chunk change, not to the old value", () => {
    // `setSentOrd((n) => n + 1)` after a navigation must count from the first
    // sentence of the new chunk, not from where the reader was in the old one.
    withRoot(0, (read, write, goTo) => {
      write(8);
      goTo("xyz");
      write((n) => n + 1);
      expect(read()).toBe(1);
    });
  });
});
