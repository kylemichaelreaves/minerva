"""Correcting a token's part of speech (#253).

`upos` was displayed by the inspector and read by three layout consumers —
row wrapping, the topological-field runs, and `isFiniteVerb`, which locates
LINKE KLAMMER — but was not correctable. Only `head` and `deprel` were, so a
curator could watch a bad tag distort the diagram with no way to say so.

Unlike `deprel`, whose inventory is checked by *shape* because the closed list
lives with the picker, UD's part-of-speech inventory is 17 tags and closed for
good, so membership is checked here.
"""

from __future__ import annotations

import pytest
from conftest import StubBackend, make_deps  # type: ignore[import-not-found]

from minerva.http.handlers.syntax import (
    _handle_syntax_correction_create,
)
from minerva.http.server_core import _HTTPError
from minerva.syntax import queries as q
from minerva.syntax import validate as v

CHUNK = "hegel-p17"


def fake_tokens() -> list[q.SyntaxToken]:
    """`Der Geist entwickelt.` — 1 -> 2, 2 -> 3, 3 = root."""

    def t(tok_id, form, head, deprel, upos):
        return q.SyntaxToken(
            sent_ord=0,
            tok_id=tok_id,
            form=form,
            lemma=form.lower(),
            upos=upos,
            xpos=None,
            feats=None,
            misc=None,
            head=head,
            deprel=deprel,
            surface_start=tok_id,
            surface_end=tok_id + len(form),
        )

    return [
        t(1, "Der", 2, "det", "DET"),
        t(2, "Geist", 3, "nsubj", "NOUN"),
        t(3, "entwickelt", 0, "root", "VERB"),
    ]


@pytest.fixture
def deps(populated_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("minerva.syntax.parse.parse_text", lambda _text: fake_tokens())
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")
    return make_deps(populated_db, StubBackend())


def post(deps, **payload):
    return _handle_syntax_correction_create(deps, CHUNK, payload)


class TestTheEndpoint:
    def test_upos_is_a_correctable_kind(self) -> None:
        assert "upos" in q.CORRECTABLE

    def test_retagging_a_token_records_the_correction(self, deps) -> None:
        body = post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRON")

        assert body["id"] > 0
        assert body["token"]["upos"] == "PRON"
        assert body["token"]["corrected"] is True
        assert body["corrections"] == 1

    def test_the_previous_tag_is_captured_as_provenance(self, deps) -> None:
        """`from_val` is derived server-side, like the other kinds — the
        inspector's "was DET" must agree with the tree the edit landed on."""

        post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRON")

        (row,) = q.load_corrections(deps.conn, CHUNK)
        assert row.kind == "upos"
        assert row.from_val == "DET"
        assert row.to_val == "PRON"

    def test_a_tag_outside_the_ud_inventory_is_refused(self, deps) -> None:
        """TIGER/STTS tags are the likely paste — `PRELS` is not a UD upos."""

        with pytest.raises(_HTTPError) as exc:
            post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRELS")

        assert exc.value.status == 400
        assert q.load_corrections(deps.conn, CHUNK) == []

    def test_a_lowercase_tag_is_refused_rather_than_coerced(self, deps) -> None:
        """UD tags are upper-case. Coercing would make the log disagree with
        what the curator was shown."""

        with pytest.raises(_HTTPError) as exc:
            post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="pron")

        assert exc.value.status == 400
        assert q.load_corrections(deps.conn, CHUNK) == []

    def test_retagging_does_not_disturb_head_or_deprel(self, deps) -> None:
        body = post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRON")

        assert body["token"]["head"] == 2
        assert body["token"]["deprel"] == "det"

    def test_a_upos_edit_and_a_deprel_edit_on_one_token_coexist(self, deps) -> None:
        """Keyed per kind as well as per token, so relabelling and retagging
        are independent and neither shadows the other."""

        post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRON")
        body = post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nsubj")

        assert body["token"]["upos"] == "PRON"
        assert body["token"]["deprel"] == "nsubj"

    def test_the_later_retag_of_a_token_wins(self, deps) -> None:
        post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="PRON")
        body = post(deps, sent_ord=0, tok_id=1, kind="upos", to_val="ADV")

        assert body["token"]["upos"] == "ADV"


class TestValidation:
    def test_every_ud_tag_is_accepted(self) -> None:
        # The closed 17. If this list ever needs an entry, UD changed.
        for tag in (
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
        ):
            assert v.validate_upos(tag) is None, tag

    def test_the_inventory_is_exactly_seventeen_tags(self) -> None:
        assert len(v.UPOS_TAGS) == 17

    def test_a_tiger_tag_is_refused_with_a_reason_naming_it(self) -> None:
        refusal = v.validate_upos("NN")

        assert refusal is not None
        assert refusal.code == "bad-upos"
        assert "NN" in refusal.message

    def test_an_empty_tag_is_refused(self) -> None:
        assert v.validate_upos("") is not None


class TestReplay:
    def test_materialise_applies_a_upos_correction(self) -> None:
        tokens = fake_tokens()
        out = q.materialise(
            tokens,
            [
                q.Correction(
                    id=1,
                    sent_ord=0,
                    tok_id=1,
                    kind="upos",
                    from_val="DET",
                    to_val="PRON",
                )
            ],
        )

        assert out[0].upos == "PRON"
        assert out[0].corrected is True
        # Pure: the audit trail is untouched.
        assert tokens[0].upos == "DET"

    def test_an_unrecognised_kind_is_ignored_rather_than_raising(self) -> None:
        """Same contract as a correction aimed at a token that is gone: the log
        has no foreign key so it outlives a re-ingest, and a row this build does
        not understand — written by a newer one, or by hand — must be inert
        rather than fatal."""

        out = q.materialise(
            fake_tokens(),
            [q.Correction(id=1, sent_ord=0, tok_id=1, kind="lemma", from_val="a", to_val="b")],
        )

        assert out[0].lemma == "der"
        assert out[0].corrected is False

    def test_replay_is_independent_per_kind(self) -> None:
        out = q.materialise(
            fake_tokens(),
            [
                q.Correction(
                    id=1, sent_ord=0, tok_id=2, kind="upos", from_val="NOUN", to_val="PROPN"
                ),
                q.Correction(id=2, sent_ord=0, tok_id=2, kind="head", from_val="3", to_val="0"),
            ],
        )

        assert out[1].upos == "PROPN"
        assert out[1].head == 0
