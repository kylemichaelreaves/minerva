"""Two Makefile traps from the July audit (#502).

`make test` ran only the frontend, so a contributor who ran it before pushing
got a green result having run none of the backend suite. And the post-ingest
sequence (embed → lemmatize → refs rules → embed-verify → llm-verify) lived
only in prose, which is how 9 authors / 6k cross-references went unverified.

Read through `make -n`, which prints the recipe without running it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def _dry_run(*args: str) -> list[str]:
    out = subprocess.run(
        ["make", "-n", "--no-print-directory", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # One entry per command: `make -n` echoes a backslash-continued recipe
    # line as the physical lines it was written on.
    out = out.replace("\\\n", " ")
    return [" ".join(line.split()) for line in out.splitlines() if line.strip()]


def _index_of(lines: list[str], needle: str) -> int:
    hits = [i for i, line in enumerate(lines) if needle in line]
    assert hits, f"{needle!r} not in recipe:\n" + "\n".join(lines)
    return hits[0]


def test_make_test_runs_backend_and_frontend():
    lines = _dry_run("test")
    _index_of(lines, ".venv/bin/pytest")
    _index_of(lines, "npm --prefix web test")


def test_make_test_web_is_the_frontend_suite_alone():
    lines = _dry_run("test-web")
    _index_of(lines, "npm --prefix web test")
    assert not [line for line in lines if "pytest" in line]


def test_post_ingest_runs_the_documented_sequence_in_order():
    lines = _dry_run("post-ingest")
    order = [
        _index_of(lines, "snapshot-db.sh pre-post-ingest"),
        _index_of(lines, "minerva embed"),
        _index_of(lines, "terms lemmatize"),
        _index_of(lines, "terms aggregate-lemmas"),
        _index_of(lines, "refs build --strategy rules"),
        _index_of(lines, "refs build --strategy embed-verify"),
        _index_of(lines, "generate_author_artifacts.py --write"),
    ]
    assert order == sorted(order)


def test_post_ingest_does_not_spend_on_llm_verify_unless_asked():
    lines = _dry_run("post-ingest")
    assert not [line for line in lines if "--strategy llm-verify" in line and "minerva" in line]


def test_post_ingest_runs_llm_verify_with_an_explicit_budget():
    lines = _dry_run("post-ingest", "LLM_CALLS=25", "AUTHOR=Kant")
    verify = lines[_index_of(lines, "--strategy llm-verify")]
    assert "--max-llm-calls 25" in verify
    assert _index_of(lines, "--strategy llm-verify") > _index_of(lines, "--strategy embed-verify")
    rules = lines[_index_of(lines, "--strategy rules")]
    assert '--source-author "Kant"' in rules
