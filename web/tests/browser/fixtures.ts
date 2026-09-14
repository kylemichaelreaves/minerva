// Every spec imports `test`/`expect` from here, never from @playwright/test.
//
// `baseURL` is an option fixture rather than a `use.baseURL` in the config
// because the config is evaluated BEFORE globalSetup runs — reading
// process.env there yields undefined. Overriding the fixture defers the read
// to test time, when the server is up.

import { test as base, expect } from "@playwright/test";

export const test = base.extend<object, object>({
  baseURL: async ({}, use) => {
    const url = process.env.MINERVA_E2E_BASE_URL;
    if (!url) {
      throw new Error(
        "MINERVA_E2E_BASE_URL is unset — globalSetup did not run or failed. " +
          "Not falling back to a default port: a fallback would silently " +
          "test whatever server happened to be listening.",
      );
    }
    await use(url);
  },
});

export { expect };
