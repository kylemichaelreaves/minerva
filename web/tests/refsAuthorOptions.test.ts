// @vitest-environment node
// Ordering of the Refs page's two author filter dropdowns.
//
// Both lists have an endpoint path and a fallback path. The fallback fires
// whenever `/api/references/sources` returns an empty list, and derives the
// options from the rows already on the page. These tests pin the fallback's
// ordering; the endpoint path is passed through untouched and is covered in
// Refs.test.tsx.

import { describe, it, expect } from "vitest";
import { createRoot } from "solid-js";
import type { ReferencesListRow } from "~/api/refsApi";
import {
  useRefsSourceAuthors,
  useRefsTargetAuthors,
} from "~/features/Refs/components/refsList";

// Only the two author fields are read by the memos under test. The rest of
// `ReferencesListRow` is filled in so the fixture type-checks.
function rowWithAuthors(source: string, target: string): ReferencesListRow {
  return {
    id: 1,
    source_chunk_id: "c-1",
    source_span_start: null,
    source_span_end: null,
    source_form: null,
    quoted_phrase: null,
    target: {
      author: target,
      work: "w",
      in_corpus_work_id: null,
      chunk_id: null,
      locator: null,
      locator_payload: null,
      sort_key: null,
    },
    reference_type: "cites",
    confidence: 1,
    source_method: "rule",
    curator_status: "approved",
    curated_by: null,
    curated_at: null,
    note: null,
    source: { author: source, work: "w", section: null },
  };
}

// `É` is U+00C9. A default `Array.prototype.sort()` compares UTF-16 code
// units, so it sorts every accented capital after `Z` (0x5A) — putting
// `Épictète` last instead of between `Aristote` and `Zénon`. No author in
// the live corpus is non-ASCII today (48 distinct `works.author`, 94
// distinct `reference_targets.canonical_author`, none outside ASCII), so
// this fixture is synthetic: it demonstrates the comparator, not an
// ordering a user has seen.
const ACCENTED = ["Zénon", "Épictète", "Aristote"];
const ACCENTED_COLLATED = ["Aristote", "Épictète", "Zénon"];

describe("Refs author filter options", () => {
  it("collates fallback source authors by locale, not by code unit", () => {
    createRoot((dispose) => {
      const rows = ACCENTED.map((a) => rowWithAuthors(a, "T"));
      const authors = useRefsSourceAuthors(
        () => ({ sources: [] }),
        () => rows,
      );
      expect(authors()).toEqual(ACCENTED_COLLATED);
      dispose();
    });
  });

  it("collates fallback target authors by locale, not by code unit", () => {
    createRoot((dispose) => {
      const rows = ACCENTED.map((a) => rowWithAuthors("S", a));
      const authors = useRefsTargetAuthors(
        () => ({ targets: [] }),
        () => rows,
      );
      expect(authors()).toEqual(ACCENTED_COLLATED);
      dispose();
    });
  });

  it("passes the endpoint's own source ordering through untouched", () => {
    // The endpoint sorts sources CHRONOLOGICALLY (`author_sort_key` in
    // src/minerva/refs/list_queries.py), which is deliberately not
    // alphabetical. Re-sorting here would silently override it.
    createRoot((dispose) => {
      const chronological = ["Homer", "Aristote", "Épictète"];
      const authors = useRefsSourceAuthors(
        () => ({ sources: chronological }),
        () => [],
      );
      expect(authors()).toEqual(chronological);
      dispose();
    });
  });

  it("passes the endpoint's own target ordering through untouched", () => {
    createRoot((dispose) => {
      const fromEndpoint = ["Aristote", "Épictète", "Zénon"];
      const authors = useRefsTargetAuthors(
        () => ({ targets: fromEndpoint }),
        () => [],
      );
      expect(authors()).toEqual(fromEndpoint);
      dispose();
    });
  });

  it("de-duplicates authors repeated across rows", () => {
    createRoot((dispose) => {
      const rows = ["Zénon", "Aristote", "Zénon"].map((a) =>
        rowWithAuthors(a, "T"),
      );
      const authors = useRefsSourceAuthors(
        () => ({ sources: [] }),
        () => rows,
      );
      expect(authors()).toEqual(["Aristote", "Zénon"]);
      dispose();
    });
  });

  it("skips rows whose author is absent", () => {
    createRoot((dispose) => {
      const rows = [rowWithAuthors("Aristote", "T")];
      rows.push({
        ...rowWithAuthors("x", "T"),
        source: { author: null, work: "w", section: null },
      });
      const authors = useRefsSourceAuthors(
        () => ({ sources: [] }),
        () => rows,
      );
      expect(authors()).toEqual(["Aristote"]);
      dispose();
    });
  });

  it("returns an empty list when neither source has rows", () => {
    createRoot((dispose) => {
      const source = useRefsSourceAuthors(
        () => undefined,
        () => undefined,
      );
      const target = useRefsTargetAuthors(
        () => undefined,
        () => undefined,
      );
      expect(source()).toEqual([]);
      expect(target()).toEqual([]);
      dispose();
    });
  });
});
