/** Wire types for reader, terms, and translate endpoints. */

export interface Work {
  /** Stable numeric works.id — used to scope chat retrieval to this work. */
  work_id: number;
  corpus: string;
  author: string;
  work: string;
  display_title: string;
  display_subtitle?: string | null;
  lang: string;
  chunks: number;
}

/** Structural role of a chunk within its work. Absent/`null` ≡ ordinary
 * body prose; the others mark set-apart matter (Hegel Anmerkung →
 * `remark`, Zusatz → `addition`, footnotes → `note`, quotations →
 * `blockquote`). See docs/block-structure-remediation-plan.md. */
export type BlockType =
  | "body"
  | "remark"
  | "addition"
  | "note"
  | "cast"
  | "blockquote"
  // A dialectical voice by another author hosted inside the work —
  // Hobbes/Caterus/Arnauld/… objecting to Descartes' Meditations.
  // The objector's name rides in `speaker`.
  | "objection";

export interface SourceChunk {
  chunk_id: string;
  section: string | null;
  book: string | null;
  page: string | null;
  speaker: string | null;
  text: string;
  ord: number;
  /** Optional during Phase 0 rollout: only the work-range endpoint emits it
   * so far, and every chunk is currently `null` until extractors populate it. */
  block_type?: BlockType | null;
}

export interface WorkRange {
  work_id: number;
  corpus: string;
  author: string;
  work: string;
  display_title: string;
  display_subtitle?: string | null;
  lang: string;
  total: number;
  offset: number;
  limit: number;
  chunks: SourceChunk[];
}

export interface TermOccurrenceSpan {
  id: number;
  term_id: number;
  source_start: number;
  source_end: number;
  source_form: string;
  lemma: string;
  transliteration: string | null;
  short_gloss: string;
}

export interface OccurrenceMap {
  work_id: number;
  lang: string;
  from: number;
  limit: number;
  by_chunk: Record<string, TermOccurrenceSpan[]>;
}

export interface TermRenderingRow {
  id: number;
  translation_id: number;
  translator_name: string;
  year: number | null;
  language: string;
  work_title: string;
  default_rendering: string;
  translator_note: string | null;
}

export interface TermRelatedRow {
  id: number;
  source_form: string;
  source_language: string;
  short_gloss: string;
  relation_kind: string | null;
  notes: string | null;
}

export interface TermEditionCountRow {
  edition_id: number;
  name: string;
  language: string;
  is_canonical: number;
  work_title: string;
  occurrences: number;
}

export interface TermDetail {
  id: number;
  source_form: string;
  source_language: string;
  transliteration: string | null;
  lemma: string | null;
  short_gloss: string;
  long_description: string;
  renderings: TermRenderingRow[];
  occurrences_by_edition: TermEditionCountRow[];
  related: TermRelatedRow[];
}

export interface ChunkContextResponse {
  corpus: string;
  author: string;
  work: string;
  display_title: string;
  lang: string;
  focus: SourceChunk;
  before: SourceChunk[];
  after: SourceChunk[];
}

export interface WordSample {
  chunk_id: string;
  section: string | null;
  surface: string;
  surface_start: number;
  surface_end: number;
  snippet: string;
  match_start: number;
  match_end: number;
}

export interface LemmaHighlightSpan {
  start: number;
  end: number;
}

export interface LemmaHighlights {
  work_id: number;
  lang: string;
  lemma: string;
  from: number;
  limit: number;
  by_chunk: Record<string, LemmaHighlightSpan[]>;
}

export interface WordLookup {
  surface: string;
  lemma: string;
  lang: string;
  edition_id: number;
  work_id: number;
  work_title: string;
  occurrence_count: number;
  samples_offset: number;
  next_samples_offset: number | null;
  pos: string | null;
  gender: string | null;
  number: string | null;
  feats: string | null;
  samples: WordSample[];
}

export type TargetLang = "eng" | "fra" | "deu";

export interface TranslationResponse {
  translated_text: string;
  literal_text: string;
  model: string;
  cached: boolean;
}
