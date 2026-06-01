type Classy = string | false | null | undefined;

export function classnames(...xs: Classy[]): string {
  return xs.filter(Boolean).join(" ");
}

/**
 * True when `err` looks like an abort signal. Aborts come in several
 * shapes across runtimes:
 *
 *   * `DOMException` with `name === "AbortError"` (the standard
 *     fetch-abort shape in browsers and Node 17+)
 *   * Plain `Error` with `name === "AbortError"` (some polyfills and
 *     older test environments)
 *   * Other host objects that carry the same `name`
 *
 * Crucially, `DOMException` does NOT extend `Error` in every JS
 * environment (jsdom in particular), so an `err instanceof Error`
 * guard lets the canonical abort shape slip through. Duck-typing on
 * `name` is the cross-environment-safe check.
 */
export function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    err.name === "AbortError"
  );
}

/** User-visible message from a caught unknown value. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
