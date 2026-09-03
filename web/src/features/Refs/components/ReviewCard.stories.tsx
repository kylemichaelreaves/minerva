import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { ReviewCard } from "~/features/Refs/components/ReviewCard";
import type { ReviewQueueRow } from "~/api/refsApi";

const ROW: ReviewQueueRow = {
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
    text:
      "Tertia via est sumpta ex possibili et necessario. Philosophus probat hoc in XII Metaphysicae, " +
      "ostendens quod necesse est devenire ad aliquod primum movens immobile, sicut et nos hic invenimus.",
  },
};

const meta: Meta<typeof ReviewCard> = {
  title: "Refs/ReviewCard",
  component: ReviewCard,
  parameters: {
    layout: "padded",
  },
  args: {
    row: ROW,
    noteDraft: "",
    onNoteChange: (s: string) => {
      console.debug("ReviewCard onNoteChange", s);
    },
    disabled: false,
    onApprove: () => {
      console.debug("ReviewCard onApprove");
    },
    onReject: () => {
      console.debug("ReviewCard onReject");
    },
    onSkip: () => {
      console.debug("ReviewCard onSkip");
    },
    onOpenSource: (workTitle: string, chunkId: string) => {
      console.debug("ReviewCard onOpenSource", workTitle, chunkId);
    },
  },
  decorators: [
    (Story) => (
      <div style={{ "max-width": "720px" }}>
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithNoteDraft: Story = {
  args: {
    noteDraft: "Confirm Metaphysics XII reference — weak trigger on “Philosophus”.",
  },
};

export const OutOfCorpus: Story = {
  args: {
    row: {
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
      note: "Initial low-confidence flag for Conf. III.4 echo.",
      source: {
        author: "Augustine",
        work: "Confessiones",
        section: "Conf. III.4.7",
        text:
          "Inter hos ego imbecilla tunc aetate discebam libros eloquentiae, in qua eminere cupiebam " +
          "fine damnabili et ventoso per gaudia vanitatis humanae.",
      },
    },
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
  },
};
