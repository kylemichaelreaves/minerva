import type { ReferencesListRow } from "~/api/refsApi";
import { ReferenceCitationBlock } from "~/Refs/components/ReferenceCitationBlock";

export function RefRow(props: {
  row: ReferencesListRow;
  onOpenSource: (workTitle: string, chunkId: string) => void;
}) {
  const onClick = () => {
    const work = props.row.source.work;
    const chunk = props.row.source_chunk_id;
    if (work && chunk) props.onOpenSource(work, chunk);
  };

  return (
    <li class="ref-row" onClick={onClick}>
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
    </li>
  );
}
