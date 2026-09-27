/**
 * Unwrap a value a test expects to exist, or fail naming what was missing.
 *
 * Replaces the `x!` non-null assertion in tests (#689). `x!` only silences the
 * type checker: a missing element then fails later as an unhelpful
 * `Cannot read properties of null`, far from the lookup that returned it.
 */
export function must<T>(value: T | null | undefined, what = "value"): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to be present, got ${String(value)}`);
  }
  return value;
}
