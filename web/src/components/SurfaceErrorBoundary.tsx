// A per-surface error boundary (#426).
//
// The app mounted none at all, which is why a single throw during render took
// the whole screen with it — or worse, froze it. Solid **rethrows** when an
// errored resource is read, so any failed fetch whose component read its
// resource outside an error guard threw out of the update the rejection
// triggered: the update was abandoned, the DOM kept whatever it last had, and
// the throw escaped to nothing. That produced the "stuck on Loading… forever"
// class of bug three separate times (#235 in the syntax overlay, #361 in the
// term card, #426 in the Reader's concordance rail).
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

import { ErrorBoundary, type JSX } from "solid-js";

export interface SurfaceErrorBoundaryProps {
  /** Human name of the surface, used in the fallback copy. */
  label: string;
  children: JSX.Element;
}

/** Best available human-readable reason for a caught throw.
 *
 *  Solid does not hand the fallback whatever was thrown. `castError`
 *  (`solid-js/dist/solid.cjs:990`) normalizes it first:
 *
 *      new Error(typeof err === "string" ? err : "Unknown error", { cause: err })
 *
 *  So an `Error` arrives intact, a thrown string arrives as its message, and
 *  **everything else arrives as the literal text "Unknown error" with the real
 *  value on `.cause`**. Reading only `err.message` therefore renders a useless
 *  detail line for exactly the case that needs one most — a rejected fetch whose
 *  body is an object. Unwrapping `cause` is the whole job here.
 *
 *  Found while covering this file: the first version of this function tried
 *  `JSON.stringify(err)` on the top-level value, which can never fire, because
 *  by the time the fallback runs the value is always an `Error`. */
function messageOf(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  if (err.message !== "Unknown error") return err.message;
  return describeCause(err.cause);
}

function describeCause(cause: unknown): string {
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
    <ErrorBoundary
      fallback={(err: unknown, reset: () => void) => {
        // Console as well as screen: the fallback copy is for the reader, the
        // stack is for whoever has to fix it. Before this boundary existed the
        // throw at least reached the console on its own; a boundary that
        // swallowed it would be a net loss for debugging.
        console.error(`[${props.label}] surface failed:`, err);
        return (
          <div class="surface-error" role="alert">
            <div class="surface-error__head">
              {props.label} could not be displayed.
            </div>
            <div class="surface-error__detail">{messageOf(err)}</div>
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
    </ErrorBoundary>
  );
}
