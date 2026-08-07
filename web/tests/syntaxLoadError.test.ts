import { describe, expect, it } from "vitest";
import { ApiError } from "~/api/client";
import { loadErrorMessage } from "~/Syntax/loadError";

// What the overlay says when the GET fails.
//
// The same split `corrections/store.ts` makes for a refused edit, applied to
// the fetch: a 4xx is the server making a judgement about this chunk and
// saying why, and its own wording is better than anything reconstructed here.
// A 5xx or a dropped socket is not a judgement, and reporting one as though
// it were tells the reader something false about their passage.

describe("loadErrorMessage", () => {
  it("shows the server's reason when it refuses the chunk", () => {
    // The 400 `load_or_parse` raises for a non-German chunk (#231). Collapsing
    // it to the generic line loses the only part that says what to do.
    const err = new ApiError("syntax parsing is deu-only; chunk 'rep-509d' is 'eng'", 400);

    expect(loadErrorMessage(err)).toBe("syntax parsing is deu-only; chunk 'rep-509d' is 'eng'");
  });

  it("shows the server's reason for a chunk that is not there", () => {
    expect(loadErrorMessage(new ApiError("no chunk 'nope'", 404))).toBe("no chunk 'nope'");
  });

  it("stays generic for a server fault", () => {
    // "Could not load syntax: 502 Bad Gateway" reads as a statement about the
    // passage. It is a statement about the gateway.
    expect(loadErrorMessage(new ApiError("502 Bad Gateway", 502))).toBe(
      "Could not load syntax for this passage.",
    );
  });

  it("stays generic when the request never arrived", () => {
    expect(loadErrorMessage(new TypeError("Failed to fetch"))).toBe(
      "Could not load syntax for this passage.",
    );
  });

  it("stays generic when a 4xx carries no message", () => {
    expect(loadErrorMessage(new ApiError("", 400))).toBe("Could not load syntax for this passage.");
  });
});
