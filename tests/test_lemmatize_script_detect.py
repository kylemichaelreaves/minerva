"""Cross-script run detection for the lemmatize pipeline (#430).

Non-Greek text inside `grc` works was lemmatized under the Greek model,
entering `lemma_counts` as though it were Greek vocabulary — 10,474 rows,
mostly Diels-Kranz testimonia and *Oeconomica* III's medieval Latin
translation, both legitimate content that simply isn't in the work's own
script. The mirror direction (a Greek quotation inside an English, French,
German or Latin edition) has the same shape: 431 rows.

`find_alt_script_runs` locates the spans that need the *other* model;
`mask_runs` blanks them out of the text handed to the primary lemmatizer so
it never tokenizes content it would only mangle.
"""

from __future__ import annotations

from minerva.lemmatize import find_alt_script_runs, mask_runs


class TestFindAltScriptRunsGrc:
    """own_lang='grc': ASCII-Latin runs are the alternate, tagged 'lat'."""

    def test_pure_greek_has_no_alt_runs(self):
        assert find_alt_script_runs("λόγος ἐστίν", "grc") == []

    def test_embedded_latin_phrase_is_one_run(self):
        # Trailing neutral tokens ("39" — a bare digit) are excluded: the
        # run's end is always the end of an actual alt-script word, since
        # nothing after "39" confirms it belongs to the Latin span rather
        # than being the start of the next Greek clause.
        text = "λόγος PLUT. quaest. nat. 39 ἐστίν"
        runs = find_alt_script_runs(text, "grc")
        assert len(runs) == 1
        lang, start, end = runs[0]
        assert lang == "lat"
        assert text[start:end] == "PLUT. quaest. nat."

    def test_two_separated_latin_phrases_are_two_runs(self):
        text = "ἀρχή PLUT. λόγος SIMPL. τέλος"
        runs = find_alt_script_runs(text, "grc")
        assert [text[s:e] for _, s, e in runs] == ["PLUT.", "SIMPL."]
        assert all(lang == "lat" for lang, _, _ in runs)

    def test_a_run_still_open_at_the_end_of_the_text_is_still_reported(self):
        text = "ἀρχή PLUT quaest"
        runs = find_alt_script_runs(text, "grc")
        assert len(runs) == 1
        lang, start, end = runs[0]
        assert lang == "lat"
        assert text[start:end] == "PLUT quaest"

    def test_a_lone_digit_between_latin_words_does_not_split_the_run(self):
        # "(048)" in the issue's own example — apparatus line-number
        # debris sitting between two Latin words.
        text = "ἀρχή lectio 32 correctum λόγος"
        runs = find_alt_script_runs(text, "grc")
        assert len(runs) == 1
        _lang, start, end = runs[0]
        assert text[start:end] == "lectio 32 correctum"


class TestFindAltScriptRunsNonGrc:
    """own_lang != 'grc': Greek-script runs are the alternate, tagged 'grc'
    — the eng mirror, but not eng-specific: any non-Greek language could
    carry an embedded Greek quotation."""

    def test_pure_english_has_no_alt_runs(self):
        assert find_alt_script_runs("the good life", "eng") == []

    def test_embedded_greek_quotation_is_one_run(self):
        text = "he called it εὐδαιμονία in the text"
        runs = find_alt_script_runs(text, "eng")
        assert len(runs) == 1
        lang, start, end = runs[0]
        assert lang == "grc"
        assert text[start:end] == "εὐδαιμονία"

    def test_applies_to_lat_and_deu_too(self):
        for lang in ("lat", "deu", "fra"):
            text = "quotes λόγος here"
            runs = find_alt_script_runs(text, lang)
            assert len(runs) == 1
            assert runs[0][0] == "grc"


class TestMaskRuns:
    def test_no_runs_returns_text_unchanged(self):
        text = "λόγος ἐστίν"
        assert mask_runs(text, []) == text

    def test_run_is_blanked_but_length_preserved(self):
        text = "λόγος PLUT. quaest. ἐστίν"
        runs = find_alt_script_runs(text, "grc")
        masked = mask_runs(text, runs)
        assert len(masked) == len(text)
        assert "PLUT" not in masked
        assert masked.startswith("λόγος")
        assert masked.endswith("ἐστίν")

    def test_masked_run_still_reads_as_two_separate_words(self):
        # Masking blanks letters, not the single space between "PLUT."
        # and "quaest." — a downstream tokenizer must still see two
        # blanked-out words rather than one long run of spaces that
        # could accidentally merge with a neighboring token.
        text = "ἀρχή PLUT. quaest. λόγος"
        runs = find_alt_script_runs(text, "grc")
        masked = mask_runs(text, runs)
        assert masked.split() == ["ἀρχή", "λόγος"]

    def test_offsets_recovered_from_original_text_still_align(self):
        text = "ἀρχή PLUT. λόγος"
        runs = find_alt_script_runs(text, "grc")
        (_lang, start, end) = runs[0]
        assert text[start:end] == "PLUT."
        masked = mask_runs(text, runs)
        assert masked[start:end].strip() == ""
