import { For } from "solid-js";

/**
 * Concordance leaderboard loading state.
 *
 * The skeleton renders 8 placeholder rows so the layout doesn't jump
 * when the lemma index resolves. Without the explicit "Loading…"
 * label users mistake the dimmed rows for an empty table — same
 * shape, just greyer — and ask whether the page is broken or
 * still updating. The label sits above the rows in the same visual
 * region the empty/error states use (``conc-empty``), so the
 * transition between "loading" → "loaded with rows" → "empty cache"
 * stays continuous from the reader's point of view.
 *
 * The bouncing dots use pure CSS (an inline keyframes block on the
 * span elements) to avoid pulling in an animation lib just for this.
 */
export function LoadingSkeleton() {
  return (
    <>
      <div
        class="conc-loading"
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          "align-items": "center",
          gap: "10px",
          padding: "12px 4px 6px",
          color: "var(--ink-mute)",
          "font-size": "14px",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: "14px",
            height: "14px",
            "border-radius": "50%",
            border: "2px solid currentColor",
            "border-top-color": "transparent",
            animation: "conc-spin 0.8s linear infinite",
          }}
        />
        <span>Loading lemma index…</span>
        <style>{`@keyframes conc-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
      <div class="kwic-skeleton" style={{ "padding-top": "4px" }}>
        <For each={[1, 2, 3, 4, 5, 6, 7, 8]}>
          {() => (
            <div
              class="lb-row"
              style={{
                cursor: "default",
                "pointer-events": "none",
                opacity: 0.6,
              }}
            >
              <span class="bar tall" style={{ width: "20px" }} />
              <span class="bar" style={{ width: "150px", height: "16px" }} />
              <span class="bar" style={{ width: "70px" }} />
              <span class="bar" style={{ width: "50px" }} />
              <span class="bar" style={{ width: "100px" }} />
              <span class="bar" style={{ width: "100px" }} />
            </div>
          )}
        </For>
      </div>
    </>
  );
}
