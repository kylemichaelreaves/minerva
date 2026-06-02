/** Wire types for term glossary endpoints. */

export interface TermsListResponse {
  terms: {
    id: number;
    source_form: string;
    source_language: string;
    transliteration: string | null;
    lemma: string | null;
    short_gloss: string | null;
    long_description: string | null;
    occurrences: number;
  }[];
}
