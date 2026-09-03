import { Show } from "solid-js";
import type { NetworkSummary } from "~/api/networkApi";
import { CORPUS_YEAR_SPAN_LABEL } from "~/features/Landing/corpusFacts";
import { useMobileShellOptional } from "~/components/MobileShellContext";
import { NetworkFiltersBar } from "~/Network/components/NetworkFiltersBar";

export function NetworkHeader(props: {
  minConfidence?: number;
  includeRejected?: boolean;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
  totals?: NetworkSummary["totals"];
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
  const confLabel = () =>
    props.minConfidence === undefined
      ? "≥0.8"
      : `≥${props.minConfidence.toFixed(props.minConfidence >= 1 ? 0 : 1)}`;

  const shell = useMobileShellOptional();
  const isMobile = () => shell?.isMobile() ?? false;

  return (
    <header class="net-head">
      <div class="net-brand">
        <span class="mark">minerva</span>
        <span class="divider" />
        <span class="sub">citation&nbsp;network</span>
      </div>
      <NetworkFiltersBar
        minConfidence={props.minConfidence}
        includeRejected={props.includeRejected}
        sourceAuthors={props.sourceAuthors}
        corpora={props.corpora}
        sourceMethods={props.sourceMethods}
        authorOptions={props.authorOptions}
        onPatch={props.onPatch}
      />
      <div class="net-totals">
        <Show when={props.totals} fallback={<div>—</div>}>
          {/* The mobile design 5a renders the hero as:
                  <big xrefs>
                  verified cross-references
                  across the corpus
                  <AUTHORS> · <WORKS> · <SPAN> YR
              All on the same totals block, with the inline desktop
              "citations · authors · works" reduced to a single number
              + an italic byline. */}
          <Show
            when={isMobile()}
            fallback={
              <div>
                <span class="big">{props.totals!.xrefs.toLocaleString()}</span> citations
                &nbsp;·&nbsp; <span class="big">{props.totals!.authors}</span> authors &nbsp;·&nbsp;{" "}
                <span class="big">{props.totals!.works}</span> works
              </div>
            }
          >
            <div class="net-hero-num">
              <span class="big">{props.totals!.xrefs.toLocaleString()}</span>
            </div>
            <div class="net-hero-what">
              verified cross-references
              <br />
              across the corpus
            </div>
            <div class="net-hero-meta">
              <span class="num">{props.totals!.authors}</span> authors
              <span class="sep">·</span>
              <span class="num">{props.totals!.works}</span> works
              <span class="sep">·</span>
              <span class="num">{CORPUS_YEAR_SPAN_LABEL}</span> yr
            </div>
          </Show>
        </Show>
        {/* "filter: conf ≥0.8" crumb is desktop-only. The mobile chip
            strip above already carries the confidence value. */}
        <Show when={!isMobile()}>
          <div class="crumbs">
            filter: conf {confLabel()}
            <Show when={props.includeRejected}> · incl. rejected</Show>
          </div>
        </Show>
      </div>
    </header>
  );
}
