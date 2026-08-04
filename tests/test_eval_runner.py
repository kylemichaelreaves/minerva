"""Tests for `minerva.eval_runner` — work matching, hit scoring, and end-to-end run."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_hit

from minerva import eval_runner

# ---------- _normalize ----------


def test_normalize_strips_and_lowercases():
    assert eval_runner._normalize("  Republic  ") == "republic"
    assert eval_runner._normalize(None) == ""
    assert eval_runner._normalize("") == ""


# ---------- _work_matches ----------


def test_work_matches_exact():
    assert eval_runner._work_matches("ion", "ion") is True


def test_work_matches_whole_word_inside_phrase():
    assert eval_runner._work_matches("the republic", "republic") is True
    assert eval_runner._work_matches("republic, book 7", "republic") is True


def test_work_matches_does_not_substring_match():
    # The bug we fixed: 'ion' must NOT match 'constitution'.
    assert eval_runner._work_matches("athenian constitution", "ion") is False
    assert eval_runner._work_matches("definitions", "ion") is False


def test_work_matches_distinguishes_phaedo_from_phaedrus():
    assert eval_runner._work_matches("phaedo", "phaedo") is True
    assert eval_runner._work_matches("phaedrus", "phaedo") is False


def test_work_matches_handles_empty_inputs():
    assert eval_runner._work_matches("", "phaedo") is False
    assert eval_runner._work_matches("phaedo", "") is False


# ---------- _hit_matches ----------


def test_hit_matches_returns_work_and_section_flags():
    hit = make_hit(work="Republic", section="509d")
    work_ok, sec_ok = eval_runner._hit_matches(hit, ["Republic"], ["509d", "510a"])
    assert (work_ok, sec_ok) == (True, True)


def test_hit_matches_section_normalized():
    hit = make_hit(work="Republic", section="509D")
    _work_ok, sec_ok = eval_runner._hit_matches(hit, ["Republic"], ["509d"])
    assert sec_ok is True


def test_hit_matches_neither_when_wrong_work():
    hit = make_hit(work="Phaedrus", section="509d")
    work_ok, sec_ok = eval_runner._hit_matches(hit, ["Republic"], ["509d"])
    assert (work_ok, sec_ok) == (False, True)  # section coincidentally matches


# ---------- run end-to-end ----------


def test_run_against_a_tiny_gold_set(populated_db, tmp_path: Path):
    gold = [
        {
            "id": "g1",
            "question": "divided line",
            "expected_works": ["Republic"],
            "expected_sections": ["509d", "510a"],
        },
        {
            "id": "g2",
            "question": "function virtue",
            "expected_works": ["Nicomachean Ethics"],
            "expected_sections": ["1097b"],
        },
    ]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("\n".join(json.dumps(g) for g in gold))

    summary = eval_runner.run(
        conn=populated_db,
        gold_path=gold_path,
        top_k=3,
        lang="eng",
        corpus=None,  # the second question is Aristotle
        section_recall_threshold=0.5,
    )

    assert summary["n_questions"] == 2
    assert summary["work_recall_at_k"] == 1.0
    assert summary["section_recall_at_k"] == 1.0
    assert summary["pass"] is True
    assert len(summary["per_question"]) == 2
    assert all(q["section_ok"] for q in summary["per_question"])


def test_load_gold_rejects_row_missing_required_keys(tmp_path: Path):
    gold = tmp_path / "bad.jsonl"
    gold.write_text(json.dumps({"id": "g1", "question": "q"}) + "\n")  # missing both lists
    with __import__("pytest").raises(ValueError, match="missing required keys"):
        eval_runner._load_gold(gold)


def test_load_gold_rejects_invalid_json_with_line_number(tmp_path: Path):
    gold = tmp_path / "bad.jsonl"
    gold.write_text(
        json.dumps({"id": "g1", "question": "q", "expected_works": [], "expected_sections": []})
        + "\n"
        "{not valid json\n"
    )
    with __import__("pytest").raises(ValueError, match=":2:"):
        eval_runner._load_gold(gold)


def test_load_gold_rejects_non_dict_row(tmp_path: Path):
    gold = tmp_path / "bad.jsonl"
    gold.write_text("[1, 2, 3]\n")
    with __import__("pytest").raises(ValueError, match="expected object"):
        eval_runner._load_gold(gold)


def test_load_gold_rejects_non_list_expected_fields(tmp_path: Path):
    gold = tmp_path / "bad.jsonl"
    gold.write_text(
        json.dumps(
            {"id": "g1", "question": "q", "expected_works": "Republic", "expected_sections": []}
        )
        + "\n"
    )
    with __import__("pytest").raises(ValueError, match="must be lists"):
        eval_runner._load_gold(gold)


def test_load_gold_accepts_valid_rows(tmp_path: Path):
    gold = tmp_path / "ok.jsonl"
    gold.write_text(
        json.dumps(
            {
                "id": "g1",
                "question": "q",
                "expected_works": ["Republic"],
                "expected_sections": ["509d"],
            }
        )
        + "\n"
    )
    rows = eval_runner._load_gold(gold)
    assert len(rows) == 1
    assert rows[0]["id"] == "g1"


# ---------- expected_works alias resolution (#183) ----------


def _rename_republic_to_politeia(conn) -> None:
    """Reproduce #78's canonicalisation on the test corpus.

    The work becomes `Politeia`; `Republic` survives only as the English
    translation's `title_local`, exactly as it does in the real index.
    """

    work_id = conn.execute("SELECT id FROM works WHERE title = 'Republic'").fetchone()[0]
    conn.execute("UPDATE works SET title = 'Politeia' WHERE id = ?", (work_id,))
    conn.execute(
        "UPDATE translations SET title_local = 'Republic' WHERE work_id = ?", (work_id,)
    )
    conn.commit()


def test_expected_works_resolve_through_title_local(populated_db, tmp_path: Path):
    """A gold set naming the pre-rename English title still scores.

    This is #183: every Republic question read `work_ok: false` while
    returning the right passage of the right work, because the gold file
    says `Republic` and the work is now `Politeia`.
    """

    _rename_republic_to_politeia(populated_db)
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "id": "g1",
                "question": "divided line",
                "expected_works": ["Republic"],
                "expected_sections": ["509d", "510a"],
            }
        )
    )

    summary = eval_runner.run(
        conn=populated_db,
        gold_path=gold_path,
        top_k=3,
        lang="eng",
        corpus="plato",
        section_recall_threshold=0.5,
    )

    assert summary["per_question"][0]["top_hit"].startswith("Plato, Politeia")
    assert summary["work_recall_at_k"] == 1.0
    assert summary["per_question"][0]["work_ok"] is True


def test_expected_works_still_resolve_by_canonical_title(populated_db, tmp_path: Path):
    """The canonical name works too — resolution is by alias, not by rename."""

    _rename_republic_to_politeia(populated_db)
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "id": "g1",
                "question": "divided line",
                "expected_works": ["Politeia"],
                "expected_sections": ["509d"],
            }
        )
    )

    summary = eval_runner.run(
        conn=populated_db,
        gold_path=gold_path,
        top_k=3,
        lang="eng",
        corpus="plato",
        section_recall_threshold=0.5,
    )
    assert summary["work_recall_at_k"] == 1.0


def test_run_rejects_an_expected_work_no_work_answers_to(populated_db, tmp_path: Path):
    """An unresolvable `expected_works` name is an error, not a silent 0.

    The failure mode #183 documents is a metric that was wrong for
    months without consequence. A name that matches no work in the index
    can only ever score 0, so it fails loudly instead — which is also
    what makes the gold set survive the *next* rename.
    """

    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "id": "g1",
                "question": "q",
                "expected_works": ["Res Publica"],
                "expected_sections": ["509d"],
            }
        )
    )

    with __import__("pytest").raises(ValueError, match="Res Publica"):
        eval_runner.run(
            conn=populated_db,
            gold_path=gold_path,
            top_k=3,
            lang="eng",
            corpus="plato",
        )


def test_work_recall_gates_the_exit_status(populated_db, tmp_path: Path):
    """`pass` consults work recall.

    Before #183 it was decided on section recall alone, so
    `work_recall_at_k` could read 0.1 and the run still passed.
    """

    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "id": "g1",
                # Lands in the Republic's 509d, so section recall passes;
                # the expected work is Aristotle's, so work recall is 0.
                "question": "line divided into two unequal sections",
                "expected_works": ["Nicomachean Ethics"],
                "expected_sections": ["509d"],
            }
        )
    )

    summary = eval_runner.run(
        conn=populated_db,
        gold_path=gold_path,
        top_k=3,
        lang="eng",
        corpus=None,
        section_recall_threshold=0.5,
        work_recall_threshold=0.5,
    )
    assert summary["section_recall_at_k"] == 1.0
    assert summary["work_recall_at_k"] == 0.0
    assert summary["pass"] is False


def test_run_marks_failure_when_threshold_unmet(populated_db, tmp_path: Path):
    gold = [
        {
            "id": "g1",
            "question": "completely irrelevant zxqv tokens",
            "expected_works": ["Republic"],
            "expected_sections": ["509d"],
        },
    ]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(json.dumps(gold[0]))

    summary = eval_runner.run(
        conn=populated_db,
        gold_path=gold_path,
        top_k=3,
        lang="eng",
        section_recall_threshold=0.6,
    )
    assert summary["section_recall_at_k"] == 0.0
    assert summary["pass"] is False
