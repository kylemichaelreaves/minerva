// Stories for the corpus-wide /refs view.
//
// Mocks the /api/references endpoint via a tiny fixture
// that covers each visual variant (in-corpus target, out-of-corpus
// target, with/without quote, different reference_types, rejected
// status). The component is fully prop-driven for navigation
// callbacks — stories pass no-op callbacks so filter changes still
// re-fetch the mocked endpoint.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Refs from "~/Refs";
import type { ReferencesListResponse } from "~/api/refsApi";
import { withTheme } from "../../.storybook/decorators";

// ─── fixture data ─────────────────────────────────────────────────

const SAMPLE: ReferencesListResponse = {
  limit: 100,
  offset: 0,
  total: 0,
  filters: {
    source_author: null,
    target_author: null,
    target_work: null,
    reference_type: null,
  },
  references: [
    {
      id: 1,
      source_chunk_id: "c856b7a9d38b3700eab0",
      source_span_start: null,
      source_span_end: null,
      source_form: "Aristoteles in VIII Physicorum",
      quoted_phrase: null,
      target: {
        author: "Aristotle",
        work: "Physics",
        in_corpus_work_id: 110,
        chunk_id: null,
        locator: "VIII.6",
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "cites",
      confidence: 1.0,
      source_method: "manual",
      curator_status: "approved",
      note: "Aquinas's Second Way appeals to the prime mover of Phys. VIII.6.",
      source: {
        author: "Aquinas",
        work: "Summa Theologiae",
        section: "ST I, q. 2, a. 3",
      },
    },
    {
      id: 2,
      source_chunk_id: "4f1c245883e7aad638ed",
      source_span_start: null,
      source_span_end: null,
      source_form: "Philosophus",
      quoted_phrase: "νοεῖν ἄνευ φαντάσματος",
      target: {
        author: "Aristotle",
        work: "On the Soul",
        in_corpus_work_id: 107,
        chunk_id: "9866703703c8fff41076",
        locator: "III.7",
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "quotes",
      confidence: 0.95,
      source_method: "rule_strong",
      curator_status: "approved",
      note: "The phantasm article — locus classicus on Aristotelian cognition.",
      source: {
        author: "Aquinas",
        work: "Summa Theologiae",
        section: "ST I, q. 84, a. 7",
      },
    },
    {
      id: 3,
      source_chunk_id: "d0e8b483d00fdb3b3f06",
      source_span_start: null,
      source_span_end: null,
      source_form: null,
      quoted_phrase: null,
      target: {
        author: "Cicero",
        work: "Hortensius",
        in_corpus_work_id: null,
        chunk_id: null,
        locator: null,
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "alludes",
      confidence: 1.0,
      source_method: "manual",
      curator_status: "manual",
      note:
        "Augustine's 'fecisti nos ad te' echoes the call-to-philosophy of " +
        "Cicero's lost Hortensius (cited explicitly in Conf. III.4.7).",
      source: {
        author: "Augustine",
        work: "Confessiones",
        section: "Conf. I.1.1",
      },
    },
    {
      id: 4,
      source_chunk_id: "e463354b47b3905dd35e",
      source_span_start: null,
      source_span_end: null,
      source_form: "Cartesius",
      quoted_phrase: null,
      target: {
        author: "Descartes",
        work: "Principia philosophiae",
        in_corpus_work_id: 200,
        chunk_id: null,
        locator: "Pars I, art. 51",
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "disputes",
      confidence: 1.0,
      source_method: "manual",
      curator_status: "manual",
      note:
        "E I, P14's monism explicitly extends-by-correcting Descartes's " +
        "two-substance ontology in Princ. I.51-54.",
      source: {
        author: "Spinoza",
        work: "Ethica",
        section: "E I, P14",
      },
    },
    {
      id: 5,
      source_chunk_id: "1c412af61fcaa5e0902b",
      source_span_start: null,
      source_span_end: null,
      source_form: "Kant",
      quoted_phrase: null,
      target: {
        author: "Kant",
        work: "Critique of Pure Reason",
        in_corpus_work_id: 250,
        chunk_id: null,
        locator: null,
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "corrects",
      confidence: 1.0,
      source_method: "manual",
      curator_status: "manual",
      note:
        "PR §258 — the state as actuality of the ethical Idea, against " +
        "Kant's contractualist construal.",
      source: {
        author: "Hegel",
        work: "Elements of the Philosophy of Right",
        section: "§258",
      },
    },
    {
      id: 99,
      source_chunk_id: "abc1234567890abc1234",
      source_span_start: null,
      source_span_end: null,
      source_form: "Plato",
      quoted_phrase: null,
      target: {
        author: "Plato",
        work: "*",
        in_corpus_work_id: 81,
        chunk_id: null,
        locator: null,
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "cites",
      confidence: 0.55,
      source_method: "rule_weak",
      curator_status: "auto",
      note: null,
      source: {
        author: "Hegel",
        work: "Lectures on the History of Philosophy, Vol. II",
        section: "I. From Thales to Aristotle, ¶42",
      },
    },
  ],
};

// ─── fetch interceptor ────────────────────────────────────────────
//
// Same pattern as TermCard.stories.tsx — override globalThis.fetch
// once at module load. Non-/api/references requests pass through.

const ORIGINAL_FETCH = globalThis.fetch.bind(globalThis);
globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
  if (url.includes("/api/references") && !url.includes("/sources")) {
    // Tiny client-side filter so the stories' filter selects make
    // visible changes against the mock.
    const u = new URL(url, "http://localhost");
    const sa = u.searchParams.get("source_author");
    const ta = u.searchParams.get("target_author");
    const tw = u.searchParams.get("target_work");
    const rt = u.searchParams.get("reference_type");
    const includeRej = u.searchParams.get("include_rejected") === "1";
    const filtered = SAMPLE.references.filter((r) => {
      if (sa && r.source.author !== sa) return false;
      if (ta && r.target.author !== ta) return false;
      if (tw && r.target.work !== tw) return false;
      if (rt && r.reference_type !== rt) return false;
      if (!includeRej && r.curator_status === "rejected") return false;
      return true;
    });
    return new Response(
      JSON.stringify({
        limit: 100,
        offset: 0,
        total: filtered.length,
        filters: {
          source_author: sa,
          target_author: ta,
          target_work: tw,
          reference_type: rt,
        },
        references: filtered,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
  return ORIGINAL_FETCH(input, init);
};

// ─── meta ─────────────────────────────────────────────────────────

const meta: Meta<typeof Refs> = {
  title: "Refs/CorpusBrowser",
  component: Refs,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    onNavigate: () => {
      /* stories don't push routes */
    },
    onOpenSource: (workTitle: string, chunkId: string) => {
      console.debug("onOpenSource", workTitle, chunkId);
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  parameters: {
    docs: {
      description: {
        story:
          "Full corpus view with no filters — every reference variant " +
          "(in-corpus, out-of-corpus, with quote, multiple types).",
      },
    },
  },
};

export const DefaultDark: Story = {
  decorators: [withTheme("dark")],
};

export const FilteredByAquinasSource: Story = {
  args: {
    sourceAuthor: "Aquinas",
  },
};

export const FilteredByCiceroTarget: Story = {
  args: {
    targetAuthor: "Cicero",
  },
};

export const FilteredByTypeQuotes: Story = {
  args: {
    referenceType: "quotes",
  },
};

export const EmptyResult: Story = {
  args: {
    sourceAuthor: "Augustine",
    targetAuthor: "Kant",
  },
  parameters: {
    docs: {
      description: {
        story:
          "Filter combination with no matches — surfaces the empty-state " +
          "card and 'Clear filters' affordance.",
      },
    },
  },
};

// Mobile (iPhone 14, 390×844). Per design 4a: filter dropdowns become
// a horizontal chip strip (Source / Target / Type), cards reorder
// vertically (source row → italic quote with oxblood left rule →
// arrow → target row), no page padding. Active filter chip flips to
// ink-filled. Tapping a chip opens the underlying Select popover as
// a full-screen sheet (design 4b).
export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "iphone14" },
  },
};

export const MobileFiltered: Story = {
  args: {
    sourceAuthor: "Augustine",
  },
  parameters: {
    viewport: { defaultViewport: "iphone14" },
    docs: {
      description: {
        story:
          "Mobile with an active filter chip — the Author chip should " +
          "render ink-filled (paper text) to telegraph 'this facet is on'.",
      },
    },
  },
};
