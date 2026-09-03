// Three-dot bouncing loader. The animation lives in CSS (`.dots`
// keyframes in styles.css); this component is just the markup so
// every "something is in flight" surface uses identical glyphs. Used
// by the Thread "considering" row and the Reader rail's
// "Translating" state.

export function LoadingDots() {
  return (
    <span class="dots">
      <span />
      <span />
      <span />
    </span>
  );
}
