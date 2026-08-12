# `/close-out` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode the seven-step per-issue close-out procedure as `.claude/commands/close-out.md`, backed by a tested `scripts/check_pr_link.py` that turns the PR↔issue link check from an instruction into an exit code.

**Architecture:** Two artifacts with a clean seam. The deterministic half — four checks over a PR's base branch, its resolved closing links, and the text destined for its merge commit — is a Python script with pure functions and a thin IO shell, unit-tested against fixtures. The judgment half is a markdown command that sequences seven phases and calls the script at phase 5. #322's `PostToolUse` hook will later call the same script, so there is one implementation.

**Tech Stack:** Python 3.13 (stdlib only — `argparse`, `re`, `json`, `subprocess`), pytest, the `gh` CLI, GNU make, Claude Code slash-command markdown.

**Spec:** `docs/superpowers/specs/2026-08-10-close-out-command-design.md`
**Issue:** #321. Related: #322 (hooks, consumes the script), #320 (`make audit`, landed).

## Global Constraints

- Python 3.13, stdlib only. No new dependency — `pyproject.toml` is not touched.
- `scripts/` is coverage-excluded, so the diff-coverage gate does not apply. Tests exist because this script's failure mode is silence, not because a gate demands them.
- House style, copied from `scripts/check_diff_coverage.py`: `#!/usr/bin/env python3`, a module docstring carrying the rationale under CAPS section headers, `from __future__ import annotations`, `REPO = Path(__file__).resolve().parent.parent`, a `Problem` exception for refusals, `main() -> int`, errors to `sys.stderr` prefixed `check-pr-link:`, `if __name__ == "__main__": sys.exit(main())`.
- Every no-data path is an error, not a pass. An inert gate is worse than no gate (#116).
- `scripts/` is not a package; tests load the module via `importlib.util.spec_from_file_location`, exactly as `tests/test_check_diff_coverage.py:24-31` does.
- **Test fixtures use issue numbers in the 999000+ range.** They must contain literal closing-keyword-plus-number strings, which are inert inside a file but live inside a commit message or PR body. Never paste fixture text into either.
- `.envrc` exports `GH_TOKEN`, so plain `gh` inside the script resolves to the `kylemichaelreaves` account when invoked through `make` in a direnv-active shell. The script does not shell out to `direnv`.
- `make check` after every edit made while fixing `make check`'s output.

---

### Task 1: The backtick-blind closing-reference scanner

The single most important function in the change. It is what would have caught the incident that motivates the whole gate.

**Files:**
- Create: `scripts/check_pr_link.py`
- Test: `tests/test_check_pr_link.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `scan_closing_refs(text: str) -> set[int]` — every issue number a GitHub closing keyword points at anywhere in `text`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_check_pr_link.py`:

```python
"""Tests for the PR-to-issue link gate (#321).

The gate exists because three documented failure modes are all silent: a
stacked PR registers no link however many closing lines it carries, retargeting
to main does not backfill, and a closing keyword merely *discussed* in prose
still fires. The third one shut #176 three minutes after the same paragraph
said it must stay open.

The measurement that shaped this file: PR #293's `closingIssuesReferences` was
EMPTY and its merge commit closed #176 anyway. GitHub's PR-body parser exempted
a backticked reference and its commit-message parser did not, and on a squash
merge the body becomes the message. So a clean resolved-reference list is not
evidence of safety, and the scanner must not exempt backticks.

Fixture issue numbers are all 999000+. They are inert in a file — GitHub parses
commit messages and PR bodies, not tree contents — but live the moment anyone
pastes them into either.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_pr_link", REPO / "scripts" / "check_pr_link.py"
)
assert _spec is not None
assert _spec.loader is not None
cpl = importlib.util.module_from_spec(_spec)
sys.modules["check_pr_link"] = cpl
_spec.loader.exec_module(cpl)


class TestScanClosingRefs:
    def test_plain_keyword_and_number(self):
        assert cpl.scan_closing_refs("Closes #999001") == {999001}

    def test_backticks_are_not_an_escape(self):
        """The #293 shape, and the reason this function exists. GitHub's
        commit-message parser acted on exactly this text while the PR-body
        parser did not. A scanner that strips or skips code spans reintroduces
        the bug it was written to catch."""

        body = "part 2's PR is the one carrying `Closes #999001`."
        assert cpl.scan_closing_refs(body) == {999001}

    def test_is_case_insensitive(self):
        assert cpl.scan_closing_refs("CLOSES #999001") == {999001}
        assert cpl.scan_closing_refs("closed #999002") == {999002}

    def test_matches_every_keyword_github_acts_on(self):
        """GitHub's documented set, exactly. Getting this wrong in either
        direction is a defect: a missing keyword is a hole in the gate, an
        extra one is a false positive that trains people to ignore it."""

        for kw in (
            "close", "closes", "closed",
            "fix", "fixes", "fixed",
            "resolve", "resolves", "resolved",
        ):
            assert cpl.scan_closing_refs(f"{kw} #999001") == {999001}, kw

    def test_ignores_words_github_does_not_act_on(self):
        """`Refs` is the documented way to reference without closing, and
        `closing`/`fixing` are not in GitHub's set. Matching them would fail
        PRs that are correctly written."""

        assert cpl.scan_closing_refs("Refs #999001") == set()
        assert cpl.scan_closing_refs("See #999001") == set()
        assert cpl.scan_closing_refs("closing #999001") == set()
        assert cpl.scan_closing_refs("fixing #999001") == set()

    def test_finds_every_reference_not_just_the_first(self):
        text = "Closes #999001. Fixes #999002.\nresolved #999003"
        assert cpl.scan_closing_refs(text) == {999001, 999002, 999003}

    def test_requires_the_number_to_be_adjacent(self):
        """A keyword and a number in the same paragraph but not next to each
        other is ordinary prose. Flagging it would make the gate noise."""

        assert cpl.scan_closing_refs("This closes the loop. See #999001.") == set()

    def test_known_gap_an_intervening_word_is_not_matched(self):
        """DOCUMENTED LIMITATION, asserted so it is recorded rather than
        assumed. Whether GitHub itself acts on `closes issue #N` has not been
        verified against the API; if it does, this is a hole and widening the
        separator is the fix. Check 3 (`evaluate`, Task 2) is the backstop for
        anything GitHub actually resolves from the PR body — but NOT for a
        commit message, which is where the gap would bite."""

        assert cpl.scan_closing_refs("closes issue #999001") == set()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_check_pr_link.py -v`
Expected: collection error — `FileNotFoundError` / `spec_from_file_location` returns None, because `scripts/check_pr_link.py` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/check_pr_link.py`:

```python
#!/usr/bin/env python3
"""Verify a PR's closing links registered — and that none registered by accident (#321).

Three documented failure modes, each hit in this repo, and all three silent:

* A PR based on anything other than the default branch registers no closing
  link, however many `Closes` lines its body carries.
* The body is parsed when it is written, not when the base changes. Retargeting
  a stacked PR afterwards does not backfill; the body has to be edited again.
* The parser reads prose. A closing keyword next to an issue number fires
  whether the sentence is *using* the keyword or *talking about* it.

WHY A CLEAN `closingIssuesReferences` IS NOT ENOUGH

GitHub runs two parsers and they disagree. PR #293's `closingIssuesReferences`
was **empty** — its PR-body parser exempted a backticked reference — and its
merge commit closed #176 anyway, because the commit-message parser does not
exempt backticks and a squash merge turns the body into the message. So this
script does not merely read the API's answer; it also scans the text destined
for that commit, backtick-blind, before the commit exists.

WHY IT REFUSES RATHER THAN REPORTING ZERO

Every "no data" path is an error. A PR that cannot be fetched, a repo whose
default branch cannot be resolved — a naive implementation calls each of those
"nothing to report, fine", and an inert gate is worse than no gate (#116).

Usage:
    scripts/check_pr_link.py <pr> [issue ...]

    scripts/check_pr_link.py 330 297 300   # must close exactly 297 and 300
    scripts/check_pr_link.py 328           # must close nothing (a Refs-only PR)
"""

from __future__ import annotations

import re

#: GitHub's closing keywords, exactly as documented. `closing` and `fixing` are
#: deliberately absent because GitHub does not act on them, and matching them
#: would fail correctly-written PRs.
_KEYWORDS = r"close[sd]?|fix(?:e[sd])?|resolve[sd]?"

#: Keyword, then up to three non-letter characters, then #N.
#:
#: The separator class is what makes this BACKTICK-BLIND, and that is the whole
#: point. Narrowing it to bare prose — stripping code spans, requiring a plain
#: space — reintroduces exactly the bug this catches. See the module docstring.
_CLOSING_REF = re.compile(
    rf"\b(?:{_KEYWORDS})\b[^A-Za-z]{{0,3}}#(\d+)", re.IGNORECASE
)


def scan_closing_refs(text: str) -> set[int]:
    """Issue numbers a GitHub closing keyword points at anywhere in `text`."""
    return {int(m.group(1)) for m in _CLOSING_REF.finditer(text)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_check_pr_link.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint, then commit**

```bash
make lint-py
git add scripts/check_pr_link.py tests/test_check_pr_link.py
git commit -m "feat(scripts): backtick-blind scanner for closing references (#321)

GitHub runs two parsers and they disagree: PR #293's resolved-reference list
was empty and its merge commit still shut #176, because the commit-message
parser does not exempt backticks and a squash merge turns the body into the
message. The scanner therefore does not exempt them either.

Refs #321"
```

---

### Task 2: The four checks

**Files:**
- Modify: `scripts/check_pr_link.py`
- Test: `tests/test_check_pr_link.py`

**Interfaces:**
- Consumes: `scan_closing_refs(text: str) -> set[int]` from Task 1.
- Produces:
  - `Failure` — frozen dataclass with fields `check: str` and `detail: str`.
  - `evaluate(*, base_ref: str, default_branch: str, resolved: set[int], expected: set[int], scanned_text: dict[str, str]) -> list[Failure]`. `scanned_text` maps a human label (`"PR body"`, `"commit 4153e4c"`) to the text to scan. Empty list means the PR is sound.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_pr_link.py`:

```python
def _evaluate(**overrides):
    """A sound PR, with named overrides. Every test states only its defect."""
    kwargs = dict(
        base_ref="main",
        default_branch="main",
        resolved={999001},
        expected={999001},
        scanned_text={"PR body": "Closes #999001"},
    )
    kwargs.update(overrides)
    return cpl.evaluate(**kwargs)


class TestEvaluate:
    def test_a_sound_pr_produces_no_failures(self):
        assert _evaluate() == []

    def test_base_other_than_the_default_branch_fails(self):
        """A stacked PR registers nothing. This has to fail even when the body
        is perfect and `closingIssuesReferences` looks plausible, because the
        link is what does not exist."""

        failures = _evaluate(base_ref="feat/other", resolved=set())
        assert [f.check for f in failures] == ["base", "missing"]
        assert "feat/other" in failures[0].detail

    def test_an_expected_issue_that_did_not_register_fails(self):
        failures = _evaluate(resolved=set())
        assert [f.check for f in failures] == ["missing"]
        assert "999001" in failures[0].detail

    def test_multi_issue_pr_reports_only_the_dropped_number(self):
        """The case a single-issue check cannot see. PR #315 carried two
        issues, #297 and #300; a batch PR silently dropping one is the failure
        this exists for."""

        failures = _evaluate(
            resolved={999001},
            expected={999001, 999002},
            scanned_text={"PR body": "Closes #999001. Closes #999002."},
        )
        assert [f.check for f in failures] == ["missing"]
        assert "999002" in failures[0].detail
        assert "[999002]" in failures[0].detail

    def test_an_issue_that_registered_but_was_not_claimed_fails(self):
        failures = _evaluate(resolved={999001, 999002})
        assert [f.check for f in failures] == ["unexpected"]
        assert "999002" in failures[0].detail

    def test_the_293_shape_a_backticked_keyword_with_an_empty_resolved_list(self):
        """THE headline case. PR #293 was doc-only, deliberately Refs-only, and
        its resolved list was correctly empty — and it still closed an open
        issue on merge. Checks 1-3 all pass here. Only the scan catches it, and
        a naive implementation ships without this test passing."""

        failures = _evaluate(
            resolved=set(),
            expected=set(),
            scanned_text={
                "PR body": "part 2's PR is the one carrying `Closes #999001`."
            },
        )
        assert [f.check for f in failures] == ["hazard"]
        assert "999001" in failures[0].detail
        assert "PR body" in failures[0].detail

    def test_a_hazard_in_a_commit_message_is_caught(self):
        """`closingIssuesReferences` is computed from the body and cannot see
        this at all."""

        failures = _evaluate(
            scanned_text={
                "PR body": "Closes #999001",
                "commit 4153e4c": "chore: mention `Fixes #999002` in passing",
            }
        )
        assert [f.check for f in failures] == ["hazard"]
        assert "999002" in failures[0].detail
        assert "commit 4153e4c" in failures[0].detail

    def test_the_prs_own_closing_lines_are_not_hazards(self):
        """The body of a correct PR is full of closing keywords next to the
        numbers it claims. Flagging those would make the gate unusable."""

        assert (
            _evaluate(
                resolved={999001, 999002},
                expected={999001, 999002},
                scanned_text={"PR body": "Closes #999001. Closes #999002."},
            )
            == []
        )

    def test_reports_every_independent_defect_at_once(self):
        """One run, one full list. Fixing them one CI round at a time is the
        cost this replaces."""

        failures = _evaluate(
            base_ref="feat/other",
            resolved={999003},
            expected={999001},
            scanned_text={"PR body": "Closes #999004"},
        )
        assert [f.check for f in failures] == [
            "base",
            "missing",
            "unexpected",
            "hazard",
        ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_check_pr_link.py::TestEvaluate -v`
Expected: 9 errors — `AttributeError: module 'check_pr_link' has no attribute 'evaluate'`.

- [ ] **Step 3: Write the minimal implementation**

Add to `scripts/check_pr_link.py`, after `scan_closing_refs`:

```python
@dataclass(frozen=True)
class Failure:
    """One independent defect. `check` is a stable slug for tests and hooks;
    `detail` is what a human needs in order to fix it."""

    check: str
    detail: str


def evaluate(
    *,
    base_ref: str,
    default_branch: str,
    resolved: set[int],
    expected: set[int],
    scanned_text: dict[str, str],
) -> list[Failure]:
    """Every way this PR's closing links are wrong, in a fixed order.

    `scanned_text` maps a label to text that will reach the merge commit — the
    PR title, its body, and the branch's commit messages. All of it is scanned
    backtick-blind, because the commit-message parser is.
    """
    failures: list[Failure] = []

    if base_ref != default_branch:
        failures.append(
            Failure(
                "base",
                f"base is {base_ref!r}, not {default_branch!r}. GitHub registers a "
                "closing link only for PRs targeting the default branch, so every "
                "closing line in this PR is inert. Retargeting is not enough on its "
                "own: the body is parsed when written, so it must be edited again "
                "afterwards to re-trigger the scan.",
            )
        )

    if missing := expected - resolved:
        failures.append(
            Failure(
                "missing",
                f"expected to close {sorted(expected)}, GitHub resolved "
                f"{sorted(resolved)} — missing {sorted(missing)}. Each number needs "
                "its own keyword: `Closes #1, #2` links only the first.",
            )
        )

    if unexpected := resolved - expected:
        failures.append(
            Failure(
                "unexpected",
                f"GitHub resolved {sorted(unexpected)}, which this PR does not claim "
                "to close. A closing keyword next to an issue number anywhere in the "
                "body is enough, including inside a sentence about the convention.",
            )
        )

    for label, text in scanned_text.items():
        if hazards := scan_closing_refs(text) - expected:
            failures.append(
                Failure(
                    "hazard",
                    f"{label} puts a closing keyword next to {sorted(hazards)}, which "
                    "this PR does not claim to close. On a squash merge the body "
                    "becomes the commit message, and the commit-message parser does "
                    "not exempt backticks — this is how #176 closed while the "
                    "paragraph doing it explained the issue had to stay open. "
                    "Rewrite it to keep the keyword away from the number.",
                )
            )

    return failures
```

Add `from dataclasses import dataclass` to the imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_check_pr_link.py -v`
Expected: 17 passed.

- [ ] **Step 5: Lint, then commit**

```bash
make lint-py
git add scripts/check_pr_link.py tests/test_check_pr_link.py
git commit -m "feat(scripts): the four PR-link checks (#321)

Base branch, missing links, unexpected links, and a backtick-blind scan of the
text destined for the merge commit. The fourth is the only one that catches the
#293 shape, where the resolved-reference list was correctly empty and the merge
commit shut an open issue regardless.

Refs #321"
```

---

### Task 3: IO shell, CLI, and the make target

**Files:**
- Modify: `scripts/check_pr_link.py`
- Modify: `Makefile` (after the `check-author-imports` target, ~line 153)

**Interfaces:**
- Consumes: `evaluate(...)`, `Failure` from Task 2.
- Produces: `main() -> int`; `make check-pr-link PR=<n> [ISSUES="<n> <n>"]`.

- [ ] **Step 1: Add the IO shell and `main`**

There is no unit test for this step, deliberately and for the same reason `scripts/check_diff_coverage.py` has none for `changed_lines()`: it is a subprocess boundary, and mocking `gh` would test the mock. All logic worth testing already lives in the two pure functions. Verification is the live run in Step 3.

Add to `scripts/check_pr_link.py`:

```python
class Problem(Exception):
    """A refusal. Distinct from a failed check: this is the script being
    unable to answer, which must never be reported as a pass."""


def _gh_json(args: list[str]) -> dict:
    proc = subprocess.run(
        ["gh", *args], cwd=REPO, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Problem(f"`gh {' '.join(args)}` failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Problem(f"`gh {' '.join(args)}` returned non-JSON: {exc}") from None


def _commit_messages(base_ref: str, head_ref: str) -> dict[str, str]:
    """Every commit on the branch, labelled by short sha.

    Uses the remote refs rather than the working tree so the answer does not
    depend on which branch happens to be checked out.
    """
    proc = subprocess.run(
        [
            "git", "log", "--format=%h%x00%B%x1e",
            f"origin/{base_ref}..origin/{head_ref}",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise Problem(
            f"could not read commits for origin/{head_ref}: {proc.stderr.strip()}. "
            "Push the branch first — this reads the remote, not the working tree."
        )
    out: dict[str, str] = {}
    for record in proc.stdout.split("\x1e"):
        if "\x00" not in record:
            continue
        sha, message = record.split("\x00", 1)
        out[f"commit {sha.strip()}"] = message
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a PR's closing links registered, and only the intended ones."
    )
    ap.add_argument("pr", type=int, help="pull request number")
    ap.add_argument(
        "issues",
        nargs="*",
        type=int,
        help="issue numbers this PR must close; omit to assert it closes none",
    )
    args = ap.parse_args()

    expected = set(args.issues)

    try:
        pr = _gh_json(
            [
                "pr", "view", str(args.pr),
                "--json", "baseRefName,headRefName,title,body,closingIssuesReferences",
            ]
        )
        repo = _gh_json(["repo", "view", "--json", "defaultBranchRef"])
        default_branch = repo["defaultBranchRef"]["name"]
        scanned = {
            "PR title": pr["title"] or "",
            "PR body": pr["body"] or "",
            **_commit_messages(pr["baseRefName"], pr["headRefName"]),
        }
    except (Problem, KeyError, TypeError) as exc:
        print(f"check-pr-link: {exc}", file=sys.stderr)
        return 1

    failures = evaluate(
        base_ref=pr["baseRefName"],
        default_branch=default_branch,
        resolved={r["number"] for r in pr["closingIssuesReferences"]},
        expected=expected,
        scanned_text=scanned,
    )

    claim = f"close {sorted(expected)}" if expected else "close nothing"
    print(f"check-pr-link: PR #{args.pr} should {claim}; scanned {len(scanned)} text(s)")

    if failures:
        for f in failures:
            print(f"  [{f.check}] {f.detail}", file=sys.stderr)
        print(
            f"check-pr-link: FAILED — {len(failures)} defect(s). "
            "This is a bug in the PR, not in the check.",
            file=sys.stderr,
        )
        return 1

    print("check-pr-link: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add `argparse`, `json`, `subprocess`, `sys` and `from pathlib import Path` to the imports, and `REPO = Path(__file__).resolve().parent.parent` below them.

- [ ] **Step 2: Add the make target**

In `Makefile`, immediately after the `check-author-imports` target:

```makefile
# Verify a PR's closing links actually registered (#321). Deliberately NOT part
# of `make check` — it needs a PR that already exists.
#
#   make check-pr-link PR=328                    # asserts it closes nothing
#   make check-pr-link PR=330 ISSUES="297 300"   # asserts exactly those two
check-pr-link:
	@test -n "$(PR)" || { echo 'usage: make check-pr-link PR=<n> [ISSUES="<n> <n>"]' >&2; exit 2; }
	$(PYTHON) scripts/check_pr_link.py $(PR) $(ISSUES)
```

- [ ] **Step 3: Verify against three real PRs**

These are live PRs whose state is already known, which is what makes them a test.

```bash
make check-pr-link PR=328        # Refs-only, closes nothing  -> expect ok, exit 0
make check-pr-link PR=327        # Refs-only, closes nothing  -> expect ok, exit 0
make check-pr-link PR=328 ISSUES="321"   # a lie -> expect [missing], exit 1
```

Expected on the third: `[missing] expected to close [321], GitHub resolved [] — missing [321]`.

If any of the first two fail, the check is wrong — both were verified by hand as `closingIssuesReferences: []` on base `main` with no keyword hazard.

- [ ] **Step 4: Run the full gate**

Run: `make check`
Expected: green. Re-run it after any edit made while fixing its output.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_pr_link.py Makefile
git commit -m "feat(scripts): make check-pr-link (#321)

Wires the two pure functions to gh and git and exposes them as a make target.
Verified against PRs #327 and #328, both known Refs-only, plus a deliberate
false claim to confirm it fails.

Not added to \`make check\`: it needs a PR that already exists.

Refs #321"
```

---

### Task 4: The command

**Files:**
- Create: `.claude/commands/close-out.md`

**Interfaces:**
- Consumes: `make check-pr-link PR=<n> ISSUES="..."` from Task 3.
- Produces: the `/close-out` command. Nothing consumes it programmatically.

Note on frontmatter: `allowed-tools` is deliberately **omitted** so the command inherits whatever the session exposes. Pinning a list is a portability bug — tool availability varies by harness, and a command that names a tool the session lacks is worse than one that names none.

- [ ] **Step 1: Write the command file**

Create `.claude/commands/close-out.md`:

````markdown
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
(`check-diff-coverage`). It does **not** evaluate Sonar's duplication rating, its
reliability rating, or the fact that a *renamed* file arrives at the coverage
gate with its whole surface counted as new (#324).

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

Then, always:

```
make check-pr-link PR=<n> ISSUES="<the confirmed issues>"
```

**Exit condition:** that command exits 0. A non-zero exit means the PR is
broken, not that the check is wrong.

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
````

- [ ] **Step 2: Verify the command loads**

Run `/close-out` with no arguments in a fresh Claude Code session in this repo and confirm it appears in the command list with its description, and that `$ARGUMENTS` interpolates when given a number.

If it does not appear, the frontmatter is malformed — check that the `---` fences are the first bytes of the file.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/close-out.md
git commit -m "feat(claude): /close-out, the seven-phase issue procedure (#321)

The repo's first committed project command. Sequences the procedure that was
spread across CLAUDE.md, CONTRIBUTING.md and the close-out plan, with an exit
condition per phase and a hard halt when phase 1 contradicts the issue.

allowed-tools is omitted on purpose: pinning a tool list is a portability bug,
since availability varies by harness.

Refs #321"
```

---

### Task 5: Point the prose at the executable form

**Files:**
- Modify: `CLAUDE.md` (the "Close the loop: every PR links its issue" section)
- Modify: `docs/CONTRIBUTING.md` (the "Record what you find" section)
- Modify: `docs/backlog-closeout-plan.md` (the "Standing gates" section, ~line 129)

Nothing is deleted. CLAUDE.md binds every session, including ones that never invoke the command, and a command file is invisible to anyone reading the repo. The accepted risk is drift between the two.

- [ ] **Step 1: CLAUDE.md**

After the existing `gh pr view <n> --json closingIssuesReferences` block, add:

```markdown
`make check-pr-link PR=<n> ISSUES="<n> <n>"` runs that query and three more —
base branch, unexpected links, and a backtick-blind scan of the text destined
for the merge commit — and exits non-zero on any of them. `/close-out` calls it
at phase 5.
```

- [ ] **Step 2: `docs/CONTRIBUTING.md`**

At the end of the "Record what you find" section, before "Separate what you
measured from what you think", add:

```markdown
`/close-out` walks this as phase 7, and will not finish until every finding has
both an issue number and a batch row.
```

- [ ] **Step 3: `docs/backlog-closeout-plan.md`**

At the end of the "Standing gates" bullet list, add:

```markdown
- These gates are enumerated with their exit conditions in
  `.claude/commands/close-out.md`. The command is the executable form; this
  list is the reasoning behind it. If they disagree, the disagreement is a bug
  in one of them — say which.
```

- [ ] **Step 4: Run the full gate**

Run: `make check`
Expected: green.

- [ ] **Step 5: Commit, push, and open the PR**

**All five tasks land on the existing branch `feat/321-close-out-command`,
which already carries the design spec and is already open as PR #328.** Do not
cut a new branch and do not open a second PR. #328 was opened deliberately
`Refs`-only because at that point nothing was implemented; completing the work
is what turns it into the PR that resolves the issue.

```bash
git add CLAUDE.md docs/CONTRIBUTING.md docs/backlog-closeout-plan.md
git commit -m "docs: point the three prose sources at /close-out (#321)

Nothing removed. CLAUDE.md binds sessions that never invoke the command, and a
command file is invisible to anyone reading the repo, so the prose stays and
gains a pointer.

Refs #321"
git push
```

Then **edit PR #328's body** — retitle it to `feat: /close-out and the PR-link
gate`, replace the "spec only" framing with what actually shipped, and put the
closing keyword next to 321 there. Every commit above says `Refs` because none
of them completes the issue alone; the body is what completes it.

```bash
gh pr edit 328 --title "feat: /close-out and the PR-link gate" --body-file <path>
```

Editing the body matters mechanically, not just cosmetically: GitHub parses the
body when it is written, so a body that gained its closing line only after the
PR was opened still registers — but only because the edit re-triggers the scan.

Then verify, with the thing this PR just built:

```
make check-pr-link PR=<n> ISSUES="321"
```

**Do not paste test-fixture text into the PR body.** The fixtures contain
literal closing-keyword-plus-number strings, and backticks are not a defence in
a commit message.

---

## Self-review

**Spec coverage.** Every section of `2026-08-10-close-out-command-design.md` maps to a task: the four checks → Tasks 1–2; `.py` over `.sh` and the house style → Global Constraints; the make target → Task 3; the seven phases and the omitted `allowed-tools` → Task 4; the three prose pointers → Task 5; the fixture hazard → Global Constraints and Task 5 Step 5. The spec's testing section named five cases for the script; all five appear in Tasks 1–2, plus four the spec did not enumerate (multi-issue drop, hazard in a commit message, own closing lines not flagged, all defects at once).

**Deliberately out of scope, per the spec:** `.claude/settings.json` and hooks (#322), and the live trial of the command on #291 — that is a later round, not a step here.

**One known gap, recorded rather than hidden:** `scan_closing_refs` does not match `closes issue #N`. Whether GitHub acts on that form is unverified. Task 1 asserts the current behaviour so it is a documented limitation rather than an assumption, and the note names check 3 as the partial backstop and the commit-message path as the place it would still bite.
