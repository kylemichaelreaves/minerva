// Integration test: build a throwaway index from the committed fixture
// corpus, spawn the real Python server (`minerva serve --llm none`) against
// it on an ephemeral port, drive the API through node fetch, and assert the
// response shapes. Skipped only when the venv binary isn't present, so this
// won't fail in environments without Python.
//
// The whole suite runs identically in CI and locally. It did not use to:
// the server ran against the developer's gitignored `data/index.sqlite`, so
// in CI every data-dependent test skipped itself and the assertions rotted
// unnoticed until someone ran them by hand (#133).
//
// @vitest-environment node

import { describe, it, expect, beforeAll, afterAll } from "vitest";
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
// Committed slice of the real corpus. The server used to run against the
// developer's `data/index.sqlite`, which is gitignored and absent in CI —
// so every data-dependent test skipped there and only ever ran locally,
// where nobody watched them (#133). Building a throwaway index from this
// makes the suite behave identically in both places.
const FIXTURE_JSONL = resolve(REPO_ROOT, "tests/fixtures/corpus.jsonl");
// Gate on the venv binary ONLY. A missing Python install is a legitimate
// environment difference; a missing fixture is not — it is committed, so
// its absence means something is wrong and beforeAll should say so loudly
// rather than skip. Skipping on a missing fixture would rebuild the exact
// trap this file was fixed to escape.
const RUN_E2E = existsSync(MINERVA_BIN);
const describeOrSkip = RUN_E2E ? describe : describe.skip;

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

describeOrSkip("e2e: minerva serve --llm none", () => {
  let proc: ChildProcess;
  let baseUrl: string;
  let tmpDir: string;

  beforeAll(async () => {
    const port = await freePort();
    baseUrl = `http://127.0.0.1:${port}`;
    // Index and conversations DB both live in a tmp dir for the run, so
    // we neither read nor pollute the developer's data/ directory.
    tmpDir = mkdtempSync(join(tmpdir(), "minerva-e2e-"));
    const indexDb = join(tmpDir, "index.sqlite");
    const convDb = join(tmpDir, "conversations.sqlite");

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
          `${built.stdout}\n${built.stderr}`,
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
    // No `hasCorpus` escape hatch any more: the fixture is committed, so
    // an empty index is a real failure rather than an environment quirk.
    //
    // Asserting the exact count (derived from the fixture, so it stays
    // correct if the fixture changes) also proves we are serving the
    // throwaway index and not some other database that happened to be
    // lying around — which is precisely how the old setup went wrong.
    const fixtureChunks = readFileSync(FIXTURE_JSONL, "utf8")
      .split("\n")
      .filter((l) => l.trim().length > 0).length;
    expect(health.chunks_total).toBe(fixtureChunks);
  }, 60_000);

  afterAll(() => {
    if (!proc.killed) {
      proc.kill("SIGTERM");
    }
    if (tmpDir) {
      rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  interface WorkRow {
    work_id: number;
    corpus: string;
    author: string;
    work: string;
    lang: string;
    chunks: number;
  }

  async function fetchWorks(): Promise<WorkRow[]> {
    const r = await fetch(`${baseUrl}/api/works`);
    expect(r.ok).toBe(true);
    return ((await r.json()) as { works: WorkRow[] }).works;
  }

  /** The biggest work in `corpus`, as served.
   *
   * Corpus ids are manifest-generated and stable; work titles are not
   * (Plato's were all renamed once already). Deriving the row at run
   * time is what keeps these tests from going stale again — see #133.
   */
  async function pickLargestWork(corpus: string): Promise<WorkRow> {
    const rows = (await fetchWorks()).filter((w) => w.corpus === corpus);
    expect(rows.length).toBeGreaterThan(0);
    return rows.reduce((a, b) => (b.chunks > a.chunks ? b : a));
  }

  it("GET /api/health returns chunk stats", async () => {
    const r = await fetch(`${baseUrl}/api/health`);
    expect(r.ok).toBe(true);
    const json = (await r.json()) as Record<string, unknown>;
    expect(json.backend).toBe("none");
    expect(typeof json.chunks_total).toBe("number");
    expect(json.chunks_total as number).toBeGreaterThan(0);
    expect(Array.isArray(json.chunks_by_corpus_lang)).toBe(true);
  });

  it("POST /api/chat scopes retrieval to a work named in the query", async () => {
    // Naming a work must make the server-side detectors
    // (`agent.detect_corpus` + `agent.detect_work`) narrow retrieval to
    // that one work. The title comes from /api/works rather than a
    // literal: this assertion used to hardcode "Republic" and went
    // stale the moment Plato's titles were canonicalised to
    // Latinized-Greek, failing locally while CI skipped it (#133).
    //
    // Note this exercises the *canonical* title (`works.title`). The
    // English and German names live in `title_local` and do NOT scope
    // today — that's #164, and it is deliberately not pinned here.
    // Both levels are needed and both come from the served row: the
    // author name is what `detect_corpus` keys on, and only once a
    // corpus is resolved does `detect_work` run at all. Naming the work
    // without the author leaves retrieval corpus-wide.
    const target = await pickLargestWork("plato");
    const named = target.work;
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        query: `the divided line in ${target.author}'s ${named}`,
        history: [],
      }),
    });
    expect(r.ok).toBe(true);
    const json = (await r.json()) as {
      backend: string;
      abstained: boolean;
      dominant: string;
      paragraphs: unknown;
      citations: { src: string }[];
    };
    expect(json).toMatchObject({
      backend: "none",
      abstained: false,
      // `expect.stringMatching` returns an asymmetric matcher typed as
      // `any` — the linter's `no-unsafe-assignment` can't see through it.
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      dominant: expect.stringMatching(/^[PAHK]$/),
    });
    expect(Array.isArray(json.paragraphs)).toBe(true);
    expect(Array.isArray(json.citations)).toBe(true);
    expect(json.citations.length).toBeGreaterThan(0);
    // Every citation must come from the work that was named. This is
    // the property the old `Republic 509` assertion was really standing
    // in for, minus the retrieval-quality claim — 509 is no longer
    // returned even when scoping works, which is #165 and belongs in
    // `minerva eval` rather than a contract test.
    const offWork = json.citations.map((c) => c.src).filter((s) => !s.includes(named));
    expect(offWork).toEqual([]);
    // Two round-trips (works list, then chat) against the full index —
    // the 5s default is not enough once /api/works is in the path.
  }, 30_000);

  it("POST /api/chat abstains on a nonsense query", async () => {
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "zxqv asdf qwer" }),
    });
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { abstained: boolean; paragraphs: string[] };
    expect(json.abstained).toBe(true);
    expect(json.paragraphs[0]).toMatch(/could not find enough evidence/i);
  }, 30_000);

  it("POST /api/chat 400s on an empty query", async () => {
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "   " }),
    });
    expect(r.status).toBe(400);
    const json = (await r.json()) as { error: string };
    expect(json.error).toMatch(/empty 'query'/);
  });

  it("OPTIONS preflight returns CORS headers", async () => {
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "OPTIONS",
      headers: { Origin: baseUrl },
    });
    expect(r.status).toBe(204);
    expect(r.headers.get("access-control-allow-origin")).toBe(baseUrl);
    expect(r.headers.get("access-control-allow-methods")).toMatch(/POST/);
    expect(r.headers.get("access-control-allow-methods")).toMatch(/DELETE/);
  });

  // ---------- Conversation persistence ----------

  it("POST /api/chat without conversation_id mints one and returns title", async () => {
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "Where is the divided line introduced?" }),
    });
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { conversation_id: string; title: string };
    expect(typeof json.conversation_id).toBe("string");
    expect(json.conversation_id.length).toBeGreaterThan(5);
    expect(json.title).toMatch(/Where is the divided line/);
  }, 30_000);

  it("GET /api/conversations lists persisted conversations", async () => {
    // Seed at least one.
    await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "Republic 514a" }),
    });
    const r = await fetch(`${baseUrl}/api/conversations`);
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { conversations: { id: string; title: string }[] };
    expect(json.conversations.length).toBeGreaterThan(0);
    expect(json.conversations[0]!.id).toBeDefined();
  }, 30_000);

  it("GET /api/conversations/:id returns the message history", async () => {
    const create = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "On the cave" }),
    });
    const { conversation_id } = (await create.json()) as { conversation_id: string };
    const r = await fetch(`${baseUrl}/api/conversations/${conversation_id}`);
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { id: string; messages: { role: string }[] };
    expect(json.id).toBe(conversation_id);
    expect(json.messages.length).toBe(2);
    expect(json.messages[0]!.role).toBe("user");
    expect(json.messages[1]!.role).toBe("assistant");
  }, 30_000);

  it("DELETE /api/conversations/:id removes it (subsequent GET 404s)", async () => {
    const create = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "Phaedo on recollection" }),
    });
    const { conversation_id } = (await create.json()) as { conversation_id: string };
    const del = await fetch(`${baseUrl}/api/conversations/${conversation_id}`, {
      method: "DELETE",
    });
    expect(del.status).toBe(204);
    const after = await fetch(`${baseUrl}/api/conversations/${conversation_id}`);
    expect(after.status).toBe(404);
  }, 30_000);

  it("DELETE on an unknown id returns 404", async () => {
    const r = await fetch(`${baseUrl}/api/conversations/abcdef1234`, { method: "DELETE" });
    expect(r.status).toBe(404);
  });

  it("rejects malformed conversation ids with 400", async () => {
    // The path regex matches /api/conversations/<anything>, but the handler
    // validates the id format and surfaces 400.
    const r = await fetch(`${baseUrl}/api/conversations/bad@id`, { method: "DELETE" });
    expect(r.status).toBe(400);
  });

  it("a second turn with conversation_id appends to the same thread", async () => {
    const first = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "What is virtue?" }),
    });
    const { conversation_id: cid } = (await first.json()) as { conversation_id: string };
    const second = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "And how is it taught?", conversation_id: cid }),
    });
    const body = (await second.json()) as { conversation_id: string; title?: string };
    expect(body.conversation_id).toBe(cid);
    // Title is only emitted on the first turn.
    expect(body.title).toBeUndefined();
    const detail = await fetch(`${baseUrl}/api/conversations/${cid}`);
    const json = (await detail.json()) as { messages: { role: string }[] };
    expect(json.messages.map((m) => m.role)).toEqual(["user", "assistant", "user", "assistant"]);
  });

  // ---------- Reader: /api/works, /api/works/:id, /api/translate ----------

  it("GET /api/works returns well-formed rows for the ingested corpora", async () => {
    // Contract, not content. This used to assert a literal
    // `w.work === "Republic"`, which the Plato rename invalidated
    // (#133). Corpus ids are generated from manifest.yaml and are the
    // stable thing to assert on; titles are not.
    const works = await fetchWorks();
    expect(works.length).toBeGreaterThan(0);
    for (const w of works) {
      expect(typeof w.work).toBe("string");
      expect(w.work.length).toBeGreaterThan(0);
      expect(typeof w.corpus).toBe("string");
      expect(w.lang).toMatch(/^[a-z]{3}$/);
      expect(w.chunks).toBeGreaterThan(0);
    }
    // Whatever else is ingested, the corpus the reader is built around
    // must be present.
    expect(works.some((w) => w.corpus === "plato")).toBe(true);
  });

  it("GET /api/works/:work returns ordered chunks", async () => {
    const target = (await fetchWorks()).find((w) => w.corpus === "plato" && w.lang === "eng");
    expect(target).toBeDefined();
    const r = await fetch(
      `${baseUrl}/api/works/${encodeURIComponent(target!.work)}?lang=eng&limit=5`,
    );
    expect(r.ok).toBe(true);
    const json = (await r.json()) as {
      work: string;
      lang: string;
      chunks: { ord: number }[];
      total: number;
    };
    expect(json.work).toBe(target!.work);
    expect(json.lang).toBe("eng");
    expect(json.chunks.length).toBeGreaterThan(0);
    const ords = json.chunks.map((c) => c.ord);
    expect(ords).toEqual([...ords].sort((a, b) => a - b));
  });

  it("GET /api/works/:work 404s on unknown work", async () => {
    const r = await fetch(`${baseUrl}/api/works/${encodeURIComponent("Does Not Exist")}?lang=eng`);
    expect(r.status).toBe(404);
  });

  it("POST /api/translate with --llm none returns the placeholder", async () => {
    const r = await fetch(`${baseUrl}/api/translate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_text: "Μῆνιν ἄειδε θεὰ", target_lang: "eng" }),
    });
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { translated_text: string; cached: boolean; model: string };
    expect(typeof json.translated_text).toBe("string");
    expect(json.cached).toBe(false);
    expect(json.model).toBe("none");
  });

  it("POST /api/translate rejects unsupported target_lang", async () => {
    const r = await fetch(`${baseUrl}/api/translate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_text: "x", target_lang: "klingon" }),
    });
    expect(r.status).toBe(400);
  });

  it("POST /api/translate rejects empty source_text", async () => {
    const r = await fetch(`${baseUrl}/api/translate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_text: "   ", target_lang: "eng" }),
    });
    expect(r.status).toBe(400);
  });
});
