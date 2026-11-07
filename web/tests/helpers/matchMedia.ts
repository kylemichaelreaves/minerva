/**
 * A stand-in `MediaQueryList` for tests that mock `window.matchMedia`.
 *
 * lib.dom still types `addListener`/`removeListener` as required members, so a
 * fake has to define them — and typescript-eslint >= 8.72 flags defining a
 * deprecated member under `no-deprecated`. Keeping the one fake here keeps the
 * one suppression here, instead of in every test that mocks the query.
 */
export function fakeMediaQueryList(query: string, matches: boolean): MediaQueryList {
  return {
    matches,
    media: query,
    onchange: null,
    /* eslint-disable @typescript-eslint/no-deprecated -- required by lib.dom's MediaQueryList; some libs still call the legacy API */
    addListener: () => undefined,
    removeListener: () => undefined,
    /* eslint-enable @typescript-eslint/no-deprecated */
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  };
}
