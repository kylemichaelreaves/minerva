import { Show } from "solid-js";
import type { SelectOption } from "~/components/Select";
import { referenceTypeSelectOptions } from "~/utils/referenceTypes";
import { RefsFilterField } from "~/features/Refs/components/RefsFilterField";
import { stringsToSelectOptions } from "~/features/Refs/components/refsList";

export interface RefsFiltersBarProps {
  variant?: "browse" | "review";
  sourceAuthor: string | undefined;
  targetAuthor?: string | undefined;
  referenceType: string | undefined;
  includeRejected?: boolean | undefined;
  sourceOptions: string[];
  targetOptions?: string[];
  onChange: (patch: {
    sourceAuthor?: string;
    targetAuthor?: string;
    targetWork?: string;
    referenceType?: string;
    includeRejected?: boolean;
  }) => void;
}

export function RefsFiltersBar(props: RefsFiltersBarProps) {
  const review = () => props.variant === "review";
  const sourceOpts = (): SelectOption[] => stringsToSelectOptions(props.sourceOptions);
  const targetOpts = (): SelectOption[] =>
    stringsToSelectOptions(props.targetOptions ?? []);

  return (
    <div class="refs-filters">
      <RefsFilterField
        label="Source"
        placeholder="Any source"
        ariaLabel="Source author"
        options={sourceOpts()}
        value={props.sourceAuthor}
        onChange={(v) => { props.onChange({ sourceAuthor: v || undefined }); }}
      />
      <Show when={!review()}>
        <RefsFilterField
          label="Target"
          placeholder="Any target"
          ariaLabel="Target author"
          options={targetOpts()}
          value={props.targetAuthor}
          onChange={(v) => { props.onChange({ targetAuthor: v || undefined }); }}
        />
      </Show>
      <RefsFilterField
        label="Type"
        placeholder="Any type"
        ariaLabel="Reference type"
        options={referenceTypeSelectOptions()}
        value={props.referenceType}
        onChange={(v) => { props.onChange({ referenceType: v || undefined }); }}
      />
      <Show when={!review()}>
        <label class="refs-check refs-filter-check">
          <input
            type="checkbox"
            checked={Boolean(props.includeRejected)}
            onChange={(e) =>
              { props.onChange({ includeRejected: e.currentTarget.checked }); }
            }
          />
          <span class="refs-check-box" aria-hidden="true" />
          <span class="refs-check-label">Include rejected</span>
        </label>
      </Show>
    </div>
  );
}
