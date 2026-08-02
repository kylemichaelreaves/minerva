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

## Verify before claiming

`make check` — ruff (`src tests scripts perseus`) + eslint + tsc + pytest
+ vitest + author/API/import gates. Run it and read the output before
saying something passes.

Two gates are easy to miss because they don't block a merge:

- **SonarCloud** fails PRs under 80% coverage *of the lines you changed*.
  Not a required check (#158), so nothing stops you — check it anyway.
- **Chunk-count validation is silently skipped in CI** because the DB is
  gitignored (#157). It only ever runs locally.

Branch protection is `strict: true`: every merge to `main` puts open PRs
`BEHIND` and they need `git rebase origin/main` before they can merge.

## Don't trust a stated root cause

Issues and commit messages name culprits that are often wrong. Verify with
`git log -S '<symbol>'` and `git show <commit>^:<path>` before repeating
the attribution — in #116 both defect classes turned out to predate the
commit the issue blamed, and the real cause was the missing lint gate.

## Destructive operations

`scripts/snapshot-db.sh <reason>` before anything that mutates the DB.
See [docs/MEMORY.md](docs/MEMORY.md) for the operator rules — re-ingest
wipes derived tables unless the documented preservation paths are used.
