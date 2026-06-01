import type { SelectOption } from "~/components/Select";
import type { ReferenceType } from "~/utils/types";

export const REFERENCE_TYPES: readonly ReferenceType[] = [
  "cites",
  "quotes",
  "paraphrases",
  "alludes",
  "comments_on",
  "translates",
  "disputes",
  "corrects",
] as const;

export function referenceTypeLabel(t: ReferenceType): string {
  return t === "comments_on" ? "comments on" : t;
}

export function referenceTypeSelectOptions(): SelectOption[] {
  return REFERENCE_TYPES.map((t) => ({
    value: t,
    label: referenceTypeLabel(t),
  }));
}
