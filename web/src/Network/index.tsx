// Citation-network dashboard orchestrator.

import { Show, createMemo, createSignal, onMount } from "solid-js";
import { fetchNetworkSummary } from "~/api/networkApi";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import { MobileSheet } from "~/components/MobileSheet";
import { useMobileShell } from "~/components/MobileShellContext";
import { NetworkBody } from "~/Network/components/Body";
import { NetworkHeader } from "~/Network/components/Header";
import { NetworkFiltersBar } from "~/Network/components/NetworkFiltersBar";
import "~/Network/network.css";

export interface NetworkProps {
  minConfidence?: number;
  includeRejected?: boolean;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
  onNavigate: (patch: {
    minConfidence?: number;
    includeRejected?: boolean;
    sourceAuthors?: string[];
    corpora?: string[];
    sourceMethods?: string[];
  }) => void;
  onOpenPair: (source: string, target: string) => void;
  onOpenTargetWork: (author: string, work: string) => void;
  /** Mobile drilldown — open the chronological arc full-screen (5b). */
  onOpenArc: () => void;
  /** Mobile drilldown — open verification coverage full-screen (6). */
  onOpenCoverage: () => void;
}

export default function Network(props: NetworkProps) {
  const shell = useMobileShell();

  onMount(() => {
    shell.registerSurfaceActions({
      openFilters: () => shell.setFiltersSheetOpen(true),
    });
  });

  const { data, loading, error } = useAbortableFetch(
    () => ({
      minConfidence: props.minConfidence,
      includeRejected: props.includeRejected,
      sourceAuthors: props.sourceAuthors,
      corpora: props.corpora,
      sourceMethods: props.sourceMethods,
    }),
    fetchNetworkSummary,
  );

  const [allAuthors, setAllAuthors] = createSignal<string[]>([]);
  const stash = createMemo(() => {
    const d = data();
    if (
      d &&
      !props.sourceAuthors?.length &&
      !props.corpora?.length &&
      !props.sourceMethods?.length &&
      allAuthors().length === 0
    ) {
      setAllAuthors(d.matrix.authors.map((a) => a.name));
    }
    return null;
  });
  stash();

  function patch(p: Partial<{
    minConfidence?: number;
    includeRejected?: boolean;
    sourceAuthors?: string[];
    corpora?: string[];
    sourceMethods?: string[];
  }>) {
    props.onNavigate({
      minConfidence: props.minConfidence,
      includeRejected: props.includeRejected,
      sourceAuthors: props.sourceAuthors,
      corpora: props.corpora,
      sourceMethods: props.sourceMethods,
      ...p,
    });
  }

  const authorOptions = () =>
    allAuthors().length > 0
      ? allAuthors()
      : (data()?.matrix.authors.map((a) => a.name) ?? []);

  return (
    <div class="net">
      <NetworkHeader
        minConfidence={props.minConfidence}
        includeRejected={props.includeRejected}
        sourceAuthors={props.sourceAuthors}
        corpora={props.corpora}
        sourceMethods={props.sourceMethods}
        totals={data()?.totals}
        authorOptions={authorOptions()}
        onPatch={patch}
      />
      <MobileSheet
        open={shell.isMobile() && shell.filtersSheetOpen()}
        title="Filters"
        onClose={() => shell.setFiltersSheetOpen(false)}
      >
        <NetworkFiltersBar
          minConfidence={props.minConfidence}
          includeRejected={props.includeRejected}
          sourceAuthors={props.sourceAuthors}
          corpora={props.corpora}
          sourceMethods={props.sourceMethods}
          authorOptions={authorOptions()}
          onPatch={patch}
        />
      </MobileSheet>
      <Show
        when={data() && !error()}
        fallback={
          <div class={error() ? "net-error" : "net-loading"}>
            {error() ?? (loading() ? "Loading citation network…" : "")}
          </div>
        }
      >
        <NetworkBody
          summary={data()!}
          onOpenPair={props.onOpenPair}
          onOpenTargetWork={props.onOpenTargetWork}
          onOpenArc={props.onOpenArc}
          onOpenCoverage={props.onOpenCoverage}
        />
      </Show>
      <footer class="net-footer">
        <span>
          {data()?.totals.xrefs.toLocaleString() ?? "—"} xrefs · strategies:
          rules + embed-verify + llm-verify
        </span>
        <span>minerva / citation network</span>
      </footer>
    </div>
  );
}
