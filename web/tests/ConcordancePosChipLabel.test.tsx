// The POS chip in the active-filter strip names the class the way the POS
// dropdown does (#892).
//
// The chip used to re-derive its label as `pos.toLowerCase()`, while the
// dropdown reads `POS_OPTIONS`. The two agreed for every value except ADP,
// which the dropdown calls "prep": `?pos=ADP` showed "adp" on the chip and
// "prep" in the control that set it.

import { render, waitFor } from "@solidjs/testing-library";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type * as concordanceApi from "~/api/concordanceApi";
import type { LemmaIndexResponse } from "~/api/concordanceApi";
import type * as readerApi from "~/api/readerApi";

const fetchLemmaIndex = vi.fn<typeof concordanceApi.fetchLemmaIndex>();
const listWorks = vi.fn<typeof readerApi.listWorks>();

vi.mock("~/api/readerApi", () => ({
  listWorks: (...args: Parameters<typeof readerApi.listWorks>) => listWorks(...args),
}));

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaIndex: (...args: Parameters<typeof concordanceApi.fetchLemmaIndex>) =>
      fetchLemmaIndex(...args),
  };
});

import { POS_OPTIONS } from "~/Concordance/components/FilterBar";
import { ConcordanceIndexPage } from "~/Concordance/components/IndexPage";

const RESPONSE: LemmaIndexResponse = {
  scope: "corpus",
  scope_label: "",
  lang: "deu",
  letter: null,
  sort: "freq",
  total_lemmas: 1,
  total_occurrences: 1,
  letter_counts: {},
  limit: 200,
  offset: 0,
  next_offset: null,
  rows: [],
};

const posChip = () =>
  Array.from(document.querySelectorAll(".afs .afs-pill"))
    .map((e) => e.textContent.replace(/\s+/g, " ").trim())
    .find((t) => t.startsWith("POS"));

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  fetchLemmaIndex.mockResolvedValue(RESPONSE);
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
});

describe("concordance index — POS chip label (#892)", () => {
  it.each([
    ["ADP", "prep"],
    ["NOUN", "noun"],
    ["all", "all"],
  ])("labels pos=%s as %s, as the dropdown does", async (pos, label) => {
    render(() => (
      <ConcordanceIndexPage lang="deu" pos={pos} onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() => expect(posChip()).toBeDefined());
    expect(posChip()).toContain(label);
    if (pos === "ADP") expect(posChip()).not.toContain("adp");
  });

  it("agrees with POS_OPTIONS for every non-default option", async () => {
    for (const opt of POS_OPTIONS.filter((o) => o.value && o.value !== "all")) {
      const { unmount } = render(() => (
        <ConcordanceIndexPage
          lang="deu"
          pos={opt.value}
          onNavigate={vi.fn()}
          onOpenLemma={vi.fn()}
        />
      ));
      await waitFor(() => expect(posChip()).toBeDefined());
      expect(posChip()).toContain(opt.label);
      unmount();
    }
  });

  it("falls back to the raw value, lower-cased, for a POS the dropdown does not list", async () => {
    render(() => (
      <ConcordanceIndexPage lang="deu" pos="SCONJ" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() => expect(posChip()).toBeDefined());
    expect(posChip()).toContain("sconj");
  });
});
