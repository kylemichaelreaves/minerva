"""The two refusals: a correction may not make a cycle or disturb the root.

These are the integrity guarantees for hand-corrected trees. A cycle makes the
tree unwalkable — subtree hover, topological fields and CoNLL-U export all
recurse — and a sentence with no root, or two, is not a dependency tree at all
and will not reparse.

Validation is pure and lives here rather than in the endpoint because the
client enforces the same two rules for its instant refusal flash. The server
is the copy that matters: it is what a script talks to.
"""

from __future__ import annotations

from minerva.syntax import validate as v
from minerva.syntax.queries import SyntaxToken


def tok(tok_id: int, head: int | None, deprel: str = "dep", sent_ord: int = 0) -> SyntaxToken:
    return SyntaxToken(
        sent_ord=sent_ord,
        tok_id=tok_id,
        form=f"w{tok_id}",
        lemma=None,
        upos=None,
        xpos=None,
        feats=None,
        misc=None,
        head=head,
        deprel=deprel,
        surface_start=tok_id,
        surface_end=tok_id + 1,
    )


def chain() -> list[SyntaxToken]:
    """`1 -> 2 -> 3`, 3 is the root. The smallest tree with a real subtree."""

    return [tok(1, 2, "det"), tok(2, 3, "nsubj"), tok(3, 0, "root")]


# ---------- head ----------


def test_accepts_a_legal_reattachment():
    # 1 currently hangs off 2; hanging it off the root instead is fine.
    assert v.validate_head(chain(), sent_ord=0, tok_id=1, new_head=3) is None


def test_refuses_attaching_a_token_to_itself():
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=2, new_head=2)
    assert refusal is not None
    assert refusal.code == "cycle"
    # The panel shows the reason verbatim, so it has to name the word rather
    # than its index.
    assert "w2" in refusal.message


def test_refuses_a_head_inside_the_token_s_own_subtree():
    # 1 hangs off 2, so hanging 2 off 1 closes the loop 2 -> 1 -> 2.
    #
    # Deliberately not the root: in a well-formed tree the root governs every
    # token, so *any* reattachment of it is also a cycle. The root refusal
    # wins there, because "give the root to another token first" says more
    # than "that would make a cycle". See the root tests below.
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=2, new_head=1)
    assert refusal is not None
    assert refusal.code == "cycle"
    # The UI flashes the loop, so the path has to come back with the refusal.
    assert refusal.tokens == (2, 1)


def test_refuses_a_head_that_is_not_a_token_in_this_sentence():
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=1, new_head=9)
    assert refusal is not None
    assert refusal.code == "unknown-head"


def test_refuses_moving_the_only_root_off_zero():
    # Nothing would have head 0, so the sentence would have no root at all.
    # This edit is a cycle too — the root governs everything — but the root
    # refusal is the one that tells the user what to do about it.
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=3, new_head=2)
    assert refusal is not None
    assert refusal.code == "no-root"
    assert refusal.tokens == (3,)


def test_refuses_promoting_a_second_token_to_root():
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=1, new_head=0)
    assert refusal is not None
    assert refusal.code == "two-roots"
    # Both claimants, so the UI can show which one is already the root.
    assert refusal.tokens == (1, 3)


def test_validates_against_the_named_sentence_only():
    # A chunk holds several sentences and ids restart at 1 in each. Token 1 of
    # sentence 1 must not be confused with token 1 of sentence 0.
    tokens = [*chain(), tok(1, 0, "root", sent_ord=1), tok(2, 1, "obj", sent_ord=1)]
    # Legal in sentence 1: 2 already hangs off 1, reattaching to 1 is a no-op.
    assert v.validate_head(tokens, sent_ord=1, tok_id=2, new_head=1) is None
    # But 3 does not exist in sentence 1, even though it does in sentence 0.
    assert v.validate_head(tokens, sent_ord=1, tok_id=3, new_head=1) is not None


def test_refuses_an_edit_to_a_token_that_is_not_there():
    refusal = v.validate_head(chain(), sent_ord=0, tok_id=7, new_head=1)
    assert refusal is not None
    assert refusal.code == "unknown-token"


def test_an_unparsed_head_does_not_count_as_a_root():
    # `_` in CoNLL-U is head=None: not parsed, not attached to root. A tree
    # whose only null-headed token is corrected to 0 gains its first root.
    tokens = [tok(1, 2, "det"), tok(2, None, "_")]
    assert v.validate_head(tokens, sent_ord=0, tok_id=2, new_head=0) is None


def test_a_cycle_among_unparsed_tokens_is_still_refused():
    # Walking up from a null head must terminate rather than loop forever.
    tokens = [tok(1, None, "_"), tok(2, 1, "dep"), tok(3, 0, "root")]
    assert v.validate_head(tokens, sent_ord=0, tok_id=1, new_head=2) is not None


# ---------- deprel ----------


def test_accepts_a_plain_relation():
    assert v.validate_deprel("nsubj") is None


def test_accepts_a_subtyped_relation():
    assert v.validate_deprel("acl:relcl") is None


def test_refuses_an_empty_relation():
    refusal = v.validate_deprel("")
    assert refusal is not None
    assert refusal.code == "bad-deprel"


def test_refuses_a_relation_that_is_not_shaped_like_one():
    # TIGER labels, capitals, whitespace and anything a paste could carry.
    for bad in ("Sb", "nsubj ", "obj|x", "a:b:c", "nsubj;DROP TABLE", "ROOT"):
        assert v.validate_deprel(bad) is not None, bad
