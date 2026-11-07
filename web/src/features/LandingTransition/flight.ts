// Geometry for the landing → chat transition: where the question and the
// composer start (measured on the landing, before the swap) and where they
// land (measured in the chat, right after it), turned into Web Animations
// keyframes. Reads only — nothing here writes to the DOM.
//
// The question cannot be a scaled snapshot: it wraps at ~648px in the
// landing box and at the user turn's width in the thread, so it travels as
// real text whose box and font animate, and it reflows on the way.

export interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** Animate over the whole flight. */
export const MORPH_PROPS = ["fontSize", "lineHeight", "color", "fontStyle"] as const;
/** Fade in from transparent over the flight's last stretch (the user turn's
 *  rule on desktop, the bubble's fill and border on mobile). */
export const CHROME_PROPS = [
  "backgroundColor",
  "borderTopColor",
  "borderRightColor",
  "borderBottomColor",
  "borderLeftColor",
] as const;
/** Copied from the landed body and held fixed for the whole flight, so the
 *  ghost's text box never changes shape except by its width. `white-space`
 *  is deliberately not among them: the ghost is `pre-wrap` like the
 *  textarea (landingTransition.css), so frame 0 matches what you typed line
 *  for line; the user turn collapses line breaks, so a multi-line question
 *  settles into the turn's wrapping when the real body takes over. */
export const FRAME_PROPS = [
  "fontFamily",
  "fontWeight",
  "letterSpacing",
  "overflowWrap",
  "wordBreak",
  "paddingTop",
  "paddingRight",
  "paddingBottom",
  "paddingLeft",
  "borderTopWidth",
  "borderRightWidth",
  "borderBottomWidth",
  "borderLeftWidth",
  "borderTopStyle",
  "borderRightStyle",
  "borderBottomStyle",
  "borderLeftStyle",
] as const;

export type MorphProp = (typeof MORPH_PROPS)[number];
export type ChromeProp = (typeof CHROME_PROPS)[number];
export type FrameProp = (typeof FRAME_PROPS)[number];

export interface FlightOrigin {
  text: string;
  textTop: number;
  textLeft: number;
  textWidth: number;
  /** How far the question is scrolled inside the textarea, and how much of
   *  it shows: frame 0 clips the ghost to that window. */
  scrollTop: number;
  visibleHeight: number;
  style: Record<MorphProp, string>;
  box: Rect;
}

export interface FlightTarget {
  body: Rect;
  style: Record<MorphProp | ChromeProp | FrameProp, string>;
  composer: Rect;
}

function rectOf(el: Element): Rect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

function px(value: string): number {
  return Number.parseFloat(value) || 0;
}

function pick<K extends string>(cs: CSSStyleDeclaration, props: readonly K[]): Record<K, string> {
  // Every name in the prop lists is a string-valued longhand, so index the
  // declaration as a plain record (`cs[p]` types as possibly a method).
  const values = cs as unknown as Record<string, string>;
  const out = {} as Record<K, string>;
  for (const p of props) out[p] = values[p] ?? "";
  return out;
}

export function measureOrigin(textarea: HTMLTextAreaElement, box: HTMLElement): FlightOrigin {
  const r = textarea.getBoundingClientRect();
  const cs = getComputedStyle(textarea);
  return {
    // What `createComposer.send` submits — the ghost must say the same thing.
    text: textarea.value.trim(),
    // Minus `scrollTop`: a question taller than the textarea's max height is
    // scrolled inside it, and the ghost carries the whole of it, first line
    // included.
    textTop: r.top + px(cs.borderTopWidth) + px(cs.paddingTop) - textarea.scrollTop,
    textLeft: r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft),
    textWidth: textarea.clientWidth - px(cs.paddingLeft) - px(cs.paddingRight),
    scrollTop: textarea.scrollTop,
    visibleHeight: textarea.clientHeight - px(cs.paddingTop) - px(cs.paddingBottom),
    style: pick(cs, MORPH_PROPS),
    box: rectOf(box),
  };
}

export function measureTarget(body: HTMLElement, composer: HTMLElement): FlightTarget {
  return {
    body: rectOf(body),
    style: pick(getComputedStyle(body), [...MORPH_PROPS, ...CHROME_PROPS, ...FRAME_PROPS]),
    composer: rectOf(composer),
  };
}

export function ghostKeyframes(
  o: FlightOrigin,
  t: FlightTarget,
): { move: Keyframe[]; chrome: Keyframe[] } {
  // The ghost wears the target's padding and border widths throughout, so
  // its outer box at the origin is the text origin pushed out by them.
  const s = t.style;
  const insetLeft = px(s.paddingLeft) + px(s.borderLeftWidth);
  const insetTop = px(s.paddingTop) + px(s.borderTopWidth);
  const insetX = insetLeft + px(s.paddingRight) + px(s.borderRightWidth);

  // The ghost carries the whole question, but on frame 0 shows only the
  // window the textarea showed — a long, scrolled question would otherwise
  // appear above the box, over the owl — and opens to all of it in flight.
  const windowTop = o.scrollTop + insetTop;
  const from: Keyframe = {
    top: `${o.textTop - insetTop}px`,
    left: `${o.textLeft - insetLeft}px`,
    width: `${o.textWidth + insetX}px`,
    clipPath: `inset(${windowTop}px 0px calc(100% - ${windowTop + o.visibleHeight}px) 0px)`,
  };
  const to: Keyframe = {
    top: `${t.body.top}px`,
    left: `${t.body.left}px`,
    width: `${t.body.width}px`,
    clipPath: "inset(0px 0px 0px 0px)",
  };
  for (const p of MORPH_PROPS) {
    from[p] = o.style[p];
    to[p] = s[p];
  }

  const clear: Keyframe = {};
  const shown: Keyframe = {};
  for (const p of CHROME_PROPS) {
    clear[p] = "transparent";
    shown[p] = s[p];
  }
  return { move: [from, to], chrome: [clear, shown] };
}

/** How far to move a bottom-anchored box so that, once it is `from`'s
 *  height, it sits exactly on `from`: centre onto centre, and bottom onto
 *  bottom — which, at that height, is top onto top. */
export function settleOffset(from: Rect, to: Rect): { dx: number; dy: number } {
  return {
    dx: from.left + from.width / 2 - (to.left + to.width / 2),
    dy: from.top + from.height - (to.top + to.height),
  };
}

/** The real chat composer, FLIPped onto the landing box: its centre onto
 *  the box's centre, and its width and height onto the box's — so frame 0
 *  is the landing box, whatever the question's length. The composer wrap is
 *  pinned to the bottom of the page, so a height change moves the box's
 *  top, not its bottom: the wrap's translate aligns bottoms. The scope pill
 *  sits in the box's footer on both ends, so it rides with these two and
 *  needs no animation of its own. */
export function composerKeyframes(
  o: FlightOrigin,
  t: FlightTarget,
): { wrap: Keyframe[]; box: Keyframe[] } {
  const { dx, dy } = settleOffset(o.box, t.composer);
  return {
    wrap: [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0px, 0px)" }],
    box: [
      { maxWidth: `${o.box.width}px`, height: `${o.box.height}px` },
      { maxWidth: `${t.composer.width}px`, height: `${t.composer.height}px` },
    ],
  };
}
