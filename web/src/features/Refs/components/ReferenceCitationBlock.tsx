import { Show } from "solid-js";
import { referenceTypeLabel } from "~/utils/referenceTypes";
import type { ReferenceType } from "~/utils/types";

export interface CitationEnd {
  author: string | null;
  work: string | null;
  section?: string | null;
  locator?: string | null;
}

export function ReferenceCitationSourceLine(props: { source: CitationEnd }) {
  return (
    <>
      <span class="ref-row-author">{props.source.author ?? "?"}</span>
      <Show when={props.source.work}>
        {(w) => <em class="ref-row-work">{w()}</em>}
      </Show>
      <Show when={props.source.section}>
        {(s) => <span class="ref-row-locator">{s()}</span>}
      </Show>
    </>
  );
}

export function ReferenceCitationBlock(props: {
  variant: "list" | "review-target";
  source: CitationEnd;
  target: CitationEnd;
  referenceType: string;
  quotedPhrase?: string | null;
  note?: string | null;
  confidence: number;
  sourceMethod: string;
  curatorStatus?: string;
  /** Undefined = the caller does not carry provenance; null = unrecorded. */
  curatedBy?: string | null;
  showOutOfCorpus?: boolean;
  inCorpusWorkId?: number | null;
  sourceForm?: string | null;
}) {
  const targetEnd = () => (
    <>
      <span class="ref-row-author">{props.target.author}</span>
      <em class="ref-row-work">{props.target.work}</em>
      <Show when={props.target.locator}>
        {(l) => <span class="ref-row-locator">{l()}</span>}
      </Show>
      <Show when={props.showOutOfCorpus && props.inCorpusWorkId == null}>
        <span class="review-oop">out-of-corpus</span>
      </Show>
    </>
  );

  // #720: who decided the row. A decided status with no recorded author
  // predates migration 0039, so it reads "unrecorded", never "machine";
  // an undecided auto row with no author shows nothing.
  const curatedLabel = (): string | null => {
    if (props.curatedBy === undefined) return null;
    if (props.curatedBy) return `by ${props.curatedBy}`;
    return props.curatorStatus && props.curatorStatus !== "auto" ? "unrecorded" : null;
  };

  return (
    <>
      <Show when={props.variant === "list"}>
        <div class="ref-row-head">
          <div class="ref-row-source">
            <ReferenceCitationSourceLine source={props.source} />
          </div>
          <span class="ref-arrow" aria-hidden="true">
            →
          </span>
          <div class="ref-row-target">{targetEnd()}</div>
          <span class="ref-row-chip">
            {referenceTypeLabel(props.referenceType as ReferenceType)}
          </span>
        </div>
      </Show>

      <Show when={props.variant === "review-target"}>
        <div class="review-target-block">
          <span class="ref-arrow" aria-hidden="true">
            →
          </span>
          <div class="ref-row-target">{targetEnd()}</div>
          <span class="ref-row-chip">
            {referenceTypeLabel(props.referenceType as ReferenceType)}
          </span>
        </div>
      </Show>

      <Show when={props.quotedPhrase}>
        {(q) => (
          <div class={props.variant === "list" ? "ref-row-quote" : "review-quote"}>
            « {q()} »
          </div>
        )}
      </Show>

      <Show when={props.note}>
        {(n) => <div class="ref-row-note">{n()}</div>}
      </Show>

      <div class={props.variant === "list" ? "ref-row-meta" : "review-meta"}>
        <span class={props.variant === "list" ? "ref-row-conf" : "review-conf"}>
          conf {props.confidence.toFixed(2)}
        </span>
        <span class={props.variant === "list" ? "ref-row-method" : "review-method"}>
          {props.sourceMethod}
        </span>
        <Show when={props.sourceForm}>
          {(f) => <span class="review-form">trigger: «{f()}»</span>}
        </Show>
        <Show when={props.curatorStatus && props.curatorStatus !== "approved"}>
          <span class={`ref-row-status status-${props.curatorStatus}`}>
            {props.curatorStatus}
          </span>
        </Show>
        <Show when={curatedLabel()}>
          {(label) => <span class="ref-row-curated">{label()}</span>}
        </Show>
      </div>
    </>
  );
}
