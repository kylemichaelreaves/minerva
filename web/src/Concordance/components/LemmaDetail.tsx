// F2 — Lemma detail / KWIC grid. Orchestrator composes useLemmaDetail;
// presentational pieces live in ./components.

import { For, Show, createEffect, createMemo, createSignal, type Accessor } from "solid-js";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import {
  fetchLemmaDetail,
  type ConcScope,
  type KwicRow,
  type LemmaDetailResponse,
} from "~/api/concordanceApi";
import { useListKeyboardNav } from "~/hooks/useListKeyboardNav";
import { ConcEmpty, LemmaCacheEmpty } from "~/Concordance/components/ConcEmpty";
import { FilterRail } from "~/Concordance/components/FilterRail";
import { KwicRowEl } from "~/Concordance/components/KwicRow";
import { KwicSkeleton } from "~/Concordance/components/KwicSkeleton";
import { LemmaIdentityCard } from "~/Concordance/components/LemmaIdentityCard";
import { useMobile } from "~/hooks/useMobile";
import { MobileSheet } from "~/components/shell/MobileSheet";
import "~/Concordance/concordance.css";

export interface LemmaDetailProps {
  lemma: string;
  lang?: string;
  scope?: ConcScope;
  scopeAuthors?: string[];
  scopeWorks?: string[];
  caseFilter?: string;
  numberFilter?: string;
  surface?: string;
  onNavigate: (patch: {
    scope?: ConcScope;
    scopeAuthors?: string[];
    scopeWorks?: string[];
    caseFilter?: string;
    numberFilter?: string;
    surface?: string;
  }) => void;
  onBackToIndex: () => void;
  onOpenChunk: (work: string, chunkId: string) => void;
}

export function ConcordanceLemmaDetail(props: LemmaDetailProps) {
  const lang = () => props.lang ?? "deu";
  const scope = (): ConcScope => props.scope ?? "corpus";

  const { data, loading, error, cursor, setCursor, morph } = useLemmaDetail({
    lemma: () => props.lemma,
    lang,
    scope,
    scopeAuthors: () => props.scopeAuthors,
    scopeWorks: () => props.scopeWorks,
    surface: () => props.surface,
    caseFilter: () => props.caseFilter,
    numberFilter: () => props.numberFilter,
  });

  const isMobile = useMobile();
  const [sheetOpen, setSheetOpen] = createSignal(false);

  // Queue navigation — shared hook owns the form-element guard and the
  // listener lifecycle. `enabled` mutes everything (including Escape)
  // while the mobile filter sheet is open so Escape closes the sheet
  // instead of bouncing back to the index.
  useListKeyboardNav({
    enabled: () => !sheetOpen(),
    // ⌘/Ctrl + Arrow chords zoom the scope; handled before the hook's
    // modifier bail-out.
    onKey: (e) => {
      if (!(e.metaKey || e.ctrlKey)) return false;
      if (e.key === "ArrowUp" && scope() !== "corpus") {
        e.preventDefault();
        props.onNavigate({
          scope: "corpus",
          scopeAuthors: undefined,
          scopeWorks: undefined,
        });
        return true;
      }
      if (e.key === "ArrowDown" && scope() !== "work") {
        const topWork = data()?.work_breakdown[0]?.value;
        if (topWork) {
          e.preventDefault();
          props.onNavigate({ scope: "work", scopeWorks: [topWork], scopeAuthors: undefined });
          return true;
        }
      }
      return false;
    },
    onNext: () => {
      const rows = data()?.rows ?? [];
      setCursor((c) => Math.min(rows.length - 1, c + 1));
      scrollRowIntoView();
    },
    onPrev: () => {
      setCursor((c) => Math.max(0, c - 1));
      scrollRowIntoView();
    },
    onSelect: () => {
      const r = (data()?.rows ?? []).at(cursor());
      if (r) props.onOpenChunk(r.work, r.chunk_id);
    },
    onEscape: () => props.onBackToIndex(),
  });

  /** Reset every URL-bound filter at once, used by the applied-
   *  filters card and the mobile sheet's Reset button. Scope is the
   *  one knob we DON'T touch — narrowing scope is a directed action
   *  the user took at the F1 page, and the back-to-index link is the
   *  right exit. */
  const resetAllFilters = () =>
    props.onNavigate({
      caseFilter: undefined,
      numberFilter: undefined,
      surface: undefined,
    });

  /** Active-filter count for the mobile FAB badge. Mirrors the
   *  applied-filters card's pill count minus the scope pill, since on
   *  mobile the scope crumb has its own visible row above the KWIC. */
  const filterCount = createMemo(() => {
    let n = 0;
    if (props.caseFilter) n += 1;
    if (props.numberFilter) n += 1;
    if (props.surface) n += 1;
    return n;
  });

  /** FilterRail closure — same pattern as Refs/index.tsx's filtersBar.
   *  Invoked once in the desktop rail slot and once inside the mobile
   *  sheet, so the 12 props are wired in exactly one place. Only
   *  called from inside `<Show when={data()}>` guards, which hand it
   *  their narrowed accessor. */
  const filterRail = (d: Accessor<LemmaDetailResponse>) => (
    <FilterRail
      data={d()}
      scope={scope()}
      scopeAuthors={props.scopeAuthors}
      scopeWorks={props.scopeWorks}
      caseFilter={props.caseFilter}
      numberFilter={props.numberFilter}
      surface={props.surface}
      onSetScope={(patch) => props.onNavigate(patch)}
      onSetCase={(v) => props.onNavigate({ caseFilter: v })}
      onSetNumber={(v) => props.onNavigate({ numberFilter: v })}
      onSetSurface={(v) => props.onNavigate({ surface: v })}
      onToggleWork={(w) => {
        // Toggle one work in the scope=work selection. Adding the first
        // work enters work-scope (and drops the author binding, since
        // work-scope is more specific); removing the last work falls
        // back up to author scope (preserving the Author binding when
        // there is one) or to corpus otherwise.
        const cur = props.scopeWorks ?? [];
        const next = cur.includes(w) ? cur.filter((x) => x !== w) : [...cur, w];
        if (next.length > 0) {
          props.onNavigate({ scope: "work", scopeWorks: next, scopeAuthors: undefined });
        } else {
          props.onNavigate({
            scope: props.scopeAuthors?.length ? "author" : "corpus",
            scopeWorks: undefined,
          });
        }
      }}
      onClearWorks={() =>
        // Clear ALL works → back up to author (when bound) or corpus.
        props.onNavigate({
          scope: props.scopeAuthors?.length ? "author" : "corpus",
          scopeWorks: undefined,
        })
      }
      onResetAll={resetAllFilters}
    />
  );

  return (
    <div class="conc-stage conc-detail">
      <Show when={data()}>
        {(d) => (
        <div class="conc-head" style={{ "align-items": "flex-start" }}>
          <div style={{ flex: 1 }}>
            <LemmaIdentityCard lemma={props.lemma} lang={lang()} data={d()} />
            <div
              style={{
                "font-family": "var(--sans)",
                "font-size": "11px",
                color: "var(--ink-mute)",
                "margin-top": "2px",
              }}
            >
              <a
                style={{ color: "var(--accent)", cursor: "pointer", "text-decoration": "none" }}
                onClick={() => props.onBackToIndex()}
              >
                ‹ back to index
              </a>
            </div>
          </div>
        </div>
        )}
      </Show>

      <Show when={!!error()}>
        <Show
          // `error()` is already a string — `useAbortableFetch` runs it
          // through `errorMessage`. The `String(… as unknown)` this replaces
          // was working around `createResource.error` being `unknown`.
          when={(error() ?? "").toLowerCase().includes("lemma cache")}
          fallback={
            <ConcEmpty icon="!" title="Couldn't load occurrences">
              <div>{error()}</div>
            </ConcEmpty>
          }
        >
          <LemmaCacheEmpty
            lang={lang()}
            title="No lemma cache"
            body={
              <>
                spaCy hasn't lemmatised the {lang().toUpperCase()} edition yet — the concordance
                can't key occurrences until the cache lands.
              </>
            }
            footer={<>Runs once per edition · ~3 min for ~30k chunks.</>}
          />
        </Show>
      </Show>

      <Show when={loading() && !data()}>
        <KwicSkeleton />
      </Show>

      <Show when={!error()}>
      <Show when={data()}>
        {(d) => (
        <Show
          when={d().total > 0}
          fallback={
            <ConcEmpty icon="∅" title="No occurrences with these filters">
              <div>
                <em>{props.lemma}</em>
                {Object.entries(morph())
                  .map(([k, v]) => ` · ${k}=${v}`)
                  .join("")}
                {props.surface ? ` · surface=${props.surface}` : ""} doesn't appear in{" "}
                {d().scope_label || "this scope"}.
              </div>
              <div class="broaden">
                <Show when={props.numberFilter}>
                  {(() => {
                    const drop = props.caseFilter
                      ? d().case_breakdown.find((b) => b.value === props.caseFilter)?.count
                      : d().case_breakdown.reduce((s, b) => s + b.count, 0);
                    return (
                      <a onClick={() => props.onNavigate({ numberFilter: undefined })}>
                        Drop Number{drop !== undefined ? ` · ${drop.toLocaleString()} hits` : ""}
                      </a>
                    );
                  })()}
                </Show>
                <Show when={props.caseFilter}>
                  {(() => {
                    const drop = props.numberFilter
                      ? d().number_breakdown.find((b) => b.value === props.numberFilter)?.count
                      : d().case_breakdown.reduce((s, b) => s + b.count, 0);
                    return (
                      <a onClick={() => props.onNavigate({ caseFilter: undefined })}>
                        Drop Case{drop !== undefined ? ` · ${drop.toLocaleString()} hits` : ""}
                      </a>
                    );
                  })()}
                </Show>
                <Show when={props.surface}>
                  <a onClick={() => props.onNavigate({ surface: undefined })}>Drop Surface form</a>
                </Show>
                <Show when={scope() !== "corpus"}>
                  <a onClick={() => props.onNavigate({ scope: "corpus" })}>Zoom to corpus</a>
                </Show>
              </div>
            </ConcEmpty>
          }
        >
          <div class="kwic-stage">
            <Show when={!isMobile()}>{filterRail(d)}</Show>
            <div class="kwic-pane" classList={{ "kwic-refetching": loading() }}>
              <div class="kwic-toolbar">
                <span class="ct">
                  Showing <b>{d().rows.length}</b> of <b>{d().total.toLocaleString()}</b>
                </span>
                <span class="kbd">
                  <kbd>j</kbd>/<kbd>k</kbd> next / prev · <kbd>↵</kbd> open chunk ·{" "}
                  <Show when={scope() !== "corpus"}>
                    <kbd>⌘↑</kbd> zoom out ·{" "}
                  </Show>
                  <Show when={scope() !== "work" && d().work_breakdown.length > 0}>
                    <kbd>⌘↓</kbd> zoom in ·{" "}
                  </Show>
                  <kbd>esc</kbd> back
                </span>
              </div>
              <div class="kwic-grid">
                <For each={d().rows}>
                  {(row, idx) => (
                    <KwicRowEl
                      row={row}
                      cur={idx() === cursor()}
                      onClick={() => {
                        setCursor(idx());
                        props.onOpenChunk(row.work, row.chunk_id);
                      }}
                      onHover={() => setCursor(idx())}
                    />
                  )}
                </For>
              </div>
            </div>
          </div>
        </Show>
        )}
      </Show>
      </Show>

      {/* Mobile FAB + sheet. Renders the same FilterRail inside the
          sheet body — content drives the design, not duplicated layout. */}
      <Show when={isMobile() && !error()}>
      <Show when={data()}>
        {(d) => (
      <Show when={d().total > 0}>
        <button type="button" class="conc-fab" onClick={() => setSheetOpen(true)}>
          ≡ Filters
          <Show when={filterCount() > 0}>
            <span class="badge">{filterCount()}</span>
          </Show>
        </button>
        <MobileSheet
          open={sheetOpen()}
          title="Filter occurrences"
          onClose={() => setSheetOpen(false)}
        >
          <div class="conc-mob-sheet">
            {filterRail(d)}
            <div class="conc-mob-sheet-foot">
              <span
                class="reset"
                onClick={() => {
                  resetAllFilters();
                  setSheetOpen(false);
                }}
              >
                ↺ Reset all
              </span>
              <span class="done" onClick={() => setSheetOpen(false)}>
                <b>{d().total.toLocaleString()}</b> occurrences →
              </span>
            </div>
          </div>
        </MobileSheet>
      </Show>
        )}
      </Show>
      </Show>
    </div>
  );
}

interface UseLemmaDetailArgs {
  lemma: () => string;
  lang: () => string;
  scope: () => ConcScope;
  scopeAuthors: () => string[] | undefined;
  scopeWorks: () => string[] | undefined;
  surface: () => string | undefined;
  caseFilter: () => string | undefined;
  numberFilter: () => string | undefined;
}

export function useLemmaDetail(args: UseLemmaDetailArgs) {
  const [cursor, setCursor] = createSignal(0);

  const morph = createMemo<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    const caseFilter = args.caseFilter();
    const numberFilter = args.numberFilter();
    if (caseFilter) m.Case = caseFilter;
    if (numberFilter) m.Number = numberFilter;
    return m;
  });

  // `resetOnChange` because the args carry the *lemma*: without it the
  // previous lemma's occurrences stay on screen under the new lemma's
  // heading and counts until the new answer lands, which is a wrong answer
  // rather than a flicker. The signal is what the raw `createResource` here
  // could not thread — a superseded lemma's request used to run to
  // completion against the server (#65).
  const {
    data,
    loading,
    error,
  } = useAbortableFetch(
    () => ({
      lemma: args.lemma(),
      lang: args.lang(),
      scope: args.scope(),
      authors: args.scopeAuthors(),
      works: args.scopeWorks(),
      surface: args.surface(),
      morph: morph(),
    }),
    async (p, signal) =>
      fetchLemmaDetail(
        {
          lemma: p.lemma,
          lang: p.lang,
          scope: p.scope,
          authors: p.authors,
          works: p.works,
          surface: p.surface,
          morph: Object.keys(p.morph).length > 0 ? p.morph : undefined,
          limit: 100,
        },
        signal,
      ),
  { resetOnChange: true },
  );

  createEffect(() => {
    // Reset the KWIC cursor whenever the underlying query changes. This
    // must track EVERY input the `data` resource reads above — omitting
    // lemma / lang / scope-authors / scope-works left the cursor on a
    // stale (possibly out-of-range) row after those changed (issue #66).
    args.lemma();
    args.lang();
    args.scope();
    args.scopeAuthors();
    args.scopeWorks();
    args.surface();
    morph();
    setCursor(0);
  });

  return { data, loading, error, cursor, setCursor, morph };
}

/** Keep the KWIC cursor row visible as j/k navigation moves it. */
function scrollRowIntoView() {
  queueMicrotask(() => {
    document.querySelector<HTMLElement>(".kwic-row.cur")?.scrollIntoView({ block: "nearest" });
  });
}

export type { KwicRow };
