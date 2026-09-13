# Minerva — working rules

Full contributor guide: [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).
This file is the short list of things that bind every session.

## Record what you find

**Anything you discover that isn't already in the tracker gets a GitHub
issue — before you move on.** Every kind of work, every time: fixing a
bug, adding an author, reviewing a diff, reading code for an unrelated
reason. File it whether or not you intend to fix it.

The point is that the finding survives the session it was found in.

Counts: a bug you noticed but didn't cause; a fix you scoped down and the
part you left out; a guard that's inert; a check that runs but validates
nothing; a test whose name misdescribes it; a value you had to
reverse-engineer because it was undocumented.

Doesn't count: already tracked (link it instead), or fixed in the same
change.

Issues carry evidence — the command and its output, or `file:line` and
the lines themselves — plus how you found it, the precedent PR/issue, and
labels. See the "Record what you find" section of CONTRIBUTING for the
full shape.

**Split the body under `## Measured` and `## Hypothesis`, with the cause
and the proposed fix under the second.** The two halves keep very
different: across the twelve close-out issues, eleven of twelve measured
numbers still reproduced and not one defect was imaginary — while three of
the four batches worked so far had to correct the *explanation*
mid-implementation. #262's proposed fix would not have stopped the hang,
and #125's recommended flag did the opposite of what the issue wanted. A
pointer to a defect is durable because someone hit it; a diagnosis is a
guess written before anyone tried the fix. Writing both in one voice is
how the guess gets inherited as fact — and it is what gives "Don't trust a
stated cause" below something specific to check.

If a fix is genuinely one line, make it. If it needs a decision, another
reviewer, or more scope than the change you're on, file it and say in the
PR what you left out and why. Shrinking scope is fine; doing it silently
isn't.

## Close the loop: every PR links its issue

**A PR that resolves an issue carries `Closes #N` in the PR body, targets
`main`, and is verified to have registered the link.** Filing issues is
worthless if closing them is manual — the backlog then only ever grows.

Three GitHub behaviours make this fail silently, and all three have bitten
us:

- **The link only registers for PRs targeting the default branch.** A
  stacked PR based on another branch records nothing, however many
  `Closes #N` lines it contains.
- **The body is parsed when it is written, not when the base changes.**
  Retargeting a stacked PR to `main` afterwards does *not* backfill the
  link; the body has to be edited again.
- **The parser reads prose, and code formatting is no defence.** It scans
  the merge commit message for a closing keyword next to any issue
  number, with no notion of whether the sentence is *using* the keyword or
  *talking about* it, and backticks do not exempt it. PR #293 was a
  doc-only change carrying `Refs #176`, whose `closingIssuesReferences`
  was correctly empty — and it still closed #176, because a sentence in
  the body read "part 2's PR is the one carrying `Closes #176`". The line
  explaining that the issue must stay open is what closed it. When writing
  *about* the convention, keep the keyword away from a live issue number.

So don't assume — check, the same way you'd check `make check`:

```
gh pr view <n> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
```

Empty output on a PR that fixes something is a bug in the PR. Keep the
keyword in the commit message too, so a squash-merge or a direct push
still closes the issue if the link is missing.

`make check-pr-link PR=<n> ISSUES="<n> <n>"` runs that query and three more —
base branch, unexpected links, and a backtick-blind scan of the text destined
for the merge commit — and exits non-zero on any of them. `/close-out` calls it
at phase 5.

When a PR should deliberately *not* close its issue — a partial fix, or a
fix nobody has verified yet — write `Refs #N` instead and say why in the
body. Silence reads as an oversight.

## Verify before claiming

`make check` — ruff (`src tests scripts perseus`) + eslint + tsc + pytest
+ vitest + changed-line coverage + author/API/import gates. Run it and read
the output before saying something passes. **Re-run it after any edit you
make while fixing its output** — two pushes on #254 failed CI on a lint
error and a tsc arity error introduced *after* the last local run.

**SonarCloud** fails PRs under 80% coverage *of the lines you changed*, and
is a **required check** as of #158 — a red gate blocks the merge. `make check`
evaluates the same thing locally as of #255 (`check-diff-coverage`), counting
**branches as well as statements** because Sonar does: a one-line guard whose
false branch is untested scores 3/4, not 100% (#250).

**The same thing, on different inputs — and the difference is `data/`.**
`check-diff-coverage` measures the tests that actually ran, and a test gated
on a file under `data/` runs locally and *skips in CI*, because `.gitignore`
keeps the corpus out of every checkout. The local number is then higher than
Sonar's and nothing says so. Measured on #573: `hobbes_la.py` read **97%**
locally and **63%** in CI, and the gate failed at 69.8% new-code coverage
against a green `make check`. The same silence cost #133 three e2e assertions
that had been failing for months against a renamed corpus.

So a parser whose tests read real corpus files needs a **committed fixture**
— a short excerpt in the real shape, under `tests/fixtures/` — or its
coverage is measured only on the machine that has the data. To see what CI
sees, hide the input and re-run:

```
mv data/<corpus>/<dir> /tmp/hidden && .venv/bin/python -m pytest <test file> \
  -q --cov=<module> --cov-report=term; mv /tmp/hidden data/<corpus>/<dir>
```

Do not substitute `make coverage` for it. That reports *whole-project*
coverage — a different number, which can be green while the gate is red. On
#254 the project sat at 75% while the PR's new code was at 58.5%.
`scripts/**` and `perseus/**` are coverage-excluded, so the bar applies to
`src/minerva/` and `web/src/`. Comparing against something other than main:
`make check DIFF_BASE=origin/other`.

`make check` still does not cover everything CI does:

- **Duplication** (≤3% on new code) and the **reliability** rating are Sonar
  gates with no local equivalent. Copying a component wholesale fails them at
  any coverage — #254 duplicated a picker and had to extract the shared shell.
- A red **security** rating on a PR that touched operator tooling used to mean
  a moved line (#167); the backlog is now triaged to zero, so treat a new one
  as real. See CONTRIBUTING.
- The **maintainability** rating on new code must be **A**, and the thing that
  actually drops it is **cognitive complexity ≤ 15 per function**. It blocked
  #559 at 29 while `check-diff-coverage` was green at 91.7% the whole time, so
  nothing local warned. Adding to a function that is already dense is enough —
  `_split_chapter_block` had been over the line for a while and a small
  restructure made it Sonar's problem. Extract rather than argue with it; the
  piece you pull out usually wants its own name anyway.

  **Ruff's `C901` is not this metric and will not protect you.** Cyclomatic
  and cognitive complexity disagree about *which* function is the problem —
  measured on #559's two revisions:

  ```
  $ ruff check --select C901 --config "lint.mccabe.max-complexity=10" split_paragraphic.py
  C901 `split_by_section` is too complex (12 > 10)     # both before AND after
  ```

  Ruff flags `split_by_section` in both revisions and never flags
  `_split_chapter_block` — the one Sonar failed the build on. Enabling `C901`
  as a local proxy buys a different list, not an early warning.

  Note a line that merely *moves* counts as new code in full, so a comment
  added above an untouched regex hands you its pre-existing smells. That is
  how #559 also acquired a super-linear-backtracking warning on a line it
  never edited. The finding was real; the attribution was an artefact.

**After any ingest, run `make generate-authors` and commit the result.**
`data/index.sqlite` is gitignored, so CI validates against the two
committed snapshots instead: `data/authors/chunk_counts.json` for the
per-corpus count bands, and `data/authors/chunk_granularity.json` for
per-work/lang chunk length (#176). Local runs have the real index and fail
if either snapshot has drifted from it — but only locally, so a stale
snapshot leaves CI checking a fossil.

The granularity gate is **baseline-pinned**: the work/lang pairs that
already exceed its thresholds are excused by `granularity.known_coarse`
in `data/authors/manifest.yaml`. Count them rather than quoting a number
from here — the baseline shrinks every time something is re-chunked, and
the 94 this paragraph used to name was true when the gate landed (#292,
2026-08-08) and was 64 seven days later:

```
./.venv/bin/python -c "import yaml; print(len(yaml.safe_load(open('data/authors/manifest.yaml'))['granularity']['known_coarse']))"
``` A newly-coarse work appears in the
generated snapshot and fails `make check-authors` until it is either
re-chunked or added to that baseline by hand — the manifest is policy and
is not regenerated, which is what keeps the gate from blessing its own
violations. Removing a fixed entry is enforced too; a stale one fails the
same way.

Branch protection is `strict: true`: every merge to `main` puts open PRs
`BEHIND` and they need `git rebase origin/main` before they can merge.

## Don't trust a stated cause — and correct the record when it's wrong

Issues, commit messages, and docs name culprits, flags, versions and
counts that are often wrong. Verify — `git log -S '<symbol>'`, `git show
<commit>^:<path>`, `--help`, or just run the thing — before repeating a
claim. In #116 both defect classes predated the commit the issue blamed,
and the real cause was the missing lint gate.

**When what you find materially differs from what the source says, record
the difference before you move on.** Same standing obligation as "Record
what you find" above, with one deliberate exception: **a correction is not
a new issue.** It goes on the thing that was wrong.

- Wrong claim in an **issue** → comment on that issue.
- Wrong claim in a **doc, comment, or commit message** → fix it in the
  same PR.
- Either way, say it in the PR body too.

Carry four things: what the source claims, what is actually true, the
command and its output that shows it, and — the part that stops the
repeat — **what would have gone wrong had you trusted it**.

"Material" means it changes the fix, the scope, or the risk. A flag that
does the opposite of what the issue recommends is material: #125 proposed
`uv sync --frozen` to fail the build on a stale lock, but `--frozen`
*skips* that check and installs the stale lock at exit 0 — `--locked` is
the one that fails. Shipping the issue as written would have pinned CI to
a lock that could drift from `pyproject.toml` forever, which is the exact
bug the issue set out to fix. A count or a status that someone would plan
around is material (#205's grep missed 2 tracked files; #197's "three
Dependabot PRs are stuck" was true when filed and isn't now). Typos and
rephrasings are not.

Corrections don't add to the backlog. They keep it honest.

## Destructive operations

`scripts/snapshot-db.sh <reason>` before anything that mutates the DB.
See [docs/MEMORY.md](docs/MEMORY.md) for the operator rules — re-ingest
wipes derived tables unless the documented preservation paths are used.
