# Top-level shortcuts so you can run common commands from the repo root
# without `cd`-ing into web/ or fiddling with the venv path.
#
# Usage: `make <target>` from /Users/kreaves/src/minerva.

WEB := web
NPM := npm --prefix $(WEB)
PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
POIETES := .venv/bin/minerva
RUFF := .venv/bin/ruff

# Override on the command line, e.g. `make run LLM=anthropic LLM_MODEL=claude-sonnet-4-6`.
LLM ?= none
LLM_MODEL ?=
PORT ?= 8000
# Retrieval language. `any` (default) searches every language in the
# index — required for non-English-primary authors (Nietzsche/Marx in
# deu, Cicero/Spinoza in lat, Hebrew Bible in heb, …) to be visible in
# chat. Override for English-only experiments: `make run MINERVA_LANG=eng`.
# Named MINERVA_LANG (not LANG) on purpose: make exports variables into
# every recipe's environment, and `LANG=any` is an invalid locale that
# would leak into every subprocess (python, node, sqlite3, …).
MINERVA_LANG ?= any
LLM_MODEL_FLAG := $(if $(LLM_MODEL),--llm-model $(LLM_MODEL))

.PHONY: help test test-unit test-e2e test-browser test-watch test-py test-all typecheck audit \
        coverage coverage-py coverage-web \
        lint lint-py lint-web format format-py format-web check \
        generate-authors check-authors check-api-types check-author-imports \
        check-pr-link check-pr-citations check-diff-coverage check-coverage-exclusions \
        check-format-baseline check-test-location \
        build dev run run-host start ingest reindex reingest \
        ingest-only reingest-only embed embed-eng stats \
        install-lemma-models

help:
	@echo "Targets:"
	@echo "  make run          Start backend (:$(PORT)) + Vite dev (:5173). Ctrl-C stops both."
	@echo "                    Override the model: make run LLM=anthropic LLM_MODEL=claude-sonnet-4-6"
	@echo "  make run-host     Same as run, but Vite binds to 0.0.0.0 so a phone on the same"
	@echo "                    LAN can hit the dev server. Backend stays on loopback — Vite's"
	@echo "                    proxy bridges /api, so no CORS or auth changes needed."
	@echo "  make start        Build the SolidJS bundle and serve it + the API on :$(PORT)"
	@echo "  make dev          Vite dev server only (no Python backend)"
	@echo "  make build        Build the production SolidJS bundle into web/dist"
	@echo "  make test         Run the full frontend test suite (unit + components + e2e)"
	@echo "  make test-unit    Fast loop: unit + component tests only (no Python)"
	@echo "  make test-e2e     Integration tests that spawn 'minerva serve --llm none'"
	@echo "  make test-browser Browser tests (Playwright, Chromium) against the built bundle"
	@echo "  make test-watch   Vitest in watch mode"
	@echo "  make test-py      Python backend tests (pytest)"
	@echo "  make test-all     Backend pytest + frontend vitest"
	@echo "  make typecheck    tsc --noEmit on web/"
	@echo "  make lint         ruff check (Python) + eslint (TypeScript)"
	@echo "  make lint-py      Python lint only (ruff check)"
	@echo "  make lint-web     TypeScript lint only (eslint)"
	@echo "  make format       Apply ruff format + prettier"
	@echo "  make format-py    Python format only"
	@echo "  make format-web   TypeScript format only (prettier)"
	@echo "  make check        All gates: lint + typecheck + tests"
	@echo "  make ingest       Parse raw corpus sources into data/chunks.jsonl"
	@echo "  make reindex      Rebuild data/index.sqlite from the existing chunks.jsonl"
	@echo "  make reingest     Re-parse + re-index in one shot (after parser changes)"
	@echo "  make embed        Compute / refresh sentence-transformer embeddings (all languages)"
	@echo "  make embed-eng    Embed English chunks only (faster for English-only experiments)"
	@echo "  make stats        Print index statistics"
	@echo "  make audit        Check whole-corpus invariants against the live index"

test:
	$(NPM) test

test-unit:
	$(NPM) run test:unit

# Same suites, instrumented, so `check-diff-coverage` has something to read.
# `check` uses these rather than the bare ones above: running each suite twice
# would cost ~50s, while the instrumentation alone costs ~6s (#255).
#
# `-n auto` (pytest-xdist): the suite isn't CPU-bound (55% of one core
# locally with no parallelism), so splitting across workers is close to
# free. pytest-cov combines per-worker coverage automatically when
# pytest-xdist is installed -- verified the TOTAL is identical with and
# without `-n auto` before relying on it.
test-py-cov:
	$(PYTEST) --cov --cov-report=xml --cov-report=term:skip-covered -n auto

test-unit-cov:
	$(NPM) run test:coverage

test-e2e:
	$(NPM) run test:e2e

# No `npm run build` here: the fixture server builds the bundle it serves,
# so every entry point gets it — including `npx playwright test` (#610).
test-browser:
	$(NPM) run test:browser

test-watch:
	$(NPM) run test:watch

typecheck:
	$(NPM) run typecheck

build:
	$(NPM) run build

dev:
	$(NPM) run dev

test-py:
	$(PYTEST)

test-all: test-py test

# Coverage targets — emit reports without enforcing a threshold. The
# CI workflow uses the same flags; running locally with `make
# coverage-py` / `make coverage-web` gives the same view contributors
# get in PR logs.
coverage-py:
	$(PYTEST) --cov --cov-report=term --cov-report=html

coverage-web:
	$(NPM) run test:coverage

coverage: coverage-py coverage-web

# ---------- Lint / format / check ----------
# Single-tool stacks per language: ruff handles Python (lint + format),
# eslint + prettier handle TypeScript. `check` runs everything that has
# to pass before a commit.

lint-py:
	$(RUFF) check src tests scripts perseus

lint-web:
	$(NPM) run lint

lint: lint-py lint-web

# The --fix scope matches lint-py so `make format-py && make check`
# can't leave a lint error behind. The `ruff format` scope is
# deliberately narrower: formatting scripts/ and perseus/ is a large
# reflow that belongs with #136, which also has to settle the
# codegen-owned files ruff currently reformats out of sync.
format-py:
	$(RUFF) format src tests
	$(RUFF) check --fix src tests scripts perseus

format-web:
	$(NPM) run format
	$(NPM) run lint:fix

format: format-py format-web

generate-authors:
	$(PYTHON) scripts/generate_author_artifacts.py --write
	$(PYTHON) scripts/check_author_ingest.py --all --write-chunk-counts

check-authors:
	$(PYTHON) scripts/generate_author_artifacts.py --check
	$(PYTHON) scripts/check_author_ingest.py --all

check-api-types:
	$(PYTHON) scripts/check_api_types.py

check-author-imports:
	$(PYTHON) scripts/check_author_imports.py

# pyproject.toml's [tool.coverage.run].omit and sonar-project.properties's
# sonar.coverage.exclusions must agree on src/minerva/ entries, or a file
# omitted from one but not the other gets a manufactured 0% from Sonar's
# blocking gate — happened twice (migrations, #339; cli/__init__.py, #345)
# before either was noticed.
check-coverage-exclusions:
	$(PYTHON) scripts/check_coverage_exclusions.py

# Frontend tests belong in web/tests, never beside the component (#547).
# Sonar's `sonar.sources` covers web/src, so a colocated test is analysed as
# production source with 0% coverage and fails the required new-code gate for
# a reason unrelated to the change. `check-diff-coverage` cannot see this —
# it reads the vitest lcov report, which excludes test files by nature — so
# the local gate stays green and the remote one blocks.
check-test-location:
	$(PYTHON) scripts/check_test_location.py

# Verify a PR's closing links actually registered (#321). Deliberately NOT part
# of `make check` — it needs a PR that already exists.
#
#   make check-pr-link PR=327                    # asserts it closes nothing
#   make check-pr-link PR=315 ISSUES="297 300"   # asserts exactly those two
check-pr-link:
	@test -n "$(PR)" || { echo 'usage: make check-pr-link PR=<n> [ISSUES="<n> <n>"]' >&2; exit 2; }
	$(PYTHON) scripts/check_pr_link.py $(PR) $(ISSUES)

# Verify every `PR #N` this repo cites in prose is really a PR (#335). Also out
# of `make check`, and for the same reason: it queries GitHub.
#
# The population here is the one that rots. A worked example is self-correcting
# — paste it, watch it fail — which is how three of #335's four wrong numbers
# turned up. A sentence attributing work to a PR is never executed by anyone, so
# `PR #297` sat in a test docstring and a design spec asserting that an issue
# number was the PR that carried it.
check-pr-citations:
	$(PYTHON) scripts/check_pr_citations.py

# SonarCloud gates PRs at 80% coverage OF THE LINES THE DIFF CHANGED and is a
# required check, so this is the local equivalent (#255). Note the suites here
# are the instrumented ones: `make coverage` reports whole-project coverage,
# which is a different number and can be green while the gate is red — on #254
# the project sat at 75% while the PR's new code was at 58.5%.
#
# Override the comparison point when working off something other than main:
#   make check DIFF_BASE=origin/some-branch
DIFF_BASE ?= origin/main

check-diff-coverage:
	$(PYTHON) scripts/check_diff_coverage.py --base $(DIFF_BASE)

# Prettier never ran in `make check`, so 152 of 352 files had drifted before
# this gate existed (#483). Reformatting them all fails the changed-line gate
# at 74.4%, so the drift is pinned in `web/.prettier-baseline` and everything
# else is held to the formatter. The baseline is policy — hand-edited, and the
# gate fails on a *stale* pin too, so it can only shrink.
check-format-baseline:
	$(PYTHON) scripts/check_format_baseline.py

check: lint typecheck test-py-cov test-unit-cov test-e2e test-browser check-diff-coverage check-authors check-api-types check-author-imports check-coverage-exclusions check-format-baseline check-test-location

# Full local dev: Python API in the background, Vite in the foreground.
# When Vite exits (or Ctrl-C), the trap kills the backend.
run:
	@$(POIETES) serve --llm $(LLM) $(LLM_MODEL_FLAG) --lang $(MINERVA_LANG) --port $(PORT) & \
	SERVER_PID=$$!; \
	trap "kill $$SERVER_PID 2>/dev/null; wait $$SERVER_PID 2>/dev/null" EXIT INT TERM; \
	$(NPM) run dev || true

# LAN-exposed dev: same as `run`, but Vite binds to 0.0.0.0 so any
# device on the same Wi-Fi can browse the dev UI. The Python backend
# stays on the loopback interface — Vite's /api proxy bridges to it
# server-side, so no CORS, no LLM-billing exposure, no auth changes
# needed. Vite will print a "Network:" line with the LAN IP.
#
# Phone testing tip: macOS Firewall may prompt on first run. Click
# "Allow" so Node can accept inbound connections from your phone.
run-host:
	@$(POIETES) serve --llm $(LLM) $(LLM_MODEL_FLAG) --lang $(MINERVA_LANG) --port $(PORT) & \
	SERVER_PID=$$!; \
	trap "kill $$SERVER_PID 2>/dev/null; wait $$SERVER_PID 2>/dev/null" EXIT INT TERM; \
	$(NPM) run dev -- --host || true

# Production: one process, one port. Builds the SPA, then serves API + bundle.
start: build
	$(POIETES) serve --llm $(LLM) $(LLM_MODEL_FLAG) --lang $(MINERVA_LANG) --port $(PORT) --static $(WEB)/dist

# ---------- Corpus ingest / index ----------
# Re-run after editing parsers (minerva/corpus/, hegel_works.py, etc.).
# `reingest` is the canonical command — it re-parses sources into JSONL
# and rewrites the SQLite index from scratch. Conversation history lives
# in a separate DB (data/conversations.sqlite) and is unaffected.

ingest:
	$(POIETES) ingest

# Destructive targets snapshot the DB + chunks.jsonl first (repo
# convention: scripts/snapshot-db.sh <reason> before any DB-mutating
# operation). The script refuses to run when data/index.sqlite doesn't
# exist, so a fresh checkout skips the snapshot instead of failing.
define snapshot_db
	@if [ -f data/index.sqlite ]; then scripts/snapshot-db.sh $(1); \
	else echo "(no data/index.sqlite yet — skipping snapshot)"; fi
endef

reindex:
	$(call snapshot_db,pre-reindex)
	$(POIETES) index --reset

# Snapshot once, up front — before `ingest` overwrites chunks.jsonl
# (the snapshot captures both the DB and the JSONL), so the steps are
# inlined here rather than reusing the ingest/reindex prerequisites.
reingest:
	$(call snapshot_db,pre-reingest)
	$(POIETES) ingest
	$(POIETES) index --reset
	@echo ""
	@echo "Re-ingest complete. Run 'make embed' to refresh vector embeddings"
	@echo "(only needed if you use --use-vectors retrieval)."

# Single-corpus reingest. Pass ONLY=<source_id[,source_id...]> (one or
# more IngestSource ids — see `minerva ingest --help`). Only the named
# sources are re-parsed and only their chunks are re-indexed in place;
# every other corpus's chunks, lemmas, embeddings, and cross_references
# are preserved. Typical 10×+ faster than `make reingest` for a single-
# corpus edit (~1.5s for theognis vs ~16s for `index --reset`).
#
# Example:
#   make reingest-only ONLY=hegel_de
#   make reingest-only ONLY=plato,aristotle
ingest-only:
	@if [ -z "$(ONLY)" ]; then echo "Usage: make ingest-only ONLY=<source_id[,...]>"; exit 1; fi
	$(POIETES) ingest --only "$(ONLY)"

# Like `reingest`, snapshot before the JSONL merge — not just before
# the index step — so the pre-run chunks.jsonl is captured too.
reingest-only:
	@if [ -z "$(ONLY)" ]; then echo "Usage: make reingest-only ONLY=<source_id[,...]>"; exit 1; fi
	$(call snapshot_db,pre-reingest-only)
	$(POIETES) ingest --only "$(ONLY)"
	$(POIETES) index --incremental --from-ingest-only
	@echo ""
	@echo "Incremental re-ingest complete. Other corpora preserved."

# Default embed covers every language (non-English authors need vectors
# in their source language for retrieval to find them). `embed-eng` is
# the narrower English-only shortcut for English-primary experiments.
embed:
	$(POIETES) embed --lang any

embed-eng:
	$(POIETES) embed --lang eng

stats:
	$(POIETES) stats

# Whole-corpus invariant check against the live index (#320). Reads every
# row rather than sampling — both wrong numbers in this repo's history came
# from a sample that looked representative — and reports rather than gates,
# because `ara` violates the lemma-surface invariant on purpose. Run it
# after any pass that writes derived tables. ~40s on the current corpus.
# Point it elsewhere with MINERVA_DB=<path> (a snapshot, say).
audit:
	$(PYTHON) scripts/audit_invariants.py

# Install the spaCy / LatinCy model wheels `terms lemmatize` needs.
#
# Two commands because they are two different kinds of dependency: the
# `lemma` extra is ordinary PyPI packages resolved through `uv.lock`, while
# the models are pinned direct URLs held OUT of the lock on purpose — a URL
# dependency in the graph makes `uv sync --locked` fetch from github.com and
# huggingface.co on every CI job, and a 429 there failed PRs (#282). See
# `lemma-models.txt` for the full rationale and the integrity rules.
install-lemma-models:
	uv pip install -e '.[lemma]'
	uv pip install -r lemma-models.txt
