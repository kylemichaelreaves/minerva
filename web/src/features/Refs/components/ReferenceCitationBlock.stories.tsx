import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { ReferenceCitationBlock } from "~/features/Refs/components/ReferenceCitationBlock";

const meta: Meta<typeof ReferenceCitationBlock> = {
  title: "Refs/ReferenceCitationBlock",
  component: ReferenceCitationBlock,
  parameters: {
    layout: "padded",
  },
  args: {
    variant: "list",
    source: {
      author: "Aquinas",
      work: "Summa Theologiae",
      section: "ST I, q. 84, a. 7",
    },
    target: {
      author: "Aristotle",
      work: "On the Soul",
      locator: "III.7",
    },
    referenceType: "quotes",
    quotedPhrase: "νοεῖν ἄνευ φαντάσματος",
    note: "The phantasm article — locus classicus on Aristotelian cognition.",
    confidence: 0.95,
    sourceMethod: "rule_strong",
    curatorStatus: "approved",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const ListVariant: Story = {};

export const WithPendingStatus: Story = {
  args: {
    curatorStatus: "auto",
    confidence: 0.55,
    sourceMethod: "rule_weak",
  },
};

export const ReviewTarget: Story = {
  args: {
    variant: "review-target",
    showOutOfCorpus: true,
    inCorpusWorkId: null,
    sourceForm: "Cicero in Hortensio",
    note: undefined,
    target: {
      author: "Cicero",
      work: "Hortensius",
      locator: null,
    },
    referenceType: "alludes",
    quotedPhrase: null,
    confidence: 0.62,
    sourceMethod: "rule_weak",
  },
};

export const InCorpusReviewTarget: Story = {
  args: {
    variant: "review-target",
    showOutOfCorpus: true,
    inCorpusWorkId: 110,
    sourceForm: "Philosophus",
    note: undefined,
    target: {
      author: "Aristotle",
      work: "Metaphysics",
      locator: "XII",
    },
    referenceType: "cites",
    quotedPhrase: null,
    confidence: 0.55,
    sourceMethod: "rule_weak",
  },
};
