// @vitest-environment node
import { createRoot, createSignal } from "solid-js";
import { describe, expect, it } from "vitest";
import { createScopedSignal } from "~/Syntax/chunkScoped";

// State that belongs to one chunk, in an overlay that outlives the chunk.
//
// `SyntaxRoute` re-fetches rather than re-mounting on a chunk change, so
// nothing unmounts and nothing is reinitialised. Clearing it with an effect
// would work a beat late, and for that beat the previous chunk's state is
// live over the new tree. Stamping the value with its chunk moves the reset
// into the read, where there is no beat (#141).

/** Run *body* inside a Solid root, disposing after. */
function withRoot<T>(body: (chunkId: () => string, goTo: (id: string) => void) => T): T {
  let dispose = () => {
    /* replaced below */
  };
  const [chunkId, setChunkId] = createSignal("abc");
  try {
    return createRoot((d) => {
      dispose = d;
      return body(chunkId, (id) => {
        setChunkId(id);
      });
    });
  } finally {
    dispose();
  }
}

describe("createScopedSignal", () => {
  it("holds a value while the chunk is unchanged", () => {
    withRoot((chunkId) => {
      const [read, write] = createScopedSignal(chunkId, 0);
      write(7);
      expect(read()).toBe(7);
    });
  });

  it("reads as empty on a different chunk", () => {
    withRoot((chunkId, goTo) => {
      const [read, write] = createScopedSignal(chunkId, 0);
      write(7);
      goTo("xyz");
      expect(read()).toBe(0);
    });
  });

  it("resets immediately, not on a later tick", () => {
    // The distinction that rules an effect out: an effect would leave the old
    // value readable for the rest of this synchronous turn, which is exactly
    // when the overlay re-renders against the new tree.
    withRoot((chunkId, goTo) => {
      const [read, write] = createScopedSignal(chunkId, null as number | null);
      write(3);
      goTo("xyz");
      expect(read()).toBeNull();
    });
  });

  it("does not resurrect the old value when the chunk comes back", () => {
    withRoot((chunkId, goTo) => {
      const [read, write] = createScopedSignal(chunkId, 0);
      write(7);
      goTo("xyz");
      write(0);
      goTo("abc");
      expect(read()).toBe(0);
    });
  });

  it("takes an updater, applied to the value on the current chunk", () => {
    withRoot((chunkId) => {
      const [read, write] = createScopedSignal(chunkId, 0);
      write(2);
      write((n) => n + 3);
      expect(read()).toBe(5);
    });
  });

  it("applies an updater to empty after a chunk change, not to the old value", () => {
    // `setSentOrd((n) => n + 1)` after a navigation must count from the first
    // sentence of the new chunk, not from where the reader was in the old one.
    withRoot((chunkId, goTo) => {
      const [read, write] = createScopedSignal(chunkId, 0);
      write(8);
      goTo("xyz");
      write((n) => n + 1);
      expect(read()).toBe(1);
    });
  });
});
