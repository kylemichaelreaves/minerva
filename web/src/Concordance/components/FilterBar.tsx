// F1 desktop header-bar filter row — Sort dropdown, POS dropdown,
// Frequency-range slider, and lemma search. Lives directly under the
// scope pill on the index page. The mobile filter sheet renders the
// same groups stacked.

import { For, Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { isConcSort, type ConcScope, type ConcSort } from "~/api/concordanceApi";
import { Select, type SelectOption } from "~/components/primitives/Select";

/** Debounce window for the lemma search box. Each commit patches the
 *  URL and refetches the lemma index, so per-keystroke commits were a
 *  refetch storm; 250 ms is short enough to feel live. Enter/blur
 *  flush immediately. */
export const SEARCH_DEBOUNCE_MS = 250;

/** UD POS tags that show up on the leaderboard. The backend default
 *  whitelist is content words (NOUN/VERB/ADJ/PROPN); the dropdown lets
 *  the user narrow further or override the default to surface function
 *  words via the ``all`` value (passed to the backend as ``pos_in=all``). */
/** Concordance languages the leaderboard can render. The corpus also
 *  carries Hebrew and Arabic, but those need an RTL + non-segmental
 *  letter rail we don't build yet, so they're deliberately omitted from
 *  the switcher (the backend would happily serve them via ?lang=heb). */
export const LANG_OPTIONS: { value: string; label: string }[] = [
  { value: "deu", label: "German" },
  { value: "grc", label: "Greek" },
  { value: "lat", label: "Latin" },
  { value: "eng", label: "English" },
  { value: "fra", label: "French" },
];

export const POS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "default" },
  { value: "NOUN", label: "noun" },
  { value: "VERB", label: "verb" },
  { value: "ADJ", label: "adj" },
  { value: "PROPN", label: "propn" },
  { value: "ADV", label: "adv" },
  { value: "ADP", label: "prep" },
  { value: "DET", label: "det" },
  { value: "PRON", label: "pron" },
  { value: "all", label: "all (incl. function words)" },
];

export interface FilterBarProps {
  /** Active concordance language (ISO-639-3). Drives the Language
   *  dropdown's current value. */
  lang: string;
  sort: ConcSort;
  pos?: string;
  freqMin?: number;
  freqMax?: number;
  /** Largest observed frequency in the current scope — drives the
   *  slider's upper bound so the knob's position is meaningful. */
  freqCeil: number;
  q?: string;
  /** Scope narrowing. The Author picker appears for author/work scope;
   *  the Work picker appears for work scope (with the Author picker
   *  acting as an optional filter on the work list). Options come from
   *  the page (built from /api/works for the active language). */
  scope: ConcScope;
  scopeAuthors?: string[];
  scopeWorks?: string[];
  authorOptions: SelectOption[];
  workOptions: SelectOption[];
  /** Toggle an author in the selection — appends if absent, removes if
   *  already selected. The add-Select calls this on pick. */
  onPickAuthor: (author: string | undefined) => void;
  /** Toggle a work in the scope=work selection — appends if absent,
   *  removes if already selected. The add-Select calls this on pick. */
  onPickWork: (work: string | undefined) => void;
  onSetLang: (v: string) => void;
  onSetSort: (v: ConcSort) => void;
  onSetPos: (v: string | undefined) => void;
  onSetFreqRange: (min: number | undefined, max: number | undefined) => void;
  onSetQ: (v: string | undefined) => void;
}

/** The Language / Sort / POS controls, on the shared `Select` (#364).
 *
 *  This replaced a local `Dropdown` that could not be operated from the
 *  keyboard at all: a `<span>` trigger with no `tabindex`, `<span>` options
 *  with no roles, and Escape as the only key handled — which could only ever
 *  fire for a popover already opened with a mouse. Its comment justified
 *  skipping `Select` on the grounds that it needed "no keyboard nav beyond
 *  what native focus already gives us"; that is true of a `<button>` and was
 *  not true of the markup written. Two `Select`s already sat in this same bar
 *  with arrows, Home/End, Enter, Space, type-ahead and
 *  `aria-activedescendant`, so the bar was split down the middle.
 *
 *  `clearable` is off: each of the three always has a value, and the
 *  placeholder is not a state the reader should be able to land back on.
 */
function FbarSelect(props: {
  ariaLabel: string;
  value: string;
  placeholder?: string;
  options: SelectOption[];
  onPick: (v: string) => void;
}) {
  return (
    <span class="fbar-drop">
      <Select
        options={props.options}
        value={props.value || undefined}
        placeholder={props.placeholder}
        ariaLabel={props.ariaLabel}
        clearable={false}
        onChange={props.onPick}
      />
    </span>
  );
}

const SORT_OPTIONS: SelectOption[] = [
  { value: "freq", label: "Frequency" },
  { value: "alpha", label: "A→Z" },
  { value: "pos", label: "POS" },
];

/** Two-thumb range slider over [0, ceil]. Used both for the F1 desktop
 *  filter bar and for the mobile filter sheet's "Frequency" row.
 *
 *  Implementation note: `<input type="range">` is one of Solid's
 *  awkward primitives — Solid's standard JSX binding for `value` and
 *  `max` sets the HTML *attribute* once but doesn't reliably push
 *  subsequent signal changes onto the DOM `.value` / `.max`
 *  properties. The visible thumb position is driven by the DOM
 *  property, so a bare ``value={lo()}`` desynchronises the second
 *  time the signal updates (e.g. after a Reset).
 *
 *  Fix: hold a ref per thumb and write `.value` / `.max` from a
 *  ``createEffect`` whenever the source accessors fire. The effect's
 *  compute tracks the reads and its apply writes the DOM, so the DOM
 *  stays in sync.
 */
export function FreqRange(props: {
  min: number | undefined;
  max: number | undefined;
  ceil: number;
  onChange: (min: number | undefined, max: number | undefined) => void;
}) {
  const ceil = () => Math.max(1, props.ceil);
  // Live drag state. Each `onChange` commit patches the URL and
  // refetches the lemma index, so committing per `input` event made a
  // drag fire one refetch per pixel. Instead, `input` only updates the
  // local drag value (fill bar + edge labels track the knob live) and
  // the commit happens on `change` — which range inputs fire on
  // release. null = not dragging, follow the URL-bound props.
  const [loDrag, setLoDrag] = createSignal<number | null>(null);
  const [hiDrag, setHiDrag] = createSignal<number | null>(null);
  const lo = () => loDrag() ?? props.min ?? 1;
  const hi = () => hiDrag() ?? props.max ?? ceil();
  const loPct = () => {
    const c = ceil();
    if (c <= 1) return 0;
    return Math.min(99, Math.max(0, ((lo() - 1) / (c - 1)) * 100));
  };
  const hiPct = () => {
    const c = ceil();
    if (c <= 1) return 100;
    return Math.min(100, Math.max(1, ((hi() - 1) / (c - 1)) * 100));
  };

  // Don't let the knobs cross — clamp to the opposite bound so the
  // slider can't invert (the backend tolerates it, but the UX is
  // confusing).
  const clampLo = (v: number) => Math.min(v, hi());
  const clampHi = (v: number) => Math.max(v, lo());

  const commitLo = (raw: number) => {
    const v = clampLo(raw);
    props.onChange(v <= 1 ? undefined : v, props.max);
    setLoDrag(null);
  };
  const commitHi = (raw: number) => {
    const v = clampHi(raw);
    props.onChange(props.min, v >= ceil() ? undefined : v);
    setHiDrag(null);
  };

  let loEl: HTMLInputElement | undefined;
  let hiEl: HTMLInputElement | undefined;
  createEffect(
    () => ({ max: String(ceil()), lo: String(lo()), hi: String(hi()) }),
    (v) => {
      if (loEl) {
        loEl.max = v.max;
        loEl.value = v.lo;
      }
      if (hiEl) {
        hiEl.max = v.max;
        hiEl.value = v.hi;
      }
    },
  );

  return (
    <span class="fbar-range">
      <span class="ed">{lo().toLocaleString()}</span>
      <span class="track">
        <span class="fill" style={{ left: `${loPct()}%`, right: `${100 - hiPct()}%` }} />
        <input
          ref={loEl}
          class="thumb"
          type="range"
          min={1}
          onInput={(e) => setLoDrag(clampLo(Number(e.currentTarget.value)))}
          onChange={(e) => commitLo(Number(e.currentTarget.value))}
        />
        <input
          ref={hiEl}
          class="thumb"
          type="range"
          min={1}
          onInput={(e) => setHiDrag(clampHi(Number(e.currentTarget.value)))}
          onChange={(e) => commitHi(Number(e.currentTarget.value))}
        />
      </span>
      <span class="ed">{hi().toLocaleString()}</span>
    </span>
  );
}

export function FilterBar(props: FilterBarProps) {
  // Local live value for the search box. Committing (URL patch +
  // lemma-index refetch) is debounced; the input itself stays
  // responsive per keystroke. Enter/blur flush immediately.
  // A writable derived signal: it seeds from `props.q` and re-derives on
  // external changes (chip removal, back/forward, the other FilterBar
  // instance committing), while keystrokes write over it locally.
  const [qLocal, setQLocal] = createSignal(() => props.q ?? "");
  let qTimer: ReturnType<typeof setTimeout> | undefined;
  const cancelQTimer = () => {
    if (qTimer !== undefined) {
      clearTimeout(qTimer);
      qTimer = undefined;
    }
  };
  onCleanup(cancelQTimer);
  const commitQ = () => {
    cancelQTimer();
    const next = qLocal().trim() || undefined;
    if (next !== props.q) props.onSetQ(next);
  };
  const onQInput = (value: string) => {
    setQLocal(value);
    cancelQTimer();
    qTimer = setTimeout(commitQ, SEARCH_DEBOUNCE_MS);
  };

  // Add-Select options exclude works already in scope so a work can't
  // be picked twice. Selection set is keyed off scopeWorks.
  const addWorkOptions = createMemo<SelectOption[]>(() => {
    const chosen = new Set(props.scopeWorks ?? []);
    return props.workOptions.filter((o) => !chosen.has(o.value));
  });

  // Same for authors — exclude already-selected authors so each can be
  // picked once. Selection set is keyed off scopeAuthors.
  const addAuthorOptions = createMemo<SelectOption[]>(() => {
    const chosen = new Set(props.scopeAuthors ?? []);
    return props.authorOptions.filter((o) => !chosen.has(o.value));
  });

  // The three label memos that used to live here are gone with the local
  // `Dropdown` (#364): `Select` derives the trigger's text from the option
  // matching `value`, so restating each mapping by hand was the duplication
  // that let POS and Sort drift from their own option lists.
  return (
    <div class="fbar">
      <div class="grp">
        <span class="lab">Language</span>
        <FbarSelect
          ariaLabel="Language"
          value={props.lang}
          options={LANG_OPTIONS}
          onPick={(v) => props.onSetLang(v)}
        />
      </div>

      <Show when={props.scope !== "corpus"}>
        <div class="grp">
          <span class="lab">Author</span>
          {/* Add-an-author picker: like the Work picker, the Select only
              ADDS — never bound to a value (always shows the
              placeholder), and picking an author appends it to
              scopeAuthors via onPickAuthor. Already-selected authors are
              excluded from the options. The chosen authors render as
              removable chips beside it. */}
          <Select
            options={addAuthorOptions()}
            value={undefined}
            onChange={(v) => {
              if (v) props.onPickAuthor(v);
            }}
            placeholder={props.scope === "work" ? "any author" : "add an author…"}
            clearable={false}
            filterable
            ariaLabel="Add an author to the concordance scope"
          />
          <Show when={(props.scopeAuthors?.length ?? 0) > 0}>
            <span class="fbar-work-chips">
              <For each={props.scopeAuthors}>
                {(a) => (
                  <span class="fbar-work-chip">
                    <span class="v" title={a}>
                      {a}
                    </span>
                    <button
                      type="button"
                      class="x"
                      aria-label={`Remove ${a} from the scope`}
                      onClick={() => props.onPickAuthor(a)}
                    >
                      ×
                    </button>
                  </span>
                )}
              </For>
            </span>
          </Show>
        </div>
      </Show>
      <Show when={props.scope === "work"}>
        <div class="grp">
          <span class="lab">Work</span>
          {/* Add-a-work picker: the Select only ADDS — it's never bound
              to a value (always shows the placeholder), and picking a
              work appends it to scopeWorks via onPickWork. Already-
              selected works are excluded from the options so they can't
              be re-picked. The chosen works render as removable chips
              beside it. */}
          <Select
            options={addWorkOptions()}
            value={undefined}
            onChange={(v) => {
              if (v) props.onPickWork(v);
            }}
            placeholder="add a work…"
            clearable={false}
            filterable
            ariaLabel="Add a work to the concordance scope"
          />
          <Show when={(props.scopeWorks?.length ?? 0) > 0}>
            <span class="fbar-work-chips">
              <For each={props.scopeWorks}>
                {(w) => (
                  <span class="fbar-work-chip">
                    <span class="v" title={w}>
                      {w}
                    </span>
                    <button
                      type="button"
                      class="x"
                      aria-label={`Remove ${w} from the scope`}
                      onClick={() => props.onPickWork(w)}
                    >
                      ×
                    </button>
                  </span>
                )}
              </For>
            </span>
          </Show>
        </div>
      </Show>

      <div class="grp">
        <span class="lab">Sort</span>
        <FbarSelect
          ariaLabel="Sort"
          value={props.sort}
          options={SORT_OPTIONS}
          onPick={(v) => {
            if (isConcSort(v)) props.onSetSort(v);
          }}
        />
      </div>

      <div class="grp">
        <span class="lab">POS</span>
        <FbarSelect
          ariaLabel="POS"
          value={props.pos ?? ""}
          placeholder="default"
          options={POS_OPTIONS}
          onPick={(v) => props.onSetPos(v || undefined)}
        />
      </div>

      <div class="grp">
        <span class="lab">Frequency ≥</span>
        <FreqRange
          min={props.freqMin}
          max={props.freqMax}
          ceil={props.freqCeil}
          onChange={(lo, hi) => props.onSetFreqRange(lo, hi)}
        />
      </div>

      <span class="fbar-spacer" />

      <span class="fbar-search">
        <span class="ico">⌕</span>
        <input
          type="text"
          placeholder="Find lemma — type any word…"
          value={qLocal()}
          onInput={(e) => onQInput(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitQ();
          }}
          onBlur={commitQ}
        />
      </span>
    </div>
  );
}
