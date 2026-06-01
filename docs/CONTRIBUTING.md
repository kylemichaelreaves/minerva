# Contributing to Minerva

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | **3.13** (see `.python-version`) | `<3.14` required for LatinCy spaCy / Stanza-fallback Greek + Latin lemmatizers |
| [uv](https://github.com/astral-sh/uv) | latest | Recommended; stdlib `venv` + `pip` also works |
| Node.js | **22** | For `web/` — matches CI |
| direnv | optional | Auto-loads API keys from `.envrc` |

## Clone and install

```bash
git clone <repo-url> minerva && cd minerva

uv venv -p 3.13
uv pip install -e '.[embed,hegel,lemma,dev]'

npm ci --prefix web

cp .envrc.example .envrc   # optional — fill in LLM keys, then: direnv allow
```

Never commit `.envrc` (gitignored). Only `.envrc.example` belongs in git.

## Corpus bootstrap

**Corpus data is not in the repository.** `data/index.sqlite`, `data/chunks.jsonl`,
and `perseus/raw_*/` are gitignored and must be built locally.

Minimal path (Plato + Aristotle):

```bash
python3 perseus/download_perseus_plato.py --lang both --skip-existing
python3 perseus/download_perseus_aristotle.py --lang both --skip-existing
.venv/bin/minerva ingest
.venv/bin/minerva index --reset
.venv/bin/minerva stats
```

See [README.md](../README.md) Quickstart for optional authors (Hegel, Kant, Latin
originals, etc.).

## Lint actively, not just at the gate

Catch lint and type errors **as you write**, not when `make check` runs five
minutes before you push. Three layers, in order of how often each fires:

1. **Editor — live.** The repo ships `.vscode/extensions.json` and
   `.vscode/settings.json` so first-open VS Code prompts you to install
   ESLint, Prettier, Ruff, and Pylance and turns on lint-on-save + format-on-save.
   Other editors are fine — match the same loop:
   - ESLint runs on every save in `web/`
   - Ruff runs on every save in `src/minerva/` and `tests/`
   - Prettier formats TS / JSON; Ruff formats Python
   - TypeScript uses the workspace `tsdk` so editor diagnostics match `make typecheck`.

2. **Pre-commit hook — every commit.** Install the project hook once:
   ```bash
   ./scripts/install-git-hooks.sh
   ```
   The `pre-commit` hook runs `make lint typecheck` (under ~10 s). Test
   suites are deliberately NOT in the hook — adding them pushes latency
   past the point where contributors reach for `--no-verify`. Bypass with
   `--no-verify` only in genuine emergencies; the CI gate will catch you.

3. **CI — every push / PR.** [`.github/workflows/check.yml`](../.github/workflows/check.yml)
   mirrors `make check` (ruff + eslint + tsc + pytest + vitest unit).
   PRs can't merge red.

If you're adding a new lint rule, also add it to the existing layer that
enforces it. Don't add a rule that only fires in CI — that's where lint
debt starts.

## Verify before a PR

```bash
make check    # ruff + eslint + tsc + pytest + vitest unit + check-authors + check-api-types + check-author-imports
```

Backend: import per-author work tables from `minerva.authors.<author>_works`
(see [BACKEND.md](BACKEND.md)). Handler JSON changes need contract fixtures in
`tests/fixtures/api/` and matching types in `web/src/api/types/`.

### Python coverage (baseline)

Optional report (requires `[dev]` extras):

```bash
make coverage-py
```

**Baseline (Mar 2026):** ~**61%** line coverage on `src/minerva/` (full pytest
suite). `refs/llm_verify.py` and `refs/rules/scripture_cite/` have dedicated
helper tests in `tests/test_llm_verify_helpers.py` and
`tests/test_scripture_cite_lexicon.py`. CI does not gate on coverage yet; do not
regress modules you touch without cause.

If you changed [`data/authors/manifest.yaml`](../data/authors/manifest.yaml),
run `make generate-authors` and commit the regenerated blocks in
`corpus_registry.py`, `author_ordering.py`, and `atlasData.ts`.

This mirrors [`.github/workflows/check.yml`](../.github/workflows/check.yml).
E2E tests (`make test-e2e`) run on pushes to `main` only.

## First-use downloads (not in git)

| When | What |
|------|------|
| First `minerva terms lemmatize --lang grc/lat` | LatinCy spaCy wheels (`grc_dep_web_sm`, `la_core_web_sm`) from HuggingFace — install via `uv pip install <wheel-url>` (see `lemmatize.py` docstring). Stanza fallback only when LatinCy isn't installed. |
| First `minerva embed` | `sentence-transformers` model download |
| `[lemma]` extra install | spaCy `de_core_news_sm` + `fr_core_news_sm` + `en_core_web_sm` wheels (via `pyproject.toml`) |

Tests mock lemmatizer paths — `make check` does not require these models.

## Where to look

| Doc | Purpose |
|-----|---------|
| [README.md](../README.md) | Product overview, Quickstart |
| [INGESTION.md](INGESTION.md) | Add-an-author checklist |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Routes, DBs, HTTP API |
| [BACKEND.md](BACKEND.md) | Module layout, SQL, error handling, testing conventions for `src/minerva/` |
| [FRONTEND.md](FRONTEND.md) | Solid component, CSS, reactivity, testing conventions for `web/` |
| [MEMORY.md](MEMORY.md) | Operator rules (snapshots, re-ingest) |
| [SCRIPTS.md](SCRIPTS.md) | One-off operator scripts |
| [FigJam — App Flow](https://www.figma.com/board/9yBqT8fZSPFwcARJrnBy26) | User journeys + ingestion pipeline |
| [FigJam — Ingest Wave](https://www.figma.com/board/uaeZ5hqmEClhmBQf4Gv0xA) | Author-ingest checklist visual |

## Adding a new author

Follow [INGESTION.md](INGESTION.md) end-to-end, including **§14 (chat integration)**
and [MEMORY.md](MEMORY.md) snapshot discipline. Indexing alone does not make an
author visible in chat.
