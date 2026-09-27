// @vitest-environment node
import { describe, it, expect } from "vitest";
import { errorMessage, isAbortError } from "~/utils/util";

describe("errorMessage", () => {
  it("returns Error.message", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("stringifies non-Error values", () => {
    expect(errorMessage("plain")).toBe("plain");
    expect(errorMessage(42)).toBe("42");
  });

  it("stringifies plain objects", () => {
    expect(errorMessage({ code: "X" })).toBe("[object Object]");
  });
});

describe("isAbortError", () => {
  it("detects AbortError by name", () => {
    const err = new DOMException("aborted", "AbortError");
    expect(isAbortError(err)).toBe(true);
  });

  it("returns false for other errors", () => {
    expect(isAbortError(new Error("nope"))).toBe(false);
  });
});
