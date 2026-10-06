// @vitest-environment node
import { createRoot, createSignal } from "solid-js";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "~/api/client";
import type { CorrectionAccepted, SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";
import type { Correction } from "~/Syntax/corrections/apply";
import { createCorrectionStore, type CorrectionTransport } from "~/Syntax/corrections/store";

// The optimistic queue. Correcting a tree is hand labour done at speed —
// relabel, look, relabel — so the diagram has to move the instant the user
// commits, not a round trip later.
//
// Which means the interesting behaviour is all in the failure paths: what the
// tree looks like after the server refuses, after the network drops, and
// after two edits race. An optimistic store that only works when the server
// agrees is just a slow store with extra steps.
//
// The transport is injected rather than mocked at the module boundary, so
// these tests drive real store logic against a controllable server.

/**
 * Indexed access that fails loudly. `noUncheckedIndexedAccess` is on, so a
 * bare `xs[0]` is `T | undefined` and every assertion would need a `?.` that
 * quietly passes when the element is missing — which is exactly the bug these
 * tests exist to catch.
 */
function at<T>(xs: readonly T[], i: number): T {
  const v = xs[i];
  if (v === undefined) throw new Error(`no element at ${String(i)}`);
  return v;
}

const tok = (id: number, head: number | null, deprel: string): SyntaxToken => ({
  id,
  form: `w${String(id)}`,
  lemma: null,
  upos: null,
  xpos: null,
  feats: null,
  misc: null,
  head,
  deprel,
  start: id,
  end: id + 1,
  corrected: false,
});

const doc = (): SyntaxSentence[] => [
  { sent_ord: 0, tokens: [tok(1, 2, "det"), tok(2, 3, "nsubj"), tok(3, 0, "root")] },
];

const accepted = (id: number, token: SyntaxToken): CorrectionAccepted => ({
  id,
  chunk_id: "abc",
  sent_ord: 0,
  token,
  corrections: id,
});

/** A transport whose POST resolves with a server-assigned id. */
function okTransport(): CorrectionTransport {
  let next = 100;
  return {
    // Typed explicitly: `vi.fn` infers `any` params from the bare arrow, and
    // an `any` here would let a wrong-shaped request through the very tests
    // meant to pin the request shape.
    post: vi.fn<CorrectionTransport["post"]>((_chunkId, req) => {
      const id = next++;
      const t = tok(req.tokId, req.kind === "head" ? Number(req.toVal) : 2, req.toVal);
      return Promise.resolve(accepted(id, { ...t, corrected: true }));
    }),
    remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
  };
}

/** Run *body* inside a Solid reactive root, disposing after. */
async function withStore(
  transport: CorrectionTransport,
  body: (store: ReturnType<typeof createCorrectionStore>) => Promise<void> | void,
): Promise<void> {
  let dispose = () => {
    /* replaced below */
  };
  const store = createRoot((d) => {
    dispose = d;
    return createCorrectionStore(
      () => "abc",
      () => doc(),
      transport,
    );
  });
  try {
    await body(store);
  } finally {
    dispose();
  }
}

describe("createCorrectionStore", () => {
  it("shows the edit before the server has answered", async () => {
    let release = () => {
      /* replaced below */
    };
    const pending = new Promise<CorrectionAccepted>((resolve) => {
      release = () => {
        resolve(accepted(1, { ...tok(1, 2, "nmod"), corrected: true }));
      };
    });
    const transport: CorrectionTransport = {
      post: vi.fn(() => pending),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withStore(transport, async (store) => {
      const inFlight = store.relabel(0, 1, "nmod");

      // The whole point: the tree has already moved.
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
      expect(at(at(store.sentences(), 0).tokens, 0).corrected).toBe(true);
      expect(store.pending()).toBe(1);

      release();
      await inFlight;
      expect(store.pending()).toBe(0);
    });
  });

  it("keeps the edit once the server confirms it", async () => {
    await withStore(okTransport(), async (store) => {
      await store.relabel(0, 1, "nmod");

      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
      expect(store.corrections()).toHaveLength(1);
    });
  });

  it("adopts the server's id so undo addresses a real row", async () => {
    await withStore(okTransport(), async (store) => {
      await store.relabel(0, 1, "nmod");

      // The optimistic entry carried a temporary id; the row's real id is
      // what DELETE needs.
      expect(at(store.corrections(), 0).id).toBe(100);
    });
  });

  it("rolls the edit back when the server refuses it", async () => {
    const transport: CorrectionTransport = {
      post: vi.fn(() => Promise.reject(new ApiError("would make a cycle", 409))),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withStore(transport, async (store) => {
      await store.reattach(0, 2, 1);

      // Rolled all the way back — a refused edit must leave no trace, or the
      // client and the database disagree about what the tree is.
      expect(at(at(store.sentences(), 0).tokens, 1).head).toBe(3);
      expect(at(at(store.sentences(), 0).tokens, 1).corrected).toBe(false);
      expect(store.corrections()).toHaveLength(0);
    });
  });

  it("surfaces the server's reason for a refusal", async () => {
    const transport: CorrectionTransport = {
      post: vi.fn(() => Promise.reject(new ApiError("w1 is inside the subtree of w2.", 409))),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withStore(transport, async (store) => {
      await store.reattach(0, 2, 1);

      expect(store.refusal()?.message).toContain("inside the subtree");
    });
  });

  it("refuses an illegal edit locally without asking the server", async () => {
    const transport = okTransport();

    await withStore(transport, async (store) => {
      // 2 -> 1 closes a loop; the client knows that and must not post it.
      await store.reattach(0, 2, 1);

      expect(transport.post).not.toHaveBeenCalled();
      expect(store.refusal()?.code).toBe("cycle");
      expect(at(at(store.sentences(), 0).tokens, 1).head).toBe(3);
    });
  });

  it("refuses a relation the picker could not have produced", async () => {
    const transport = okTransport();

    await withStore(transport, async (store) => {
      await store.relabel(0, 1, "ojb");

      expect(transport.post).not.toHaveBeenCalled();
      expect(store.refusal()?.code).toBe("bad-deprel");
    });
  });

  it("clears a refusal once a good edit lands", async () => {
    await withStore(okTransport(), async (store) => {
      await store.reattach(0, 2, 1);
      expect(store.refusal()).not.toBeNull();

      await store.relabel(0, 1, "nmod");

      expect(store.refusal()).toBeNull();
    });
  });

  it("rolls back on a network failure the same way as on a refusal", async () => {
    const transport: CorrectionTransport = {
      post: vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withStore(transport, async (store) => {
      await store.relabel(0, 1, "nmod");

      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("det");
      expect(store.refusal()).not.toBeNull();
    });
  });

  it("validates each edit against the tree the previous one left behind", async () => {
    await withStore(okTransport(), async (store) => {
      // Move 1 under the root, so 2 no longer governs it...
      await store.reattach(0, 1, 3);
      // ...which makes 2 -> 1 legal, though it was a cycle a moment ago.
      await store.reattach(0, 2, 1);

      expect(store.refusal()).toBeNull();
      expect(at(at(store.sentences(), 0).tokens, 1).head).toBe(1);
    });
  });

  it("undoes a correction and reverts the token", async () => {
    const transport = okTransport();

    await withStore(transport, async (store) => {
      await store.relabel(0, 1, "nmod");
      await store.undo(at(store.corrections(), 0).id);

      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("det");
      expect(store.corrections()).toHaveLength(0);
      expect(transport.remove).toHaveBeenCalledWith(100);
    });
  });

  it("restores the correction when undo fails on the server", async () => {
    const transport = okTransport();
    transport.remove = vi.fn(() => Promise.reject(new ApiError("boom", 500)));

    await withStore(transport, async (store) => {
      await store.relabel(0, 1, "nmod");
      await store.undo(at(store.corrections(), 0).id);

      // The row is still there, so the client must not pretend otherwise.
      expect(store.corrections()).toHaveLength(1);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
    });
  });

  it("treats undo of an already-deleted row as success", async () => {
    const transport = okTransport();
    transport.remove = vi.fn(() => Promise.reject(new ApiError("not found", 404)));

    await withStore(transport, async (store) => {
      await store.relabel(0, 1, "nmod");
      await store.undo(at(store.corrections(), 0).id);

      // 404 means it is gone, which is what undo wanted. Restoring it would
      // resurrect a row that does not exist.
      expect(store.corrections()).toHaveLength(0);
    });
  });

  it("counts corrections for the footer", async () => {
    await withStore(okTransport(), async (store) => {
      await store.relabel(0, 1, "nmod");
      await store.relabel(0, 2, "obj");

      expect(store.correctedTokens(0)).toBe(2);
    });
  });
});

describe("what counts as a refusal", () => {
  const failWith = (err: Error): CorrectionTransport => ({
    post: vi.fn(() => Promise.reject(err)),
    remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
  });

  it("calls a 409 a refusal", async () => {
    await withStore(failWith(new ApiError("cycle", 409)), async (store) => {
      await store.relabel(0, 1, "nmod");
      expect(store.refusal()?.code).toBe("conflict");
    });
  });

  it("calls a gateway error unsaved, not refused", async () => {
    // A 502 from the dev proxy is the server being unreachable, not the
    // server saying no. Labelling it "Refused · 502 Bad Gateway" tells the
    // user their edit was rejected on the merits, which is a lie.
    await withStore(failWith(new ApiError("502 Bad Gateway", 502)), async (store) => {
      await store.relabel(0, 1, "nmod");
      expect(store.refusal()?.code).toBe("network");
      expect(store.refusal()?.message).toContain("not saved");
    });
  });

  it("calls a dropped connection unsaved", async () => {
    await withStore(failWith(new TypeError("Failed to fetch")), async (store) => {
      await store.relabel(0, 1, "nmod");
      expect(store.refusal()?.code).toBe("network");
    });
  });
});

describe("corrections from an earlier session", () => {
  const saved = [
    { id: 7, sentOrd: 0, tokId: 1, kind: "deprel" as const, toVal: "nmod", fromVal: "det" },
  ];

  /** A store seeded with a log the server already had. */
  async function withSeeded(
    transport: CorrectionTransport,
    body: (store: ReturnType<typeof createCorrectionStore>) => Promise<void> | void,
  ): Promise<void> {
    let dispose = () => {
      /* replaced below */
    };
    const store = createRoot((d) => {
      dispose = d;
      return createCorrectionStore(
        () => "abc",
        () => doc(),
        transport,
        () => saved,
      );
    });
    try {
      await body(store);
    } finally {
      dispose();
    }
  }

  it("replays the saved log into the tree", async () => {
    await withSeeded(okTransport(), (store) => {
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
      expect(at(at(store.sentences(), 0).tokens, 0).corrected).toBe(true);
    });
  });

  it("can undo a correction it did not make", async () => {
    // The reload case. Without the saved log the Revert button has no id to
    // send and the tree has no way back to `det`.
    const transport = okTransport();

    await withSeeded(transport, async (store) => {
      await store.undo(7);

      expect(transport.remove).toHaveBeenCalledWith(7);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("det");
      expect(at(at(store.sentences(), 0).tokens, 0).corrected).toBe(false);
    });
  });

  it("does not resurrect an undone correction on the next read", async () => {
    await withSeeded(okTransport(), async (store) => {
      await store.undo(7);

      // `saved` is derived from the fetch and still contains id 7; the store
      // has to remember that it is gone rather than re-deriving it.
      expect(store.corrections()).toHaveLength(0);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("det");
    });
  });

  it("restores a saved correction when the server refuses the undo", async () => {
    const transport = okTransport();
    transport.remove = vi.fn(() => Promise.reject(new ApiError("boom", 500)));

    await withSeeded(transport, async (store) => {
      await store.undo(7);

      expect(store.corrections()).toHaveLength(1);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
    });
  });

  it("keeps a session edit alongside the saved ones", async () => {
    await withSeeded(okTransport(), async (store) => {
      await store.relabel(0, 2, "obj");

      expect(store.corrections().map((c) => c.id)).toEqual([7, 100]);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("nmod");
      expect(at(at(store.sentences(), 0).tokens, 1).deprel).toBe("obj");
    });
  });

  it("carries the saved from_val for the provenance line", async () => {
    await withSeeded(okTransport(), (store) => {
      expect(at(store.corrections(), 0).fromVal).toBe("det");
    });
  });
});

describe("a navigation between chunks", () => {
  // `SyntaxRoute` deliberately re-fetches rather than re-mounting when the
  // chunk changes, so the store outlives the chunk it was created on. Every
  // test here drives that transition: the store has to follow the chunk, and
  // nothing from the old one may survive into the new tree (#141).

  /** Two chunks of different shapes, so a leak between them is visible. */
  const chunkDocs: Record<string, SyntaxSentence[]> = {
    abc: doc(),
    xyz: [{ sent_ord: 0, tokens: [tok(1, 0, "root")] }],
  };

  /** Run *body* with a store whose chunk can be changed mid-test. */
  async function withNavigation(
    transport: CorrectionTransport,
    body: (
      store: ReturnType<typeof createCorrectionStore>,
      goTo: (id: string) => void,
    ) => Promise<void> | void,
    savedFor: (chunkId: string) => readonly Correction[] = () => [],
  ): Promise<void> {
    let dispose = () => {
      /* replaced below */
    };
    const [chunkId, setChunkId] = createSignal("abc");
    const store = createRoot((d) => {
      dispose = d;
      return createCorrectionStore(
        chunkId,
        () => chunkDocs[chunkId()] ?? [],
        transport,
        () => savedFor(chunkId()),
      );
    });
    try {
      await body(store, (id) => {
        setChunkId(id);
      });
    } finally {
      dispose();
    }
  }

  it("posts to the chunk it is on now, not the one it was created with", async () => {
    const transport = okTransport();

    await withNavigation(transport, async (store, goTo) => {
      goTo("xyz");
      await store.relabel(0, 1, "nmod");

      // Posting to `abc` is what produces "no token 1 in sentence 0 of this
      // chunk" — the server correctly refusing a coherent edit to the wrong
      // passage, which reads to the user as a judgement on the edit.
      expect(transport.post).toHaveBeenCalledWith("xyz", expect.anything());
    });
  });

  it("drops the previous chunk's corrections instead of replaying them", async () => {
    await withNavigation(okTransport(), async (store, goTo) => {
      await store.relabel(0, 1, "nmod");
      expect(store.corrections()).toHaveLength(1);

      goTo("xyz");

      expect(store.corrections()).toHaveLength(0);
      // Token 1 of `xyz` is a different word that happens to share an id.
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("root");
      expect(at(at(store.sentences(), 0).tokens, 0).corrected).toBe(false);
    });
  });

  it("does not land an in-flight edit from the previous chunk on the new one", async () => {
    let release = () => {
      /* replaced below */
    };
    const answered = new Promise<CorrectionAccepted>((resolve) => {
      release = () => {
        resolve(accepted(100, { ...tok(1, 2, "nmod"), corrected: true }));
      };
    });
    const transport: CorrectionTransport = {
      post: vi.fn(() => answered),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withNavigation(transport, async (store, goTo) => {
      const inFlight = store.relabel(0, 1, "nmod");
      goTo("xyz");
      release();
      await inFlight;

      // The reconcile that swaps the optimistic id for the server's must not
      // write the row into a chunk it was never about.
      expect(store.corrections()).toHaveLength(0);
      expect(at(at(store.sentences(), 0).tokens, 0).deprel).toBe("root");
    });
  });

  it("does not carry a refusal across to the new chunk", async () => {
    const transport: CorrectionTransport = {
      post: vi.fn(() => Promise.reject(new ApiError("would make a cycle", 409))),
      remove: vi.fn<CorrectionTransport["remove"]>(() => Promise.resolve()),
    };

    await withNavigation(transport, async (store, goTo) => {
      await store.relabel(0, 1, "nmod");
      expect(store.refusal()).not.toBeNull();

      goTo("xyz");

      // The panel names tokens by id, and id 1 is a different word here.
      expect(store.refusal()).toBeNull();
    });
  });

  it("does not double the log when the reader navigates back", async () => {
    // The edit made on `abc` comes back from the server on the return visit,
    // in `saved`. If the session copy also survives, the same correction is
    // in the log twice and Revert points at one of two identical rows.
    const savedOnReturn: Correction[] = [
      { id: 100, sentOrd: 0, tokId: 1, kind: "deprel", toVal: "nmod", fromVal: "det" },
    ];
    let visited = false;

    await withNavigation(
      okTransport(),
      async (store, goTo) => {
        await store.relabel(0, 1, "nmod");
        goTo("xyz");
        visited = true;
        goTo("abc");

        expect(store.corrections()).toHaveLength(1);
      },
      (chunkId) => (visited && chunkId === "abc" ? savedOnReturn : []),
    );
  });
});
