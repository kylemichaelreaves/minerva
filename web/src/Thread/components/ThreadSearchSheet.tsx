import { For, Show, createMemo, createSignal, type JSX } from "solid-js";
import type { Turn } from "~/utils/types";
import { MobileSheet } from "~/components/MobileSheet";

function turnText(msg: Turn): string {
  if (msg.role === "user") return msg.text;
  if (msg.streaming && msg.streamText) return msg.streamText;
  // MinervaTurn carries its rendered text as paragraphs once streaming
  // settles. Joining preserves the line breaks search would have hit on
  // streamText.
  return msg.paragraphs.join("\n\n");
}

function turnId(msg: Turn, index: number): string {
  return msg.role === "user" ? `user-${index}` : `minerva-${index}`;
}

export function ThreadSearchSheet(props: {
  open: boolean;
  messages: Turn[];
  onClose: () => void;
}) {
  const [query, setQuery] = createSignal("");

  const matches = createMemo(() => {
    const q = query().trim().toLowerCase();
    if (!q) return [];
    const out: { index: number; id: string; preview: string; role: string }[] = [];
    props.messages.forEach((msg, index) => {
      const text = turnText(msg);
      if (text.toLowerCase().includes(q)) {
        out.push({
          index,
          id: turnId(msg, index),
          preview: text,
          role: msg.role,
        });
      }
    });
    return out;
  });

  function highlight(text: string): JSX.Element {
    const q = query().trim();
    if (!q) return text;
    const lower = text.toLowerCase();
    const idx = lower.indexOf(q.toLowerCase());
    if (idx < 0) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark>{text.slice(idx, idx + q.length)}</mark>
        {text.slice(idx + q.length)}
      </>
    );
  }

  function scrollTo(id: string) {
    const el = document.querySelector(`[data-turn-id="${id}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    props.onClose();
  }

  return (
    <MobileSheet open={props.open} title="Search thread" onClose={props.onClose}>
      <input
        type="search"
        class="thread-search-input"
        placeholder="Search this conversation…"
        value={query()}
        onInput={(e) => setQuery(e.currentTarget.value)}
      />
      <p class="thread-search-count">
        {query().trim()
          ? `${matches().length} match${matches().length === 1 ? "" : "es"}`
          : "Type to search"}
      </p>
      <ul class="thread-search-results">
        <For each={matches()}>
          {(m) => (
            <li>
              <button type="button" class="thread-search-hit" onClick={() => scrollTo(m.id)}>
                <span class="thread-search-role">{m.role === "user" ? "You" : "Minerva"}</span>
                <span class="thread-search-preview">{highlight(m.preview.slice(0, 160))}</span>
              </button>
            </li>
          )}
        </For>
      </ul>
      <Show when={query().trim() && matches().length === 0}>
        <p class="thread-search-empty">No matches in this thread.</p>
      </Show>
    </MobileSheet>
  );
}
