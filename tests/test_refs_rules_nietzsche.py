"""Smoke tests for `minerva.refs.rules.nietzsche`.

Nietzsche is ingested as German-only via zeno.org HTML. All rules
gate on `langs=("deu",)`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.nietzsche import RULES


def _chunk(
    text: str,
    *,
    lang: str = "deu",
    work: str = "Jenseits von Gut und Böse",
    section: str | None = "Aphorismus 1",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Nietzsche",
        work=work,
        lang=lang,
        section=section,
        text=text,
    )


def _candidates_for(text: str, **kw: object) -> list[tuple[str, str, str]]:
    chunk = _chunk(text, **kw)  # type: ignore[arg-type]
    out: list[tuple[str, str, str]] = []
    for rule in RULES:
        for cand in rule.scan(chunk):
            out.append(
                (rule.name, cand.target_author, cand.source_form_snapshot)
            )
    return out


# ════════════════════════════════════════════════════════════════════
# Strong-mention out-of-corpus targets
# ════════════════════════════════════════════════════════════════════


class TestNietzscheStrongMentions:

    def test_sokrates_named(self) -> None:
        cands = _candidates_for(
            "das Problem des Sokrates ist das Problem des Rationalismus"
        )
        assert any(c[0] == "nietzsche_sokrates" and c[1] == "Socrates" for c in cands)

    def test_sokratisch_adjective(self) -> None:
        cands = _candidates_for(
            "die sokratische Dialektik zerstört den dionysischen Mythos"
        )
        assert any(c[1] == "Socrates" for c in cands)

    def test_christus_named(self) -> None:
        cands = _candidates_for(
            "Jesus aus Nazareth, der einzige Christ"
        )
        assert any(c[0] == "nietzsche_christus" and c[1] == "Christ" for c in cands)

    def test_christentum_named(self) -> None:
        cands = _candidates_for(
            "das Christentum hat unser Verständnis der Tugend verkehrt"
        )
        assert any(c[1] == "Christ" and c[2] == "Christentum" for c in cands)

    def test_christlich_adjective(self) -> None:
        cands = _candidates_for(
            "die christliche Moral ist eine Sklavenmoral"
        )
        assert any(c[1] == "Christ" for c in cands)

    def test_schopenhauer_named(self) -> None:
        cands = _candidates_for(
            "Schopenhauer war mein Erzieher in Sachen des Pessimismus"
        )
        assert any(c[0] == "nietzsche_schopenhauer" and c[1] == "Schopenhauer" for c in cands)

    def test_schopenhauersche(self) -> None:
        cands = _candidates_for(
            "die Schopenhauersche Metaphysik des Willens"
        )
        assert any(c[1] == "Schopenhauer" for c in cands)

    def test_wagner_named(self) -> None:
        cands = _candidates_for(
            "der Fall Wagner zeigt die décadence der modernen Musik"
        )
        assert any(c[0] == "nietzsche_wagner" and c[1] == "Wagner" for c in cands)

    def test_richard_wagner_full_name(self) -> None:
        cands = _candidates_for(
            "Richard Wagner in Bayreuth war ein anderes Buch"
        )
        assert any(c[1] == "Wagner" and "Richard Wagner" in c[2] for c in cands)


# ════════════════════════════════════════════════════════════════════
# In-corpus targets
# ════════════════════════════════════════════════════════════════════


class TestNietzscheInCorpusMentions:

    def test_kant_named(self) -> None:
        cands = _candidates_for(
            "Kant hatte eine Frage übersehen, die nach dem Wert der Wahrheit"
        )
        assert any(c[1] == "Kant" and c[2] == "Kant" for c in cands)

    def test_kantianer(self) -> None:
        cands = _candidates_for(
            "alle Kantianer sind im Grunde Christen"
        )
        assert any(c[1] == "Kant" for c in cands)

    def test_hegel_named(self) -> None:
        cands = _candidates_for(
            "Hegel und sein Schüler Marx haben die Geschichte zur Mystik erhoben"
        )
        assert any(c[1] == "Hegel" and c[2] == "Hegel" for c in cands)

    def test_platon_german_form(self) -> None:
        cands = _candidates_for(
            "Platon ist langweilig, sagte ich einst"
        )
        assert any(c[1] == "Plato" and c[2] == "Platon" for c in cands)

    def test_platonisch(self) -> None:
        cands = _candidates_for(
            "die platonische Idee des Guten ist ein Ressentiment-Begriff"
        )
        assert any(c[1] == "Plato" for c in cands)

    def test_aristoteles_named(self) -> None:
        cands = _candidates_for(
            "Aristoteles hat noch die griechische Lebenshaltung verstanden"
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristoteles" for c in cands)

    def test_spinoza_named(self) -> None:
        cands = _candidates_for(
            "Spinoza! Ich habe meinen Vorgänger, und welchen!"
        )
        assert any(c[1] == "Spinoza" and c[2] == "Spinoza" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Other out-of-corpus targets
# ════════════════════════════════════════════════════════════════════


class TestNietzscheOtherTargets:

    def test_darwin_named(self) -> None:
        cands = _candidates_for(
            "gegen Darwin: was die Gattungen erhält, ist nicht das Stärkste"
        )
        assert any(c[1] == "Darwin" and c[2] == "Darwin" for c in cands)

    def test_darwinismus(self) -> None:
        cands = _candidates_for(
            "der Darwinismus ist eine falsche Lehre vom Leben"
        )
        assert any(c[1] == "Darwin" and c[2] == "Darwinismus" for c in cands)

    def test_goethe_named(self) -> None:
        cands = _candidates_for(
            "Goethe nannte sich einen Heiden im Christen-Land"
        )
        assert any(c[1] == "Goethe" for c in cands)

    def test_buddha_named(self) -> None:
        cands = _candidates_for(
            "Buddha und das Christentum sind beides Nihilismus-Religionen"
        )
        assert any(c[1] == "Buddha" for c in cands)

    def test_buddhismus(self) -> None:
        cands = _candidates_for(
            "der Buddhismus ist hundertmal ehrlicher als das Christentum"
        )
        assert any(c[1] == "Buddha" and c[2] == "Buddhismus" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestNietzscheLangFiltering:

    def test_english_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "Socrates is the central target of Birth of Tragedy",
            lang="eng",
        )
        assert cands == []

    def test_french_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "Socrate est le pivot du rationalisme classique",
            lang="fra",
        )
        assert cands == []
