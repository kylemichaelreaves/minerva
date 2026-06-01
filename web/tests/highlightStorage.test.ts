// Tests for the persistent-highlight localStorage helper. Verifies
// the load → save → reload round-trip, per-work key isolation, and
// graceful handling of corrupted / empty payloads.

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  loadHighlights,
  saveHighlights,
  type SavedHighlight,
} from "~/utils/highlightStorage";

const SAMPLE: SavedHighlight = {
  chunkId: "rep-509d",
  start: 5,
  end: 17,
  source: "divided line",
  ref: "509d",
};

describe("highlightStorage", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("returns [] when nothing is stored", () => {
    expect(loadHighlights("Republic")).toEqual([]);
  });

  it("round-trips a single highlight", () => {
    saveHighlights("Republic", [SAMPLE]);
    expect(loadHighlights("Republic")).toEqual([SAMPLE]);
  });

  it("round-trips multiple highlights in order", () => {
    const second: SavedHighlight = {
      ...SAMPLE,
      chunkId: "rep-510a",
      start: 0,
      end: 8,
      source: "intelligible",
      ref: "510a",
    };
    saveHighlights("Republic", [SAMPLE, second]);
    expect(loadHighlights("Republic")).toEqual([SAMPLE, second]);
  });

  it("per-work keys are isolated", () => {
    saveHighlights("Republic", [SAMPLE]);
    expect(loadHighlights("Phaedo")).toEqual([]);
  });

  it("replaces the full list on each save (not append)", () => {
    saveHighlights("Republic", [SAMPLE]);
    const replacement: SavedHighlight = {
      ...SAMPLE,
      chunkId: "rep-514a",
      start: 0,
      end: 4,
      source: "cave",
      ref: "514a",
    };
    saveHighlights("Republic", [replacement]);
    expect(loadHighlights("Republic")).toEqual([replacement]);
  });

  it("empty array deletes the storage key", () => {
    saveHighlights("Republic", [SAMPLE]);
    saveHighlights("Republic", []);
    // Direct localStorage probe — the entry should be GONE, not just
    // an empty array; this keeps the namespace tidy across many works.
    expect(localStorage.getItem("minerva:highlights:Republic")).toBeNull();
    expect(loadHighlights("Republic")).toEqual([]);
  });

  it("returns [] when stored payload is corrupted JSON", () => {
    localStorage.setItem("minerva:highlights:Republic", "{ not valid json");
    expect(loadHighlights("Republic")).toEqual([]);
  });

  it("returns [] when stored payload is a non-array", () => {
    localStorage.setItem(
      "minerva:highlights:Republic",
      JSON.stringify({ chunkId: "x" }),
    );
    expect(loadHighlights("Republic")).toEqual([]);
  });

  it("drops malformed entries while keeping valid ones", () => {
    const mixed = [
      SAMPLE,
      { chunkId: "no-numbers", start: "x", end: 5, source: "", ref: "" },
      { ...SAMPLE, chunkId: "rep-510a" },
    ];
    localStorage.setItem("minerva:highlights:Republic", JSON.stringify(mixed));
    const loaded = loadHighlights("Republic");
    expect(loaded.length).toBe(2);
    expect(loaded[0].chunkId).toBe("rep-509d");
    expect(loaded[1].chunkId).toBe("rep-510a");
  });
});
