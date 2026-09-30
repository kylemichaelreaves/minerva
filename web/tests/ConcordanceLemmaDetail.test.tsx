// The KWIC grid's data lifecycle across a lemma change.
//
// `useLemmaDetail` used to be a raw `createResource` with no AbortSignal:
// a superseded lemma's request ran to completion against the server, and
// nothing cancelled it when the component unmounted (#65). Migrating it to
// `useAbortableFetch` fixes that, but only correctly if the previous lemma's
// answer is dropped the moment the lemma changes — the args carry the lemma,
// so keeping it would render the old occurrences under the new heading.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@solidjs/testing-library";
import { createSignal } from "solid-js";

const fetchLemmaDetail = vi.fn();

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaDetail: (...args: unknown[]) => fetchLemmaDetail(...args) as never,
  };
});

import { ConcordanceLemmaDetail } from "~/Concordance/components/LemmaDetail";

const row = (surface: string) => ({
  chunk_id: `c-${surface}`,
  section: "¶1",
  book: "I",
  work: "Kritik der reinen Vernunft",
  author: "Kant",
  ord: 0,
  surface,
  pos: "NOUN",
  morph: {},
  morph_str: "",
  kwic_left: "der ",
  kwic_match: surface,
  kwic_right: " ist",
});

const detail = (lemma: string, surface: string) => ({
  lemma,
  lang: "deu",
  scope: "corpus" as const,
  scope_label: "the corpus",
  filters: { pos: null, morph: {}, surface: null },
  total: 1,
  limit: 100,
  offset: 0,
  pos_breakdown: [],
  case_breakdown: [],
  number_breakdown: [],
  gender_breakdown: [],
  surface_breakdown: [],
  work_breakdown: [],
  drop_counts: {},
  rows: [row(surface)],
  next_offset: null,
});

function renderDetail(lemma: () => string) {
  return render(() => (
    <ConcordanceLemmaDetail
      lemma={lemma()}
      lang="deu"
      scope="corpus"
      onNavigate={vi.fn()}
      onBackToIndex={vi.fn()}
      onOpenChunk={vi.fn()}
    />
  ));
}

beforeEach(() => {
  fetchLemmaDetail.mockReset();
});

describe("<ConcordanceLemmaDetail />", () => {
  it("renders the occurrences for its lemma", async () => {
    fetchLemmaDetail.mockResolvedValue(detail("Begriff", "Begriffe"));

    renderDetail(() => "Begriff");

    expect(await screen.findAllByText("Begriffe")).not.toHaveLength(0);
  });

  it("passes an AbortSignal so a superseded request can be cancelled", async () => {
    fetchLemmaDetail.mockResolvedValue(detail("Begriff", "Begriffe"));

    renderDetail(() => "Begriff");
    await screen.findAllByText("Begriffe");

    // The raw `createResource` this replaced had no way to hand one over,
    // so every abandoned lemma query ran to completion server-side.
    expect(fetchLemmaDetail).toHaveBeenCalledWith(
      expect.objectContaining({ lemma: "Begriff" }),
      expect.any(AbortSignal),
    );
  });

  it("does not show the previous lemma's occurrences under the new lemma", async () => {
    const [lemma, setLemma] = createSignal("Begriff");
    let releaseSecond!: () => void;
    const second = new Promise((resolve) => {
      releaseSecond = () => {
        resolve(detail("Anschauung", "Anschauungen"));
      };
    });
    fetchLemmaDetail.mockImplementation((args: { lemma: string }) =>
      args.lemma === "Begriff" ? Promise.resolve(detail("Begriff", "Begriffe")) : second,
    );

    // `renderDetail` reads the accessor inside its JSX, which is exactly the
    // tracked scope the rule is asking for — it just cannot see across the
    // helper. The reactivity is real: the assertions below depend on it.
    // eslint-disable-next-line solid/reactivity
    renderDetail(lemma);
    expect(await screen.findAllByText("Begriffe")).not.toHaveLength(0);

    setLemma("Anschauung");

    // While the new lemma is in flight, nothing on screen may still be
    // claiming to be about the old one.
    await waitFor(() => {
      expect(screen.queryAllByText("Begriffe")).toHaveLength(0);
    });

    releaseSecond();
    expect(await screen.findAllByText("Anschauungen")).not.toHaveLength(0);
  });

  it("shows the server's reason when the fetch fails", async () => {
    fetchLemmaDetail.mockRejectedValue(new Error("upstream exploded"));

    renderDetail(() => "Begriff");

    expect(await screen.findByText("Couldn't load occurrences")).toBeInTheDocument();
    expect(screen.getByText("upstream exploded")).toBeInTheDocument();
  });

  it("leaves Enter on a focused filter chip to the chip, not the KWIC cursor (#702)", async () => {
    fetchLemmaDetail.mockResolvedValue({
      ...detail("Begriff", "Begriffe"),
      case_breakdown: [{ value: "Acc", count: 1 }],
    });
    const onOpenChunk = vi.fn();
    render(() => (
      <ConcordanceLemmaDetail
        lemma="Begriff"
        lang="deu"
        scope="corpus"
        onNavigate={vi.fn()}
        onBackToIndex={vi.fn()}
        onOpenChunk={onOpenChunk}
      />
    ));
    const chip = await screen.findByRole("button", { name: "Akk" });
    chip.focus();
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    chip.dispatchEvent(enter);
    // Not preventDefault-ed, so the browser's own Enter→click activation
    // runs; and the current KWIC hit is not opened in the Reader.
    expect(enter.defaultPrevented).toBe(false);
    expect(onOpenChunk).not.toHaveBeenCalled();

    // Enter with nothing focused still opens the current hit.
    chip.blur();
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
    );
    expect(onOpenChunk).toHaveBeenCalledWith("Kritik der reinen Vernunft", "c-Begriffe");
  });

  it("routes a missing lemma cache to its own explainer", async () => {
    // The branch that used to read `String(data.error as unknown)`; the
    // hook hands over a real string now.
    fetchLemmaDetail.mockRejectedValue(new Error("lemma cache is empty for deu"));

    renderDetail(() => "Begriff");

    expect(await screen.findByText("No lemma cache")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load occurrences")).toBeNull();
  });
});
