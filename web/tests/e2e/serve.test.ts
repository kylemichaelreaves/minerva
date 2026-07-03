// Integration test: spawn the real Python server (`minerva serve --llm none`)
// on an ephemeral port, drive POST /api/chat through node fetch, and assert
// the response shape. Skipped automatically when the venv binary isn't
// present, so this won't fail in environments without Python.
//
// @vitest-environment node

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const MINERVA_BIN = resolve(REPO_ROOT, ".venv/bin/minerva");
const STATIC_DIR = resolve(REPO_ROOT, "web/dist");
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
  // Whether the server booted against a populated index. CI doesn't ingest
  // the (multi-GB, gitignored) corpus, so it serves an empty DB — the
  // server-contract tests below still run, but the data-dependent ones
  // (chunk stats, retrieval, works list) skip rather than fail. Set from
  // /api/health in beforeAll.
  let hasCorpus = false;

  beforeAll(async () => {
    const port = await freePort();
    baseUrl = `http://127.0.0.1:${port}`;
    // Conversations DB lives in a tmp dir for the test run so we don't
    // pollute the developer's data/ directory.
    tmpDir = mkdtempSync(join(tmpdir(), "minerva-e2e-"));
    const convDb = join(tmpDir, "conversations.sqlite");
    proc = spawn(
      MINERVA_BIN,
      [
        "serve",
        "--llm",
        "none",
        "--port",
        String(port),
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
    hasCorpus = typeof health.chunks_total === "number" && health.chunks_total > 0;
    if (!hasCorpus) {
      console.warn(
        "[e2e] server index is empty (chunks_total=0) — skipping data-dependent " +
          "assertions. CI does not ingest the corpus; run `make reingest` locally " +
          "to exercise these.",
      );
    }
  }, 30_000);

  afterAll(() => {
    if (!proc.killed) {
      proc.kill("SIGTERM");
    }
    if (tmpDir) {
      rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it("GET /api/health returns chunk stats", async (ctx) => {
    if (!hasCorpus) return ctx.skip();
    const r = await fetch(`${baseUrl}/api/health`);
    expect(r.ok).toBe(true);
    const json = (await r.json()) as Record<string, unknown>;
    expect(json.backend).toBe("none");
    expect(typeof json.chunks_total).toBe("number");
    expect(json.chunks_total as number).toBeGreaterThan(0);
    expect(Array.isArray(json.chunks_by_corpus_lang)).toBe(true);
  });

  it("POST /api/chat returns the expected shape and finds Republic 509 for the divided line", async (ctx) => {
    if (!hasCorpus) return ctx.skip();
    // The query names Plato AND the Republic so the server-side
    // detectors (`agent.detect_corpus` + `agent.detect_work`) scope
    // retrieval to that one work. Both levels are needed: "divided
    // line" is too generic for BM25 alone (geometry passages in
    // Aristotle outscore it), and even within the Plato corpus the
    // analogy at Republic 509-511 doesn't literally contain "divided
    // line" (Plato writes "a line divided into two unequal segments"),
    // so as the corpus grows, dialogues like the Statesman with denser
    // literal matches push it out of an author-scoped top-k. Naming
    // the work pins the scope and makes 509d the top hit.
    const r = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "the divided line in Plato's Republic", history: [] }),
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
    const sources = json.citations.map((c) => c.src);
    expect(sources.some((s) => /Plato, Republic 509/i.test(s))).toBe(true);
  });

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

  it("GET /api/works returns a list with the known corpora", async (ctx) => {
    if (!hasCorpus) return ctx.skip();
    const r = await fetch(`${baseUrl}/api/works`);
    expect(r.ok).toBe(true);
    const json = (await r.json()) as { works: { work: string; lang: string }[] };
    expect(Array.isArray(json.works)).toBe(true);
    expect(json.works.length).toBeGreaterThan(0);
    // The corpus has at least one Plato work.
    expect(json.works.some((w) => w.work === "Republic")).toBe(true);
  });

  it("GET /api/works/:work returns ordered chunks", async (ctx) => {
    if (!hasCorpus) return ctx.skip();
    const r = await fetch(
      `${baseUrl}/api/works/${encodeURIComponent("Republic")}?lang=eng&limit=5`,
    );
    expect(r.ok).toBe(true);
    const json = (await r.json()) as {
      work: string;
      lang: string;
      chunks: { ord: number }[];
      total: number;
    };
    expect(json.work).toBe("Republic");
    expect(json.lang).toBe("eng");
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
