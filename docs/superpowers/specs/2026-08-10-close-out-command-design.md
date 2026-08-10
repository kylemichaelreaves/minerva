# `/close-out` — the per-issue close-out procedure as a command

**Status:** approved 2026-08-10
**Issues:** #321 (this); #322 (hooks — consumes the script this lands)
**Related:** `CLAUDE.md`, `docs/CONTRIBUTING.md`, `docs/backlog-closeout-plan.md`
(the three documents the procedure is currently spread across); #320 (`make
audit`, the round's first tooling step)

Second step of the agreed tooling round: #320 → **#321** → #322.

## Problem

The procedure for working one backlog issue is real and repeatable, and is
reconstructed from prose in three documents every session. Steps get skipped,
and the skips have cost reruns. #321 enumerates seven steps and, for each, the
incident where it was missed:

| Step | Missed |
|---|---|
| 1. Verify the issue's claims first | Six claims needed correcting on 2026-08-09 alone |
| 2. TDD the fix | — |
| 3. `make check`, again after any fix-edit | Two pushes on #254 failed CI on errors introduced after the last local run |
| 4. Verify against the live corpus | — |
| 5. PR against `main`, link verified | Three documented silent failure modes |
| 6. Record what the issue got wrong, on the issue | Batches 1–5 |
| 7. File what you found, and slot it into a batch | …produced eleven unslotted issues |

Steps 1 and 4 are judgment and cannot become gates. What can be encoded is the
sequence, the exit condition of each step, and the mechanical checks that hang
off it.

`.claude/` holds only `settings.local.json` today — no commands, no hooks, no
`settings.json`.

## Decisions

Four forks were settled before design, two of them named as open in #321
itself.

**1. Step 1's verdict controls the flow.** `CONFIRMED` proceeds to step 2.
Anything else posts the correction on the issue immediately — step 6 pulled
forward — then **halts** with the corrected scope for a go/no-go.

A hard refusal would be wrong: #304 was built after its stated blocker turned
out false. Never halting would also be wrong: #311's proposed fix was discarded
entirely, and the remaining six steps would have run against a premise nobody
re-approved. The verdict is the only thing that distinguishes the two cases, so
the verdict is what branches.

**2. One command, seven ordered phases, each gated on its own exit condition.**
Not a thin orchestrator over existing skills: the repo-specific parts — the
`closingIssuesReferences` check, the `## Measured` / `## Hypothesis` split, batch
slotting — have no skill to delegate to and would still need writing. Phase 2
does delegate to `superpowers:test-driven-development`.

**3. It takes one or more issue numbers and produces one PR.** Batches land
together in this repo — PR #297 carried both #297 and #300. Phase 1 runs per
issue and reports a verdict for each; phases 2–4 cover the combined change;
phase 5 emits one PR with a closing line per confirmed issue and verifies that
*every* number came back. A multi-issue link check is precisely where a number
gets dropped silently.

Rejected: a `--with` flag promoting one issue to primary. The ride-alongs would
get a weaker phase-1 pass than the primary, which is the shape of #300's
accounting fix reaching one of eight scrapers.

**4. The mechanical checks land as a script, not as prose in the command.**
#321 says the command should invoke #322's checks rather than duplicate them,
and #322 does not exist yet. Extracting `scripts/check_pr_link.py` now gives one
implementation with one set of tests: the command calls it in phase 5, and
#322's `PostToolUse` hook calls the same script later. It also converts phase
5's gate from an instruction into an exit code.

## Design

### `scripts/check_pr_link.py`

`.py`, not `.sh` — every sibling gate is Python: `check_diff_coverage.py`,
`check_api_types.py`, `check_author_imports.py`, `check_author_ingest.py`.

Inputs: a PR number and the issue numbers the PR is expected to close.
Sources: `gh pr view <n> --json baseRefName,body,closingIssuesReferences`, and
`git log` over the branch's commits.

Four checks:

1. **Base is the default branch.** A stacked PR registers no link however many
   closing lines it carries.
2. **`closingIssuesReferences` ⊇ expected.** Reports the missing numbers.
3. **`closingIssuesReferences` ⊆ expected.** An unintended reference that GitHub
   *did* resolve from the body shows up here as an extra number, with no need for
   the script to judge whether a sentence uses the keyword or discusses it.
4. **Backtick-blind keyword scan over the text destined for the merge commit** —
   the PR title and body (which are the squash-merge default message) and the
   branch's own commit messages. Hits outside the expected set fail.

Check 4 is not a redundant regex behind check 3: the two parsers disagree, and
check 3 alone would have missed the incident that motivates this whole gate. See
below.

##### Measured: the two parsers disagree

```
$ gh pr view 293 --json baseRefName,mergeCommit,closingIssuesReferences \
    --jq '{base:.baseRefName, merge:.mergeCommit.oid, closes:[.closingIssuesReferences[].number]}'
{"base":"main","closes":[],"merge":"c00d55c5ff62a1829afb9ff2cd8e424544add5b4"}

$ gh api repos/:owner/:repo/issues/176/timeline \
    --jq '.[] | select(.event=="closed" or .event=="reopened") | "\(.event)\t\(.created_at)\t\(.commit_id // "-")"'
closed          2026-08-08T22:55:39Z    c00d55c5ff62a1829afb9ff2cd8e424544add5b4
reopened        2026-08-08T22:56:07Z    -

$ git log -1 --format='%B' c00d55c5 | grep -niE "(close[sd]?|fix(e[sd])?|resolve[sd]?)[^.]{0,40}#[0-9]+"
32:part 2's PR is the one carrying `Closes #176`.
```

PR #293's `closingIssuesReferences` is **empty** — the PR-body parser exempted
the backticked reference — and #176 was nonetheless closed 28 seconds before it
was reopened, by that PR's merge commit. The commit-message parser does not
exempt backticks, and on a squash merge the PR body *is* the commit message.

Two consequences for the script:

- The scan must be **backtick-blind**, and must run over the PR body and title,
  not only over commits that already exist. At PR-creation time the merge commit
  does not exist yet; its text does.
- A green check 3 is not evidence of safety. `[]` was the correct value for
  #293 and the issue still closed.

`CLAUDE.md` states this correctly ("whose `closingIssuesReferences` was correctly
empty — and it still closed #176"); an earlier draft of this spec credited the
catch to check 3 and was corrected against the API above before implementation.

Exit non-zero on any failure, quoting the offending text. Structure: pure
functions over the JSON and the message text, with the subprocess boundary
injected, so tests feed fixtures instead of reaching GitHub.

`make check-pr-link PR=<n> ISSUES="<n> <n>"`. Deliberately **not** part of
`make check` — it needs a PR that already exists.

#### A hazard in this change's own tests

The fixtures must contain literal closing-keyword-plus-number strings to test
checks 3 and 4. Inside a file that is inert: GitHub parses commit messages and
PR bodies, not tree contents. The live hazard is quoting fixture text into this
PR's own body or commit message — and per the measurement above, backticks are
not a defence there. Mitigations: fixtures use numbers that are not live issues,
and the PR body describes the checks without reproducing their inputs.

### `.claude/commands/close-out.md`

The repo's first committed project command. Frontmatter: `description`,
`argument-hint: <issue> [issue...]`, `allowed-tools`.

The body is seven phases. Each carries what to do, its **exit condition**, and
what to do when the condition fails. The model maintains a per-issue verdict
table across phases so a multi-issue run cannot lose one.

| # | Phase | Exit condition |
|---|---|---|
| 1 | **Verify the claims.** Per issue, re-run everything under `## Measured`. Check the cause named under `## Hypothesis` with `git log -S`, `git show <c>^:<path>`, `--help`, or by running the thing. | A verdict recorded for every issue: `CONFIRMED` / `CORRECTED` / `NOT-REPRODUCED`. Anything but `CONFIRMED` → post the correction on that issue, then halt. |
| 2 | **TDD the fix.** Delegates to `superpowers:test-driven-development`. | A test watched to fail for the right reason before implementation. |
| 3 | **`make check`.** | The last run happened *after* the last edit — not merely "it was green once". |
| 4 | **Corpus verification.** Conditional: fires only when the change touches corpus data. `make audit`, or targeted SQL against the live index. | Numbers pasted, not asserted. |
| 5 | **Branch, PR, link.** Base `main`; one closing line per confirmed issue in the body *and* the commit message. | `make check-pr-link` exits 0. Non-zero means the PR is broken, not that the check is wrong. |
| 6 | **Correct the record.** | Every `CORRECTED` verdict has its comment on the issue and a line in the PR body. Doc and comment corrections ship in the same PR. |
| 7 | **File and slot findings.** New issues get the `## Measured` / `## Hypothesis` split, evidence, labels. | Every finding has both an issue number *and* a batch row in `docs/backlog-closeout-plan.md`, in this PR. |

Phase 5 is also where the standing "every round ends with a PR" gate is
satisfied.

### The three prose sources

Nothing is deleted. Each gains a one-line pointer to the executable form:

- `CLAUDE.md`, "Close the loop" → `make check-pr-link` as the checked version of
  the `gh pr view` line already there.
- `docs/CONTRIBUTING.md`, "Record what you find" → phase 7.
- `docs/backlog-closeout-plan.md`, "Standing gates" → the gates are enumerated
  in the command.

The risk is drift: prose and command diverge and nobody notices. Accepted, on
the grounds that the alternative — reducing CLAUDE.md to "run the command" —
fails for exactly the sessions that never invoke it. CLAUDE.md binds every
session; a command file is invisible to anyone reading the repo.

## Testing

- `tests/test_check_pr_link.py`. Precedent: `tests/test_check_diff_coverage.py`,
  `tests/test_audit_invariants.py`. Coverage note: `scripts/**` is
  coverage-excluded, so the diff-coverage gate does not apply — the tests exist
  because this script's failure mode is silence, not because a gate demands
  them. Cases: base is not `main`; an expected issue missing; an unexpected
  issue present in `closingIssuesReferences`; **a backticked keyword in the PR
  body while `closingIssuesReferences` is empty** — the #293 shape, and the case
  a naive implementation passes; a keyword in a branch commit message only; the
  all-clear.
- A markdown prompt has no unit test. The command's trial is a **live run on the
  next batch**, nominally **#291** (the `min_chunk_chars=60` floor): small,
  self-contained, and its central claim — the Nietzsche signatures are 66–113
  chars — is exactly what phase 1 exists to check. Confirmed exercises the happy
  path; contradicted exercises the halt.
- Not dogfooded on its own PR. That would be circular, and phase 4 has nothing
  to verify against on a doc-and-script change.

## Scope boundary

This change does **not** add `.claude/settings.json` or any hook. That is #322,
whose own open questions are unsettled: when `make check` is tolerable to run
automatically, and how to scope the keyword grep. What this change does for #322
is land the script its hook will call, so the hooks round is wiring rather than
reimplementation.

The PR resolves #321 and carries `Refs #322`.
