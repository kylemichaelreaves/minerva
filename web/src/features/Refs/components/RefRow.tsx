import type { ReferencesListRow } from "~/api/refsApi";
import { ReferenceCitationBlock } from "~/features/Refs/components/ReferenceCitationBlock";

export function RefRow(props: {
  row: ReferencesListRow;
  onOpenSource: (workTitle: string, chunkId: string) => void;
}) {
  const onClick = () => {
    const work = props.row.source.work;
    const chunk = props.row.source_chunk_id;
    if (work && chunk) props.onOpenSource(work, chunk);
  };

  // A real <button> rather than a clickable <li>: the row opens its source
  // passage, and as a bare list item it had no name, no tab stop and no key
  // handling, so the source was reachable only with a mouse. `role="button"`
  // plus a hand-rolled Enter/Space handler would satisfy the same audit
  // (typescript:S6847, typescript:S1082) but re-implements what the platform
  // already does, and trades those two findings for typescript:S6819.
  return (
    <li class="ref-row-item">
      <button type="button" class="ref-row" onClick={onClick}>
        <ReferenceCitationBlock
          variant="list"
          source={props.row.source}
          target={{
            author: props.row.target.author,
            work: props.row.target.work,
            locator: props.row.target.locator,
          }}
          referenceType={props.row.reference_type}
          quotedPhrase={props.row.quoted_phrase}
          note={props.row.note}
          confidence={props.row.confidence}
          sourceMethod={props.row.source_method}
          curatorStatus={props.row.curator_status}
        />
      </button>
    </li>
  );
}
