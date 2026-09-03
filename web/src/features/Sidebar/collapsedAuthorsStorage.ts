const COLLAPSED_STORAGE_KEY = "minerva:reader:collapsed-authors";

export function loadCollapsedAuthors(): Set<string> {
  try {
    const raw = localStorage.getItem(COLLAPSED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((x): x is string => typeof x === "string"));
    }
  } catch {
    // Quota / parse / disabled-storage failures all fall through to
    // an empty set; UI still works, just without persistence.
  }
  return new Set();
}

export function saveCollapsedAuthors(set: Set<string>): void {
  try {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // Silent: persisting fold state is nice-to-have, not load-bearing.
  }
}
