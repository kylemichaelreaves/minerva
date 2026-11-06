import type { UserTurn } from "~/utils/types";

export function UserTurnView(props: { msg: UserTurn }) {
  return (
    <div class="turn turn-user fade-in">
      {/* The column wrapper: thread.css caps it at `--col` on wide screens so
          the question sits directly above the composer, while the turn's
          own top rule stays full-width like Minerva's. */}
      <div class="turn-user-inner">
        <div class="turn-meta">You · {props.msg.time}</div>
        <div class="turn-body">{props.msg.text}</div>
      </div>
    </div>
  );
}
