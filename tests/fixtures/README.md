# Test fixtures

## `corpus.jsonl`

A 120-chunk slice of the real corpus, in the format `minerva ingest`
emits and `minerva index` consumes. `web/tests/e2e/serve.test.ts` builds
a throwaway index from it in `beforeAll` and serves that, so the e2e
suite runs identically in CI and locally.

Before this existed, the e2e server ran against `data/index.sqlite`.
That file is gitignored and never built in CI, so every data-dependent
assertion skipped itself there and only ever executed on a developer's
machine — where three of them had been failing against a renamed corpus
for some time before anyone noticed (#133).

### What it contains, and why

| corpus | work | lang | chunks |
|---|---|---|---|
| plato | Politeia | eng | 60 |
| plato | Theaitetos | eng | 30 |
| aristotle | Nicomachean Ethics | eng | 30 |

Two Plato works rather than one, so "naming a work confines retrieval to
it" is a real assertion — with a single work it would hold trivially.
Aristotle is there so corpus detection has something to get wrong.

The rows are verbatim from `data/chunks.jsonl`, not synthesised, so the
fixture exercises the same shapes the app sees: `title_local` populated
(`Republic`, `Theaetetus`), `block_type` set, real `translator` and
`edition_year`, real section locators.

### Regenerating

Only needed if the JSONL schema changes or the assertions need different
data. Requires a full local index:

```bash
python3 - <<'PY'
import json
WANT = {
    ("plato", "Politeia", "eng"): 60,
    ("plato", "Theaitetos", "eng"): 30,
    ("aristotle", "Nicomachean Ethics", "eng"): 30,
}
got = {k: [] for k in WANT}
with open("data/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        k = (d.get("corpus"), d.get("work"), d.get("lang"))
        if k in got and len(got[k]) < WANT[k] and (d.get("text") or "").strip():
            got[k].append(d)
        if all(len(v) >= WANT[k] for k, v in got.items()):
            break
with open("tests/fixtures/corpus.jsonl", "w", encoding="utf-8") as f:
    for r in (r for v in got.values() for r in v):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
PY
```

Keep it small — it is committed, and the point is a fast, deterministic
index build (~1s), not corpus coverage. No embeddings are generated;
retrieval under `--llm none` is FTS-based and doesn't need them.
