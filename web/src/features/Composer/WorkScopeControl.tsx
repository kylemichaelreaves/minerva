import { For, Show, createEffect, createMemo, createSignal } from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";
import { useEscape } from "~/hooks/useEscape";
import type { ChatScope } from "~/features/conversations/conversationsCtrl";
import type { Work } from "~/utils/types";

/**
 * Chat work-scope control: shows the current scope as a pill ("All works"
 * when unscoped, the work's title when scoped) and opens a searchable
 * drop-up picker over all works. Picking sets the scope; the × clears it.
 * The picker filters across every author by default, with a one-click
 * "Within {author}" toggle (the current scope's author) to narrow.
 */
interface WorkScopeControlProps {
  scope: () => ChatScope | null;
  works: () => Work[];
  ensureWorks: () => Promise<void>;
  onSet: (scope: ChatScope | null) => void;
}

const _MAX_ROWS = 60; // cap rendered rows — 964 works, filter to narrow

export default function WorkScopeControl(props: WorkScopeControlProps) {
  const [open, setOpen] = createSignal(false);
  const [filter, setFilter] = createSignal("");
  const [withinAuthor, setWithinAuthor] = createSignal(false);
  let rootRef: HTMLDivElement | undefined;
  let filterInput: HTMLInputElement | undefined;

  useClickOutside(
    () => rootRef,
    open,
    () => setOpen(false),
  );
  // Gated, not checked inside: ungated, the listener claimed every Escape
  // (`preventDefault`) with the menu closed, so nothing after it — the chat's
  // Escape-to-landing — could tell a free Escape from one this had used.
  useEscape(() => setOpen(false), open);
  createEffect(() => {
    if (open()) filterInput?.focus();
  });

  // /api/works returns a row per (work, language); collapse to one row
  // per work_id for the picker.
  const uniqueWorks = createMemo(() => {
    const seen = new Set<number>();
    const out: Work[] = [];
    for (const w of props.works()) {
      if (!seen.has(w.work_id)) {
        seen.add(w.work_id);
        out.push(w);
      }
    }
    return out;
  });

  const contextAuthor = createMemo(() => {
    const s = props.scope();
    if (!s) return null;
    return uniqueWorks().find((w) => w.work_id === s.workId)?.author ?? null;
  });

  const filtered = createMemo(() => {
    const q = filter().trim().toLowerCase();
    const author = withinAuthor() ? contextAuthor() : null;
    const rows = uniqueWorks().filter((w) => {
      if (author && w.author !== author) return false;
      if (!q) return true;
      return `${w.author} ${w.display_title}`.toLowerCase().includes(q);
    });
    rows.sort(
      (a, b) => a.author.localeCompare(b.author) || a.display_title.localeCompare(b.display_title),
    );
    return rows.slice(0, _MAX_ROWS);
  });

  function openPicker() {
    void props.ensureWorks();
    setFilter("");
    setWithinAuthor(false);
    setOpen(true);
  }

  function pick(w: Work) {
    props.onSet({ workId: w.work_id, title: w.display_title });
    setOpen(false);
  }

  return (
    <div class="chat-scope-control" ref={rootRef}>
      <Show
        when={props.scope()}
        fallback={
          <button
            type="button"
            class="chat-scope__pill"
            aria-haspopup="dialog"
            aria-label="Scope: All works"
            onClick={openPicker}
          >
            All works
            <span class="chat-scope__chevron" aria-hidden="true">
              ▾
            </span>
          </button>
        }
      >
        {(scope) => (
          <div class="chat-scope">
            <button
              type="button"
              class="chat-scope__pill chat-scope__work"
              aria-haspopup="dialog"
              aria-label={`Scope: ${scope().title}`}
              title="Change work"
              onClick={openPicker}
            >
              {scope().title}
            </button>
            <button
              type="button"
              class="chat-scope__clear"
              aria-label={`Clear scope: ${scope().title}`}
              onClick={() => props.onSet(null)}
            >
              ×
            </button>
          </div>
        )}
      </Show>

      <Show when={open()}>
        <div class="chat-scope-pop" role="dialog" aria-label="Scope chat to a work">
          <input
            ref={filterInput}
            class="chat-scope-pop__filter"
            type="text"
            placeholder="Filter works by title or author…"
            value={filter()}
            onInput={(e) => setFilter(e.currentTarget.value)}
          />
          <Show when={contextAuthor()}>
            {(author) => (
              <label class="chat-scope-pop__toggle">
                <input
                  type="checkbox"
                  checked={withinAuthor()}
                  onChange={(e) => setWithinAuthor(e.currentTarget.checked)}
                />
                Within {author()}
              </label>
            )}
          </Show>
          <div class="chat-scope-pop__list">
            <For
              each={filtered()}
              fallback={<div class="chat-scope-pop__empty">No matching works</div>}
            >
              {(w) => (
                <button type="button" class="chat-scope-pop__row" onClick={() => pick(w)}>
                  <span class="chat-scope-pop__author">{w.author}</span>
                  <span class="chat-scope-pop__title">{w.display_title}</span>
                </button>
              )}
            </For>
          </div>
        </div>
      </Show>
    </div>
  );
}
