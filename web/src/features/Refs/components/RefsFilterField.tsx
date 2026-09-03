import { Select, type SelectOption } from "~/components/Select";

export function RefsFilterField(props: {
  label: string;
  placeholder: string;
  ariaLabel: string;
  options: SelectOption[];
  value: string | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <label class="refs-filter">
      <span class="refs-filter-label">{props.label}</span>
      <Select
        options={props.options}
        value={props.value ?? ""}
        onChange={props.onChange}
        placeholder={props.placeholder}
        ariaLabel={props.ariaLabel}
      />
    </label>
  );
}
