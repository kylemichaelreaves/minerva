---
name: close-out
description: Use when taking a tracked defect to a merged PR in this repo — a backlog issue number, "close out #N", "clear the backlog", or picking up an issue someone filed earlier
---

# Close-out

Work one or more backlog issues to a merged-ready PR.

**Core principle:** an issue is a pointer written by someone who hit a
problem, plus a guess written by someone who had not yet tried the fix.
The pointer is usually right. The guess is often wrong. Treat them
differently or you inherit the guess as fact.

## The phases

Seven, in order. Each has an exit condition; do not advance past one that
is unmet — say what is blocking and stop.

Keep a verdict table from phase 1 onward and restate it at each phase
boundary, so a multi-issue run cannot lose one:

| Issue | Verdict | Notes |
|-------|---------|-------|

| # | Phase | Exit condition |
|---|-------|----------------|
| 1 | **Verify the claims.** Re-run every command under `## Measured`. Check the cause under `## Hypothesis` independently. → references/verifying-claims.md | A verdict per issue backed by output you saw this session. |
| 2 | **TDD the fix.** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. | A test you watched fail, for the reason you expected, before any implementation existed. "It would have failed" does not count. |
| 3 | **`make check`.** | Green, **and the last run happened after the last edit.** Re-run after any edit made while fixing its output. |
| 4 | **Verify against the live corpus.** Only when the change touches corpus data, ingest, refs or lemmas. Say explicitly that you are skipping it, and why. | Numbers pasted into the PR body. Never report a sampled number as a population number. |
| 5 | **Branch, PR, verify the link.** → references/pr-linkage.md | `make check-pr-link PR=<n> ISSUES="..."` exits 0, run after the last change to the PR's title, body or commits. |
| 6 | **Correct the record.** | Every non-CONFIRMED verdict has its comment on the issue **and** its line in the PR body. Wrong claims in docs, comments or commit messages are fixed in this PR. |
| 7 | **File findings, and slot them.** → references/filing-findings.md | Every finding has an issue number, and either a row in an active plan or an explicit note that no active plan covers it. |

## When a verdict is not CONFIRMED

Phase 1 produces `CONFIRMED`, `CORRECTED`, or `NOT-REPRODUCED`. Post the
correction on the issue immediately — that is unconditional, and it is
never a new issue; it goes on the thing that was wrong.

Whether you then **halt for a go/no-go** is decided by one question:

> **Does the correction change what gets built?**

| Halt and ask | Record and continue |
|---|---|
| The defect does not reproduce | The defect reproduces; only the issue's explanation of it was wrong |
| The fix approach changes | The approach is unchanged and the correction only narrows or clarifies it |
| The scope grows beyond what the issue describes | The scope shrinks, or is identical |
| The fix cannot land as described — a gate blocks it, or a prerequisite is unfixed | The fix lands as described |
| Two defensible fixes now exist and the issue picked neither | The issue's own reasoning already settles the choice |

Any single row on the left means halt. Present the corrected scope and
wait. This is graded on purpose: an unconditional halt on every
correction gets argued away, and measurably does — see
references/verifying-claims.md for the baseline runs.

## Red flags

- About to write code while a left-column row is true.
- Writing a number into an issue that you did not produce **this phase**.
- "The scope is unchanged, so there's nothing to decide" — check the
  table rather than the feeling. Narrowing is continue; *cannot land* is
  halt, and both feel like "unchanged" at 6pm.
- Verifying the one file, symbol or number an earlier note named, without
  asking how many others there are.
- A finding filed with a numerator and no denominator.
