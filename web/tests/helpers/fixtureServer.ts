// Stands up the real Python server against a throwaway index built from the
// committed fixture corpus. Shared by two suites with different runners:
// `tests/e2e/serve.test.ts` (vitest, node env, drives the API through fetch)
// and `tests/browser/globalSetup.ts` (Playwright, drives the built bundle in
// Chromium). It lives here rather than in either suite because both are
// siblings and neither owns it — and because copying it would put the two
// copies straight into Sonar's duplication gate (#254).

import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const MINERVA_BIN = resolve(REPO_ROOT, ".venv/bin/minerva");
const STATIC_DIR = resolve(REPO_ROOT, "web/dist");
const FIXTURE_JSONL = resolve(REPO_ROOT, "tests/fixtures/corpus.jsonl");

export interface FixtureServer {
  baseUrl: string;
  stop: () => void;
}

export function minervaBinPath(): string {
  return MINERVA_BIN;
}

/** Gate on the venv binary ONLY. A missing Python install is a legitimate
 *  environment difference; a missing fixture is not — it is committed, so
 *  its absence means something is wrong and startup should say so loudly
 *  rather than skip. Skipping on a missing fixture would rebuild the exact
 *  trap this suite was fixed to escape (#133). */
export function hasMinervaBin(): boolean {
  return existsSync(MINERVA_BIN);
}

export function fixtureChunkCount(): number {
  return readFileSync(FIXTURE_JSONL, "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0).length;
}

function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", rej);
    srv.listen(0, () => {
      const addr = srv.address();
      if (addr && typeof addr === "object") {
        const { port } = addr;
        srv.close(() => {
          res(port);
        });
      } else {
        srv.close(() => {
          rej(new Error("could not bind ephemeral port"));
        });
      }
    });
  });
}

async function waitForHealth(url: string, timeoutMs = 15000): Promise<unknown> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.json();
    } catch (_) {
      // server not up yet
    }
    await new Promise((res) => setTimeout(res, 150));
  }
  throw new Error(`server at ${url} did not become ready within ${timeoutMs}ms`);
}

export async function startFixtureServer(): Promise<FixtureServer> {
  const port = await freePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  // Index and conversations DB both live in a tmp dir for the run, so
  // we neither read nor pollute the developer's data/ directory.
  const tmpDir = mkdtempSync(join(tmpdir(), "minerva-e2e-"));
  const indexDb = join(tmpDir, "index.sqlite");
  const convDb = join(tmpDir, "conversations.sqlite");

  // `proc` is declared here, outside the try, so the catch below can see
  // and kill it regardless of which line inside the try throws. Every
  // throw path — missing fixture, failed index build, health timeout, or
  // a chunk-count mismatch — has to reach the same cleanup, or a failed
  // setup leaks a real `minerva serve` process that outlives the run.
  let proc: ChildProcess | undefined;
  try {
    if (!existsSync(FIXTURE_JSONL)) {
      throw new Error(
        `fixture corpus missing at ${FIXTURE_JSONL}. It is committed — ` +
          `see tests/fixtures/README.md. Not skipping: a silent skip here ` +
          `is the bug this suite was fixed to avoid (#133).`,
      );
    }

    // Build the throwaway index before booting. 120 chunks, ~1s — no
    // embeddings, which retrieval doesn't need under `--llm none`.
    const built = spawnSync(
      MINERVA_BIN,
      ["index", "--db", indexDb, "--input", FIXTURE_JSONL, "--reset"],
      { cwd: REPO_ROOT, encoding: "utf8" },
    );
    if (built.status !== 0) {
      throw new Error(
        `fixture index build failed (exit ${String(built.status)}):\n` +
          `${built.stdout}\n${built.stderr}\n${String(built.error)}\n` +
          `If MINERVA_BIN is missing, run \`uv sync\` to create .venv/ first.`,
      );
    }

    proc = spawn(
      MINERVA_BIN,
      [
        "serve",
        "--llm",
        "none",
        "--port",
        String(port),
        "--db",
        indexDb,
        "--static",
        STATIC_DIR,
        "--conversations-db",
        convDb,
      ],
      { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] },
    );
    proc.stderr?.on("data", (b: Buffer) => process.stderr.write(`[serve] ${b.toString()}`));

    const health = (await waitForHealth(`${baseUrl}/api/health`)) as {
      chunks_total?: number;
    };
    const expected = fixtureChunkCount();
    // Asserting the exact count (derived from the fixture, so it stays
    // correct if the fixture changes) also proves we are serving the
    // throwaway index and not some other database that happened to be
    // lying around — which is precisely how the old setup went wrong.
    if (health.chunks_total !== expected) {
      throw new Error(
        `served index has ${String(health.chunks_total)} chunks, fixture has ` +
          `${String(expected)} — the server is reading some other database.`,
      );
    }
  } catch (e) {
    proc?.kill("SIGTERM");
    rmSync(tmpDir, { recursive: true, force: true });
    throw e;
  }

  return {
    baseUrl,
    stop: () => {
      if (!proc.killed) proc.kill("SIGTERM");
      rmSync(tmpDir, { recursive: true, force: true });
    },
  };
}
