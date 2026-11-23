import { For, Show } from "solid-js";
import type { AuthorPair } from "~/api/networkApi";
import {
  formatYearEra,
  furthestBack,
  logWeight,
  type ArcAuthor,
} from "~/Network/components/arcLayout";

const ROWS = 5;

/** Strip under the arcs. With no author in focus it lists the top
 *  pairs; with one it lists who that author cites and who cites them.
 *  Every row focuses an author. */
export function ArcDetail(props: {
  /** The previewed or clicked author, if any. */
  active: string | null;
  /** True when `active` is a click (sticky) rather than a hover preview. */
  pinned: boolean;
  topPairs: AuthorPair[];
  allPairs: AuthorPair[];
  hideIntra: boolean;
  byName: ReadonlyMap<string, ArcAuthor>;
  onFocus: (name: string | null) => void;
}) {
  return (
    <div class="net-arc-detail">
      <Show when={props.active} fallback={<TopPairs {...props} />}>
        {(name) => <AuthorDetail {...props} name={name()} />}
      </Show>
    </div>
  );
}

function Bar(props: { n: number; max: number; color: string }) {
  const w = () => Math.max(4, logWeight(props.n, props.max) * 100);
  return <span class="bar" style={{ width: `${w()}%`, background: props.color }} />;
}

function TopPairs(props: {
  topPairs: AuthorPair[];
  hideIntra: boolean;
  onFocus: (name: string | null) => void;
}) {
  const max = () => props.topPairs[0]?.n ?? 1;
  return (
    <>
      <div class="h">
        <span>Top pairs{props.hideIntra ? " — intra-scripture hidden" : ""}</span>
      </div>
      <div class="rows">
        <For each={props.topPairs.slice(0, ROWS)}>
          {(p) => (
            <button type="button" class="li" onClick={() => props.onFocus(p.src)}>
              <span class="nm">
                {p.src} → {p.tgt}
              </span>
              <Bar n={p.n} max={max()} color="var(--net-arc-out)" />
              <span class="v">{p.n.toLocaleString()}</span>
            </button>
          )}
        </For>
      </div>
    </>
  );
}

function AuthorDetail(props: {
  name: string;
  pinned: boolean;
  allPairs: AuthorPair[];
  byName: ReadonlyMap<string, ArcAuthor>;
  onFocus: (name: string | null) => void;
}) {
  const out = () => props.allPairs.filter((p) => p.src === props.name);
  const inn = () => props.allPairs.filter((p) => p.tgt === props.name);
  const max = () => Math.max(1, ...out().map((p) => p.n), ...inn().map((p) => p.n));
  const self = () => props.byName.get(props.name);
  const far = () => furthestBack(props.name, out(), props.byName);
  return (
    <>
      <div class="h">
        <span>
          {props.name}
          <Show when={self()?.dated}> · {formatYearEra(self()?.year ?? 0)}</Show>
          <Show when={far()}>
            {(f) => (
              <>
                {" "}
                · reaches back furthest to {f().name} ({f().years.toLocaleString()} yrs)
              </>
            )}
          </Show>
        </span>
        <Show when={props.pinned}>
          <button type="button" class="clr" onClick={() => props.onFocus(null)}>
            Clear ✕
          </button>
        </Show>
      </div>
      <div class="two">
        <PairList
          title="Cites"
          color="var(--net-arc-out)"
          pairs={out()}
          who={(p) => p.tgt}
          max={max()}
          byName={props.byName}
          onFocus={props.onFocus}
        />
        <PairList
          title="Cited by"
          color="var(--net-arc-in)"
          pairs={inn()}
          who={(p) => p.src}
          max={max()}
          byName={props.byName}
          onFocus={props.onFocus}
        />
      </div>
    </>
  );
}

function PairList(props: {
  title: string;
  color: string;
  pairs: AuthorPair[];
  who: (p: AuthorPair) => string;
  max: number;
  byName: ReadonlyMap<string, ArcAuthor>;
  onFocus: (name: string | null) => void;
}) {
  return (
    <div>
      <div class="ct">
        <i class="sw" style={{ background: props.color }} />
        {props.title}
      </div>
      <Show when={props.pairs.length > 0} fallback={<div class="empty">None in corpus.</div>}>
        <For each={props.pairs.slice(0, ROWS)}>
          {(p) => {
            const name = props.who(p);
            // An accessor: `byName` is a prop, and the callback body is
            // untracked, so a const would keep the first map it saw.
            const a = () => props.byName.get(name);
            return (
              <button type="button" class="li" onClick={() => props.onFocus(name)}>
                <span class="nm">
                  {name}
                  <Show when={a()?.dated}>
                    <span class="yr">{formatYearEra(a()?.year ?? 0)}</span>
                  </Show>
                </span>
                <Bar n={p.n} max={props.max} color={props.color} />
                <span class="v">{p.n.toLocaleString()}</span>
              </button>
            );
          }}
        </For>
      </Show>
    </div>
  );
}
