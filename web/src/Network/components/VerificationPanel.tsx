import { For, createMemo } from "solid-js";
import type { VerificationRow } from "~/api/networkApi";
import { VERIFICATION_METHODS } from "~/Network/constants";

export function VerificationPanel(props: { rows: VerificationRow[] }) {
  const colors = createMemo(() => [
    "var(--net-navy)",
    "color-mix(in oklab, var(--net-navy) 70%, var(--paper))",
    "color-mix(in oklab, var(--net-navy) 45%, var(--paper))",
    "color-mix(in oklab, var(--net-navy) 22%, var(--paper))",
    "var(--paper-edge)",
  ]);
  return (
    <div class="net-panel">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Verification coverage</div>
          <div class="net-panel-q">How sure are we — per author?</div>
        </div>
      </div>
      <div class="net-panel-body">
        <div class="net-verif-wrap">
          <div class="net-verif-legend">
            <For each={VERIFICATION_METHODS}>
              {(k, i) => (
                <span>
                  <i style={{ background: colors()[i()] }} />
                  {k}
                </span>
              )}
            </For>
          </div>
          <div class="net-verif-rows">
            <For each={props.rows}>
              {(row) => {
                const total = row.total || 1;
                return (
                  <div class="net-verif-row">
                    <div class="name" title={row.author}>
                      {row.author}
                    </div>
                    <div class="net-verif-bar">
                      <For each={VERIFICATION_METHODS}>
                        {(k, i) => {
                          // row.parts is typed as Record<Method, number> but
                          // a method missing from the verification mix isn't
                          // a key at all — TS thinks the access is always
                          // defined, runtime returns undefined.
                          // (Record<Method, number> has literal keys, so
                          // noUncheckedIndexedAccess doesn't apply here.)
                          // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
                          const v = (row.parts[k] ?? 0) / total;
                          return (
                            <span
                              style={{
                                width: `${(v * 100).toFixed(2)}%`,
                                background: colors()[i()],
                              }}
                              // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
                              title={`${k}: ${row.parts[k]?.toLocaleString() ?? 0}`}
                            />
                          );
                        }}
                      </For>
                    </div>
                    <div class="total">{row.total.toLocaleString()}</div>
                  </div>
                );
              }}
            </For>
          </div>
        </div>
      </div>
    </div>
  );
}

