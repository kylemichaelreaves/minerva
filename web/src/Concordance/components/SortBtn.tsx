export function SortBtn(props: { label: string; cur: boolean; onClick: () => void }) {
  return (
    <span
      onClick={props.onClick}
      style={{
        "font-family": "var(--mono)",
        "font-size": "11px",
        "letter-spacing": "0.06em",
        cursor: "pointer",
        color: props.cur ? "var(--ink)" : "var(--ink-mute)",
        "font-weight": props.cur ? 700 : 400,
      }}
    >
      {props.label}
    </span>
  );
}
