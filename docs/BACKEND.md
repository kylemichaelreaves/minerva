# Backend conventions

`src/minerva/` is a Python 3.13 SQLite-backed application — corpus ingest,
retrieval, lemma cache, and the HTTP API that the SolidJS frontend talks to.
This doc codifies the conventions reviewers will hold a backend diff to.

For architecture (route tables, DB layout, ChatContext), see
[ARCHITECTURE.md](ARCHITECTURE.md). For ingest-specific rules, see
[INGESTION.md](INGESTION.md).

## Module layout

- **Top-level packages**: `concordance/`, `reader/`, `refs/`, `ingest/`,
  `store/`, `agent/`, `http/`, `syntax/`, `text/`. Each contains a `__init__.py` that re-exports
  the public surface (functions, classes, types). Importers go through the
  package, not the module file.
- **Chat** lives at the package root (not a `chat/` subpackage):
  `chat_service.py` (turn orchestration), `chat_context.py` (DB + retrieval
  context for one request), and `agent/` (compose, retrieval, prompts).
- **Per-author work tables** live under `src/minerva/authors/` — import
  `minerva.authors.<author>_works`, never `minerva.<author>_works` at the
  package root. Shared work metadata is in `corpus_works.py`.
- **One responsibility per module.** `concordance/queries.py` is the read path;
  if a write path lands, it goes in `concordance/writes.py`, not the same file.
- **`syntax/`** splits along its dependency seam, which is the point of the
  package: `parse.py` wraps Stanza (a lazy German singleton; the model
  downloads to `~/stanza_resources/` on first use) and is the only module
  needing the `[lemma]` extra, imported lazily so the rest works without it;
  `queries.py` (`load_or_parse`, `append_correction`, `delete_correction`,
  and the replay `materialise`) and `validate.py` (tree invariants — cycle,
  single root, deprel shape) depend on nothing but `sqlite3`. Keep
  `materialise` pure: it is the integrity guarantee for every hand correction
  in the system. **Tests must mock at the pipeline boundary** — CI installs
  `.[dev,hegel,embed]`, *not* `[lemma]`, so there is no `stanza` and no model
  there. A test that constructs a real pipeline passes locally and fails
  everywhere else.
- **HTTP handlers** live in `src/minerva/http/handlers/` — thin wrappers that
  unpack the request, call the domain function, return JSON. No business logic
  in handlers. Transport (`ChatHandler`, static SPA, `serve()`) is in
  `http/serve.py`, routing in `http/router.py`; `minerva serve` enters through
  `cli/serve_cmd.py`. Tests import from `minerva.http.*` directly.

## SQL and the store

- **Parameterized queries always.** `conn.execute(sql, params)` — never string
  formatting into the SQL body. See `concordance/queries.py:lemma_index` for
  the canonical pattern: build `sql_fragment` + `params: list[Any]` pairs,
  concatenate fragments, pass params as a single list.
- **`LIKE` patterns must escape `%` and `_`** when user input feeds them. The
  escape clause goes on the SQL: `LIKE ? ESCAPE '\\'`. See the `q` parameter
  in `lemma_index` for the pattern.
- **Migrations live in `src/minerva/migrations/`** as numbered `.sql` or `.py`
  files. Each migration is idempotent (`CREATE TABLE IF NOT EXISTS`,
  `ADD COLUMN` wrapped in a check). The schema test (`test_migrations.py`)
  verifies a fresh DB ends in the expected shape.
- **Views (`chunks_full`)** are recreated by every migration that renames an
  underlying table — SQLite blocks `ALTER … RENAME` while a view references the
  column. See [MEMORY.md](MEMORY.md) "SQLite migration PRAGMA dance".

## Errors and validation

- **`BadRequestError`** for client-fixable problems (missing param, invalid enum
  value, malformed range). The HTTP handler maps it to a 400.
- **`NotFoundError`** for explicit not-found responses. Maps to a 404.
- **Validate at boundaries.** Inside a function that's already been called with
  a validated arg, trust the type. Don't re-validate.
- **Integer parsing** — guard with `try: int(query.get(…)) except ValueError`
  and raise `BadRequestError`. The handler tests assume this shape.
- **Inverted user ranges** (e.g. `max_count < min_count` during slider drag) —
  return zero rows rather than erroring. The UI surfaces the empty-result
  state itself; an error would just look like a network failure.

## Logging and side effects

- The store is the only mutable surface. Domain functions take a `conn` and
  the read functions are pure-of-side-effects on the DB.
- LLM calls go through `llm.LLMBackend`. Tests use `StubBackend` (see
  `tests/conftest.py`) — never call real models in unit tests.
- File I/O happens in `ingest/` and the CLI; domain code receives already-read
  inputs.

## Linting — keep it live

Ruff is the single linter + formatter for Python. Run it constantly:

- **Editor**: install the Ruff extension. The shipped `.vscode/settings.json`
  wires lint-on-save, format-on-save, and `source.fixAll.ruff` /
  `source.organizeImports.ruff` so the editor matches `make lint-py` /
  `make format-py` to the keystroke.
- **Commit**: install the pre-commit hook (`./scripts/install-git-hooks.sh`).
  It runs `make lint typecheck` before each commit.
- **Don't introduce a rule that only CI enforces.** If you tighten ruff's
  config, run `ruff check --fix` against the whole tree in the same change.
  Don't ship a config that the existing code violates — the rule loses
  its meaning the moment contributors learn to ignore the noise.

When ruff flags an intentional pattern (a re-exported underscore name
for test patching, a circular import behind `TYPE_CHECKING`), suppress
per-line with `# noqa: <code>  # <reason>`. Always include the reason.

## Tests

Tests live under `tests/` (flat layout). pytest is the test runner;
`make test-py` runs them.

**Required for every PR that touches `src/minerva/`:**
- A query function (`concordance/queries.py`, `reader/queries.py`, etc.) ships
  with a `test_<module>.py` that exercises each query param, each filter
  combination, and the edge cases (empty result, inverted range, wildcards in
  user input, NULL handling).
- A migration ships with an entry in `test_migrations.py` confirming a fresh
  DB ends in the expected shape.
- A new HTTP handler ships with `test_server_<topic>.py` exercising the
  request-validation path (missing params → 400, bad enum → 400) plus the
  happy path through to a real `ServerDeps`.

**Pattern** — see `tests/test_concordance_queries.py` for a fixture-built
SQLite store with seeded lemma rows. `tests/conftest.py` provides
`populated_db`, `make_chunk`, `make_deps`, and `StubBackend` for handler tests.

**Optional** — utility functions with no I/O and no branching (pure name
normalisation, tag stripping). Add a test the moment a branch lands.

`make test-py` runs the full suite. `make check` (run before any PR) chains
ruff + eslint + tsc + pytest + vitest unit + `check-authors` +
`check-api-types` + `check-author-imports`.

**API contract (handler JSON ↔ frontend types)** — when a handler response
shape changes, update the matching fixture under `tests/fixtures/api/*.keys.json`,
the pytest case in `tests/test_api_contract.py`, and the TS interface in
`web/src/api/types/`. `make check-api-types` verifies fixture keys exist on
the TS types. `scripts/check_author_imports.py` blocks deprecated root
`*_works.py` import paths.

## Backend backlog (deferred)

| Item | Notes |
|------|-------|
| `chat/` subpackage | Optional move of `chat_service` + `chat_context`; root modules are canonical today |
| Text-normalization modules into `text/` | `textnorm` (72), `orthography` (74), `transliterate` (199), `heading_clean` (347) sit at the root beside a 118-LOC `text/`. Not free: `textnorm.py:18` documents its own root import path and two `scripts/` consumers use it. `text/`'s empty-facade problem is separate and tracked in #326 |
| `corpus_*.py` into `corpus/` | `corpus_registry` (717), `corpus_extract` (380), `corpus_works` (117) sit beside the `corpus/` package. `corpus_registry.py` is **codegen'd** — lines 32-596 are inside `# BEGIN CORPORA` / `# END CORPORA` and written by `scripts/generate_author_artifacts.py`, so a move touches the generator, not just the module |
| Split `lemmatize.py` by language backend | Only when actively editing the lemmatizer |
| Perseus downloader template | Operator surface — see [INGESTION.md](INGESTION.md) |
| OpenAPI / pydantic wire models | Contract tests + TS types cover the API surface |

## Where to look

| Pattern you need                       | Look at                                              |
|----------------------------------------|------------------------------------------------------|
| Read query with multiple filters       | `src/minerva/concordance/queries.py` `lemma_index`   |
| Wildcard-safe `LIKE` escaping          | same file, the `q_sql` block                         |
| Migration with a table rebuild         | `src/minerva/migrations/0011_aquinas_citation_system.py` |
| HTTP handler that maps domain errors   | `src/minerva/http/handlers/concordance.py`           |
| Fixture-built corpus for tests         | `tests/conftest.py` `populated_db`                   |
| Concordance test with seeded lemmas    | `tests/test_concordance_queries.py`                  |
| Stubbed LLM for handler tests          | `tests/conftest.py` `StubBackend`                    |
| API contract fixtures + TS check       | `tests/fixtures/api/`, `scripts/check_api_types.py`  |
| Author works import path               | `src/minerva/authors/<author>_works.py`              |
| Chat turn orchestration                | `src/minerva/chat_service.py`, `agent/`              |
