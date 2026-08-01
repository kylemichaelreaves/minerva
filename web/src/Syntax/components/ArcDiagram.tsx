import { For, Show, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import type { SyntaxToken } from "~/api/syntaxApi";
import {
  type Arc,
  apexY,
  arcPath,
  arcsOf,
  assignLevels,
  isNonProjective,
} from "~/Syntax/layout/arcs";
import { FIELD_NAMES, type FieldName, fieldRuns, topologicalFields } from "~/Syntax/layout/fields";
import { minimapTicks, visibleSpan } from "~/Syntax/layout/minimap";
import { TOKEN_GAP } from "~/Syntax/layout/measure";
import { type ArcSegment, breakRows, segmentArcs } from "~/Syntax/layout/rows";

// The diagram: a wrapped row of tokens with dependency arcs bracketing above,
// and non-projective arcs mirrored below. Position carries the discontinuity —
// a crossing arc is not a different colour, it is on the other side of the line.
//
// Widths come from the laid-out DOM rather than an estimate. Arc endpoints are
// token centres, so a few pixels of error reads as a bug, and German diacritics
// measure unpredictably.

/** Clearance above the tallest arc so labels are not clipped. */
const HEAD_ROOM = 26;
/** How far a cut segment stops short of the measure edge. */
const EDGE = 6;
/** Horizontal padding on `.syn-tok`, which the probe (a bare `.syn-form`)
 *  does not carry. Without it every row underestimates its own width by 8px
 *  per token and the last few overflow the measure. */
const TOKEN_PAD_X = 8;

export interface ArcDiagramProps {
  tokens: SyntaxToken[];
  /** Token whose subtree is isolated; everything else dims. */
  hovered: number | null;
  onHover: (id: number | null) => void;
  onSelect?: (id: number) => void;
  selected?: number | null;
  /** Token holding keyboard focus. Arrow keys move it. */
  focused?: number | null;
  /** The token being reattached, while a reattachment is in progress. */
  lifted?: number | null;
  /** Heads the lifted token may legally take — these ring. */
  candidates?: readonly number[];
  /** The candidate currently proposed, which the arc previews to. */
  proposed?: number | null;
  /** A target that was refused, flashed until dismissed. */
  refused?: number | null;
  /** Draw the derived topological fields under the row. */
  showFields?: boolean;
  /** Begin a pointer drag from this token. */
  onDragStart?: (id: number, e: PointerEvent) => void;
}

/** Every token governed by *root*, transitively — the constituent it heads. */
function subtreeOf(arcs: readonly Arc[], root: number): Set<number> {
  const kids = new Map<number, number[]>();
  for (const a of arcs) {
    const list = kids.get(a.head);
    if (list) list.push(a.dep);
    else kids.set(a.head, [a.dep]);
  }
  const out = new Set([root]);
  const stack = [root];
  while (stack.length) {
    const cur = stack.pop();
    if (cur === undefined) break;
    for (const kid of kids.get(cur) ?? []) {
      if (!out.has(kid)) {
        out.add(kid);
        stack.push(kid);
      }
    }
  }
  return out;
}

export function ArcDiagram(props: ArcDiagramProps) {
  const [measure, setMeasure] = createSignal(1200);
  const [widths, setWidths] = createSignal<Map<number, number>>(new Map());

  let host: HTMLDivElement | undefined;

  // Measure each token's width ONCE, from a hidden probe. A token's width does
  // not depend on which row it lands on, which is what breaks the circularity:
  // widths decide the row breaks, the row breaks decide the DOM, and measuring
  // the DOM would decide the widths. Row-local x positions are then computed
  // analytically from those widths and TOKEN_GAP — the same arithmetic the
  // flex row performs, so the arcs land exactly on the glyphs.
  //
  // Re-run when fonts resolve: measuring against fallback metrics places every
  // arc wrong on first paint and then snaps, which reads as broken.
  const remeasure = () => {
    if (!host) return;
    setMeasure(host.clientWidth || 1200);
    const probe = host.querySelector<HTMLElement>(".syn-probe");
    if (!probe) return;
    const next = new Map<number, number>();
    for (const cell of Array.from(probe.querySelectorAll<HTMLElement>("[data-probe]"))) {
      next.set(Number(cell.dataset.probe), cell.offsetWidth);
    }
    setWidths(next);
  };

  onMount(() => {
    remeasure();
    void document.fonts.ready.then(remeasure);
    const ro = new ResizeObserver(remeasure);
    if (host) ro.observe(host);
    onCleanup(() => {
      ro.disconnect();
    });
  });

  const arcs = createMemo(() => arcsOf(props.tokens));

  const levelled = createMemo(() => {
    const all = arcs();
    const projective = all.filter((a) => !isNonProjective(a, props.tokens));
    const crossing = all.filter((a) => isNonProjective(a, props.tokens));
    const withLevel = new Map<string, number>();
    for (const { arc, level } of assignLevels(projective))
      withLevel.set(`${arc.dep}>${arc.head}`, level);
    for (const { arc, level } of assignLevels(crossing))
      withLevel.set(`${arc.dep}>${arc.head}`, level);
    return {
      projective: projective.map((a) => ({
        ...a,
        level: withLevel.get(`${a.dep}>${a.head}`) ?? 1,
      })),
      crossing: crossing.map((a) => ({ ...a, level: withLevel.get(`${a.dep}>${a.head}`) ?? 1 })),
    };
  });

  /** Measured width, or a length-proportional estimate before first paint. */
  const widthOf = (id: number, form: string): number =>
    (widths().get(id) ?? form.length * 10) + TOKEN_PAD_X;

  const rows = createMemo(() =>
    breakRows(
      props.tokens,
      props.tokens.map((t) => widthOf(t.id, t.form)),
      measure(),
    ),
  );

  /** Row-local geometry: left edge and centre of every token, and the row's
   *  used width. Mirrors the flex row's own arithmetic. */
  const rowGeometry = createMemo(() => {
    const byId = new Map(props.tokens.map((t) => [t.id, t]));
    return rows().map((ids) => {
      const centre = new Map<number, number>();
      // Left and right edges too: an arc lands on a centre, but a field
      // bracket encloses whole tokens and has to reach past their glyphs.
      const edge = new Map<number, { l: number; r: number }>();
      let x = 0;
      for (const id of ids) {
        const w = widthOf(id, byId.get(id)?.form ?? "");
        centre.set(id, x + w / 2);
        edge.set(id, { l: x, r: x + w });
        x += w + TOKEN_GAP;
      }
      return { centre, edge, width: Math.max(0, x - TOKEN_GAP) };
    });
  });

  const segments = createMemo(() => {
    const r = rows();
    const l = levelled();
    return [...segmentArcs(l.projective, r, false), ...segmentArcs(l.crossing, r, true)];
  });

  const dimmed = createMemo(() => {
    const h = props.hovered;
    if (h === null) return null;
    return subtreeOf(arcs(), h);
  });

  const byId = createMemo(() => new Map(props.tokens.map((t) => [t.id, t])));

  // The one derived layer in the diagram. Recomputed from the live tree, so a
  // reattachment that fixes the parse moves the brackets with it — which is
  // the whole argument for deriving the fields rather than annotating them.
  const fields = createMemo(() => (props.showFields ? topologicalFields(props.tokens) : []));

  /** The bands to draw on one row: a field can span a wrap, and can be cut in
   *  two by material it does not claim.
   *
   *  `stagger` alternates by *field*, not by run, so a field crossing a wrap
   *  keeps the same vertical slot on both rows. The stagger is what lets the
   *  marks carry the full German names — `RECHTE KLAMMER` is wider than the
   *  one-token field it labels, and two of those on one line would collide. */
  const bandsFor = (rowIdx: number): { name: FieldName; l: number; r: number; stagger: boolean }[] => {
    const g = rowGeometry()[rowIdx];
    const ids = rows()[rowIdx];
    if (!g || !ids) return [];
    const isPunct = (id: number) => byId().get(id)?.upos === "PUNCT";
    const out: { name: FieldName; l: number; r: number; stagger: boolean }[] = [];
    fields().forEach((f, k) => {
      for (const run of fieldRuns(f.tokens, ids, isPunct)) {
        const first = g.edge.get(run[0] ?? -1);
        const last = g.edge.get(run[run.length - 1] ?? -1);
        if (first && last) out.push({ name: f.name, l: first.l, r: last.r, stagger: k % 2 === 1 });
      }
    });
    return out;
  };

  // ---- the whole-sentence strip ----
  //
  // Which rows are on screen, tracked with an IntersectionObserver rather
  // than a scroll listener on the pane: the diagram does not know which
  // ancestor scrolls it, and does not need to.
  const [visibleRows, setVisibleRows] = createSignal<ReadonlySet<number>>(new Set());

  const observeRow = (el: HTMLElement, rowIdx: number) => {
    const io = new IntersectionObserver(
      (entries) => {
        const on = entries.at(-1)?.isIntersecting ?? false;
        setVisibleRows((prev) => {
          if (prev.has(rowIdx) === on) return prev;
          const next = new Set(prev);
          if (on) next.add(rowIdx);
          else next.delete(rowIdx);
          return next;
        });
      },
      { threshold: 0 },
    );
    io.observe(el);
    onCleanup(() => {
      io.disconnect();
    });
  };

  const ticks = createMemo(() => {
    const l = levelled();
    return minimapTicks(props.tokens, [...l.projective, ...l.crossing]);
  });

  /** Deepest stack in the sentence, so tick heights scale to the tallest. */
  const maxDepth = createMemo(() => Math.max(1, ...ticks().map((t) => t.depth)));

  const frame = createMemo(() => {
    const span = visibleSpan(rows(), visibleRows());
    const n = props.tokens.length;
    if (!span || n === 0) return null;
    return { left: (span[0] / n) * 100, right: 100 - (span[1] / n) * 100 };
  });

  const segsFor = (rowIdx: number, below: boolean): ArcSegment[] =>
    segments().filter((s) => s.row === rowIdx && s.below === below);

  const stackHeight = (rowIdx: number, below: boolean): number => {
    const segs = segsFor(rowIdx, below);
    if (!segs.length) return 0;
    const top = Math.max(...segs.map((s) => s.level));
    return apexY(top, 1, 0, 0) * -1 + HEAD_ROOM;
  };

  return (
    <div class="syn-diagram" ref={host}>
      <div class="syn-probe" aria-hidden="true">
        <For each={props.tokens}>
          {(t) => (
            <span data-probe={t.id} class="syn-form">
              {t.form}
            </span>
          )}
        </For>
      </div>
      {/* Only when the sentence wraps. A strip over a sentence you can already
          see whole is decoration, and the design shows it on exactly one
          frame: the 53-token one. */}
      <Show when={rows().length > 1}>
        <div class="syn-minimap" aria-hidden="true">
          <div class="syn-minilab">
            <span>Whole sentence · {props.tokens.length} tokens</span>
            <span>arc depth</span>
          </div>
          <div class="syn-mini">
            <For each={ticks()}>
              {(t) => (
                <div
                  class={`syn-tick${t.corrected ? " syn-tick-corr" : ""}`}
                  style={{ height: `${String(6 + (t.depth / maxDepth()) * 26)}px` }}
                />
              )}
            </For>
            <Show when={frame()}>
              {(f) => (
                <div
                  class="syn-vp"
                  style={{ left: `${String(f().left)}%`, right: `${String(f().right)}%` }}
                />
              )}
            </Show>
          </div>
        </div>
      </Show>
      <For each={rows()}>
        {(ids, rowIdx) => {
          const above = () => stackHeight(rowIdx(), false);
          const below = () => stackHeight(rowIdx(), true);
          const geom = () => rowGeometry()[rowIdx()];
          const xOf = (k: number | "L" | "R"): number | null => {
            const g = geom();
            if (!g) return null;
            if (k === "L") return EDGE;
            if (k === "R") return Math.max(EDGE, g.width - EDGE);
            return g.centre.get(k) ?? null;
          };

          const stack = (isBelow: boolean, height: number) => (
            <svg width="100%" height={height} aria-hidden="true">
              <For each={segsFor(rowIdx(), isBelow)}>
                {(s) => {
                  const apex = () =>
                    isBelow ? -apexY(s.level, 1, 0, 0) : height + apexY(s.level, 1, 0, 0);
                  const rowY = () => (isBelow ? 0 : height);
                  const side = isBelow ? -1 : 1;
                  // Bundled so `Show`'s callback form narrows both at once —
                  // Solid cannot narrow two separate accessors through a
                  // boolean condition, and `!` on every use reads badly in
                  // geometry code where a null really would be a bug.
                  const at = (): { xh: number; xd: number } | null => {
                    const a = xOf(s.from);
                    const b = xOf(s.to);
                    return a === null || b === null ? null : { xh: a, xd: b };
                  };
                  const dimClass = () => {
                    const d = dimmed();
                    if (!d) return "";
                    const [depStr, headStr] = s.key.split(">");
                    const dep = Number(depStr);
                    const head = Number(headStr);
                    return d.has(dep) && d.has(head) ? "" : " syn-dim";
                  };
                  return (
                    <Show when={at()}>
                      {(c) => (
                        <g class={`syn-arcg syn-a-${s.below ? "np" : "mach"}${dimClass()}`}>
                          <path
                            class="syn-arc"
                            d={arcPath(c().xh, c().xd, apex(), rowY(), side, s.cutFrom, s.cutTo)}
                          />
                          <Show when={s.arrow}>
                            <polygon
                              points={`${c().xd},${rowY()} ${c().xd - 4},${rowY() - side * 8} ${c().xd + 4},${rowY() - side * 8}`}
                            />
                          </Show>
                          <Show when={!s.through}>
                            <text x={(c().xh + c().xd) / 2} y={apex() - side * 8} class="syn-rel">
                              {s.deprel}
                            </text>
                          </Show>
                          <Show when={s.cutTo || s.cutFrom}>
                            <text
                              class="syn-cut"
                              x={
                                s.cutTo
                                  ? c().xd - (s.to === "R" ? 4 : -4)
                                  : c().xh - (s.from === "R" ? 4 : -4)
                              }
                              y={apex() - side * 5}
                              text-anchor={(s.cutTo ? s.to : s.from) === "R" ? "end" : "start"}
                            >
                              {(s.cutTo ? s.to : s.from) === "R"
                                ? `→ ${s.partner}`
                                : `← ${s.partner}`}
                            </text>
                          </Show>
                        </g>
                      )}
                    </Show>
                  );
                }}
              </For>
            </svg>
          );

          // Frame 06's token states, in priority order: the word being moved
          // is `lifted`, the target under consideration is `head-of cand`,
          // a refused target is `bad`, and everything else it could legally
          // go to merely rings.
          const reattachState = (id: number): string => {
            if (props.lifted == null) return "";
            if (id === props.refused) return " syn-bad";
            if (id === props.lifted) return " syn-lifted";
            if (id === props.proposed) return " syn-cand syn-head-of";
            return props.candidates?.includes(id) ? " syn-cand" : "";
          };

          return (
            <div
              class="syn-rowblock"
              ref={(el) => {
                observeRow(el, rowIdx());
              }}
            >
              <div class="syn-above" style={{ height: `${above()}px` }}>
                {stack(false, above())}
              </div>
              <div class="syn-toks" onMouseLeave={() => props.onHover(null)}>
                <For each={ids}>
                  {(id) => {
                    const t = () => byId().get(id);
                    const state = () => {
                      const d = dimmed();
                      if (props.selected === id) return " syn-focus";
                      if (!d) return "";
                      if (id === props.hovered) return " syn-head-of";
                      return d.has(id) ? " syn-sub" : " syn-dimtok";
                    };
                    return (
                      <button
                        type="button"
                        data-tok={id}
                        data-row={rowIdx()}
                        // One tab stop for the whole diagram: Tab reaches the
                        // tokens, then arrows move between them. Fifty-three
                        // tab stops in a row is not navigation.
                        tabindex={props.focused === id || (props.focused === null && id === ids[0]) ? 0 : -1}
                        ref={(el) => {
                          if (props.focused === id) queueMicrotask(() => el.focus());
                        }}
                        aria-label={`${t()?.form ?? ""}, token ${String(id)}`}
                        aria-current={props.focused === id ? "true" : undefined}
                        class={`syn-tok${t()?.upos === "PUNCT" ? " syn-punct" : ""}${
                          t()?.head === 0 ? " syn-root" : ""
                        }${t()?.corrected ? " syn-corr" : ""}${state()}${reattachState(id)}`}
                        onMouseEnter={() => props.onHover(id)}
                        onPointerDown={(e) => props.onDragStart?.(id, e)}
                        onClick={() => props.onSelect?.(id)}
                      >
                        <div class="syn-form">{t()?.form}</div>
                        <div class="syn-ix">{id}</div>
                      </button>
                    );
                  }}
                </For>
              </div>
              <Show when={below() > 0}>
                <div class="syn-below" style={{ height: `${below()}px` }}>
                  {stack(true, below())}
                </div>
              </Show>
              {/* Under the non-projective stack rather than tight against the
                  row: frame 04 has both, and an inferred bracket must not
                  crowd out a parsed arc. */}
              <Show when={bandsFor(rowIdx()).length > 0}>
                <div class="syn-fields" aria-hidden="true">
                  <For each={bandsFor(rowIdx())}>
                    {(b) => (
                      <div
                        class={`syn-field${b.stagger ? " syn-stag" : ""}`}
                        style={{ left: `${String(b.l - 4)}px`, width: `${String(b.r - b.l + 8)}px` }}
                      >
                        <span>{FIELD_NAMES[b.name]}</span>
                      </div>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          );
        }}
      </For>
    </div>
  );
}

export { subtreeOf, TOKEN_GAP };
