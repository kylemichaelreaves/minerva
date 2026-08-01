"""Storage and replay for dependency-syntax trees.

`materialise` is the integrity guarantee for the whole overlay: the machine
parse in `chunk_syntax` is immutable, corrections are an append-only log, and
the tree anyone actually sees is the result of replaying one over the other.
If replay is wrong, a scholar's correction silently doesn't take — the worst
failure this tool can have, because it looks like it worked.

No Stanza here. CI installs `.[dev,hegel,embed]`, not `[lemma]`, so there is
no parser and no model available; these tests build token structures directly.
"""

from __future__ import annotations

import pytest

from minerva.syntax import queries as q

# Corrections have no foreign key, so they accept any id — including one that
# never existed. That is the point of them.
CHUNK = "chunk-abc"

# The parse *does* cascade from chunks, so it needs a real one from the
# fixture corpus. The asymmetry is deliberate: a parse is reproducible machine
# output and should die with its chunk; a correction is human judgement and
# must not.
PARSED_CHUNK = "rep-509d"


def tok(
    tok_id: int,
    form: str,
    *,
    head: int | None = 0,
    deprel: str = "root",
    sent_ord: int = 0,
) -> q.SyntaxToken:
    return q.SyntaxToken(
        sent_ord=sent_ord,
        tok_id=tok_id,
        form=form,
        lemma=form.lower(),
        upos="NOUN",
        xpos=None,
        feats=None,
        misc=None,
        head=head,
        deprel=deprel,
        surface_start=tok_id * 10,
        surface_end=tok_id * 10 + len(form),
    )


# `Der Geist hat sich ... entwickelt.` in miniature: 1 -> 2, 2 -> 3, 3 = root.
def pristine() -> list[q.SyntaxToken]:
    return [
        tok(1, "Der", head=2, deprel="det"),
        tok(2, "Geist", head=3, deprel="nsubj"),
        tok(3, "entwickelt", head=0, deprel="root"),
    ]


def correction(cid: int, tok_id: int, kind: str, to: str, frm: str | None = None) -> q.Correction:
    return q.Correction(id=cid, sent_ord=0, tok_id=tok_id, kind=kind, from_val=frm, to_val=to)


# ---------- materialise: the replay ----------


def test_no_corrections_returns_the_parse_untouched() -> None:
    out = q.materialise(pristine(), [])

    assert [t.head for t in out] == [2, 3, 0]
    assert not any(t.corrected for t in out)


def test_head_correction_applies_and_marks_the_token() -> None:
    out = q.materialise(pristine(), [correction(1, 1, "head", "3", frm="2")])

    assert out[0].head == 3
    assert out[0].corrected is True
    # Untouched tokens stay machine-attributed.
    assert out[1].corrected is False


def test_deprel_correction_applies() -> None:
    out = q.materialise(pristine(), [correction(1, 2, "deprel", "obj")])

    assert out[1].deprel == "obj"
    assert out[1].corrected is True


def test_later_correction_wins_over_earlier() -> None:
    """Append-only means the same token can be edited repeatedly. Replay is
    in id order and the last write is the current value."""

    out = q.materialise(
        pristine(),
        [correction(1, 1, "head", "3", frm="2"), correction(2, 1, "head", "2", frm="3")],
    )

    assert out[0].head == 2
    assert out[0].corrected is True


def test_replay_order_follows_id_not_list_order() -> None:
    """The store returns rows ordered by id; a caller that hands them over
    shuffled must not silently get a different tree."""

    later = correction(2, 1, "head", "2")
    earlier = correction(1, 1, "head", "3")

    out = q.materialise(pristine(), [later, earlier])

    assert out[0].head == 2


def test_correction_for_an_absent_token_is_ignored() -> None:
    """A patch can outlive the parse it was made against — corrections have
    no foreign key precisely so they survive a re-ingest. A stale one must be
    inert, not an exception."""

    out = q.materialise(pristine(), [correction(1, 99, "head", "1")])

    assert [t.head for t in out] == [2, 3, 0]
    assert not any(t.corrected for t in out)


def test_corrections_are_scoped_by_sentence() -> None:
    tokens = [
        tok(1, "A", head=0, deprel="root", sent_ord=0),
        tok(1, "B", head=0, deprel="root", sent_ord=1),
    ]

    out = q.materialise(tokens, [q.Correction(1, 1, 1, "head", None, "0")])

    # Only sentence 1's token 1 moves; sentence 0's is a different token.
    assert out[0].corrected is False
    assert out[1].corrected is True


def test_head_zero_is_applicable_and_distinct_from_unparsed() -> None:
    """Reattaching to root is `head = 0`; `_` is null. Replay must be able to
    produce the former without producing the latter."""

    out = q.materialise(pristine(), [correction(1, 1, "head", "0")])

    assert out[0].head == 0
    assert out[0].head is not None


def test_materialise_does_not_mutate_its_input() -> None:
    """The pristine parse is the audit trail. Replay handing back mutated
    rows would corrupt it in any caller that reuses the list."""

    original = pristine()

    q.materialise(original, [correction(1, 1, "head", "3")])

    assert original[0].head == 2
    assert original[0].corrected is False


# ---------- storage round-trip ----------


@pytest.fixture
def conn(populated_db):
    return populated_db


def test_load_parse_returns_none_when_never_parsed(conn) -> None:
    """Distinguishable from "parsed, no tokens" — otherwise an empty chunk is
    re-parsed on every single open."""

    assert q.load_parse(conn, PARSED_CHUNK) is None


def test_save_then_load_round_trips(conn) -> None:
    q.save_parse(conn, PARSED_CHUNK, pristine(), parser="stanza-de-test")

    loaded = q.load_parse(conn, PARSED_CHUNK)

    assert loaded is not None
    assert [(t.tok_id, t.form, t.head, t.deprel) for t in loaded] == [
        (1, "Der", 2, "det"),
        (2, "Geist", 3, "nsubj"),
        (3, "entwickelt", 0, "root"),
    ]


def test_an_empty_parse_still_counts_as_parsed(conn) -> None:
    q.save_parse(conn, PARSED_CHUNK, [], parser="stanza-de-test")

    assert q.load_parse(conn, PARSED_CHUNK) == []


def test_saving_again_replaces_the_previous_parse(conn) -> None:
    q.save_parse(conn, PARSED_CHUNK, pristine(), parser="v1")
    q.save_parse(conn, PARSED_CHUNK, [tok(1, "Nur", head=0)], parser="v2")

    loaded = q.load_parse(conn, PARSED_CHUNK)

    assert loaded is not None
    assert [t.form for t in loaded] == ["Nur"]


def test_append_and_load_corrections(conn) -> None:
    first = q.append_correction(
        conn, CHUNK, sent_ord=0, tok_id=1, kind="head", from_val="2", to_val="3"
    )
    second = q.append_correction(
        conn, CHUNK, sent_ord=0, tok_id=2, kind="deprel", from_val="nsubj", to_val="obj"
    )

    rows = q.load_corrections(conn, CHUNK)

    assert [c.id for c in rows] == [first, second]
    assert rows[1].kind == "deprel"


def test_corrections_are_isolated_per_chunk(conn) -> None:
    q.append_correction(conn, CHUNK, sent_ord=0, tok_id=1, kind="head", from_val=None, to_val="3")

    assert q.load_corrections(conn, "some-other-chunk") == []


def test_delete_correction_removes_only_that_row(conn) -> None:
    first = q.append_correction(
        conn, CHUNK, sent_ord=0, tok_id=1, kind="head", from_val=None, to_val="3"
    )
    q.append_correction(conn, CHUNK, sent_ord=0, tok_id=2, kind="head", from_val=None, to_val="1")

    assert q.delete_correction(conn, first) is True

    assert [c.tok_id for c in q.load_corrections(conn, CHUNK)] == [2]


def test_deleting_an_absent_correction_reports_false(conn) -> None:
    assert q.delete_correction(conn, 12345) is False


def test_corrections_survive_the_chunk_disappearing(conn) -> None:
    """No foreign key, on purpose: hand annotation must outlive a re-ingest.
    This asserts the schema decision, not just the code."""

    q.append_correction(
        conn, "ne-1097b", sent_ord=0, tok_id=1, kind="head", from_val=None, to_val="3"
    )
    conn.execute("DELETE FROM chunks WHERE chunk_id = 'ne-1097b'")
    conn.commit()

    assert len(q.load_corrections(conn, "ne-1097b")) == 1
