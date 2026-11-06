import { Index, Show } from "solid-js";
import { classnames } from "~/utils/util";
import { LoadingDots } from "~/components/primitives/LoadingDots";
import type { MinervaTurn, Turn, UserTurn } from "~/utils/types";
import { MinervaTurnView } from "~/Thread/components/MinervaTurnView";
import { ThreadSkeleton } from "~/Thread/components/ThreadSkeleton";
import { turnId } from "~/Thread/turnId";
import "~/Thread/thread.css";
import { UserTurnView } from "~/Thread/components/UserTurnView";
import type { Phase } from "~/features/LandingTransition/controller";

export type { ExpandedState } from "~/Thread/components/MinervaTurnView";

interface ThreadProps {
  messages: Turn[];
  thinking: boolean;
  hydrating?: boolean;
  marginNotes: boolean;
  pinnedChunkIds?: string[];
  onTogglePin?: (chunkId: string) => void;
  onOpenReader?: (workId: string, sourceLang: string | undefined, chunkId: string) => void;
  /** The landing → chat transition's phase, while it runs. */
  arriving?: Phase;
}

export default function Thread(props: ThreadProps) {
  const showSkeleton = () => Boolean(props.hydrating) && props.messages.length === 0;
  return (
    <div
      class={classnames(
        "thread",
        props.marginNotes && "has-margin",
        props.arriving === "lift" && "lt-arriving",
        props.arriving === "fade" && "lt-fading",
      )}
    >
      <Show when={showSkeleton()}>
        <ThreadSkeleton />
      </Show>
      <Index each={props.messages}>
        {(msg, index) => (
          <div data-turn-id={turnId(msg(), index)}>
            {/* <Show> (not a plain ternary) — the ternary re-evaluated as a
                whole whenever msg() changed, tearing down and recreating
                MinervaTurnView on every SSE delta and wiping its
                useCitationExpand state on finalize. Show keys on the
                condition's truthiness; while the role stays the same only
                the lazy prop getters re-run. */}
            <Show
              when={msg().role === "user"}
              fallback={
                <MinervaTurnView
                  msg={msg() as MinervaTurn}
                  marginNotes={props.marginNotes}
                  pinnedChunkIds={props.pinnedChunkIds}
                  onTogglePin={props.onTogglePin}
                  onOpenReader={props.onOpenReader}
                />
              }
            >
              <UserTurnView msg={msg() as UserTurn} />
            </Show>
          </div>
        )}
      </Index>
      <Show when={props.thinking}>
        <div class="turn turn-minerva">
          <div class="turn-meta">
            <span>Minerva</span>
            <span class="dot-sep" />
            <span class="turn-philosopher">
              <span class="glyph">M</span>thinking
            </span>
          </div>
          <div class="thinking">
            <span>considering</span>
            <LoadingDots />
          </div>
        </div>
      </Show>
    </div>
  );
}
