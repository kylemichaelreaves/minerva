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
   - Ruff runs on every save in `src/minerva/`, `tests/`, `scripts/`, and
     `perseus/` — the last two joined the gate in #117, after 41 undefined
     names accumulated in the years they went unlinted
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
`tests/test_scripture_cite_lexicon.py`.

**SonarCloud gates PRs at 80% coverage of the lines you changed** (new code
only — pre-existing debt in a file you touch doesn't count against you), and
since #158 it is a **required status check** — a red gate blocks the merge.

`scripts/**` and `perseus/**` are in `sonar.coverage.exclusions`, so the 80%
bar applies to `src/` and `web/src/` only. Operator tooling is still analysed
for issues, just not held to a coverage bar.

### Security findings in operator tooling

The `pythonsecurity:*` rules flag developer scripts for taking a `--db` or
`--out` path from the CLI ("LLMs running this code with faulty CLI arguments
can…"). For `scripts/**` and `perseus/**` the invoking user *is* the operator:
no privilege boundary is crossed, so #167 triaged the backlog to zero — 21
Accepted, 6 False Positive — and a red security rating now means something.

If you add a finding in one of these files, don't reflexively accept it. Check
which of the three cases it is:

- **False positive** — the rule's own exception list already covers it. Both
  live examples: `http://www.tei-c.org/ns/1.0` is an XML namespace *identifier*
  that must byte-match the documents (changing it breaks TEI parsing), and
  `serve.py` builds `http://{host}` strings to *compare* Origin headers against
  a loopback bind (`--host` defaults to `127.0.0.1`).
- **Accepted** — the dataflow is real but the impact is nil, because the
  operator chose the path and runs as themselves. The three `S2083` BLOCKERs in
  `download_early_modern.py` are `combined.parent / "human_nature.txt"`: a
  literal filename joined to a directory the operator named.
- **Real** — anything where the tainted value comes from *downloaded* data
  rather than from the operator's own argv. Fix these; don't accept them.

Record the reasoning in the PR, since SonarCloud's status changes don't carry
one.

If you changed [`data/authors/manifest.yaml`](../data/authors/manifest.yaml),
run `make generate-authors` and commit the regenerated blocks in
`corpus_registry.py`, `author_ordering.py`, and `atlasData.ts`.

This mirrors [`.github/workflows/check.yml`](../.github/workflows/check.yml).
E2E tests (`make test-e2e`) run on pushes to `main` only.

## First-use downloads (not in git)

| When | What |
|------|------|
| First `minerva terms lemmatize --lang grc/lat` | LatinCy spaCy wheels (`grc_dep_web_sm`, `la_core_web_sm`) from HuggingFace. Stanza fallback only when LatinCy isn't installed. |
| First `minerva embed` | `sentence-transformers` model download |
| `[lemma]` extra install | All five spaCy model wheels — `de_core_news_sm`, `fr_core_news_sm`, `en_core_web_sm`, and the two LatinCy ones above (via `pyproject.toml`) |

Install the models with `uv pip install -e '.[lemma]'`, **not** by pasting a
wheel URL. `pyproject.toml` pins each one to an immutable URL (a commit SHA
for the two HuggingFace wheels) plus a `#sha256=` fragment that uv verifies;
a hand-written URL gets neither. HuggingFace `main` is a mutable branch and
does move — `la_core_web_sm-3.9.4` was pinned that way and has since been
deleted upstream (#122).

Tests mock lemmatizer paths — `make check` does not require these models.

## Record what you find

**Anything you discover that isn't already in the tracker gets an issue —
before you move on.** This is a rule, not a suggestion, and it applies to
every kind of work: fixing a bug, adding an author, reviewing a PR,
reading code for an unrelated reason.

File it whether or not you intend to fix it. The point is that the finding
survives the session it was found in.

**What counts:** a bug you noticed but didn't cause; a fix you scoped down
and the part you left out; a guard that turns out to be inert; a check that
runs but validates nothing; a test whose name misdescribes it; a value you
had to reverse-engineer because it was undocumented; anything you caught
yourself saying "someone should look at that" about.

**What doesn't:** things already tracked (link instead), and anything you
fixed in the same change.

Rules for a useful issue:

- **Evidence, not impression.** Paste the command and its output, or the
  `file:line` and the lines themselves. "Feels fragile" isn't a finding.
- **Say how you found it**, and what you'd already ruled out. That's what
  stops the next person re-deriving it.
- **Link the precedent** — the PR or issue that introduced it, and the one
  that surfaced it. `git log -S '<symbol>'` usually names the commit; verify
  with `git show <commit>^:<path>` before blaming one, because the obvious
  culprit is often not the origin.
- **Label it** so it's findable: `bug` / `tech-debt` / `security` plus the
  area (`backend`, `frontend`, `ingest`, `refs`, `cli-scripts`,
  `github_actions`, `dependencies`).

If a fix is genuinely one line, just make it. If it needs a decision, a
different reviewer, or more scope than the change you're on, file it — and
say in your PR description what you left out and why. Shrinking scope is
fine; shrinking it silently isn't.

## Correct the record

The companion rule to the one above, and it works in the opposite
direction: **when what you find materially differs from what an issue, doc,
or commit message claims, record the difference before you move on.**

Sources here are frequently wrong in ways that matter. An issue names the
wrong commit, recommends a flag that does the opposite of what it says,
counts seven occurrences where there are nine, or describes a state that
was true when filed and has since changed. Each one is a trap the next
person walks into, and re-deriving the same correction is pure waste.

**A correction is not a new issue.** This is the deliberate difference from
"Record what you find" — filing a fresh issue every time a source is wrong
would bloat the tracker with meta-commentary and bury the correction where
nobody hitting the original will see it. Put it on the thing that was
wrong:

| Wrong claim lives in | Where the correction goes |
|---|---|
| An issue | A comment on that issue |
| A doc, code comment, or workflow comment | Fixed in the same PR |
| A commit message (immutable) | The PR body, and the issue it references |

Either way it goes in your PR description too — reviewers are judging your
change against the issue, so a silent divergence reads as a mistake.

A useful correction carries four things:

- **What the source claims** — quoted, so there's no ambiguity about what
  is being corrected.
- **What is actually true.**
- **The evidence** — the command and its output, same bar as an issue.
  `--help` output and a two-line experiment both count.
- **What would have gone wrong had you trusted it.** This is the part that
  prevents the repeat, and the part people skip.

Worked example — #125 recommended switching CI to `uv sync --frozen` so a
stale lockfile would fail the build. It does the opposite:

```
$ uv sync --help | grep -A1 -E "^\s+--(frozen|locked)"
      --locked   Assert that the `uv.lock` will remain unchanged
      --frozen   Sync without updating the `uv.lock` file
```

Against a deliberately stale lock:

```
$ uv sync --frozen --dry-run --extra dev   # exit 0 — installs the stale lock, ignores pyproject
$ uv sync --locked --dry-run --extra dev   # exit 1
The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
```

Had we shipped the issue as written, CI would have pinned itself to a lock
free to drift from `pyproject.toml` indefinitely — the exact failure the
issue existed to fix, now harder to see because the fix looked applied.

**Material** means it changes the fix, the scope, or the risk. Typos,
rephrasings, and stylistic disagreements are not material — don't paper
issues with them.

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
| [FigJam — Application Architecture](https://www.figma.com/board/3EXl1NgThKiIs2sBeEKHOz) | Canonical board: corpus → pipeline → stores → API → frontend → refs |
| [FigJam — App Flow](https://www.figma.com/board/9yBqT8fZSPFwcARJrnBy26) | Superseded; user journeys + ingestion pipeline |
| [FigJam — Ingest Wave](https://www.figma.com/board/uaeZ5hqmEClhmBQf4Gv0xA) | Author-ingest checklist visual |

## Adding a new author

Follow [INGESTION.md](INGESTION.md) end-to-end, including **§14 (chat integration)**
and [MEMORY.md](MEMORY.md) snapshot discipline. Indexing alone does not make an
author visible in chat.
