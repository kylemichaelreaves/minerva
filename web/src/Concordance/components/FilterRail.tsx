// F2 unified-rail filter UI. Top-down: Scope segmented control →
// applied-filters card (chips + reset) → Work checkbox list with
// search + "+N more" → Case → Number → Gender (prose lock-state when
// single-valued) → Surface form chips with "+N more".

import { For, Show, createMemo, createSignal } from "solid-js";
import type { ConcScope, LemmaDetailResponse } from "~/api/concordanceApi";
import {
  abbrevWork,
  caseLabelFor,
  CASES_ORDER,
  GENDER_LABEL,
  formatGenderShare,
  GENDERS_ORDER,
  lockedGender,
  numberLabelFor,
  NUMBERS_ORDER,
  sortBucketsByOrder,
} from "~/Concordance/constants";
import { FilterChipGroup } from "~/Concordance/components/FilterChipGroup";

const WORK_CAP = 8;
const SURFACE_CAP = 6;

export function FilterRail(props: {
  data: LemmaDetailResponse;
  scope: ConcScope;
  scopeAuthors?: string[];
  scopeWorks?: string[];
  caseFilter?: string;
  numberFilter?: string;
  surface?: string;
  onSetScope: (patch: { scope: ConcScope; scopeAuthors?: string[]; scopeWorks?: string[] }) => void;
  onSetCase: (v: string | undefined) => void;
  onSetNumber: (v: string | undefined) => void;
  onSetSurface: (v: string | undefined) => void;
  /** Toggle one work in the multi-select scope (add if absent, remove
   *  if present). */
  onToggleWork: (w: string) => void;
  /** Clear ALL selected works. */
  onClearWorks: () => void;
  onResetAll: () => void;
}) {
  // Morphology abbreviations are language-specific: German uses Akk/Vok,
  // Greek & Latin the classical Acc/Voc (+ a dual number). Drive both
  // off the response's ``lang`` so the detail rail matches the data.
  const caseLabel = createMemo(() => caseLabelFor(props.data.lang));
  const numberLabel = createMemo(() => numberLabelFor(props.data.lang));

  const orderedCases = createMemo(() => sortBucketsByOrder(props.data.case_breakdown, CASES_ORDER));
  const orderedNumbers = createMemo(() =>
    sortBucketsByOrder(props.data.number_breakdown, NUMBERS_ORDER),
  );
  const orderedGenders = createMemo(() =>
    sortBucketsByOrder(props.data.gender_breakdown, GENDERS_ORDER),
  );

  /** The lemma's dominant gender, when it has one — see `lockedGender`
   *  in the Concordance constants for the threshold, and for why it
   *  must be computed over the **raw** buckets rather than
   *  `orderedGenders()`: reading the canonically-sorted list scored
   *  whichever of Masc/Fem/Neut came first against the threshold, so
   *  this rail showed a multi-gender chooser while the identity card
   *  beside it reported a locked gender (#507). */
  const locked = createMemo(() => lockedGender(props.data.gender_breakdown));

  /** Fast membership test for the checkbox `.on` state + applied pills. */
  const selectedWorks = createMemo(() => new Set(props.scopeWorks ?? []));

  /** The one selected work. Only read where `selectedWorks().size === 1`,
   *  so joining the set yields exactly that work — the same value as
   *  `scopeWorks[0]`, duplicates included. */
  const soleWork = () => [...selectedWorks()].join("");

  /** Author segment label: one author → its name; multiple → "N
   *  authors"; none → the "Author" prompt. */
  const authorLabel = createMemo(() => {
    const [first, ...rest] = props.scopeAuthors ?? [];
    if (first === undefined) return "Author";
    if (rest.length === 0) return first;
    return `${rest.length + 1} authors`;
  });

  const [workSearch, setWorkSearch] = createSignal("");
  const [workExpanded, setWorkExpanded] = createSignal(false);
  const [surfaceExpanded, setSurfaceExpanded] = createSignal(false);

  /** Work list, filtered by the in-rail search field. Substring match
   *  on the displayed work title (post-abbreviation). */
  const visibleWorks = createMemo(() => {
    const all = props.data.work_breakdown;
    const q = workSearch().trim().toLowerCase();
    const filtered = q
      ? all.filter(
          (b) => abbrevWork(b.value).toLowerCase().includes(q) || b.value.toLowerCase().includes(q),
        )
      : all;
    return workExpanded() || q ? filtered : filtered.slice(0, WORK_CAP);
  });
  const workOverflow = createMemo(() => props.data.work_breakdown.length - WORK_CAP);

  const visibleSurfaces = createMemo(() =>
    surfaceExpanded()
      ? props.data.surface_breakdown
      : props.data.surface_breakdown.slice(0, SURFACE_CAP),
  );
  const surfaceOverflow = createMemo(() => props.data.surface_breakdown.length - SURFACE_CAP);

  /** Pills shown in the applied-filters card. Each carries its own
   *  remove behaviour so the card never needs to know the filter kind. */
  const appliedPills = createMemo(() => {
    const pills: { k: string; v: string; italic?: boolean; onRemove: () => void }[] = [];
    // Scope — work and author — is deliberately NOT here (#387), the same
    // change made to `activeChips` on the index page for the same reason.
    //
    // `resetAllFilters` clears `caseFilter` / `numberFilter` / `surface` and
    // says why it stops there: "Scope is the one knob we DON'T touch —
    // narrowing scope is a directed action the user took at the F1 page".
    // Counting scope in "N filters applied" and offering "↺ reset" over it
    // contradicted that: the reset left those pills standing.
    //
    // Scope keeps the segmented Work/Author/Corpus bar directly above this
    // card, which is both its display and its control.
    if (props.caseFilter) {
      pills.push({
        k: "case",
        v: caseLabel()[props.caseFilter] ?? props.caseFilter,
        onRemove: () => props.onSetCase(undefined),
      });
    }
    if (props.numberFilter) {
      pills.push({
        k: "num",
        v: numberLabel()[props.numberFilter] ?? props.numberFilter,
        onRemove: () => props.onSetNumber(undefined),
      });
    }
    if (props.surface) {
      pills.push({
        k: "surface",
        v: props.surface,
        italic: true,
        onRemove: () => props.onSetSurface(undefined),
      });
    }
    return pills;
  });

  return (
    <div class="filter-rail">
      {/* Scope segmented control sits at the top — replaces the header
          pill duplicate on F2's LIVE design. The Author/Work segments
          are only active when we already have a value for them; the
          ScopePillDetail in the page header still drives the user into
          those scopes via keyboard shortcuts and the work-list. */}
      <div class="fr-group">
        <div class="fr-label">
          <span>Scope</span>
        </div>
        <div class="fr-scope">
          <span
            class={"seg" + (props.scope === "corpus" ? " on" : "")}
            onClick={() => {
              if (props.scope !== "corpus") {
                props.onSetScope({
                  scope: "corpus",
                  scopeAuthors: undefined,
                  scopeWorks: undefined,
                });
              }
            }}
          >
            Corpus
          </span>
          <span
            class={"seg" + (props.scope === "author" ? " on" : "")}
            onClick={() => {
              // Only navigable when we already have an author to scope
              // to — the work-list click below sets one, as does the
              // index page when the user clicks a lemma from an author
              // scope. Otherwise the segment is a no-op (cursor stays
              // pointer so the click target is still discoverable).
              if (props.scope !== "author" && props.scopeAuthors?.length) {
                props.onSetScope({ scope: "author" });
              }
            }}
          >
            {authorLabel()}
          </span>
          <span
            class={"seg" + (props.scope === "work" ? " on" : "")}
            onClick={() => {
              if (props.scope !== "work" && selectedWorks().size > 0) {
                props.onSetScope({ scope: "work" });
              }
            }}
          >
            {selectedWorks().size === 0
              ? "Work"
              : selectedWorks().size === 1
                ? abbrevWork(soleWork())
                : `${selectedWorks().size} works`}
          </span>
        </div>
      </div>

      <Show when={appliedPills().length > 0}>
        <div class="applied-filters">
          <div class="hd">
            <span>
              {appliedPills().length} filter{appliedPills().length === 1 ? "" : "s"} applied
            </span>
            <span class="reset" onClick={() => props.onResetAll()}>
              ↺ reset
            </span>
          </div>
          <div class="pills">
            <For each={appliedPills()}>
              {(p) => (
                <span class="pill">
                  <span class="k">{p.k}</span>
                  <span class={"v" + (p.italic ? " italic" : "")}>{p.v}</span>
                  <span
                    class="x"
                    onClick={(e) => {
                      e.stopPropagation();
                      p.onRemove();
                    }}
                  >
                    ×
                  </span>
                </span>
              )}
            </For>
          </div>
        </div>
      </Show>

      <Show when={props.data.work_breakdown.length > 0}>
        <div class="fr-group">
          <div class="fr-label">
            <span>
              Work
              <Show when={selectedWorks().size > 0}>
                <span class="applied">
                  ·{" "}
                  {selectedWorks().size === 1
                    ? abbrevWork(soleWork())
                    : `${selectedWorks().size} selected`}
                </span>
              </Show>
            </span>
            <Show when={selectedWorks().size > 0}>
              <span class="clr" onClick={() => props.onClearWorks()}>
                clear
              </span>
            </Show>
          </div>
          <Show when={props.data.work_breakdown.length > WORK_CAP}>
            <div class="fr-search">
              <span class="ico">⌕</span>
              <input
                type="text"
                placeholder="Find work…"
                value={workSearch()}
                onInput={(e) => setWorkSearch(e.currentTarget.value)}
              />
            </div>
          </Show>
          <For each={visibleWorks()}>
            {(b) => (
              <div
                class={"fr-check" + (selectedWorks().has(b.value) ? " on" : "")}
                onClick={() => props.onToggleWork(b.value)}
                title={b.value}
              >
                <span class="box" />
                <span>{abbrevWork(b.value)}</span>
                <span class="ct">{b.count.toLocaleString()}</span>
              </div>
            )}
          </For>
          <Show when={!workExpanded() && !workSearch() && workOverflow() > 0}>
            <span class="fr-more" onClick={() => setWorkExpanded(true)}>
              + {workOverflow()} more work{workOverflow() === 1 ? "" : "s"} ▾
            </span>
          </Show>
        </div>
      </Show>

      <Show when={orderedCases().length > 0}>
        <FilterChipGroup
          label="Case"
          applied={
            props.caseFilter ? (caseLabel()[props.caseFilter] ?? props.caseFilter) : undefined
          }
          onClear={() => props.onSetCase(undefined)}
          buckets={orderedCases()}
          selected={props.caseFilter}
          labelFor={(v) => caseLabel()[v] ?? v}
          titleFor={(b) => `${b.count.toLocaleString()} occurrence${b.count === 1 ? "" : "s"}`}
          onToggle={props.onSetCase}
        />
      </Show>

      <Show when={orderedNumbers().length > 0}>
        <FilterChipGroup
          label="Number"
          applied={
            props.numberFilter
              ? (numberLabel()[props.numberFilter] ?? props.numberFilter)
              : undefined
          }
          onClear={() => props.onSetNumber(undefined)}
          buckets={orderedNumbers()}
          selected={props.numberFilter}
          labelFor={(v) => numberLabel()[v] ?? v}
          titleFor={(b) => b.count.toLocaleString()}
          onToggle={props.onSetNumber}
        />
      </Show>

      <Show when={orderedGenders().length > 0}>
        <div class="fr-group">
          <div class="fr-label">
            <span>Gender</span>
          </div>
          <Show
            when={locked()}
            fallback={
              <div class="fr-opts">
                <For each={orderedGenders()}>
                  {(b) => (
                    <span class="fr-opt muted" title={b.count.toLocaleString()}>
                      {GENDER_LABEL[b.value] ?? b.value}
                    </span>
                  )}
                </For>
              </div>
            }
          >
            {/* Dominant gender — render as prose. The lemma identity
                card carries this fact too; the rail slot stays so the
                IA doesn't shift between lemmas. The measured share is
                reported rather than "single attested", which overstated
                the >95% case — and that case is most of them. */}
            {(l) => (
              <div class="fr-locked">
                <span>
                  <b>{GENDER_LABEL[l().value] ?? l().value}</b> only —{" "}
                  {formatGenderShare(l().share)} of attested forms for this lemma.
                </span>
              </div>
            )}
          </Show>
        </div>
      </Show>

      <Show when={props.data.surface_breakdown.length > 0}>
        <FilterChipGroup
          label="Surface form"
          applied={props.surface}
          onClear={() => props.onSetSurface(undefined)}
          buckets={visibleSurfaces()}
          selected={props.surface}
          labelFor={(v) => v}
          titleFor={(b) => b.count.toLocaleString()}
          onToggle={props.onSetSurface}
        >
          <Show when={!surfaceExpanded() && surfaceOverflow() > 0}>
            <span class="fr-more" onClick={() => setSurfaceExpanded(true)}>
              + {surfaceOverflow()} more form{surfaceOverflow() === 1 ? "" : "s"} ▾
            </span>
          </Show>
        </FilterChipGroup>
      </Show>
    </div>
  );
}
