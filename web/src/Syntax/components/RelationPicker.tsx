import { filterRelations, RELATIONS, relationGloss } from "~/Syntax/corrections/relations";
import { PickerShell } from "~/Syntax/components/PickerShell";

// Frame 07. Choosing the relation on an arc.
//
// The interaction — filter a closed inventory, Enter commits the highlighted
// row, never the raw text — lives in `PickerShell`, which `PosPicker` also
// uses. It was inlined here until the part-of-speech picker arrived and
// duplicated it wholesale (#253).
//
// The inventory carries both subtype families (`obj` and `expl:pv`, `acl` and
// `acl:relcl`) because Stanza's German is GSD-trained while the corrected
// trees are HDT-style — the machine writes one and the corrector reaches for
// the other. See `corrections/relations.ts`.

export interface RelationPickerProps {
  /** The word being relabelled, for the heading. */
  form: string;
  tokenId: number;
  /** The word it attaches to; absent when it is the root. */
  headForm?: string;
  headId?: number;
  /** The relation as it currently stands. */
  current: string | null;
  onCommit: (relation: string) => void;
  onCancel: () => void;
}

export function RelationPicker(props: RelationPickerProps) {
  return (
    <PickerShell
      label="Relation"
      dialogLabel={`Relabel ${props.form}`}
      filterLabel="Filter relations"
      listLabel="Relations"
      groups={(query) =>
        filterRelations(query).map((g) => ({ title: g.title, rows: g.relations }))
      }
      current={props.current}
      currentGloss={props.current ? relationGloss(props.current) : undefined}
      total={RELATIONS.length}
      footNote="UD v2 · German-HDT profile"
      emptyHint={(query) => (
        <>
          No relation matches “{query}”. The list is closed — nothing outside it can be written.
        </>
      )}
      onCommit={props.onCommit}
      onCancel={props.onCancel}
    />
  );
}
