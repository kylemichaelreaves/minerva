// Mobile network footer — three drilldown links per design 5a:
//   View as timeline → chronological arc
//   Verification coverage → per-author stacked bars
//   More views → scripture heatmap, …

interface Props {
  onOpenArc: () => void;
  onOpenCoverage: () => void;
  onOpenMore: () => void;
}

export function MobileFooterLinks(props: Props) {
  return (
    <div class="nw-foot">
      <button class="nw-foot-link" type="button" onClick={props.onOpenArc}>
        View as timeline <span class="nw-foot-arr">→</span>
        <span class="nw-foot-desc">chronological arc</span>
      </button>
      <button
        class="nw-foot-link"
        type="button"
        onClick={props.onOpenCoverage}
      >
        Verification coverage <span class="nw-foot-arr">→</span>
        <span class="nw-foot-desc">per-author stacked bars</span>
      </button>
      <button class="nw-foot-link" type="button" onClick={props.onOpenMore}>
        More views <span class="nw-foot-arr">→</span>
        <span class="nw-foot-desc">scripture heatmap, …</span>
      </button>
    </div>
  );
}
