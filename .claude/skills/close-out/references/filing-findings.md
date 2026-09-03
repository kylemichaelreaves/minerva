# Phase 7 — filing what you found

**Load when:** you are at phase 7, or any time you are about to file an
issue from something noticed in passing.

Anything discovered that is not already tracked gets its own issue,
before you finish. A bug you noticed but did not cause; a fix you scoped
down and the part you left out; a guard that is inert; a value you had to
reverse-engineer. Not: things already tracked (link them), or things you
fixed in this change.

This is CLAUDE.md's standing "record what you find" rule. It does not
expire with this workflow.

## The `## Measured` template

Every issue splits under `## Measured` and `## Hypothesis`, with the
cause and proposed fix under the second. `## Measured` has three
**required** slots:

```markdown
## Measured

<!-- 1. COMMAND — run in this phase, not recalled from earlier. -->
$ <the exact command, no head/tail/grep -m that truncates the count>

<!-- 2. OUTPUT — enough to show the claim, plus its last line. -->
<output>

<!-- 3. POPULATION — REQUIRED. N of M, or the word "unmeasured". -->
152 of the 352 files prettier considers.
```

**Slot 3 is the one that fails.** A finding with a numerator and no
denominator is the shape this repo keeps producing: "four files are
unformatted" (152), "three files typechecked by nothing" (two, and a
third that was checked all along).

If you genuinely cannot get a denominator, write `M: unmeasured` and say
why. That is honest and costs nothing. What is not allowed is a bare
count that reads as a population.

## Regenerate, do not recall

Produce slot 1 by **running the command now**, in this phase. Do not
transcribe a number from earlier in the session, from working notes, or
from memory of what you saw.

The failure this prevents, measured: three agents were handed a session
note reading *"checked drift — `src/utils/util.ts` came back flagged,
plus a 'code style issues found' line"* and asked to file the issue.

- Two re-ran the check in full and reported what was there — 149 warnings
  and 6 errors, one of them a real CSS syntax error the note never
  mentioned. One wrote that it "showed far more drift than the original
  working note's single-file claim, so I used the freshly measured
  numbers rather than the abbreviated note."
- One ran `npx prettier --check src/utils/util.ts` — **the single
  filename the note handed it** — confirmed that one file, and filed. It
  never asked how many others there were.

Same prompt, same model, opposite behaviour. Intermittent, which is why
this is a required slot rather than advice to be thorough: a slot is
either filled or visibly empty.

The original of this failure had the same shape. A `prettier --check`
piped through `tail -2` was read as the whole list, and "four files"
reached a filed issue. The truncation was invisible hours later; only
re-running surfaced it.

## Also required

- How you found it, the precedent PR/issue, and labels.
- **Slotting is separate and conditional.** Look for a plan-of-record
  document covering the area — a plan's own text says what it is scoped
  to. Slot the finding into it in this PR if one is discoverable and
  still active; a landed batch takes an `N-bis` follow-up rather than a
  new number at the end. **If no such document exists, or the only
  candidate scopes itself to something already finished, say so
  explicitly** rather than inventing a row in a closed plan (#433).
