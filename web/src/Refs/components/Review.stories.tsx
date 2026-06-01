// Stories for the curator review surface (/refs/review).
//
// Mocks /api/references/review_queue and PATCH /api/references/:id
// so the page is exercisable without the live backend. The fixture
// exercises every layout variant: in-corpus target, out-of-corpus
// target, with/without quoted phrase, with/without source-span
// highlight, and different reference types.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Review from "~/Refs/components/Review";
import type { ReviewQueueResponse } from "~/api/refsApi";
import { withTheme } from "../../../.storybook/decorators";

// ─── fixture ──────────────────────────────────────────────────────

const SAMPLE_QUEUE: ReviewQueueResponse = {
  limit: 50,
  offset: 0,
  total_pending: 3,
  references: [
    {
      id: 101,
      source_chunk_id: "abc1234567890abc1234",
      source_span_start: 24,
      source_span_end: 35,
      source_form: "Philosophus",
      quoted_phrase: null,
      target: {
        author: "Aristotle",
        work: "Metaphysics",
        in_corpus_work_id: 110,
        chunk_id: null,
        locator: "XII",
        locator_payload: null,
        sort_key: null,
      },
      reference_type: "cites",
      confidence: 0.55,
      source_method: "rule_weak",
      curator_status: "auto",
      note: null,
      source: {
        author: "Aquinas",
        work: "Summa Theologiae",
        section: "ST I, q. 2, a. 3",
        text: "Tertia via est sumpta ex possibili et necessario. Philosophus probat hoc in XII Metaphysicae, ostendens quod necesse est devenire ad aliquod primum movens immobile, sicut et nos hic invenimus. Sed quia non est possibile in causis moventibus procedere in infinitum, oportet ponere aliquod primum movens, quod a nullo movetur, et hoc omnes intelligunt Deum.",
      },
    },
    {
      id: 102,
      source_chunk_id: "def1234567890def1234",
      source_span_start: null,
      source_span_end: null,
      source_form: null,
      quoted_phrase: "Cicero in Hortensio",
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
      confidence: 0.62,
      source_method: "rule_weak",
      curator_status: "auto",
      note: "Initial low-confidence flag; reviewer should confirm Conf. III.4 echo of Hortensius's call-to-philosophy.",
      source: {
        author: "Augustine",
        work: "Confessiones",
        section: "Conf. III.4.7",
        text: "Inter hos ego imbecilla tunc aetate discebam libros eloquentiae, in qua eminere cupiebam fine damnabili et ventoso per gaudia vanitatis humanae. Et usitato iam discendi ordine perveneram in librum cuiusdam Ciceronis, cuius linguam fere omnes mirantur, pectus non ita.",
      },
    },
    {
      id: 103,
      source_chunk_id: "ghi1234567890ghi1234",
      source_span_start: 0,
      source_span_end: 17,
      source_form: "Kantischen System",
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
      reference_type: "disputes",
      confidence: 0.72,
      source_method: "rule_weak",
      curator_status: "auto",
      note: null,
      source: {
        author: "Hegel",
        work: "Phenomenology of Spirit",
        section: "§77",
        text: "Kantischen System der Erkenntnis liegt eine Trennung zugrunde, die das Wesen der Wahrheit nicht zu erfassen vermag. Die transzendentale Synthesis bleibt subjektiv, der Gegenstand bleibt jenseits.",
      },
    },
  ],
};

// ─── fetch interceptor ────────────────────────────────────────────

const ORIGINAL_FETCH = globalThis.fetch.bind(globalThis);
globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  // GET /api/references/review_queue → static fixture.
  if (url.includes("/api/references/review_queue")) {
    return new Response(JSON.stringify(SAMPLE_QUEUE), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }
  // PATCH /api/references/:id → echo back the request body merged
  // with a fake id. The story just exercises the visual handoff.
  if (/\/api\/references\/\d+$/.test(url) && init?.method === "PATCH") {
    const body =
      init.body && typeof init.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : {};
    return new Response(
      JSON.stringify({
        id: 999,
        ...body,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
  return ORIGINAL_FETCH(input, init);
};

// ─── meta ─────────────────────────────────────────────────────────

const meta: Meta<typeof Review> = {
  title: "Refs/CuratorReview",
  component: Review,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    onNavigate: () => {
      /* stories don't push routes */
    },
    onNavigateToReference: () => {
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
          "Curator queue with three pending rows. The lowest-confidence " +
          "row (0.55 Aquinas → Aristotle) lands first because the " +
          "endpoint orders by confidence ASC.",
      },
    },
  },
};

export const DefaultDark: Story = {
  decorators: [withTheme("dark")],
};

export const FilteredByAquinas: Story = {
  args: {
    sourceAuthor: "Aquinas",
  },
};

export const FilteredByType: Story = {
  args: {
    referenceType: "alludes",
  },
};
