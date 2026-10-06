// #761: a surface that throws inside <SurfaceErrorBoundary> logs
// "[<label>] surface failed:" and renders a fallback — so the test around it
// kept passing. Reader keep-alive tests ran green for months while the
// Concordance and Network surfaces crashed on `{}` fetch mocks, asserting on a
// loading skeleton or on the error fallback itself. tests/setup.ts records
// every such log and fails the test that produced it, unless the test said it
// expects one.

const recorded: string[] = [];
let expected = false;

/** Call from a test (or its beforeEach) that crashes a surface on purpose. */
export function expectSurfaceFailures(): void {
  expected = true;
}

export function recordSurfaceFailure(args: unknown[]): void {
  const [prefix, cause] = args;
  const detail = cause instanceof Error ? `${cause.name}: ${cause.message}` : String(cause);
  recorded.push(`${String(prefix)} ${detail}`);
}

/** Drain the record; throw if a surface failed in a test that didn't expect it. */
export function assertNoUnexpectedSurfaceFailures(): void {
  const failures = recorded.splice(0);
  const wasExpected = expected;
  expected = false;
  if (failures.length > 0 && !wasExpected) {
    throw new Error(
      `a surface crashed into its error boundary during this test:\n  ${failures.join("\n  ")}\n` +
        "Mock what it fetches, or call expectSurfaceFailures() if the crash is the point (#761).",
    );
  }
}
