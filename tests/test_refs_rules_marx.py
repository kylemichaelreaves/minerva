"""Smoke tests for `minerva.refs.rules.marx`.

Marx is ingested as German-only (14 works across Wikisource, PG-DE,
Internet Archive OCR, marxists.org, and web.archive.org/mlwerke.de).
All rules gate on `langs=("deu",)`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.marx import RULES


def _chunk(
    text: str,
    *,
    lang: str = "deu",
    work: str = "Das Kapital, Band I",
    section: str | None = "Erstes Kapitel",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Marx",
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
            out.append((rule.name, cand.target_author, cand.source_form_snapshot))
    return out


# ════════════════════════════════════════════════════════════════════
# In-corpus targets
# ════════════════════════════════════════════════════════════════════


class TestMarxRules:
    def test_hegel_strong_mention(self) -> None:
        cands = _candidates_for("wie Hegel in seiner Phänomenologie gezeigt hat")
        assert any(c[0] == "marx_hegel" and c[1] == "Hegel" for c in cands)

    def test_hegelsche_adjective(self) -> None:
        cands = _candidates_for("die Hegelsche Dialektik wird hier kritisch reproduziert")
        assert any(c[1] == "Hegel" and "Hegelsche" in c[2] for c in cands)

    def test_hegelianer_form(self) -> None:
        cands = _candidates_for("die jungen Hegelianer haben dieses Problem nicht erkannt")
        assert any(c[1] == "Hegel" and "Hegelianer" in c[2] for c in cands)

    def test_feuerbach_strong_mention(self) -> None:
        cands = _candidates_for("Feuerbach hat die religiöse Entfremdung zwar erkannt")
        assert any(c[0] == "marx_feuerbach" and c[1] == "Feuerbach" for c in cands)

    def test_feuerbachsche_adjective(self) -> None:
        cands = _candidates_for("die Feuerbachsche Anschauung des Sinnlichen bleibt unzureichend")
        assert any(c[1] == "Feuerbach" for c in cands)

    def test_aristoteles_german_form(self) -> None:
        cands = _candidates_for("wie schon Aristoteles in seiner Politik bemerkt hat")
        assert any(c[1] == "Aristotle" and c[2] == "Aristoteles" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Out-of-corpus targets (Smith, Ricardo, Proudhon, Stirner, Bauer)
# ════════════════════════════════════════════════════════════════════


class TestMarxOutOfCorpusTargets:
    def test_adam_smith_named(self) -> None:
        cands = _candidates_for("wie Adam Smith im Wealth of Nations dargelegt hat")
        assert any(c[1] == "Smith" and "Adam Smith" in c[2] for c in cands)

    def test_smith_alone_not_matched(self) -> None:
        # Bare "Smith" should NOT match — the rule requires "Adam
        # Smith" to disambiguate from other Smiths.
        cands = _candidates_for("John Smith hat in einer Notiz erwähnt")
        assert not any(c[0] == "marx_smith" for c in cands)

    def test_ricardo_strong_mention(self) -> None:
        cands = _candidates_for("Ricardo bestimmt den Werth durch die Arbeitsmenge")
        assert any(c[0] == "marx_ricardo" and c[1] == "Ricardo" for c in cands)

    def test_proudhon_strong_mention(self) -> None:
        cands = _candidates_for("Herr Proudhon glaubt sich auf diese Weise zu retten")
        assert any(c[0] == "marx_proudhon" and c[1] == "Proudhon" for c in cands)

    def test_stirner_strong_mention(self) -> None:
        cands = _candidates_for("Stirner verwechselt hier wieder die Idee mit dem Wirklichen")
        assert any(c[0] == "marx_stirner" and c[1] == "Stirner" for c in cands)

    def test_sankt_max_periphrasis(self) -> None:
        cands = _candidates_for("wenn Sankt Max sich zur Wahrheit emporschwingt")
        assert any(c[1] == "Stirner" and "Sankt Max" in c[2] for c in cands)

    def test_bruno_bauer_qualified(self) -> None:
        cands = _candidates_for("Bruno Bauer hat in seiner kritischen Kritik behauptet")
        assert any(c[1] == "Bauer" and "Bruno Bauer" in c[2] for c in cands)

    def test_bare_bauer_not_matched(self) -> None:
        # "Bauer" alone (German common noun for farmer/peasant)
        # must NOT match the Bruno Bauer rule.
        cands = _candidates_for("der Bauer arbeitet auf dem Land")
        assert not any(c[0] == "marx_bauer" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Utopian socialists
# ════════════════════════════════════════════════════════════════════


class TestMarxUtopianSocialists:
    def test_saint_simon_named(self) -> None:
        cands = _candidates_for("die Saint-Simonsche Schule hat dieses Problem aufgeworfen")
        assert any(c[1] == "Saint-Simon" for c in cands)

    def test_fourier_named(self) -> None:
        cands = _candidates_for("Fourier entwirft ein System von Phalansterien")
        assert any(c[1] == "Fourier" and c[2] == "Fourier" for c in cands)

    def test_owen_named(self) -> None:
        cands = _candidates_for("Robert Owen versucht in New Lanark ein soziales Experiment")
        assert any(c[1] == "Owen" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestMarxLangFiltering:
    def test_english_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "as Hegel argued in the Phenomenology",
            lang="eng",
        )
        assert cands == []

    def test_french_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "comme Hegel l'a montré dans la Phénoménologie",
            lang="fra",
        )
        assert cands == []
