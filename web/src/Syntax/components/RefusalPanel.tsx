import { Show } from "solid-js";
import { REFUSAL_TITLE, type Refusal } from "~/Syntax/corrections/validate";

// Frame 08. What the tool says when it will not do what you asked.
//
// Deliberately a panel and not a toast. A toast leaves, and the thing the
// user needs is to read the reason while looking at the tree it is about —
// "sich is inside the subtree of entwickelt" only means something next to the
// arc it describes. It stays until dismissed or until the next edit lands.
//
// It also says, every time, that nothing was written. A refusal that leaves
// the user unsure whether half of it went through is worse than no refusal.

export interface RefusalPanelProps {
  refusal: Refusal;
  onDismiss: () => void;
  /** Offered when the refusal is one that attaching to root would resolve. */
  onAttachToRoot?: () => void;
}

export function RefusalPanel(props: RefusalPanelProps) {
  const offersRoot = () =>
    props.onAttachToRoot !== undefined && props.refusal.code === "cycle";

  return (
    <div class="syn-refuse" role="alert">
      <div class="syn-rt">{REFUSAL_TITLE[props.refusal.code]}</div>
      <div class="syn-rb">{props.refusal.message}</div>
      <div class="syn-rf">
        <button type="button" class="syn-rlink" onClick={() => props.onDismiss()}>
          Esc — dismiss
        </button>
        <Show when={offersRoot()}>
          <button
            type="button"
            class="syn-rlink"
            onClick={() => props.onAttachToRoot?.()}
          >
            Attach to root instead
          </button>
        </Show>
        <span class="syn-rnote">nothing was written</span>
      </div>
    </div>
  );
}
