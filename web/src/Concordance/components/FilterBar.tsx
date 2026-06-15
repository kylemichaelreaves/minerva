// F1 desktop header-bar filter row — Sort dropdown, POS dropdown,
// Frequency-range slider, and lemma search. Lives directly under the
// scope pill on the index page. The mobile filter sheet renders the
// same groups stacked.

import { For, Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { isConcSort, type ConcScope, type ConcSort } from "~/api/concordanceApi";
import { Select, type SelectOption } from "~/components/Select";

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

/** Pull-down dropdown — a lightweight click-to-toggle popover. We don't
 *  reach for the project's `Select` because the surface area is small
 *  enough to inline (no async loading, no grouping, no keyboard nav
 *  beyond what native focus already gives us). */
function Dropdown(props: {
  label: string;
  current: string;
  options: { value: string; label: string }[];
  onPick: (v: string) => void;
}) {
  const [open, setOpen] = createSignal(false);
  return (
    <span class="fbar-drop" classList={{ on: !!props.current }}>
      <span class="trigger" onClick={() => setOpen((o) => !o)}>
        {props.label}
        <span class="chev">▾</span>
      </span>
      <Show when={open()}>
        <span class="menu" onClick={() => setOpen(false)}>
          <For each={props.options}>
            {(o) => (
              <span
                class="opt"
                classList={{ cur: o.value === props.current }}
                onClick={() => {
                  props.onPick(o.value);
                  setOpen(false);
                }}
              >
                {o.label}
              </span>
            )}
          </For>
        </span>
      </Show>
    </span>
  );
}

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
 *  ``createEffect`` whenever the source accessors fire. Solid tracks
 *  the reads inside the effect; the DOM stays in sync.
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
  const loPct = () => Math.min(99, Math.max(0, ((lo() - 1) / (ceil() - 1)) * 100));
  const hiPct = () => Math.min(100, Math.max(1, ((hi() - 1) / (ceil() - 1)) * 100));

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
  createEffect(() => {
    if (loEl) {
      loEl.max = String(ceil());
      loEl.value = String(lo());
    }
    if (hiEl) {
      hiEl.max = String(ceil());
      hiEl.value = String(hi());
    }
  });

  return (
    <span class="fbar-range">
      <span class="ed">{lo().toLocaleString()}</span>
      <span class="track">
        <span
          class="fill"
          style={{ left: `${loPct()}%`, right: `${100 - hiPct()}%` }}
        />
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
  const [qLocal, setQLocal] = createSignal("");
  // Seeds the initial value on mount and re-syncs on external changes
  // (chip removal, back/forward, the other FilterBar instance
  // committing).
  createEffect(() => setQLocal(props.q ?? ""));
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

  const sortLabel = createMemo(() => {
    switch (props.sort) {
      case "alpha":
        return "A→Z";
      case "pos":
        return "POS";
      default:
        return "Frequency";
    }
  });
  const posLabel = createMemo(() => {
    if (!props.pos) return "default";
    return POS_OPTIONS.find((o) => o.value === props.pos)?.label ?? props.pos;
  });
  const langLabel = createMemo(
    () => LANG_OPTIONS.find((o) => o.value === props.lang)?.label ?? props.lang.toUpperCase(),
  );
  return (
    <div class="fbar">
      <div class="grp">
        <span class="lab">Language</span>
        <Dropdown
          label={langLabel()}
          current={props.lang}
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
                    <span class="x" onClick={() => props.onPickAuthor(a)}>
                      ×
                    </span>
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
                    <span class="x" onClick={() => props.onPickWork(w)}>
                      ×
                    </span>
                  </span>
                )}
              </For>
            </span>
          </Show>
        </div>
      </Show>

      <div class="grp">
        <span class="lab">Sort</span>
        <Dropdown
          label={sortLabel()}
          current={props.sort}
          options={[
            { value: "freq", label: "Frequency" },
            { value: "alpha", label: "A→Z" },
            { value: "pos", label: "POS" },
          ]}
          onPick={(v) => {
            if (isConcSort(v)) props.onSetSort(v);
          }}
        />
      </div>

      <div class="grp">
        <span class="lab">POS</span>
        <Dropdown
          label={posLabel()}
          current={props.pos ?? ""}
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
