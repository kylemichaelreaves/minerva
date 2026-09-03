// F1 — Lemma frequency index. Orchestrator composes useConcordanceIndex;
// presentational pieces live in ./components.

import { For, Show, createEffect, createMemo, createSignal } from "solid-js";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import { useInfiniteScrollSentinel } from "~/hooks/useInfiniteScrollSentinel";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";
import {
  fetchLemmaIndex,
  type ConcScope,
  type ConcSort,
  type LemmaIndexRow,
} from "~/api/concordanceApi";
import { listWorks } from "~/api/readerApi";
import { ActiveFilterStrip } from "~/Concordance/components/ActiveFilterStrip";
import { ConcEmpty, LemmaCacheEmpty } from "~/Concordance/components/ConcEmpty";
import { FilterBar } from "~/Concordance/components/FilterBar";
import type { SelectOption } from "~/components/primitives/Select";
import { LbRow } from "~/Concordance/components/LbRow";
import { LoadingSkeleton } from "~/Concordance/components/LoadingSkeleton";
import { ScopePill } from "~/Concordance/components/ScopePill";
import { alphabetFor, foldInitial } from "~/Concordance/constants";
import { routeHash } from "~/routing";
import { useMobile } from "~/hooks/useMobile";
import { MobileSheet } from "~/components/shell/MobileSheet";
import "~/Concordance/concordance.css";

/** Allow-clear navigation patch — explicit `undefined` clears that field
 *  from the URL. ConcordanceRoute uses `mergeRoutePatchAllowClear` so a
 *  chip's onRemove can set `pos: undefined` and we drop the param. */
export interface IndexNavPatch {
  lang?: string;
  scope?: ConcScope;
  scopeAuthors?: string[];
  scopeWorks?: string[];
  letter?: string;
  sort?: ConcSort;
  pos?: string;
  freqMin?: number;
  freqMax?: number;
  q?: string;
}

export interface IndexPageProps {
  lang?: string;
  scope?: ConcScope;
  scopeAuthors?: string[];
  scopeWorks?: string[];
  letter?: string;
  sort?: ConcSort;
  pos?: string;
  freqMin?: number;
  freqMax?: number;
  q?: string;
  onNavigate: (patch: IndexNavPatch) => void;
  onOpenLemma: (
    lemma: string,
    scope?: ConcScope,
    scopeAuthors?: string[],
    scopeWorks?: string[],
  ) => void;
}

export function ConcordanceIndexPage(props: IndexPageProps) {
  const lang = () => props.lang ?? "deu";
  const scope = (): ConcScope => props.scope ?? "corpus";
  const sort = (): ConcSort => props.sort ?? "freq";
  const letter = () => props.letter;

  const {
    data, loading, error, setRetryKey, lettersWithHits, letterCounts, grouped,
    allRows, hasMore, appending, appendError, setSentinelEl,
  } = useConcordanceIndex({
    lang,
    scope,
    sort,
    letter,
    scopeAuthors: () => props.scopeAuthors,
    scopeWorks: () => props.scopeWorks,
    pos: () => props.pos,
    freqMin: () => props.freqMin,
    freqMax: () => props.freqMax,
    q: () => props.q,
  });

  const isMobile = useMobile();
  const [sheetOpen, setSheetOpen] = createSignal(false);

  /** Author/Work scope needs a value before the index can fetch —
   *  scope=author with no author (or scope=work with no work) is a
   *  backend 400. The pickers below fill these in. */
  const scopeIncomplete = createMemo(
    () =>
      (scope() === "author" && !props.scopeAuthors?.length) ||
      (scope() === "work" && !props.scopeWorks?.length),
  );

  /** Works manifest for the scope pickers. One fetch; the reader's
   *  /api/works list carries (author, work, lang) in chronological
   *  author order, which is exactly the order we want the menus in.
   *  useAbortableFetch (not a raw createResource) so the request is
   *  aborted on unmount and its failure is captured in `worksData.error`
   *  rather than silently leaving the pickers empty (issue #65). */
  const worksData = useAbortableFetch(
    () => null,
    (_args, signal) => listWorks(signal),
  );
  const worksList = worksData.data;
  const langWorks = createMemo(() => (worksList() ?? []).filter((w) => w.lang === lang()));
  const authorOptions = createMemo<SelectOption[]>(() => {
    const seen = new Set<string>();
    const out: SelectOption[] = [];
    for (const w of langWorks()) {
      if (!seen.has(w.author)) {
        seen.add(w.author);
        out.push({ value: w.author, label: w.author });
      }
    }
    return out;
  });
  const workOptions = createMemo<SelectOption[]>(() => {
    const authors = props.scopeAuthors ?? [];
    const seen = new Set<string>();
    const out: SelectOption[] = [];
    for (const w of langWorks()) {
      // When one or more authors are selected, narrow the work menu to
      // works by ANY of them; otherwise show every work.
      if (authors.length && !authors.includes(w.author)) continue;
      if (seen.has(w.work)) continue;
      seen.add(w.work);
      out.push({ value: w.work, label: w.work, sublabel: w.author });
    }
    return out;
  });

  /** Toggle an author — append if absent, remove if present. Dual role:
   *  in scope=work the author picker only NARROWS the work menu (data
   *  scope stays work-level, so we never set scope here); otherwise it
   *  drives scope=author. Removing the last author in author-scope falls
   *  back to corpus (mirrors how removing the last work behaves). */
  const pickAuthor = (author: string | undefined) => {
    if (!author) return;
    const cur = props.scopeAuthors ?? [];
    const next = cur.includes(author) ? cur.filter((a) => a !== author) : [...cur, author];
    if (scope() === "work") {
      // Narrow the work menu only; resetting works since the author
      // filter changed which works are valid. Data scope stays work.
      props.onNavigate({ scopeAuthors: next, scopeWorks: undefined });
      return;
    }
    if (next.length === 0) {
      props.onNavigate({ scope: "corpus", scopeAuthors: undefined, scopeWorks: undefined });
      return;
    }
    props.onNavigate({ scope: "author", scopeAuthors: next, scopeWorks: undefined });
  };
  /** Toggle a work in the scope=work selection — append if absent,
   *  remove if already present. Always lands in scope=work; when the
   *  last work is removed the page falls back to the "Choose a work"
   *  prompt (scopeIncomplete), matching the empty-scope behavior. */
  const pickWork = (work: string | undefined) => {
    if (!work) return;
    const cur = props.scopeWorks ?? [];
    const next = cur.includes(work) ? cur.filter((w) => w !== work) : [...cur, work];
    props.onNavigate({ scope: "work", scopeWorks: next });
  };

  /** Slider ceiling — the highest count we've seen so far for this
   *  scope. Monotonic: never shrinks during a filter session, so the
   *  slider scale doesn't jump when the user drags freq_max down and
   *  the top row's count drops along with it. Resets when the user
   *  changes scope (different scope = different unfiltered max). */
  const [freqCeil, setFreqCeil] = createSignal(10000);
  let lastScopeKey = "";
  createEffect(() => {
    const scopeKey = `${lang()}|${scope()}|${(props.scopeAuthors ?? []).join("\t")}|${(props.scopeWorks ?? []).join("\t")}`;
    if (scopeKey !== lastScopeKey) {
      lastScopeKey = scopeKey;
      setFreqCeil(10000);
    }
    const top = sort() === "freq" ? data()?.rows[0]?.count : undefined;
    if (top && top > freqCeil()) {
      setFreqCeil(top);
    }
  });

  /** Chips shown in the active-filter strip. Each carries its own
   *  remove patch; the strip never needs to know what kind of filter
   *  the chip represents. */
  const activeChips = createMemo(() => {
    const chips: { k: string; v: string; onRemove: () => void }[] = [];
    // Scope — author and work — is deliberately NOT here (#387).
    //
    // It used to be, and `resetAll` below does not clear it: narrowing scope
    // is a directed navigation the reader performed, and dropping it on a
    // filter reset would discard that with no undo. That policy is fine; what
    // was not fine is that the strip counted scope in "Active · N", gave it a
    // chip, and offered "reset all" over the lot. Clicking reset then cleared
    // the filters and left the chip and the control exactly as they were, so
    // the button read as broken. Measured: `?scope=author&author=Hegel&pos=NOUN&q=geist`
    // reset to `?scope=author&author=Hegel` with the strip unchanged.
    //
    // The set shown and the set cleared are now the same set. Scope keeps its
    // own affordances — the `ScopePill` breadcrumb above, and the filter bar's
    // own author/work chips, which already rendered this same value twice.
    if (props.letter) {
      chips.push({
        k: "letter",
        v: props.letter,
        onRemove: () => props.onNavigate({ letter: undefined }),
      });
    }
    if (props.pos) {
      const label = props.pos === "all" ? "all" : props.pos.toLowerCase();
      chips.push({
        k: "POS",
        v: label,
        onRemove: () => props.onNavigate({ pos: undefined }),
      });
    }
    if (props.freqMin !== undefined || props.freqMax !== undefined) {
      const lo = props.freqMin?.toLocaleString() ?? "1";
      const hi = props.freqMax?.toLocaleString() ?? "∞";
      chips.push({
        k: "freq",
        v: `${lo}–${hi}`,
        onRemove: () => props.onNavigate({ freqMin: undefined, freqMax: undefined }),
      });
    }
    if (props.q) {
      chips.push({
        k: "q",
        v: `"${props.q}"`,
        onRemove: () => props.onNavigate({ q: undefined }),
      });
    }
    return chips;
  });

  const resetAll = () =>
    props.onNavigate({
      letter: undefined,
      pos: undefined,
      freqMin: undefined,
      freqMax: undefined,
      q: undefined,
    });

  /** FilterBar closure — same pattern as Refs/index.tsx's filtersBar.
   *  Invoked once inline on desktop and once inside the mobile sheet,
   *  so the ~18 props are wired in exactly one place. */
  const filterBar = () => (
    <FilterBar
      lang={lang()}
      sort={sort()}
      pos={props.pos}
      freqMin={props.freqMin}
      freqMax={props.freqMax}
      freqCeil={freqCeil()}
      q={props.q}
      scope={scope()}
      scopeAuthors={props.scopeAuthors}
      scopeWorks={props.scopeWorks}
      authorOptions={authorOptions()}
      workOptions={workOptions()}
      onPickAuthor={pickAuthor}
      onPickWork={pickWork}
      onSetLang={(v) =>
        props.onNavigate({
          lang: v,
          letter: undefined,
          scopeAuthors: undefined,
          scopeWorks: undefined,
        })
      }
      onSetSort={(v) => props.onNavigate({ sort: v })}
      onSetPos={(v) => props.onNavigate({ pos: v })}
      onSetFreqRange={(lo, hi) => props.onNavigate({ freqMin: lo, freqMax: hi })}
      onSetQ={(v) => props.onNavigate({ q: v })}
    />
  );

  return (
    <div class="conc-stage conc-index">
      <div class="conc-head">
        <div class="conc-head-main">
          <h1 class="conc-h1">Concordance</h1>
          <div
            class="conc-sub"
            style={{ display: "flex", gap: "12px", "align-items": "center", "flex-wrap": "wrap" }}
          >
            <ScopePill
              steps={[
                { label: "Work", scope: "work", cur: scope() === "work" },
                { label: "Author", scope: "author", cur: scope() === "author" },
                {
                  label: scope() === "corpus" ? (data()?.scope_label ?? "Corpus") : "Corpus",
                  scope: "corpus",
                  cur: scope() === "corpus",
                },
              ]}
              count={scopeIncomplete() ? undefined : data()?.total_occurrences}
              onPick={(s) =>
                props.onNavigate({ scope: s, scopeAuthors: undefined, scopeWorks: undefined })
              }
            />
            {/* Both numbers, always (#377). `total_lemmas` alone sat in the
                position a reader takes for "how many rows are in this list",
                and is not that: it is computed without the frequency range,
                whose default `min_count` is 2, so the DEFAULT view already
                diverged — 28,963 printed above 11,413 rows, measured on the
                live index. The `ActiveFilterStrip` had gained a count for the
                narrowed set, but only renders when a filter chip is active, so
                on the default view the scope total was the only number on
                screen. Naming it "in scope" is the other half: it reads as the
                denominator it is rather than as the list's size. */}
            <span>
              · <b>Showing {allRows().length.toLocaleString()}</b> of{" "}
              <b>{data()?.total_lemmas.toLocaleString() ?? "—"}</b> lemmas in scope ·{" "}
              {lang().toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Desktop: header-bar filter row inline. Mobile: same controls
          rendered inside the bottom sheet (see <MobileSheet> below). */}
      <Show when={!isMobile()}>{filterBar()}</Show>

      <div class="az-rail az-rail-grid">
        <For each={alphabetFor(lang())}>
          {(L) => {
            const klass = () =>
              "l " + (L === letter() ? "cur" : lettersWithHits().has(L) ? "has" : "");
            // The dot says "something here"; the count says how much, which is
            // what makes the rail worth reading before clicking (#376).
            const title = () => {
              const n = letterCounts()[L];
              return n === undefined
                ? `${L} — nothing in scope`
                : `${L} — ${n.toLocaleString()} lemma${n === 1 ? "" : "s"}`;
            };
            return (
              <span
                class={klass()}
                title={title()}
                onClick={() => props.onNavigate({ letter: L === letter() ? undefined : L })}
              >
                {L}
              </span>
            );
          }}
        </For>
        <Show when={letter()}>
          <span class="l az-all" onClick={() => props.onNavigate({ letter: undefined })}>
            all
          </span>
        </Show>
      </div>

      <ActiveFilterStrip
        items={activeChips()}
        // Show the actual row count — this is what changes as the user narrows,
        // and as further pages append. The header retains the unfiltered scope
        // total ("135,047 lemmas") for orientation; the strip mirrors the result
        // set the user is looking at right now.
        //
        // This used to read `data()?.rows.length` and say the 200-row fetch cap
        // "is plenty for any narrowed filter". It is not: the narrowest
        // combination the UI offers short of a text query — one author plus one
        // letter — measures 1,318 lemmas for Hegel + B, and the corpus view is
        // 135,047. The list pages now (#371), so this has to follow it.
        count={allRows().length}
        countLabel="lemmas shown"
        onReset={resetAll}
      />

      {/* Mobile: floating Filters button — opens the bottom sheet that
          re-renders the same controls. The badge counts only the
          non-letter chips because the A-Z strip lives outside the sheet. */}
      <Show when={isMobile()}>
        <button type="button" class="conc-fab" onClick={() => setSheetOpen(true)}>
          ≡ Filters
          <Show when={activeChips().length > 0}>
            <span class="badge">{activeChips().length}</span>
          </Show>
        </button>
        <MobileSheet open={sheetOpen()} title="Filters" onClose={() => setSheetOpen(false)}>
          <div class="conc-mob-sheet">
            {filterBar()}
            <div class="conc-mob-sheet-foot">
              <span
                class="reset"
                onClick={() => {
                  resetAll();
                  setSheetOpen(false);
                }}
              >
                ↺ Reset all
              </span>
              <span class="done" onClick={() => setSheetOpen(false)}>
                <b>{data()?.total_lemmas.toLocaleString() ?? "—"}</b> lemmas →
              </span>
            </div>
          </div>
        </MobileSheet>
      </Show>

      <Show
        when={!scopeIncomplete()}
        fallback={
          // The pickers this prompt points at are filled from /api/works.
          // When that call failed they are empty, and telling the user to
          // pick something from them is a dead end — so say what happened
          // instead. The hook had the reason all along; nothing read it.
          <Show
            when={worksData.error() === null}
            fallback={
              <ConcEmpty icon="!" title="Couldn't load the works list">
                <div>{worksData.error()}</div>
                <div>
                  The author and work pickers stay empty until it loads, so the
                  concordance cannot be narrowed. Corpus scope still works.
                </div>
              </ConcEmpty>
            }
          >
            <ConcEmpty
              icon="◎"
              title={scope() === "work" ? "Choose a work" : "Choose an author"}
            >
              <div>
                Pick {scope() === "work" ? "a work" : "an author"} in the filter bar above to
                narrow the {lang().toUpperCase()} concordance
                {scope() === "work" ? " to a single work" : ""}.
              </div>
            </ConcEmpty>
          </Show>
        }
      >
      <Show
        when={!error()}
        fallback={
          <Show
            when={(error() ?? "").toLowerCase().includes("lemma cache")}
            fallback={
              <ConcEmpty icon="!" title="Couldn't load the lemma index">
                <div>{error()}</div>
                <div style={{ "margin-top": "10px" }}>
                  <span
                    style={{ color: "var(--accent)", cursor: "pointer" }}
                    onClick={() => setRetryKey((k) => k + 1)}
                  >
                    retry
                  </span>
                </div>
              </ConcEmpty>
            }
          >
            <LemmaCacheEmpty
              lang={lang()}
              title="No lemma cache"
              body={
                <>
                  spaCy hasn't lemmatised the {lang().toUpperCase()} edition yet — the concordance
                  needs a populated lemma cache to operate.
                </>
              }
              footer={
                <>
                  Runs once per edition. Re-fetch when complete:{" "}
                  <a onClick={() => setRetryKey((k) => k + 1)}>retry</a>
                </>
              }
            />
          </Show>
        }
      >
        <Show
          when={data() && (data()!.rows.length > 0 || !loading())}
          fallback={<LoadingSkeleton />}
        >
          <Show
            when={data()!.rows.length > 0}
            fallback={
              <Show
                when={
                  data()!.total_lemmas === 0 &&
                  data()!.total_occurrences === 0 &&
                  !letter() &&
                  scope() === "corpus"
                }
                fallback={
                  <ConcEmpty icon="∅" title="No lemmas in this scope">
                    <div>Try a different letter or change the scope.</div>
                  </ConcEmpty>
                }
              >
                <LemmaCacheEmpty
                  lang={lang()}
                  title={`No lemma cache for ${lang().toUpperCase()}`}
                  body={
                    <>
                      spaCy hasn't lemmatised this language yet. Run the lemmatizer once per edition
                      to populate the cache.
                    </>
                  }
                  footer={
                    <>
                      Re-fetch when complete: <a onClick={() => setRetryKey((k) => k + 1)}>retry</a>
                    </>
                  }
                />
              </Show>
            }
          >
            <div class="leaderboard">
              <For each={grouped()}>
                {(g) => (
                  <>
                    <Show when={g.letter}>
                      <div class="lb-letter">{g.letter}</div>
                    </Show>
                    <For each={g.rows}>
                      {(row) => (
                        <LbRow
                          row={row}
                          // The same destination the click handler navigates
                          // to, as a URL (#375). `routeHash` is pure, and the
                          // router already listens for `hashchange` precisely
                          // so in-page anchors work — so this is a real link,
                          // not a decorative one.
                          href={routeHash({
                            kind: "concordance-lemma",
                            lemma: row.lemma,
                            lang: lang(),
                            scope: scope(),
                            scopeAuthors: props.scopeAuthors,
                            scopeWorks: props.scopeWorks,
                          })}
                          onOpen={() =>
                            props.onOpenLemma(
                              row.lemma,
                              scope(),
                              props.scopeAuthors,
                              props.scopeWorks,
                            )
                          }
                        />
                      )}
                    </For>
                  </>
                )}
              </For>

              {/* Paging sentinel (#371). Mirrors `Refs/index.tsx` — the hook
                  stores the element in a signal so a sentinel that mounts later
                  still gets observed, and pre-fetches 400px early. */}
              <Show when={hasMore() && !loading()}>
                <div class="lb-sentinel" ref={setSentinelEl}>
                  <Show when={appending()}>
                    <span class="lb-sentinel-note">loading more lemmas…</span>
                  </Show>
                </div>
              </Show>
              <Show when={appendError()}>
                <div class="lb-sentinel-error">
                  Could not load more lemmas: {appendError()}
                </div>
              </Show>
            </div>
          </Show>
        </Show>
      </Show>
      </Show>
    </div>
  );
}

interface UseConcordanceIndexArgs {
  lang: () => string;
  scope: () => ConcScope;
  sort: () => ConcSort;
  letter: () => string | undefined;
  scopeAuthors: () => string[] | undefined;
  scopeWorks: () => string[] | undefined;
  pos: () => string | undefined;
  freqMin: () => number | undefined;
  freqMax: () => number | undefined;
  q: () => string | undefined;
}

/** Rows per request. The first page keeps the historic 200 so nothing about the
 *  initial render changes; appended pages use the same size. */
const PAGE_SIZE = 200;

export function useConcordanceIndex(args: UseConcordanceIndexArgs) {
  const [retryKey, setRetryKey] = createSignal(0);

  // `resetOnChange` keeps the behaviour the raw `createResource` had: its
  // `data()` read `undefined` while a new source was in flight, so the
  // skeleton showed on every filter change. What changes is that the
  // superseded request is now actually cancelled — a fast typist in the
  // search box used to leave one uncancelled 200-row index query per
  // keystroke running against the server (#65).
  /** Don't fetch an incomplete scope — scope=author without an author (or
   *  scope=work without a work) is a backend 400. The page renders a picker
   *  prompt instead; a null args object skips the request. */
  const pageArgs = () => {
    if (args.scope() === "author" && !args.scopeAuthors()?.length) return null;
    if (args.scope() === "work" && !args.scopeWorks()?.length) return null;
    return {
      lang: args.lang(),
      scope: args.scope(),
      authors: args.scopeAuthors(),
      works: args.scopeWorks(),
      letter: args.letter(),
      sort: args.sort(),
      pos: args.pos(),
      freqMin: args.freqMin(),
      freqMax: args.freqMax(),
      q: args.q(),
      _retry: retryKey(),
    };
  };

  /** The request for one page. Shared by the first page and by every appended
   *  one, so a filter can never apply to one and not the other. */
  const indexArgs = (p: NonNullable<ReturnType<typeof pageArgs>>, offset: number) => ({
    lang: p.lang,
    scope: p.scope,
    authors: p.authors,
    works: p.works,
    letter: p.letter,
    sort: p.sort,
    pos_in: p.pos,
    min_count: p.freqMin,
    max_count: p.freqMax,
    q: p.q,
    limit: PAGE_SIZE,
    offset,
  });

  const { data, loading, error } = useAbortableFetch(
    pageArgs,
    async (p, signal) =>
      p === null ? null : fetchLemmaIndex(indexArgs(p, 0), signal),
    { resetOnChange: true },
  );

  // ── Paging (#371) ─────────────────────────────────────────────────
  // The cursor is the server's `next_offset`, NOT `rows.length < total_lemmas`.
  // `total_lemmas` is not a row count: it is computed without the frequency
  // range applied, and on one branch counts DISTINCT lemma while rows are per
  // (lemma, pos). A length-vs-total test would keep asking for pages that come
  // back empty. `usePaginatedAppend.hasMore` is deliberately unused for that
  // reason — this is the one caller that cannot use it.
  const pagination = usePaginatedAppend<LemmaIndexRow>(() => data());
  const [cursor, setCursor] = createSignal<number | null>(null);
  // Mirrors the hook's own reset: a new first page replaces the cursor.
  createEffect(() => { setCursor(data()?.next_offset ?? null); });

  const firstPage = (): LemmaIndexRow[] => data()?.rows ?? [];
  const allRows = (): LemmaIndexRow[] => pagination.rows(firstPage());
  const hasMore = (): boolean => cursor() !== null;

  const fetchPage = (offset: number, signal: AbortSignal) => {
    const p = pageArgs();
    if (p === null) return Promise.resolve({ items: [] as LemmaIndexRow[] });
    return fetchLemmaIndex(indexArgs(p, offset), signal).then((res) => {
      setCursor(res.next_offset ?? null);
      return { items: res.rows };
    });
  };

  const setSentinelEl = useInfiniteScrollSentinel(
    () => hasMore() && !loading(),
    () => {
      if (!hasMore() || pagination.appending()) return;
      void pagination.loadMore(firstPage(), fetchPage);
    },
  );

  // Per-letter populations, straight from the server (#376). This used to fold
  // the letters out of `allRows()` — the rows already fetched — which made a
  // dot a property of the current sort's top slice rather than of the scope.
  // On the live index that hid G (11,125 German lemmas) and S (15,366) on
  // first paint, which is exactly when the rail is used. Paging made it drift
  // towards correct as the reader scrolled, which is not the same as being
  // right when it is read.
  const letterCounts = createMemo<Record<string, number>>(
    () => data()?.letter_counts ?? {},
  );
  const lettersWithHits = createMemo<Set<string>>(
    () => new Set(Object.keys(letterCounts())),
  );

  const grouped = createMemo<{ letter: string; rows: LemmaIndexRow[] }[]>(() => {
    const rows = allRows();
    if (args.sort() !== "alpha" && !args.letter()) {
      return [{ letter: "", rows }];
    }
    const map = new Map<string, LemmaIndexRow[]>();
    for (const r of rows) {
      // Bucket alpha-sort section headers on the folded initial so
      // ἀγαθός / ἄνθρωπος / Ἀθηνᾶ all sit under a single "Α" header.
      const c = foldInitial(r.lemma) || "·";
      if (!map.has(c)) map.set(c, []);
      map.get(c)!.push(r);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([letter, rows]) => ({ letter, rows }));
  });

  return {
    data,
    loading,
    error,
    retryKey,
    setRetryKey,
    lettersWithHits,
    letterCounts,
    grouped,
    allRows,
    hasMore,
    appending: pagination.appending,
    appendError: pagination.appendError,
    setSentinelEl,
  };
}
