import { filterPos, POS_TAGS, posGloss } from "~/Syntax/corrections/pos";
import { PickerShell } from "~/Syntax/components/PickerShell";

// Choosing a token's part of speech (#253). The interaction lives in
// `PickerShell`, which is also what `RelationPicker` is built from — the two
// edits are the same gesture and share the rule that the field filters a
// closed inventory and never accepts free text.
//
// That rule is doing more work here than it does for relations. The German
// parser carries a TIGER tag beside the UD one, and `NN` / `PRELS` / `ADJA`
// are shaped exactly like real UD tags, so free text would let the wrong
// column's value through unnoticed. See `corrections/pos.ts`.

export interface PosPickerProps {
  /** The word being retagged, for the heading. */
  form: string;
  tokenId: number;
  /** The tag as it currently stands. */
  current: string | null;
  onCommit: (upos: string) => void;
  onCancel: () => void;
}

export function PosPicker(props: PosPickerProps) {
  return (
    <PickerShell
      label="Part of speech"
      dialogLabel={`Retag ${props.form}`}
      filterLabel="Filter parts of speech"
      listLabel="Parts of speech"
      groups={(query) =>
        filterPos(query).map((g) => ({ title: g.title, rows: g.tags }))
      }
      current={props.current}
      currentGloss={props.current ? posGloss(props.current) : undefined}
      total={POS_TAGS.length}
      footNote="UD v2"
      emptyHint={(query) => (
        <>
          No part of speech matches “{query}”. The list is closed — a TIGER tag like{" "}
          <code>NN</code> cannot be written here.
        </>
      )}
      onCommit={props.onCommit}
      onCancel={props.onCancel}
    />
  );
}
