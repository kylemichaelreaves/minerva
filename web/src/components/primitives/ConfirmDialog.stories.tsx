// Stories for the modal ConfirmDialog. Simplest of the seed stories —
// pure props in, callbacks out, no fetch / no context. Validates the
// end-to-end story shape (Meta / StoryObj / args) and confirms the
// global CSS + theme decorator from `.storybook/preview.tsx` resolve
// the dialog's scrim + paper tokens correctly.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import ConfirmDialog from "~/components/ConfirmDialog";

const meta: Meta<typeof ConfirmDialog> = {
  title: "Dialogs/ConfirmDialog",
  component: ConfirmDialog,
  parameters: {
    // The dialog has its own scrim and centers itself; we don't want
    // Storybook's centered-layout to fight that.
    layout: "fullscreen",
  },
  args: {
    open: true,
    // Storybook auto-logs callbacks via the actions panel when args are
    // functions. Bind both to a tiny console.debug so the no-empty-function
    // lint rule stays happy and so the story still works if the actions
    // panel is closed.
    onConfirm: () => {
      console.debug("ConfirmDialog onConfirm");
    },
    onCancel: () => {
      console.debug("ConfirmDialog onCancel");
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: "Delete conversation?",
    message: "This will permanently remove this conversation and all its messages.",
    confirmLabel: "Delete",
    cancelLabel: "Cancel",
  },
};

export const Destructive: Story = {
  args: {
    title: "Discard unsaved changes?",
    message: "You have edits in flight that haven't been committed. Discard them and continue?",
    confirmLabel: "Discard",
    cancelLabel: "Keep editing",
  },
};

export const LongMessage: Story = {
  args: {
    title: "Re-ingest the corpus?",
    message:
      "Re-running ingest will rebuild the index from scratch, invalidate any in-flight " +
      "embeddings, and cascade-delete the curated lemma cache (chunk_lemmas). Term occurrences " +
      "survive via shadow address, but any glossary work pending a commit should be saved first. " +
      "This takes about 3 minutes on the current corpus.",
    confirmLabel: "Re-ingest",
    cancelLabel: "Cancel",
  },
};
