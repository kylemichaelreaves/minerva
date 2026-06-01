// Persistent storage for saved translation highlights.
//
// The reader's drag-to-select → Translate → dismiss flow leaves a
// "saved underline marker" on the page. Without persistence those
// markers live only in the Reader's signal state and are gone on
// page reload. This module persists them per-work in localStorage
// so the user's annotation layer survives refreshes.
//
// The actual translations themselves are already cached server-side
// in `data/translations.sqlite` (see `src/minerva/translations.py`).
// What this module persists is which passages the user previously
// selected for translation — the metadata needed to re-render the
// underline marker AND to re-fire `/api/translate(source, ref)` when
// the user clicks it again (which then hits the server cache
// instantly).
//
// Storage shape: one key per work, JSON-serialized array of
// SavedHighlight. The work id is the same string the Reader uses to
// fetch the range (`props.workId` in Reader/index.tsx). Per-work
// isolation keeps the localStorage entries small and lets us load
// only the relevant highlights on Reader mount.

const KEY_PREFIX = "minerva:highlights:";

/** One persisted highlight. `chunkId / start / end` locate the
 *  underline span on the page; `source / ref` are passed to
 *  `/api/translate` when the user clicks the saved marker to re-open
 *  the cached translation. */
export interface SavedHighlight {
  chunkId: string;
  start: number;
  end: number;
  source: string;
  ref: string;
}

function storageKey(workId: string): string {
  return `${KEY_PREFIX}${workId}`;
}

/** Read saved highlights for one work. Returns [] when nothing is
 *  stored or when the stored payload fails to parse (a stale entry
 *  from an older format shouldn't break the reader; the user can
 *  re-create highlights). */
export function loadHighlights(workId: string): SavedHighlight[] {
  try {
    const raw = localStorage.getItem(storageKey(workId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    // Defensive validation — drop entries that don't have the
    // shape we expect. Don't try to "repair" them; a bad entry is
    // forgotten silently.
    return parsed.filter(
      (x): x is SavedHighlight =>
        typeof x === "object" &&
        x !== null &&
        typeof (x as SavedHighlight).chunkId === "string" &&
        typeof (x as SavedHighlight).start === "number" &&
        typeof (x as SavedHighlight).end === "number" &&
        typeof (x as SavedHighlight).source === "string" &&
        typeof (x as SavedHighlight).ref === "string",
    );
  } catch {
    return [];
  }
}

/** Replace the full saved-highlight list for one work. Idempotent;
 *  call any time the in-memory list of saved markers changes. */
export function saveHighlights(
  workId: string,
  highlights: SavedHighlight[],
): void {
  try {
    if (highlights.length === 0) {
      // Drop the key entirely when the list is empty — keeps the
      // localStorage namespace tidy across many works.
      localStorage.removeItem(storageKey(workId));
      return;
    }
    localStorage.setItem(storageKey(workId), JSON.stringify(highlights));
  } catch {
    // localStorage quota / private-mode failures are non-fatal:
    // the user just won't get persistence this session. The runtime
    // state continues to work.
  }
}
