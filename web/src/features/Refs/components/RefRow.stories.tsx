import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { RefRow } from "~/features/Refs/components/RefRow";
import type { ReferencesListRow } from "~/api/refsApi";

const ROW: ReferencesListRow = {
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
};

const meta: Meta<typeof RefRow> = {
  title: "Refs/RefRow",
  component: RefRow,
  parameters: {
    layout: "padded",
  },
  args: {
    row: ROW,
    onOpenSource: (workTitle: string, chunkId: string) => {
      console.debug("RefRow onOpenSource", workTitle, chunkId);
    },
  },
  decorators: [
    (Story) => (
      <ul class="refs-list" style={{ "max-width": "720px", margin: "0", padding: "0" }}>
        <Story />
      </ul>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const OutOfCorpus: Story = {
  args: {
    row: {
      ...ROW,
      id: 3,
      quoted_phrase: null,
      reference_type: "alludes",
      target: {
        author: "Cicero",
        work: "Hortensius",
        in_corpus_work_id: null,
        chunk_id: null,
        locator: null,
        locator_payload: null,
        sort_key: null,
      },
      note:
        "Augustine's call-to-philosophy echoes Cicero's lost Hortensius (Conf. III.4.7).",
      source: {
        author: "Augustine",
        work: "Confessiones",
        section: "Conf. I.1.1",
      },
    },
  },
};
