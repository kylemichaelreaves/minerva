import type { UserTurn } from "~/utils/types";

export function UserTurnView(props: { msg: UserTurn }) {
  return (
    <div class="turn turn-user fade-in">
      <div class="turn-meta">You · {props.msg.time}</div>
      <div class="turn-body">{props.msg.text}</div>
    </div>
  );
}
