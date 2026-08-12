---
description: Work one or more backlog issues end to end — verify their claims, TDD the fix, gate it, PR it, and record what they got wrong
argument-hint: <issue> [issue...]
---

Work these issues to a merged-ready PR: **$ARGUMENTS**

Seven phases, in order. Each has an exit condition. **Do not advance past a
phase whose exit condition is unmet** — say what is blocking and stop.

Keep a verdict table from phase 1 onward and restate it at each phase boundary,
so a multi-issue run cannot lose one:

| Issue | Verdict | Notes |
|-------|---------|-------|

## Phase 1 — Verify the claims. Do not skip; do not skim.

For **each** issue: `gh issue view <n>`.

- Re-run every command under `## Measured` and compare the output to what the
  issue states.
- Check the cause named under `## Hypothesis` independently: `git log -S
  '<symbol>'`, `git show <commit>^:<path>`, `--help`, or just run the thing. The
  obvious culprit is frequently not the origin.
- If the issue proposes a fix, check that the fix does what the issue says it
  does. #125 proposed `uv sync --frozen` to fail on a stale lock; `--frozen`
  *skips* that check.

Record a verdict per issue: `CONFIRMED`, `CORRECTED`, or `NOT-REPRODUCED`.

**Exit condition:** every issue has a verdict backed by output you actually saw.

**If any verdict is not `CONFIRMED`:** post the correction as a comment on that
issue now — what it claims, what is true, the command and its output, and what
would have gone wrong had you trusted it. Then **stop** and present the
corrected scope for a go/no-go. Both outcomes are real: #304 was built after its
stated blocker turned out false, and #311's proposed fix was discarded entirely.
That decision is not yours to make silently.

## Phase 2 — TDD the fix

Use the `superpowers:test-driven-development` skill.

**Exit condition:** a test that you watched fail, for the reason you expected,
before any implementation existed. "It would have failed" does not count.

## Phase 3 — `make check`

**Exit condition:** green, **and the last run happened after the last edit**.
Two pushes on #254 failed CI on a lint error and a tsc arity error introduced
after the final local run. If you edit anything while fixing this phase's
output — including the fix for the thing it just flagged — run it again.

Note `make check` evaluates changed-line coverage including branches
(`check-diff-coverage`). It does **not** evaluate Sonar's duplication rating or
its reliability rating. #324 measured a renamed file arriving at Sonar's
coverage gate with its whole surface counted as new — on the specific PR it
examined, not a general law — and locally `make check` reports the opposite for
a content-free rename: no hunks, nothing to cover.

## Phase 4 — Verify against the live corpus

Conditional: only when the change touches corpus data, ingest, refs, or lemmas.
State explicitly that you are skipping it, and why, when you skip it.

`make audit`, or targeted SQL against the live index.

**Exit condition:** numbers pasted into the PR body. Not "the counts look
right" — the counts.

Never report a sampled number as a population number. Both wrong figures in this
repo's history came from a sample that looked representative.

## Phase 5 — Branch, PR, and verify the link

- Branch off `main`, named like `fix/<issue>-<slug>` or `docs/<slug>`.
- One closing line per **confirmed** issue, in the PR body **and** the commit
  message, each with its own keyword — `Closes #1, #2` links only the first.
- For an issue this PR does *not* resolve — a partial fix, or one nobody has
  verified — write `Refs #N` and say why in the body.
- Base **`main`**. A stacked PR registers no link, and retargeting afterwards
  does not backfill.
- When writing *about* this convention, keep the keyword away from any live
  issue number.

Push everything first — the PR has to actually reflect this work. The check
itself now reads the PR's commits from the GitHub API (`gh pr view --json
commits`), not local or remote git refs, so it always sees exactly the
commits GitHub will use for the merge; there is no longer a partially-pushed
gap where the check can print `ok` on unreviewed local commits.

Then, always:

```
make check-pr-link PR=<n> ISSUES="<the confirmed issues>"
```

**Exit condition:** that command exits 0, **and the last run happened after
the last edit** — same rule as phase 3. Phases 6 and 7 add commits and rewrite
the PR title and body after this check runs; a passing result from before
those edits is stale. Re-run the check after any phase 6 or 7 change to the
PR's title, body, or commits. A non-zero exit means the PR is broken, not that
the check is wrong.

One exception, measured: `closingIssuesReferences` is **eventually consistent**
after a body edit. Running the check within a second or two of `gh pr edit` can
report `[missing]` for a link that does in fact register.

**The check now absorbs this itself.** It reads the field up to three times, a
second apart, and stops as soon as every expected link is present — so a
`missing` verdict has already outwaited the lag, and the run prints `read the
link 2x` (or `3x`) when it had to. The retry is deliberately narrow: `missing` is
the only verdict the lag can fabricate, so `base`, `unexpected` and `hazard` are
never re-read.

If a `missing`-only failure survives all three reads, the summary line hedges
rather than asserting the PR is broken, and names the re-query:

```
gh pr view <n> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
```

If the number is there after all, say so — three reads over two seconds were not
enough and the bound wants raising. Any other defect it reports is real.

## Phase 6 — Correct the record

A correction goes **on the thing that was wrong**, never into a new issue.

- Wrong claim in an issue → a comment on that issue (posted in phase 1).
- Wrong claim in a doc, code comment, or commit message → fixed in this PR.
- Either way → stated in the PR body too.

**Exit condition:** every `CORRECTED` or `NOT-REPRODUCED` verdict from phase 1
has both its comment and its line in the PR body.

## Phase 7 — File and slot what you found

Anything discovered along the way that is not already tracked gets its own
issue, before you finish. A bug you noticed but did not cause; a fix you scoped
down and the part you left out; a guard that is inert; a value you had to
reverse-engineer. Not: things already tracked (link them), or things you fixed
in this change.

Each issue carries evidence — the command and its output, or `file:line` and the
lines themselves — split under `## Measured` and `## Hypothesis`, with the cause
and the proposed fix under the second. Add how you found it, the precedent
PR/issue, and labels.

Then **slot it into a batch** in `docs/backlog-closeout-plan.md`, in this PR. A
found issue is filed *and* placed; a landed batch takes an `N-bis` follow-up
rather than a new number at the end. If nothing groups, say so explicitly and
give it its own row with a reason.

**Exit condition:** every finding has both an issue number and a batch row.

## Finally

Report: the verdict table, what landed, what you deliberately left out and why,
and the `check-pr-link` output.
