// A per-surface error boundary (#426).
//
// The app mounted none at all, which is why a single throw during render took
// the whole screen with it — or worse, froze it. Solid 1 **rethrew** when an
// errored resource was read, so any failed fetch whose component read its
// resource outside an error guard threw out of the update the rejection
// triggered: the update was abandoned, the DOM kept whatever it last had, and
// the throw escaped to nothing. That produced the "stuck on Loading… forever"
// class of bug three separate times (#235 in the syntax overlay, #361 in the
// term card, #426 in the Reader's concordance rail). In Solid 2 a rejected
// async memo flows to the nearest `<Errored>` the same way, so this is still
// where an unguarded failed fetch lands.
//
// Those three are fixed at the site, by not reading a resource that failed.
// This is the net under everything else, including throws that have nothing to
// do with resources. Two rules it follows deliberately:
//
//   * It shows the underlying message. A boundary that hides the reason turns a
//     frozen surface into a silent one, which is the same defect wearing a
//     nicer coat.
//   * It offers a retry, because most of what lands here is transient — a
//     backend that was restarting when the request went out.
//
// `label` names the surface so the fallback is not a generic apology: a reader
// who sees "The concordance could not be displayed" knows the rest of the app
// is fine and knows what to retry.

import { Errored, createEffect } from "solid-js";
import type { JSX } from "@solidjs/web";

export interface SurfaceErrorBoundaryProps {
  /** Human name of the surface, used in the fallback copy. */
  label: string;
  children: JSX.Element;
}

/** Best available human-readable reason for a caught throw.
 *
 *  Solid 2's `<Errored>` hands the fallback exactly what was thrown. (Solid 1
 *  normalized it through `castError` into `new Error("Unknown error", { cause })`
 *  for anything but an `Error` or a string, and this function used to unwrap
 *  `.cause`; that wrapper is gone.) So an `Error` shows its message and
 *  anything else — a rejected fetch whose body is an object, most usefully —
 *  is described by `describeValue` rather than rendered as "[object Object]". */
function messageOf(err: unknown): string {
  if (err instanceof Error) return err.message;
  return describeValue(err);
}

function describeValue(cause: unknown): string {
  if (cause === undefined) return "Unknown error";
  if (typeof cause === "string") return cause;
  if (typeof cause === "number" || typeof cause === "boolean" || typeof cause === "bigint") {
    return String(cause);
  }
  // The two types `JSON.stringify` answers `undefined` for at runtime, even
  // though TypeScript types the call as returning `string`. Handled here so the
  // stringify below genuinely cannot come back empty.
  if (typeof cause === "function" || typeof cause === "symbol") {
    return Object.prototype.toString.call(cause);
  }
  try {
    // Circular payloads throw here — inside an error boundary's fallback,
    // which is the worst place left to throw.
    return JSON.stringify(cause);
  } catch {
    // fall through to the tag below
  }
  // `Object.prototype.toString` rather than `String(cause)`: the latter invokes
  // a user-supplied `toString`, which on the value that just broke
  // `JSON.stringify` is not somewhere to go looking for more trouble.
  return Object.prototype.toString.call(cause);
}

export default function SurfaceErrorBoundary(
  props: SurfaceErrorBoundaryProps,
): JSX.Element {
  return (
    <Errored
      fallback={(err, reset) => {
        // Console as well as screen: the fallback copy is for the reader, the
        // stack is for whoever has to fix it. Before this boundary existed the
        // throw at least reached the console on its own; a boundary that
        // swallowed it would be a net loss for debugging. An effect on the
        // error accessor, so a second failure caught while the fallback is
        // already showing is logged too.
        createEffect(
          () => err(),
          (e) => {
            console.error(`[${props.label}] surface failed:`, e);
          },
        );
        return (
          <div class="surface-error" role="alert">
            <div class="surface-error__head">
              {props.label} could not be displayed.
            </div>
            <div class="surface-error__detail">{messageOf(err())}</div>
            <button
              type="button"
              class="surface-error__retry"
              onClick={() => {
                reset();
              }}
            >
              Try again
            </button>
          </div>
        );
      }}
    >
      {props.children}
    </Errored>
  );
}
