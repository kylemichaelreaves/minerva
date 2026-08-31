"""The refusals: what a correction is not allowed to do.

A dependency tree has two structural invariants, and a hand correction is the
only thing in this system that can break either:

* **no cycles** — every token reaches the root by walking heads. Subtree
  hover, the topological-field heuristic and CoNLL-U export all recurse, so a
  loop is not a cosmetic problem; it hangs them.
* **exactly one root** — a sentence with none, or two, is not a tree and will
  not reparse.

Both are checked *before* the write, and the refusal carries the reason and
the tokens involved so the UI can name them rather than saying "invalid".
Nothing is repaired silently: the plan is explicit that an edit which would
orphan or duplicate the root shows what is wrong instead.

Pure, and deliberately free of any DB or HTTP import — the endpoint calls it,
and `web/src/Syntax/corrections/validate.ts` mirrors it so the client can
refuse instantly without a round trip. This copy is the one that matters: it
is what a script talks to.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Sequence

from .queries import SyntaxToken

# UD deprels are lowercase ASCII with at most one `:subtype`. We check the
# *shape*, not membership of the 47-entry inventory: the closed list lives
# with the picker that enforces it (`corrections/relations.ts`), and
# duplicating it here would give two lists to keep in step. The shape check is
# what stops a TIGER label, a paste, or a stray capital from reaching storage.
_DEPREL_RE = re.compile(r"^[a-z]+(:[a-z]+)?$")

#: UD's part-of-speech inventory. Checked by *membership*, not shape — unlike
#: deprels, whose subtypes are open-ended, this list is closed and has 17
#: entries across every UD release. Membership is also the only check that
#: catches the realistic mistake: pasting the TIGER/STTS tag the German parser
#: also carries (`NN`, `PRELS`, `ADJA`) into the UD column, which is
#: shaped identically to a real tag (#253).
#:
#: `PUNCT` earns its place in the picker despite looking cosmetic: row
#: wrapping breaks after punctuation and the topological-field bands split
#: around it, so mis-tagging punctuation is the one POS error that visibly
#: moves the diagram.
UPOS_TAGS: frozenset[str] = frozenset(
    {
        "ADJ",
        "ADP",
        "ADV",
        "AUX",
        "CCONJ",
        "DET",
        "INTJ",
        "NOUN",
        "NUM",
        "PART",
        "PRON",
        "PROPN",
        "PUNCT",
        "SCONJ",
        "SYM",
        "VERB",
        "X",
    }
)


@dataclasses.dataclass(frozen=True)
class Refusal:
    """Why an edit was rejected. ``tokens`` are the ones to point at."""

    code: str
    message: str
    tokens: tuple[int, ...] = ()


def _sentence(tokens: Iterable[SyntaxToken], sent_ord: int) -> dict[int, SyntaxToken]:
    """The named sentence, by token id.

    Scoped deliberately: CoNLL-U ids restart at 1 in every sentence, so token
    1 of sentence 1 is a different word from token 1 of sentence 0, and a
    correction that crossed that boundary would attach to the wrong word.
    """

    return {t.tok_id: t for t in tokens if t.sent_ord == sent_ord}


def validate_head(
    tokens: Sequence[SyntaxToken],
    *,
    sent_ord: int,
    tok_id: int,
    new_head: int,
) -> Refusal | None:
    """Whether *tok_id* may be reattached to *new_head*. None means yes."""

    sent = _sentence(tokens, sent_ord)

    tok = sent.get(tok_id)
    if tok is None:
        return Refusal(
            "unknown-token",
            f"There is no token {tok_id} in this sentence.",
            (tok_id,),
        )

    if new_head == tok_id:
        return Refusal(
            "cycle",
            f"{tok.form} cannot be its own head.",
            (tok_id,),
        )

    if new_head != 0 and new_head not in sent:
        return Refusal(
            "unknown-head",
            f"There is no token {new_head} in this sentence.",
            (tok_id, new_head),
        )

    # ---- root, before cycles ----
    #
    # Order matters and is not arbitrary. In a well-formed tree the root
    # governs every token, so *every* reattachment of the root is also a
    # cycle. Reporting that would be true and useless; "give the root to
    # another token first" is the sentence that tells the user what to do.
    other_roots = tuple(sorted(i for i, t in sent.items() if t.head == 0 and i != tok_id))

    if new_head == 0 and other_roots:
        incumbent = sent[other_roots[0]]
        return Refusal(
            "two-roots",
            f"{incumbent.form} is already the root of this sentence. A sentence has exactly one.",
            (tok_id, *other_roots),
        )

    if new_head != 0 and tok.head == 0 and not other_roots:
        return Refusal(
            "no-root",
            f"{tok.form} is the sentence root — give the root to another token first.",
            (tok_id,),
        )

    # ---- cycles ----
    #
    # Walk up from the proposed head. Reaching *tok_id* means the head lies
    # inside its own dependent's subtree. `seen` guards against a loop that
    # already exists in the data and does not pass through tok_id — a walk
    # must terminate even over a tree we did not produce.
    path: list[int] = [tok_id]
    seen = {tok_id}
    cursor = new_head
    while cursor not in (0, None):
        if cursor == tok_id:
            return Refusal(
                "cycle",
                f"{sent[new_head].form} is inside the subtree of {tok.form}. "
                "A head must lie outside its dependent's subtree, or the "
                "sentence stops being a tree.",
                tuple(path),
            )
        if cursor in seen:
            break
        seen.add(cursor)
        path.append(cursor)
        nxt = sent.get(cursor)
        if nxt is None:
            break
        cursor = nxt.head  # type: ignore[assignment]

    return None


def validate_deprel(deprel: str) -> Refusal | None:
    """Whether *deprel* is shaped like a UD relation. None means yes."""

    if not _DEPREL_RE.match(deprel):
        return Refusal(
            "bad-deprel",
            f"{deprel!r} is not a Universal Dependencies relation.",
        )
    return None


def validate_upos(upos: str) -> Refusal | None:
    """Whether *upos* is one of UD's 17 tags. None means yes.

    Deliberately not case-insensitive. A lower-case tag is a sign the value
    came from somewhere other than the picker, and coercing it would leave the
    log saying something the curator was never shown.
    """

    if upos not in UPOS_TAGS:
        return Refusal(
            "bad-upos",
            f"{upos!r} is not a Universal Dependencies part of speech.",
        )
    return None
