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

If a fix is genuinely one line, make it. If it needs a decision, another
reviewer, or more scope than the change you're on, file it and say in the
PR what you left out and why. Shrinking scope is fine; doing it silently
isn't.

## Close the loop: every PR links its issue

**A PR that resolves an issue carries `Closes #N` in the PR body, targets
`main`, and is verified to have registered the link.** Filing issues is
worthless if closing them is manual — the backlog then only ever grows.

Two GitHub behaviours make this fail silently, and both have bitten us:

- **The link only registers for PRs targeting the default branch.** A
  stacked PR based on another branch records nothing, however many
  `Closes #N` lines it contains.
- **The body is parsed when it is written, not when the base changes.**
  Retargeting a stacked PR to `main` afterwards does *not* backfill the
  link; the body has to be edited again.

So don't assume — check, the same way you'd check `make check`:

```
gh pr view <n> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
```

Empty output on a PR that fixes something is a bug in the PR. Keep the
keyword in the commit message too, so a squash-merge or a direct push
still closes the issue if the link is missing.

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

**After any ingest, run `make generate-authors` and commit the result.**
`data/index.sqlite` is gitignored, so CI validates chunk counts against
the committed `data/authors/chunk_counts.json` instead. Local runs have
the real index and fail if that snapshot has drifted from it — but only
locally, so a stale snapshot leaves CI checking a fossil.

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
