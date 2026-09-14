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

**Frontend tests go in `web/tests/`, never beside the component.** This is the
opposite of the majority convention in the wider JS ecosystem, so it is easy to
get wrong by habit, and getting it wrong is expensive in a way that is not
obvious: `sonar-project.properties` declares `sonar.sources=…,web/src` and
`sonar.tests=tests,web/tests`, so a colocated test is analysed as **production
source with 0% coverage** and fails the required new-code coverage gate for a
reason unrelated to the change. Measured on #546: two colocated files, 85 lines
counted as uncovered production code, gate at 65.2%; after moving them, with no
change to any assertion, 93.4%.

`make check`'s `check-test-location` catches this locally in seconds. It exists
because nothing else can — `check-diff-coverage` reads the vitest lcov report,
which excludes test files by nature, so the local gate and the blocking remote
gate disagree with no local signal at all.

The second cost is worse than the gate failure. A colocated duplicate is
invisible from beside the component: `web/tests/Lines.test.tsx` already existed
when a second `Lines.test.tsx` was added under `web/src`, and both the
implementer and the reviewer of that change reported no such file existed —
each had looked in only one of the two places.

### Browser tests

`web/tests/browser/` runs under Playwright against the production bundle
served by the real server. Five tests, Chromium only, in the `web · e2e` job.
Run locally with `make test-browser`.

**Locators, in order. Reach lower only when every tier above genuinely
cannot distinguish the target.**

1. `getByRole` with an accessible name.
2. Data attributes the app's own code queries — `data-chunk-id`,
   `data-offset`. These are load-bearing in `src/`, not test scaffolding.
3. `data-testid`, with a comment saying why tiers 1–2 failed.
4. Never: CSS class selectors, positional indexing as a substitute for
   identity, literal corpus text, or coordinates from anything but a box
   measured at call time.

Selecting the Nth word of a line is **not** tier 4 — a word's position in a
sentence is its identity. Picking the second `.st-btn` to mean "Translate"
is.

**This differs from the jsdom suite on purpose.** `tests/SelectionToolbar.test.tsx`
locates by `.st-btn` plus `buttons[0]`/`buttons[1]`. That suite is not being
converted, but do not "fix" the browser suite to match it — locating by class
and index is why #594 went unnoticed for the life of the component: nothing
ever consulted an accessible name.

**A flaky browser test is a defective test. Delete it; do not retry it.**
`retries: 0` is permanent. The first flaky red becomes a re-run, and once
re-running is routine the gate consumes attention and pays nothing — which is
worse than not having it. If a test needs a `waitForTimeout` to pass, it is
asserting on the wrong thing.

**Page objects return `Locator`, never `ElementHandle`, and never assert.**
A handle is a stale snapshot that gets repaired with a sleep.

**Fixtures derive corpus values at run time and throw — never skip — when the
corpus cannot satisfy them.** A silent skip is how #133's assertions rotted
for months.

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

### Checking it before you push

`make check` runs the same measurement locally (`scripts/check_diff_coverage.py`,
added in #255). It reads `coverage.xml` and `web/coverage/lcov.info`, takes the
changed-line set from `git diff origin/main`, and fails below 80%:

```
$ make check
  web/src/Syntax/components/PosPicker.tsx   45/86    52.3%  << under
                                        uncovered: [60, 62, 66, 67, 68, ...]
                                        line 67: only 0/2 branches taken
diff coverage vs origin/main: 56.2% (122/217), gate >= 80%
check-diff-coverage: FAILED — SonarCloud will block this PR.
```

Three things about it are worth knowing, because each one is a way to get a
confident wrong answer:

- **It counts branches, not just statements.** Sonar does. A one-line
  `if x != y:` guard whose false branch has no test scores 3/4, and #250
  failed the gate at 75% with 100% *line* coverage.
- **`make coverage` is not a substitute.** That is whole-project coverage. On
  #254 it read 75% while new code was at 58.5% — the number that gates.
- **It trusts that the reports match the working tree.** `make check`
  regenerates both immediately before running it. Invoking the script by hand
  after an edit measures stale line numbers and tells you nothing.

Duplication (≤3% on new code) and the reliability rating are also gates, with
no local equivalent — #254 failed both by copying a component wholesale, and
the fix was to extract the shared part rather than to test the copy harder.

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
`corpus_registry.py`, `author_ordering.py`, and `atlasData.ts`, plus the two
committed snapshots it refreshes: `data/authors/chunk_counts.json` and
`data/authors/chunk_granularity.json`.

The second one gates chunk **granularity** (#176) — per work/lang maximum and
mean chunk length — and is worth understanding before an ingest, because it is
the one check that can fail on data you did not knowingly change:

- Thresholds and the reviewed baseline (`granularity.known_coarse`) are
  **policy** and live in `manifest.yaml`. They are hand-edited, never
  regenerated. The measurements in `chunk_granularity.json` *are*
  regenerated. That split is the whole gate: were the baseline generated too,
  `make generate-authors` would silently bless every new violation.
- So a newly-coarse work fails `make check-authors` until you either fix the
  chunking or add it to `known_coarse` with a note saying why its coarseness
  is a real structural level. Adding an entry is a visible line in the PR
  diff, which is the review step.
- A **stale** entry fails the same way. When a work is re-chunked, remove its
  `author|title|lang` key from `known_coarse`, or the list only ever grows.
- 94 pairs are on the baseline today; `tolerance_pct: 5` keeps an ordinary
  text edit from failing CI.

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

`/close-out` walks this as phase 7, and will not finish until every finding has
both an issue number and a batch row.

### Separate what you measured from what you think

**Use two headings — `## Measured` and `## Hypothesis` — and put the cause
and the proposed fix under the second one.** Not cosmetic: the two halves of
an issue have very different shelf lives, and writing them in one voice has
repeatedly cost a day.

The backlog close-out gives four batches' worth of evidence. All twelve open
issues were re-verified against `main` before work started; **eleven of
twelve measured numbers still reproduced, and none of the twelve defects
turned out to be imaginary.** Then three of the four batches worked so far
hit a material correction anyway — and in every case what broke was the
explanation, never the existence of the defect:

| Issue | Held up | Did not |
|---|---|---|
| #262 | the hang, 18m47s wall for 1.62s CPU | the stated cause, **and the proposed fix, which would not have stopped the hang at all** |
| #125 | the stale-lock problem | the recommended flag — `--frozen` *skips* the check that `--locked` enforces, the exact opposite |
| #274 | the defect | the scope: fixing only the restore gate left the bug in place |
| #176 | Agamemnon at 82,256 chars | `max=560,187`, which exceeds the whole corpus's maximum of 151,427 |
| #116 | both defect classes | the commit it blamed — they predated it |

So: a pointer to a defect is close to permanently reliable, because it comes
from someone actually hitting the thing. A diagnosis is about a coin flip,
because it is written *before* anyone tried the fix. An issue that presents
both in the same register invites the next person to inherit the coin flip
as though it were the measurement — which is what happened on #262 and #274,
where the plan copied the proposed fix forward and both had to be corrected
mid-implementation.

Concretely:

- **`## Measured`** — the command and its exact output, counts, `file:line`
  and the lines themselves, and how you found it. Anything a reader can
  re-run to get the same answer. Numbers go here **only** with the query
  that produced them; a bare figure cannot be re-checked, and #176's wrong
  one was catchable precisely because its query was printed beside it.
- **`## Hypothesis`** — the cause, the suggested fix, the blamed commit,
  the guess at scope. Say it is a guess. Everything here is what
  [Correct the record](#correct-the-record) tells the implementer to verify
  before relying on, and this is what gives that rule a target instead of
  applying uniformly to every sentence.

This does not lower the evidence bar; it is what makes the bar useful.
"Feels fragile" still isn't a finding under either heading.

One thing deliberately **not** done: a `.github/ISSUE_TEMPLATE/`. Issues
here are filed with `gh issue create --body-file`, which bypasses templates
entirely, so one would look like enforcement while enforcing nothing — a
check that runs but validates nothing, which is on the list of things worth
filing an issue about.

## Close the loop: every PR links its issue

Filing issues is only half a loop. If closing them is manual, the backlog
grows monotonically no matter how much gets fixed — so **a PR that resolves
an issue carries a closing keyword in its body, targets `main`, and is
verified to have registered the link.**

```
Closes #160. Closes #179.
```

One keyword per issue — `Closes #160, #179` links only the first. The
keyword must be in the **PR body**, not just the commit message or the
title. Keep it in the commit message as well: a squash-merge or a direct
push to `main` closes from commit text, so the two together survive either
merge style.

### Three silent failure modes

GitHub will accept a `Closes #N` that does nothing, without warning — and
will also act on one you never meant to write:

1. **The PR must target the default branch.** A stacked PR based on another
   feature branch registers *no* link, however many closing keywords it
   carries. Stacking is still fine — but the PR has to be retargeted to
   `main` before merge, and see (2).
2. **The body is parsed when written, not when the base changes.**
   Retargeting a stacked PR to `main` does not backfill the link. The body
   must be edited again to re-trigger the scan.
3. **The parser cannot tell a keyword being used from one being discussed,
   and backticks are not an escape.** It scans the merge commit message for
   a closing keyword adjacent to any issue number, prose or not.

The first two were live in this repo: #213 was opened stacked, later ended
up on `main`, and sat there with `Closes #125` in its body and no link
registered. Merging it would have left #125 open with its fix shipped.

The third bit on PR #293, a doc-only change that deliberately carried
`Refs #176` because it completed no part of the issue. Its
`closingIssuesReferences` was empty, exactly as intended. It closed #176
anyway, because one sentence in the body described what part 2's PR should
carry, with the keyword spelled out beside the number. The paragraph
explaining that #176 had to stay open is what closed it, three minutes
after it was written.

So when documenting this convention — in a plan, a PR body, or this file —
keep a closing keyword away from the number of any **open** issue. The
examples above are safe only because #125, #160 and #179 are long closed;
re-closing a closed issue is a no-op.

### So verify it, don't assume it

Same discipline as `make check` — read the output:

```
$ gh pr view 213 --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
[125]
```

An empty array on a PR that fixes something is a defect in the PR. Check it
after opening, and again after any base change.

### And check what you write *about* PRs

`make check-pr-citations` asserts that every `PR #N` in this repo's prose —
docs, script docstrings, test docstrings — is really a pull request. Like
`check-pr-link` it queries GitHub, so it is deliberately outside `make check`.

It exists because the two populations rot at different rates (#335). A worked
example is self-correcting: paste `make check-pr-link PR=327`, watch it fail,
fix it — which is how three of #335's four wrong numbers were found. A sentence
attributing work to a PR is never executed by anyone, so nothing catches it. The
gate's first live run found issue #297 cited as a pull request in a test
docstring and a design spec, both naming it as the PR that carried #297 and
#300; PR #315 is the one.

The recurring error is one shape: **an issue number standing in for the PR that
closed it.** They are adjacent in time, often adjacent in a sentence, and
nothing about `#297` says which kind of thing it is.

When a sentence *reports* a wrong citation it must contain one, so the gate
carries an `_EXEMPT` table of hand-written entries with reasons. Backticks are
not the discriminator — #293 established that formatting is no defence — and an
entry whose citation has been fixed must be removed, the same enforcement
`granularity.known_coarse` gets.

### When not to close

A PR that only partly addresses an issue, or whose fix nobody has verified
yet, uses `Refs #N` and says why in the body. #214 is the worked example: it
documents the fix for #197, but the fix is a repo setting whose effect
nobody had yet observed, so closing on merge would have claimed an unproven
result. Deliberate non-closure is fine; silent non-closure isn't.

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
