import { Show, createMemo } from "solid-js";
import { useMobileShellOptional } from "~/components/MobileShellContext";
import { CORPUS_BUCKETS, SOURCE_METHODS } from "~/Network/constants";
import { FilterMenuChip } from "~/Network/components/FilterMenuChip";

export function NetworkFiltersBar(props: {
  minConfidence?: number;
  includeRejected?: boolean;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
  authorOptions: string[];
  onPatch: (
    p: Partial<{
      minConfidence?: number;
      includeRejected?: boolean;
      sourceAuthors?: string[];
      corpora?: string[];
      sourceMethods?: string[];
    }>,
  ) => void;
}) {
  // On mobile (design 5a) chip copy follows the wireframe:
  // - third chip label reads "Method" (not the raw `source_method`)
  // - all empty-state values say "any" (not "All" or "all 5")
  // - the trailing "rejected" + filter-count + Clear chips are hidden
  const shell = useMobileShellOptional();
  const isMobile = () => shell?.isMobile() ?? false;
  const emptyLabel = () => (isMobile() ? "any" : "All");
  const methodLabel = () => (isMobile() ? "Method" : "source_method");
  const methodEmptyLabel = () => (isMobile() ? "any" : "all 5");

  const filterCount = createMemo(() => {
    let n = 0;
    if (props.minConfidence !== undefined) n++;
    if (props.includeRejected) n++;
    if (props.sourceAuthors?.length) n++;
    if (props.corpora?.length) n++;
    if (props.sourceMethods?.length) n++;
    return n;
  });

  function cycleConfidence() {
    const order: (number | undefined)[] = [undefined, 0.0, 0.5, 0.9];
    const i = order.findIndex((v) => v === props.minConfidence);
    props.onPatch({ minConfidence: order[(i + 1) % order.length] });
  }
  function toggleRejected() {
    props.onPatch({ includeRejected: !props.includeRejected });
  }
  function clearAll() {
    props.onPatch({
      minConfidence: undefined,
      includeRejected: false,
      sourceAuthors: undefined,
      corpora: undefined,
      sourceMethods: undefined,
    });
  }

  const confLabel = () =>
    props.minConfidence === undefined
      ? "≥0.8"
      : `≥${props.minConfidence.toFixed(props.minConfidence >= 1 ? 0 : 1)}`;

  function multiToggle(curr: string[] | undefined, value: string): string[] | undefined {
    const set = new Set(curr ?? []);
    if (set.has(value)) set.delete(value);
    else set.add(value);
    return set.size === 0 ? undefined : Array.from(set);
  }

  function summarize(values: string[] | undefined, total: number, all: string): string {
    if (!values || values.length === 0) return all;
    if (values.length === 1) return values[0] ?? all;
    if (values.length === total) return all;
    return `${values.length} of ${total}`;
  }

  return (
    <div class="net-filters">
      <FilterMenuChip
        label="Author"
        value={summarize(
          props.sourceAuthors,
          Math.max(1, props.authorOptions.length),
          emptyLabel(),
        )}
        active={Boolean(props.sourceAuthors?.length)}
        options={props.authorOptions.map((a) => ({ key: a, label: a }))}
        selected={props.sourceAuthors ?? []}
        onToggle={(k) =>
          props.onPatch({
            sourceAuthors: multiToggle(props.sourceAuthors, k),
          })
        }
        onClear={() => props.onPatch({ sourceAuthors: undefined })}
      />
      <FilterMenuChip
        label="Corpus"
        value={summarize(props.corpora, CORPUS_BUCKETS.length, emptyLabel())}
        active={Boolean(props.corpora?.length)}
        options={CORPUS_BUCKETS.map((b) => ({ key: b.key, label: b.label }))}
        selected={props.corpora ?? []}
        onToggle={(k) => props.onPatch({ corpora: multiToggle(props.corpora, k) })}
        onClear={() => props.onPatch({ corpora: undefined })}
      />
      <FilterMenuChip
        label={methodLabel()}
        value={summarize(props.sourceMethods, SOURCE_METHODS.length, methodEmptyLabel())}
        active={Boolean(props.sourceMethods?.length)}
        options={SOURCE_METHODS.map((m) => ({ key: m, label: m }))}
        selected={props.sourceMethods ?? []}
        onToggle={(k) =>
          props.onPatch({
            sourceMethods: multiToggle(props.sourceMethods, k),
          })
        }
        onClear={() => props.onPatch({ sourceMethods: undefined })}
      />
      <button
        class={"net-chip" + (props.minConfidence !== undefined ? " active" : "")}
        onClick={cycleConfidence}
        title="Cycle minimum confidence threshold"
      >
        <span class="lbl">{isMobile() ? "Conf" : "min conf."}</span>
        <span class="val">{confLabel()}</span>
      </button>
      {/* The "rejected" toggle, the filter-count tally, and the Clear
          chip belong to the desktop chrome only; the mobile design 5a
          shows just four chips and treats clearing as a per-chip
          action via the filter sheet (4b pattern). */}
      <Show when={!isMobile()}>
        <button
          class={"net-chip" + (props.includeRejected ? " active" : "")}
          onClick={toggleRejected}
          title="Include rejected cross-references"
        >
          <span class="lbl">rejected</span>
          <span class="val">{props.includeRejected ? "shown" : "hidden"}</span>
        </button>
        <span class="net-filter-count">
          {filterCount() === 0 ? "default" : `${filterCount()} active`}
        </span>
        <Show when={filterCount() > 0}>
          <button class="net-chip-clear" onClick={clearAll}>
            Clear
          </button>
        </Show>
      </Show>
    </div>
  );
}
