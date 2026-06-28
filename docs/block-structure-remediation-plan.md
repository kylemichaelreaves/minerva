# Block-structure preservation (Remarks / Additions / notes) — remediation plan

> **Status (2026-06-27): DRAFT — design only, no code written.**
> Scope decided with the user: write the full plan before any code; **both Remarks
> and Additions must be included.** Research outcome (Phase 2): no *structured*
> German edition exists (DTA, TextGrid, Wikisource lack the work; zeno.org omits the
> Additions; the hegel.net Werke PDF is an image-only scan) — BUT the German
> Additions are freely available as **clean OCR** (archive.org Gans edition, 193
> Zusätze). Plan: label German Remarks via English §-alignment + splice the
> Additions from the Gans OCR. Triggering case:
> Hegel's *Elements of the Philosophy of Right*, whose indented **Remarks**
> (Anmerkungen) and **Additions** (Zusätze) elaborate on each numbered §. The
> elaboration *text* survived ingestion; its *structural role* did not, so it
> reads as ordinary §-body prose with no indentation.

## Problem

The ingest pipeline flattens all document structure to running plain text. A
chunk records *where* it sits (`section`, `book`, `page`, `speaker`) but never
*what kind* of block it is. So any work that distinguishes a main passage from
set-apart elaboration loses that distinction:

- **Hegel** — main § vs. *Anmerkung* (Remark) vs. *Zusatz* (Addition).
- **Spinoza** — Propositio vs. Demonstratio / Scholium / Corollarium.
- **TEI sources** — footnotes (`<note>`) are **dropped entirely** (text gone, not just unlabeled).
- Block quotes, indented matter, editorial notes across the corpus generally.

This is a global capability gap, not a Hegel-specific bug.

## Diagnosis (what the investigation found)

**The text is present; the structure is not.** For Hegel the paragraph splitter
already broke each Remark into its own chunk (`Einleitung, ¶3` = main §,
`Einleitung, ¶4` = the Remark), so block boundaries already align with chunk
boundaries — but nothing labels which is which.

Recoverability is **source-dependent**:

| Source | Marks structure? | Recoverable? |
|---|---|---|
| English — Cambridge EPUB (`…Philosophy of Right (Cam….epub`), *primary* | Yes — Remarks `<p class="blockquote">`, Additions an "Addition" label | ✅ via structure-aware re-parse |
| German — Zeno.org `pr_de.html`, *supplementary* | No — everything is `<p class="zenoPLm4n0">`, distinction already destroyed | ❌ not from this file → **re-source** (Phase 3) |

**Where structure is lost in the pipeline** (file:line):

- `src/minerva/corpus_extract.py` — `extract_html` / `extract_epub` strip all
  markup (class, `rend`, indentation) to plain text before chunking.
- `src/minerva/corpus/split_paragraphic.py:288` — paragraphs detected by blank
  lines only (`re.split(r"\n\s*\n", body)`); no block-type notion. Letter-free
  lines are dropped as non-prose (`:73`).
- `src/minerva/tei.py:271,354-361` — `<note>` (and `<castList>`) text is skipped
  entirely; `:232` concatenates a whole section's `<p>` runs into one flat string.
- `src/minerva/sources/tei_p5.py:215-243` — one chunk per `<p>`, flattened via
  `itertext()`; `rend`/element type discarded.
- Data model has no slot: `Chunk` dataclass (`tei.py:48-70`), `chunks` table
  (`store/schema.py:27-45`), reader API `SourceChunk` (`web/src/api/types/reader.ts`),
  reader query (`reader/queries.py:147-191`), chat renderer `BlockKind`
  (`web/src/utils/renderMarkdown.tsx`).

## Design: a first-class `block_type`

Add one nullable, controlled-vocabulary field that rides each chunk end-to-end.
`NULL` ≡ `body`, so every existing chunk is correct by default and the change is
backward-compatible.

**Taxonomy (start small, extensible):**

| value | meaning |
|---|---|
| `body` / NULL | main section / paragraph prose |
| `remark` | authorial set-apart commentary — Hegel *Anmerkung*, Spinoza *Scholium* |
| `addition` | editor-compiled additions — Hegel *Zusatz* (Gans, from lectures) |
| `note` | footnote / endnote (currently dropped by the TEI parser) |
| `blockquote` | quoted passage set apart from the prose |

Optional companion field `block_parent_section` (or reuse `section`) so a Remark
can point at the § it elaborates — enables "show §29 with its Remark grouped."
Decide in Phase 0 (see Open Questions).

## Phases

### Phase 0 — Plumbing (small, enabling, no behavior change)

1. `Chunk` dataclass: add `block_type: str | None = None`.
2. `chunks.jsonl`: serialize the field (writers + readers; default None).
3. Migration **`0022_chunks_block_type`** — `ALTER TABLE chunks ADD COLUMN
   block_type TEXT`. Plain additive column; no table rebuild, so this avoids the
   view/PRAGMA rebuild hazards noted in prior migrations. Bump `schema_migrations`.
4. Store insert path writes `block_type`.
5. Reader query (`reader/queries.py`) selects it; reader API JSON includes it;
   TS `SourceChunk` gains `block_type?: BlockType`.
6. No extractor changes yet → every chunk gets `NULL` → renders exactly as today.
   This phase is independently shippable and safe.

### Phase 1 — Structure-aware capture (the real work, per source format)

Each extractor learns to emit `block_type`. Order by value/recoverability:

1. **EPUB/HTML (`corpus_extract.py`)** — preserve a per-block label through
   extraction instead of flattening: map `<p class="blockquote">` → `remark`,
   the "Addition" label convention → `addition`, `<blockquote>` → `blockquote`.
   The splitter (`split_paragraphic.py`) must carry the label per paragraph
   rather than re-deriving from blank lines alone. **First target: Hegel's
   Cambridge EPUB** (the user's exact case) — this doubles as the vertical-slice
   proof that the whole spine works.

   **Correction (verified 2026-06-27):** the English EPUB currently ingests via
   `locator="section"` → **one merged chunk per §** (e.g. §4 is a single 7,281-char
   chunk holding main + Remark + Addition). So labeling-in-place is impossible;
   Phase 1.1 must **re-chunk** each § into separate typed chunks via a dedicated
   structure-aware EPUB parser (the generic flatten→blank-line-split path drops the
   markup). Consequence: Hegel EN `chunk_id`s churn → re-embed + re-lemmatize that
   work (expected, contained). This supersedes the "English = labeling only, stable
   chunk_ids" note in the migration-strategy section below. Bonus: the new parser
   also fixes ~17 spurious fragment chunks the section splitter creates by
   mis-reading inline "see § N" cross-references as new section starts.
2. **TEI (`tei.py`, `sources/tei_p5.py`)** — stop discarding `<note>`; emit it as
   a `note`-typed chunk (recovers *lost* text, not just labels). Map
   `rend="blockquote"`/`<q>`/`<quote>` → `blockquote`. Preserve `<p>` boundaries.
3. **Lexical-marker works (Spinoza et al.)** — derive `remark`/`addition` from
   leading markers ("Scholium", "Demonstratio") in the relevant splitter.

### Phase 2 — German Hegel structure (research outcome: no structured edition exists)

Research (2026-06-27) checked every freely-available structured German source.
**None hold the *Grundlinien*:**

- **Deutsches Textarchiv** — has only *Phänomenologie* + *Wissenschaft der Logik*
  (3 vols). The Rechtsphilosophie is **not in the DTA corpus.** (Original plan
  assumed DTA had it — it does not.)
- **TextGrid Repository / Digitale Bibliothek** — no edition entry; the 44 hits
  are *secondary* references that merely cite the work.
- **German Wikisource** — author-page bibliographic pointer to external scans
  only; **no on-wiki transcription** (the obvious title 404s).

**Correction + resolution (verified 2026-06-27):**

- Our Zeno source does **not** contain the Zusätze — confirmed both in
  `data/hegel/pr_de.html` (all §1–§360 + Remarks, but "Zusatz" appears 0× as a
  label) **and** on zeno.org's live per-section pages (the Einleitung page has §4's
  main text and Remark but no Zusatz). So zeno.org's *edition omits the Additions*;
  it is not a scrape gap. German problem is two-layered: Remarks = *labeling* gap,
  Additions = *content* gap.
- **The Additions ARE freely available as clean OCR text:** archive.org's Gans /
  Werke edition (`grundlinienderp00gansgoog_djvu.txt`, 1.2 MB) contains **193
  "Zusatz" labels**, clean German prose (correct umlauts, no long-ſ artifacts),
  and detectable § headings. So restoring German Additions does **not** require a
  Fraktur-OCR project — just download + parse + light cleanup (de-hyphenation,
  heading-§ vs cross-ref-§ disambiguation, footnote-marker stripping) + a
  verification pass.

Available German sources are all unstructured or typographic-only:

- **Zeno.org** (current `pr_de.html`) — main text + Remarks (flattened to identical
  `<p class="zenoPLm4n0">`); **Additions absent.**
- **hegel.net / Internet Archive** — 1821 first-edition PDF (Anmerkungen, **no
  Zusätze**) and Werke Bd. 8 / Gans editions (**with** Zusätze) as PDF/OCR;
  structure is **typographic only** → recoverable only via OCR + layout heuristics.

So "re-source a structured German edition" is **not directly achievable** — the
structured editions don't exist for this work in German. Revised options:

Because the Additions are *absent* from German, the German task is two separate
jobs — **label the Remarks** (recoverable) and, if wanted, **restore the
Additions** (needs a new source). They compose:

| Option | Job | Mechanism | Robustness |
|---|---|---|---|
| **A. English-aligned propagation (recommended for Remarks)** | Label German Remarks | Re-parse German Zeno with **§ awareness** (it carries `<h4/h5>§ N</h4>` headings the splitter collapses), then propagate `block_type` for the Remark blocks from the §-keyed, already-typed Cambridge **English** EPUB (Phase 1.1). Cannot create Additions that aren't in the German text. | High — labels from a definitively-structured source; no German heuristics/OCR |
| **B. archive.org Gans OCR for German Additions (recommended)** | Restore + label Additions | Ingest `grundlinienderp00gansgoog_djvu.txt`; split on the 193 "Zusatz." labels; attach each to the § that precedes it as an `addition`-typed chunk. Light cleanup (de-hyphenation, §-ref disambiguation, footnote strip) + verification pass. | High — clean pre-OCR'd text, no Fraktur pipeline |
| B′. hegel.net 1833 PDF | (fallback) | **Verified 2026-06-27:** pure image scan (455 full-page PNGs, zero text layer) → would need a Fraktur-OCR + layout project. Superseded by B. | Low–Medium; rejected unless B's quality proves inadequate |
| C. 1821 first edition | — | Structured by typography; Remarks only, never had Additions | content loss; rejected |

**Recommendation — hybrid (delivers both Remarks *and* Additions in German):**

1. **Remarks → Option A.** Keep Zeno's clean main+Remark text; label the Remark
   blocks by §-aligning to the already-typed Cambridge English EPUB (Phase 1.1).
2. **Additions → Option B.** Splice the 193 Zusätze from the Gans OCR in as
   `addition`-typed chunks, attached to each § by its number.

This keeps the cleanest text for the bulk (Zeno) and only introduces OCR for the
~190 Additions Zeno never carried. (Simpler-but-noisier alternative: replace Zeno
wholesale with the Gans OCR as a single consistent source that already contains all
three layers.) Re-parsing the German for § awareness + splicing changes its
`section` scheme → German `chunk_id`s churn → re-embed + re-lemmatize that corpus
(expected, contained). English needs only labeling (Phase 1.1) — no re-source.

**Zusatz parser — prototyped & validated 2026-06-27** (against
`grundlinienderp00gansgoog_djvu.txt`):

- The Additions are an **appendix** at the back (~78% through the file), under a
  `Zusätze.` header — *not* inline. Each is headed `<seq>. Zusatz zu § <N>. (<topic>.)`
  so the target § is **explicit** (exact attachment, no heuristics).
- Anchor the split on `Zusatz\s+zu\s+§\s*(\d+)` (plus the one `Zusatz zur Vorrede`);
  **ignore the leading sequence number** — it's the OCR-noisiest token. First naive
  pass captured **186/~194 (~96%)** across **184 distinct §§**, range §1–§339.
- Cleanup checklist (all modest): strip Google watermarks (`Digitized by Google`),
  running headers (`Zu § N-M.`), bare page numbers; de-hyphenate line breaks
  (`vornehm- lich`); verification pass for stray glyphs (`Hechts`→`Rechts`,
  `eini^`→`einig`, `pie`→`Die`).
- Output: one `addition`-typed chunk per Zusatz, `section = "§N Zusatz"`,
  `block_parent_section = N`, ordered after that §'s Zeno main+remark chunks.

**End-to-end hybrid prototype — validated 2026-06-27** (`scratchpad/proto_hybrid.py`,
read-only over the real EPUB + Zeno + Gans files):

- **Coverage:** EN 359 §§, DE 358 §§, **357 in both** (§1–§360).
- **English block typing** (markup-driven, essentially exact): remarks in 168 §§,
  additions in 192 §§, 105 notes. `p.blockquote*`→remark, text "Addition (H/G)."→
  addition, `p.noindent*`→main, `p.footnote`→note.
- **German Remark labeling** via "first para = main, rest = remark" heuristic vs.
  English typing: **97% agreement (347/357), ZERO false negatives** — never misses
  a real Remark; the 10 disagreements (3%) are *over*-flags (German main spanning 2
  paras) that the English alignment catches. So EN-alignment → near-perfect labeler.
- **Additions:** Gans parser attached 184 §§; **180 match an English-marked
  addition**; per-§ German↔English Zusatz text corresponds exactly (e.g. §4, §258).
- **Data-model conclusions (lock Phase 0):** chunk-level `block_type` is
  sufficient (every paragraph → one type; no span-level labeling needed); add
  `block_parent_section` for Addition→§ attachment. Build refinements: recover the
  ~8–12 Gans additions missed by the naive seq-number regex; OCR-cleanup pass on
  Addition bodies.

### Phase 3 — Rendering

- **Reader** (`web/src/Reader/components/Lines.tsx` + `reader.css`): bind
  `data-block={chunk.block_type}` on `.line`; style `remark`/`addition` with a
  left indent + soft accent rule, `note` smaller/dimmed. (Renderer agent
  confirmed this is a ~5–10 rule, single-class-binding change.)
- **Chat** (`renderMarkdown.tsx` + `markdown.ts` + `thread.css`): add a
  `blockquote` `BlockKind` so cited Remark text can render set-apart.
- **Search/retrieval (future, optional):** a filter to include/exclude
  `note`/`addition` from results, or down-weight them. Out of scope for v1.

## Migration & re-ingest strategy

Two distinct paths, chosen to protect the expensive embed/lemma/xref artifacts:

1. **Label-only re-parse (preferred where the source already marks structure,
   e.g. Hegel EN EPUB):** keep chunk **text and boundaries byte-identical**, only
   set `block_type`. Because `chunk_id = blake2b(source+work+section+text[:120])`,
   identical text ⇒ **stable chunk_ids** ⇒ no re-embed/re-lemmatize. Verify churn
   is zero with a dry-run diff before committing. *Risk:* a structure-aware
   extractor may shift a boundary (e.g. previously-merged adjacent blockquotes);
   if so it degrades to path 2 for that corpus.
2. **Full re-ingest (re-sourced works, e.g. German Hegel):** accept chunk_id
   churn; re-embed (incremental, default) + re-lemmatize + xref rebuild for that
   corpus only.

**Operational guardrails (per existing project rules):**
- `scripts/snapshot-db.sh <reason>` **before** any re-ingest — the cmd_index
  auto-snapshot is a fallback, not a substitute.
- Use the per-corpus incremental path (`minerva index --incremental --corpora
  hegel` / `make reingest-only ONLY=hegel`), **not** a global `--reset`.
- **`--only` wipes at the corpus level:** Hegel has multiple sources (EN EPUB,
  EN editor-notes HTML, DE). Re-ingesting must pass *all* Hegel sources together
  or siblings get wiped.
- Backfill English labels via path 1 first (cheap, reversible), measure, then do
  the German re-source.

## Testing

- Unit: extractor maps `class="blockquote"` → `remark`, "Addition" → `addition`,
  TEI `<note>` → `note`; splitter carries the label per paragraph.
- Golden: a small fixture (Hegel §1 + Remark; a TEI passage with a footnote)
  asserting block_type and that note text is no longer dropped.
- Migration test: `0022` applies idempotently; old chunks read back as
  `block_type IS NULL`; FTS/lemmas untouched.
- Frontend: Reader renders `data-block=remark` with indent; chat blockquote kind.
- Chunk-id stability: dry-run diff proving the EN label-only re-parse changes 0
  chunk_ids (else reclassify as path 2).

## Open questions / decisions before build

1. **German strategy (DECIDED 2026-06-27 — hybrid):** keep Zeno's clean text for
   main+Remarks (label Remarks via English §-alignment, Option A) and splice the
   193 Additions from the archive.org Gans OCR by § (Option B). Wholesale Gans-OCR
   replacement rejected (would make the whole German text OCR-noisy).
2. **Remark→§ linkage** — add `block_parent_section`, or infer from ordinal
   adjacency at render time? Affects whether we can "fold" a § with its Remark.
3. **Phase 0 alone first?** — Phase 0 is safe and shippable independently; we can
   land it, then iterate extractors per source without a flag day.
4. **`note` reintroduction** — surfacing previously-dropped TEI footnotes will
   *add* chunks to those works (id churn + re-embed). Confirm appetite before
   touching the TEI corpora.

## File map (for the build phase)

- Model/store: `src/minerva/tei.py` (`Chunk`), `src/minerva/store/schema.py`,
  `src/minerva/migrations/0022_chunks_block_type.*`, store insert path.
- Extract/split: `src/minerva/corpus_extract.py`,
  `src/minerva/corpus/split_paragraphic.py`, `src/minerva/tei.py`,
  `src/minerva/sources/tei_p5.py`.
- Hegel config: `src/minerva/authors/hegel_works.py`.
- API: `src/minerva/reader/queries.py`, reader handler.
- Frontend: `web/src/api/types/reader.ts`, `web/src/Reader/components/Lines.tsx`,
  `web/src/Reader/reader.css`, `web/src/utils/renderMarkdown.tsx`,
  `web/src/utils/markdown.ts`, `web/src/Thread/thread.css`.

## Appendix — corpus-wide audit (2026-06-28)

Hegel PR (EN + DE) is DONE end-to-end (Phases 0–3; PRs #16, #17, #20, #18, #19
merged; reader rendering is language/work-agnostic). A four-way audit of the
rest of the corpus confirms **Hegel was not special** — the same flattening
affects most works, in three distinct failure modes:

### Mode 1 — content DROPPED (text is gone, not just unstructured)

| Source / parser | What's dropped | Scale |
|---|---|---|
| **TEI.2 `tei.py:360`** drops every `<note>` + `<castList>` | translator/scholarly footnotes | **~8,100**: Plato 4,137 (Republic 2,769) + 68 castLists; Aristotle 3,507; Homer 295; Epictetus 92 |
| `split_ekgwb` strips `.footnotes`/apparatus | Nietzsche Nachlass | — |
| `extract_epub` drops editorial back-matter spine items | generic EPUB path | — |
| `split_stephanus_de` skips the "ANMERKUNGEN" section | Schleiermacher | — |

### Mode 2 — content MERGED / untyped (the Hegel problem; ~47.8k early-modern chunks are `block_type=NULL`)

- **Spinoza — CRITICAL:** Demonstratio + Scholium + Corollarium merged into one
  chunk per proposition (`split_spinoza.py`). The Scholia are Spinoza's substance.
- **Aquinas — HIGH:** the *disputatio* structure (`[arg. 1]` / `[s.c.]` / `[co.]`
  / `[ad 1]` = objections / sed contra / body / replies) is inline, never parsed.
- **Descartes — HIGH** (Objections & Replies), **Kant — HIGH** (Anmerkungen +
  A/B apparatus), **Marx / Nietzsche — MED**, **Hobbes — MED** (OCR mega-chunks),
  Hume / Locke / Pascal / Rousseau / Schiller — LOW.

### Mode 3 — apparatus POLLUTED into the text (scripture; `itertext()` pulls notes in)

- **Hebrew MT** `hebrew_mt.py:70` (2,736 verses) and **Septuagint** `tei_lxx.py:38`
  (1,575 verses): `<app>` / `<note>` critical apparatus inlined into verse text.
- **Clean (no action):** Vulgate, SBLGNT/NT, Quran, Sophocles, Lucretius, Origen,
  Aesop. French authors (Boulainvilliers / Gobineau / Renan) — LOW: footnotes are
  OCR-inlined, not recoverable structure.

### Prioritized remediation backlog (each follows the Hegel template: typed
chunks → per-corpus re-ingest + re-embed; reader rendering already done)

1. **TEI.2 note/cast capture** — one parser fix recovers ~8,100 dropped footnotes
   across Plato/Aristotle/Homer/Epictetus (emit `block_type='note'`/`'cast'`
   instead of dropping at `tei.py:349,360`). Highest impact.
2. **Spinoza** dedicated splitter (Demonstratio / Scholium / Corollarium).
3. **Scripture apparatus filtering** — strip `<note>`/`<app>` before `itertext()`
   in `hebrew_mt.py` + `tei_lxx.py`.
4. **Aquinas, Descartes, Kant** dedicated splitters.
5. Lower: **Marx, Nietzsche, Hobbes** (Hobbes is an OCR-quality issue, not parser).
