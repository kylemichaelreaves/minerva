// Loading skeleton for the F2 KWIC view — mirrors the filter rail +
// keyword-in-context grid so the layout doesn't jump when data lands.
// Extracted from ConcordanceLemmaDetail, which previously inlined it.

import { For } from "solid-js";

export function KwicSkeleton() {
  return (
    <div class="kwic-stage">
      <div class="filter-rail">
        <For each={[1, 2, 3, 4]}>
          {() => (
            <div class="fr-group">
              <div class="fr-label">
                <span class="skel-bar" style={{ width: "60px" }} />
              </div>
              <div class="fr-opts">
                <For each={[1, 2, 3]}>
                  {() => (
                    <span class="fr-opt">
                      <span class="skel-bar" style={{ width: "32px" }} />
                    </span>
                  )}
                </For>
              </div>
            </div>
          )}
        </For>
      </div>
      <div class="kwic-pane">
        <div class="kwic-toolbar">
          <span class="skel-bar" style={{ width: "140px", height: "12px" }} />
          <span
            class="skel-bar"
            style={{ width: "120px", height: "12px", "margin-left": "auto" }}
          />
        </div>
        <div class="kwic-grid">
          <For each={[1, 2, 3, 4, 5, 6]}>
            {() => (
              <div class="kwic-row" style={{ cursor: "default" }}>
                <span class="loc">
                  <span class="skel-bar" style={{ width: "50px", height: "10px" }} />
                  <br />
                  <span
                    class="skel-bar"
                    style={{ width: "60px", height: "10px", "margin-top": "4px" }}
                  />
                </span>
                <span class="left">
                  <span class="skel-bar" style={{ width: "80%", height: "12px" }} />
                </span>
                <span class="match">
                  <span class="skel-bar" style={{ width: "50px", height: "14px" }} />
                </span>
                <span class="right">
                  <span class="skel-bar" style={{ width: "85%", height: "12px" }} />
                </span>
                <span class="meta">
                  <span class="skel-bar" style={{ width: "60px", height: "10px" }} />
                </span>
              </div>
            )}
          </For>
        </div>
      </div>
    </div>
  );
}
