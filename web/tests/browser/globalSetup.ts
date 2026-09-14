// One server for the whole run. Playwright calls this once before any spec
// and awaits the returned teardown after the last one.
//
// The URL travels through the environment rather than a module export
// because globalSetup runs in a different process from the specs.

import { startFixtureServer } from "../helpers/fixtureServer";

export default async function globalSetup(): Promise<() => void> {
  const server = await startFixtureServer();
  process.env.MINERVA_E2E_BASE_URL = server.baseUrl;
  return () => {
    server.stop();
  };
}
