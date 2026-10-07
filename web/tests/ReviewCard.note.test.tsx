// The curator's note field on a review card: every keystroke is reported to
// the owner, which keeps the draft and saves it with approve/reject.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@solidjs/testing-library";
import { ReviewCard } from "~/features/Refs/components/ReviewCard";
import type { ReviewQueueRow } from "~/api/refsApi";

const ROW: ReviewQueueRow = {
  id: 10,
  source_chunk_id: "rep-509d",
  source_span_start: null,
  source_span_end: null,
  source_form: null,
  quoted_phrase: null,
  target: {
    author: "Aristotle",
    work: "Ethics",
    in_corpus_work_id: 2,
    chunk_id: "ne-1",
    locator: "1097b",
    locator_payload: null,
    sort_key: null,
  },
  reference_type: "cites",
  confidence: 0.4,
  source_method: "rule+embed",
  curator_status: "auto",
  curated_by: null,
  curated_at: null,
  note: null,
  source: {
    author: "Plato",
    work: "Republic",
    section: "509d",
    text: "Source passage text.",
  },
};

describe("<ReviewCard /> note field", () => {
  it("shows the draft and reports each edit to onNoteChange", () => {
    const onNoteChange = vi.fn();
    render(() => (
      <ReviewCard
        row={ROW}
        noteDraft="first thought"
        onNoteChange={onNoteChange}
        disabled={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onSkip={vi.fn()}
        onOpenSource={vi.fn()}
      />
    ));

    const note = screen.getByPlaceholderText<HTMLTextAreaElement>(/What did the curator notice/);
    expect(note.value).toBe("first thought");

    fireEvent.input(note, { target: { value: "locator is off by one" } });
    expect(onNoteChange).toHaveBeenCalledWith("locator is off by one");
  });
});
