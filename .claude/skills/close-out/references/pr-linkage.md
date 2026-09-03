# Phase 5 — branch, PR, and verify the link

**Load when:** the fix is green and you are about to open the PR.

- Branch off `main`, named `fix/<issue>-<slug>` or `docs/<slug>`.
- One closing line per **confirmed** issue, in the PR body **and** the
  commit message, each with its own keyword. `Closes #1, #2` links only
  the first.
- For an issue this PR does not resolve — a partial fix, or one nobody
  has verified — write `Refs #N` and say why. Silence reads as oversight.
- Base **`main`**.

## Three ways the link fails silently

- **It only registers for PRs targeting the default branch.** A stacked
  PR records nothing, however many `Closes #N` lines it carries.
- **The body is parsed when written, not when the base changes.**
  Retargeting a stacked PR to `main` afterwards does not backfill; the
  body has to be edited again.
- **The parser reads prose, and backticks are no defence.** PR #293 was a
  doc-only change carrying `Refs #176`, whose `closingIssuesReferences`
  was correctly empty — and it still closed #176, because a sentence read
  "part 2's PR is the one carrying `Closes #176`". The line explaining
  the issue must stay open is what closed it. When writing *about* this
  convention, keep the keyword away from a live issue number.

## Verify, do not assume

Push everything first — the check reads the PR's commits from the GitHub
API, so it sees exactly what GitHub will merge.

```
make check-pr-link PR=<n> ISSUES="<the confirmed issues>"
```

Exit 0 required, **and the last run must come after the last change to
the PR's title, body or commits.** Phases 6 and 7 rewrite both; a pass
from before those edits is stale.

A non-zero exit means the PR is broken, not that the check is wrong.

## The one measured exception

`closingIssuesReferences` is **eventually consistent** after a body edit.
The check absorbs this itself: it reads the field up to three times, a
second apart, stopping when the answer settles, and prints `read the link
2x` (or `3x`) when it had to.

The retry covers both directions — the field is re-derived from the body
on every edit, and a removal propagates on the same delay as an addition
(#369, which used to retry `missing` only, on the belief that
registration was monotonic). What keeps it from masking a real defect is
the PR's own text: an `unexpected` link whose number still carries a
closing keyword somewhere in the title, body or commits is real and is
never re-read. `base` and `hazard` are never re-read either.

If a `missing`-only or `unexpected`-only failure survives all three
reads, the summary hedges rather than asserting the PR is broken, and
names the re-query:

```
gh pr view <n> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
```

If the number is there after all — or gone, for `unexpected` — say so:
three reads over two seconds were not enough and the bound wants raising.
Any other defect it reports is real, including `unexpected` reported
alongside its `hazard`, which is the pairing meaning the keyword really
is still in the text.

Phase 5 also satisfies the standing "every round ends with a PR" gate.
