import { Show } from "solid-js";
import type { ReviewQueueRow } from "~/api/refsApi";
import {
  ReferenceCitationBlock,
  ReferenceCitationSourceLine,
} from "~/Refs/components/ReferenceCitationBlock";
import { SourceWithHighlight } from "~/Refs/components/SourceWithHighlight";

export function ReviewCard(props: {
  row: ReviewQueueRow;
  noteDraft: string;
  onNoteChange: (s: string) => void;
  disabled: boolean;
  onApprove: () => void;
  onReject: () => void;
  onSkip: () => void;
  onOpenSource: (workTitle: string, chunkId: string) => void;
}) {
  const source = () => props.row.source;
  const target = () => props.row.target;

  const openSource = (): void => {
    const w = source().work;
    if (w) props.onOpenSource(w, props.row.source_chunk_id);
  };

  return (
    <article class="review-card">
      <header class="review-card-head">
        <div class="review-source-cite">
          <ReferenceCitationSourceLine source={source()} />
        </div>
        <button
          class="review-source-open"
          type="button"
          onClick={openSource}
          aria-label="Open source passage in reader"
          disabled={!source().work}
        >
          Open in reader →
        </button>
      </header>

      <Show when={source().text}>
        {(textAccessor) => (
          <blockquote class="review-source-text">
            <SourceWithHighlight
              text={textAccessor()}
              start={props.row.source_span_start}
              end={props.row.source_span_end}
            />
          </blockquote>
        )}
      </Show>

      <ReferenceCitationBlock
        variant="review-target"
        source={source()}
        target={{
          author: target().author,
          work: target().work,
          locator: target().locator,
        }}
        referenceType={props.row.reference_type}
        quotedPhrase={props.row.quoted_phrase}
        confidence={props.row.confidence}
        sourceMethod={props.row.source_method}
        showOutOfCorpus
        inCorpusWorkId={target().in_corpus_work_id}
        sourceForm={props.row.source_form}
      />

      <label class="review-note">
        <span class="review-note-label">Note (optional)</span>
        <textarea
          rows="2"
          value={props.noteDraft}
          onInput={(e) => { props.onNoteChange(e.currentTarget.value); }}
          placeholder="What did the curator notice? (saved with approve/reject)"
        />
      </label>

      <div class="review-actions">
        <button
          class="review-btn review-btn-reject"
          type="button"
          disabled={props.disabled}
          onClick={props.onReject}
        >
          Reject
        </button>
        <button
          class="review-btn review-btn-skip"
          type="button"
          disabled={props.disabled}
          onClick={props.onSkip}
        >
          Skip
        </button>
        <button
          class="review-btn review-btn-approve"
          type="button"
          disabled={props.disabled}
          onClick={props.onApprove}
        >
          Approve
        </button>
      </div>
    </article>
  );
}
