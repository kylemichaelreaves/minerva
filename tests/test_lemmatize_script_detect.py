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

from minerva.lemmatize import (
    find_alt_script_runs,
    fix_grc_ascii_prefix_confusables,
    fix_grc_lemma_ascii_prefix,
    mask_runs,
)


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


class TestFixGrcAsciiPrefixConfusables:
    """#446: a `grc` word can carry an ASCII run glued to its front with
    no separating space — either a citation marker (numeral) or the
    word's own initial capital letter, misencoded as its ASCII look-alike
    rather than the correct Greek codepoint. Both are found by #430's
    `find_alt_script_runs` as ordinary Greek words (they contain a Greek
    letter), so they never reach this repair via the alt-script path.
    """

    def test_no_glued_prefix_is_unchanged(self):
        assert fix_grc_ascii_prefix_confusables("λόγος ἐστίν") == "λόγος ἐστίν"

    def test_single_confusable_letter_is_remapped_not_stripped(self):
        # "Aχεικὰμ" is the Septuagint genealogy name Achim — the leading
        # ASCII "A" is a misencoded Greek capital alpha, not debris to
        # discard. Stripping it (rather than remapping) would truncate
        # the name to "χεικὰμ".
        text = "καὶ Aχεικὰμ ἐγέννησεν"
        fixed = fix_grc_ascii_prefix_confusables(text)
        assert "Αχεικὰμ" in fixed
        assert len(fixed) == len(text)

    def test_lowercase_l_and_o_confusables_are_remapped(self):
        # Sampling (#446) found these two lowercase ASCII letters always
        # sitting at the head of a capitalized Greek word (Ι and Ο have a
        # broken/faded capital form an OCR pass reads as lowercase Latin),
        # never elsewhere — unlike the other nine lowercase ASCII letters
        # that also turned up as prefixes, which stay unhandled residue.
        assert fix_grc_ascii_prefix_confusables("lσραήλ") == "Ισραήλ"
        assert fix_grc_ascii_prefix_confusables("oζειήλ") == "Οζειήλ"

    def test_multichar_roman_numeral_run_is_blanked(self):
        # "VIIτόν" — a chapter/verse marker glued to a Greek word, not a
        # letter of it. Blanked (not deleted) so offsets stay aligned.
        text = "VIIτόν λόγον"
        fixed = fix_grc_ascii_prefix_confusables(text)
        assert fixed == "   τόν λόγον"
        assert len(fixed) == len(text)

    def test_single_v_c_l_are_numerals_not_confusables(self):
        # V, C, L have no Greek homoglyph — a bare one of these is
        # unambiguously the numeral, unlike bare I or X below.
        assert fix_grc_ascii_prefix_confusables("Vκαί") == " καί"
        assert fix_grc_ascii_prefix_confusables("Cλόγος") == " λόγος"

    def test_single_i_and_x_are_confusables_not_numerals(self):
        # Both letters are valid Roman numerals on their own (1, 10), but
        # #446's sample showed every single-character "I"/"X" prefix in
        # the live corpus is a proper name's initial letter (Ιεβουσαῖος,
        # Χανανείς) — never a citation. A 2+-character run stays a
        # numeral (test_multichar_roman_numeral_run_is_blanked above).
        assert fix_grc_ascii_prefix_confusables("Iεβουσαῖος") == "Ιεβουσαῖος"
        assert fix_grc_ascii_prefix_confusables("Xανανείς") == "Χανανείς"

    def test_unmapped_lowercase_prefix_is_left_alone(self):
        # "a", "b", "c", "d", "e", "g", "m", "n", "s", "v" also turned up
        # as glued prefixes but sampling didn't support a confident
        # mapping for any of them (some are common words, not names;
        # Greek lowercase doesn't visually resemble most of them) —
        # accepted residue, not silently guessed at.
        assert fix_grc_ascii_prefix_confusables("aὁδός") == "aὁδός"

    def test_confusable_after_a_transliteration_apostrophe_is_remapped(self):
        # The Septuagint's convention for a Hebrew name starting with a
        # guttural (ʾAleph/ʿAyin) prefixes it with a rough-breathing-like
        # apostrophe with no space — "’Aχεικὰμ" (Achim), "‘Yμεῖς" — so the
        # glued ASCII letter isn't always at the very start of a `\S+`
        # run. Found live: 53 of 98 chunk_lemmas residue rows after the
        # first cut of this fix were exactly this shape.
        assert fix_grc_ascii_prefix_confusables("’Aχεικὰμ") == "’Αχεικὰμ"
        assert fix_grc_ascii_prefix_confusables("‘Yμεῖς") == "‘Υμεῖς"
        # A plain ASCII quote opening direct speech behaves the same way.
        assert fix_grc_ascii_prefix_confusables("'Aλλʼ") == "'Αλλʼ"

    def test_ordinary_ascii_word_elsewhere_in_the_text_is_untouched(self):
        # The confusable/numeral repair only ever touches a prefix glued
        # directly onto a Greek letter — an ordinary embedded Latin word
        # is #430's job (find_alt_script_runs + mask_runs), not this
        # function's.
        text = "λόγος PLUT. quaest. ἐστίν"
        assert fix_grc_ascii_prefix_confusables(text) == text


class TestFixGrcLemmaAsciiPrefix:
    """#456: the mirror direction of #446, baked into `grc_dep_web_sm`'s
    own lemma dictionary rather than a corpus text. A clean, all-Greek
    surface form (`νησαίων`) can still come back with an ASCII-confusable
    leading character in its *lemma* (`Nησαῖος`) — #446's text-side fix
    cannot touch this, since there is no ASCII anywhere in the input for
    it to find."""

    def test_ascii_confusable_lemma_on_a_clean_surface_is_remapped(self):
        assert fix_grc_lemma_ascii_prefix("νησαίων", "Nησαῖος") == "Νησαῖος"

    def test_a_clean_lemma_is_untouched(self):
        assert fix_grc_lemma_ascii_prefix("λόγος", "λόγος") == "λόγος"

    def test_an_ascii_surface_form_is_left_to_446s_own_territory(self):
        # If the surface form itself carries the ASCII character, this is
        # #446's direction (input-side), not #456's — leave it alone here
        # so the two fixes don't compete over the same row.
        assert fix_grc_lemma_ascii_prefix("Aχεικὰμ", "Aχεικάμ") == "Aχεικάμ"

    def test_an_empty_lemma_is_untouched(self):
        assert fix_grc_lemma_ascii_prefix("νησαίων", "") == ""
