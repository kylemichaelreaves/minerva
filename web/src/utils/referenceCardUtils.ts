import type { ReferenceTarget } from "~/utils/types";

export interface ExternalLink {
  label: string;
  href: string;
}

export function isGreekQuote(phrase: string | null): boolean {
  if (!phrase) return false;
  return /[Ͱ-Ͽἀ-῿]/.test(phrase);
}

export function defaultExternalLinks(target: ReferenceTarget): ExternalLink[] {
  const author = encodeURIComponent(target.author);
  const both = encodeURIComponent(`${target.author} ${target.work}`);
  return [
    { label: "Logeion", href: `https://logeion.uchicago.edu/${author}` },
    {
      label: "Perseus",
      href: `https://www.perseus.tufts.edu/hopper/search?q=${both}`,
    },
    { label: "archive.org", href: `https://archive.org/search?query=${both}` },
  ];
}

export function defaultOpenInReader(target: ReferenceTarget): string {
  const work = encodeURIComponent(target.work);
  if (target.chunk_id !== null) {
    return `#/r/${work}?focus=${encodeURIComponent(target.chunk_id)}`;
  }
  return `#/r/${work}`;
}
