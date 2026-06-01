import { Index, Show } from "solid-js";
import { classnames } from "~/utils/util";
import { LoadingDots } from "~/components/LoadingDots";
import type { MinervaTurn, Turn, UserTurn } from "~/utils/types";
import { MinervaTurnView } from "~/Thread/components/MinervaTurnView";
import { ThreadSkeleton } from "~/Thread/components/ThreadSkeleton";
import "~/Thread/thread.css";
import { UserTurnView } from "~/Thread/components/UserTurnView";

export type { ExpandedState } from "~/Thread/components/MinervaTurnView";

interface ThreadProps {
  messages: Turn[];
  thinking: boolean;
  hydrating?: boolean;
  marginNotes: boolean;
  pinnedChunkIds?: string[];
  onTogglePin?: (chunkId: string) => void;
  onOpenReader?: (workId: string, sourceLang: string | undefined, chunkId: string) => void;
}

function turnId(msg: Turn, index: number): string {
  return msg.role === "user" ? `user-${index}` : `minerva-${index}`;
}

export default function Thread(props: ThreadProps) {
  const showSkeleton = () => Boolean(props.hydrating) && props.messages.length === 0;
  return (
    <div class={classnames("thread", props.marginNotes && "has-margin")}>
      <Show when={showSkeleton()}>
        <ThreadSkeleton />
      </Show>
      <Index each={props.messages}>
        {(msg, index) => (
          <div data-turn-id={turnId(msg(), index)}>
            {msg().role === "user" ? (
              <UserTurnView msg={msg() as UserTurn} />
            ) : (
              <MinervaTurnView
                msg={msg() as MinervaTurn}
                marginNotes={props.marginNotes}
                pinnedChunkIds={props.pinnedChunkIds}
                onTogglePin={props.onTogglePin}
                onOpenReader={props.onOpenReader}
              />
            )}
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
