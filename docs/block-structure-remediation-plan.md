# Block-structure preservation (Remarks / Additions / notes) — remediation plan

> **Status (2026-07-01): IN PROGRESS — spine shipped, mid-backlog.**
> The `block_type` capability (Phases 0–3) is built and merged, the reader renders
> it language/work-agnostically, and four backlog corpora are done (Hegel EN+DE,
> TEI note/cast recovery, Spinoza, scripture MT+LXX). **The live, resumable checklist is the
> "Execution tracker" section directly below** — start there. Everything after it
> (Problem / Diagnosis / Design / Phases / Appendix) is the original design +
> research record, kept as reference for *why* the approach is what it is.
>
> Triggering case (for context): Hegel's *Elements of the Philosophy of Right*,
> whose indented **Remarks** (Anmerkungen) and **Additions** (Zusätze) elaborate on
> each numbered §. The elaboration *text* survived ingestion; its *structural role*
> did not, so it read as ordinary §-body prose. The same flattening, an audit
> confirmed, affects most of the corpus (see Appendix).

---

## Execution tracker (resume here)

**How to use this:** pick the top unchecked item in the status table, open its
playbook, and run the proven template against it. Each playbook is written to be
startable cold in a fresh session. Update the table + check boxes as you go, and
write a per-corpus memory at the end (the gotchas always pay off on the next one).

### Status

| # | Corpus | Failure mode | State | PRs |
|---|---|---|---|---|
| — | Phase 0 plumbing (`block_type` model→DB→API→reader) | enabling | ✅ done | #16 |
| — | Hegel *Philosophy of Right* EN + DE | Mode 2 (merged) | ✅ done | #16–#20 |
| 1 | TEI.2 `<note>`/`<castList>` recovery (Plato/Aristotle/Homer/Epictetus) | Mode 1 (dropped) | ✅ done | #22–#23 |
| — | Note attribution (apparatus → translator, not author) | safety | ✅ done | #24–#26 |
| 2 | **Spinoza *Ethica*** (Demonstratio/Scholium/Corollarium merged) | Mode 2 (merged) | ✅ done | #27 |
| 3 | **Scripture apparatus** (Hebrew MT + Septuagint) — grew to include LXX `<l>` poetry recovery (Job/Prov/Wis/Song were 100% missing) + incremental-index slug/label delete-scope fix | Mode 3 (polluted) **+ Mode 1 (dropped)** | ✅ done | #29 |
| 4 | **Aquinas** *disputatio* (obj. / sed contra / body / replies) — ST 3,178→23,325 part-level chunks + chrome strip | Mode 2 (merged) | ✅ done | #30 |
| 5 | **Descartes** Objections & Replies — re-sourced (fr.wikisource Clerselier/Cousin); 537 chunks, `block_type='objection'` + objector in `speaker` | Mode 2 + attribution | ✅ done | #32 |
| 6 | **Kant** Anmerkungen — 474 `remark` chunks typed via zeno post-pass, 0 chunk_id churn (embeddings survived) | Mode 2 (merged) | ✅ done | #33 |
| 7 | Marx · Nietzsche | Mode 2 (MED) | ✅ **assessed — no fix needed** (see playbook) | — |
| 8 | Hobbes **+ Marx Kapital I–III** (OCR mega-chunks — *not* a parser fix) | data quality | ⬜ **NEXT** (re-source project) | — |

### The proven template (one corpus = one PR)

Distilled from the Hegel and Spinoza runs. Steps marked ⚠ are where past runs broke.

1. **Assess the source.** Find the structure markers; classify the fix:
   *typing* (emit `block_type`), *filtering* (strip apparatus from text), or
   *re-source* (structure absent → fetch a structured edition). Decide attribution
   up front: is the set-apart text the **author's own** (→ `remark`/`addition`,
   attributed to them) or **someone else's** (footnote/objection → attribute to the
   editor/objector, never the philosopher)? See [[refs-rules-mandatory-for-new-authors]]
   and the note-attribution work (#24–#26).
2. **Write/extend the dedicated splitter** (`corpus/split_<x>.py`). ⚠ Lazy-import
   `bs4`/`lxml` *inside* the function (`IngestDepsMissing`) — a module-top import
   crashes `minerva serve` in the CI base venv. Match locator conventions for the
   `section` strings.
3. **Wire it:** add the locator branch in `corpus/pipeline.py:parse_file`; point the
   `CorpusWork`(s) at the locator/source in `authors/<x>_works.py`.
4. **Re-source if needed:** add `perseus/download_<x>.py`; drop files in the
   registered corpus dir (`registry.py`). Commit the raw source if the parser is
   coupled to its exact bytes (precedent: Hegel Zusätze, Spinoza HTML).
5. ⚠ **Verify the parse OFFLINE, before touching the DB.** Run the splitter over the
   real files in a scratch script: counts by `block_type`, char-coverage %, **0
   duplicate `section` strings, 0 duplicate `chunk_id`s**, and spot-check the famous
   passages by name. Only proceed when counts match a known-good figure. (Spinoza's
   Part IV bug — 8/73 props — would have corrupted the corpus if re-ingested blind.)
6. **Tests:** hermetic `tmp_path` fixtures (`tests/test_split_<x>.py`) locking each
   behavior *and each bug you hit*. Model on `tests/test_split_spinoza_ethica.py`.
7. **Snapshot:** `scripts/snapshot-db.sh <reason>` (the `make` auto-snapshot is a
   fallback, not a substitute). See [[snapshot-before-destructive-ops]].
8. ⚠ **Re-ingest:** `make reingest-only ONLY=<source_ids>` — `--only` wipes at the
   **corpus** level, so pass **all sibling source ids** of a multi-source corpus or
   they get wiped. See [[only-reingest-corpus-level-wipe]].
9. **Embed:** `.venv/bin/minerva embed --lang <lang>` (incremental; only missing).
   ⚠ The reingest's own embed step may not cover new chunks — verify coverage and
   run this explicitly (Spinoza needed it: 0/925 → 925/925).
10. ⚠ **Refs (all three — rules alone is NOT enough, see [[refs-verify-required]]):**
    `refs build --strategy rules --source-author <X> --rescan-all`, then
    `--strategy embed-verify --source-author <X>`, then
    `--strategy llm-verify --source-author <X>` (background it; it only writes the
    local DB, so the PR doesn't block on it).
11. **Verify in DB:** per-work counts, `block_type` breakdown, embeddings coverage,
    a sample retrieval of a famous set-apart passage.
12. **Green:** `ruff check` the changed files + `pytest tests/` (full suite — you
    touched shared `pipeline.py`).
13. **Ship:** `direnv exec . git push -u origin <branch>`; `direnv exec . gh pr
    create`; poll `gh pr checks` until all green (no admin override — it's blocked);
    `gh pr merge --squash --delete-branch`. Personal account — always `direnv exec
    . gh ...`, never `gh auth switch`. See [[gh-account-scoping]].
14. **Memory:** update this tracker + the [[block-structure-remediation]] memory;
    write a per-corpus gotchas memory (like [[spinoza-ethica-resource]]).

### Playbooks

#### 3. Scripture apparatus filtering — ✅ DONE 2026-07-01 (PR #29)

**What shipped (scope tripled during the assess step — see gotchas):**

- `hebrew_mt._verse_text` and `tei_lxx._text_of` now skip `<note>`
  subtrees (namespaced `_text_excluding_notes` clones). MT notes carried
  whole *English* editorial sentences ("We read one or more accents in L
  differently than BHS…") spliced into 3,373 Hebrew verses; LXX notes
  carried Swete's marginal sigla/footnote variants (Gen 1:2 read
  "ἡ δὲ γῆ **A** ἦν ἀόρατος").
- **LXX poetry recovery (found during verify):** the verse walker only
  collected `<p>`, but poetic books encode text in `<l>`/`<lg>` —
  **Job (1,077), Proverbs (928), Wisdom (424), Song of Songs (116) were
  100% ABSENT from the corpus**, Lamentations was 88 hollow acrostic
  headings + 62 dropped, Letter of Jeremiah (single-chapter, no chapter
  div) fully dropped, plus ~2,769 inset-poetry verses (Gen 49, Exod 15,
  Deut 32–33, Judg 5…) across prose books. All recovered: 24,215 →
  27,082 LXX chunks. Chapter defaults to "1" when the breadcrumb has
  none; a mis-nested wrapper verse (Ps) yields its own content.
- Stray bare-text sigla (`§`, standalone Latin capitals — First1KGreek
  encoding defects outside `<note>`) scrubbed via `_STRAY_SIGLA_RE`.
- **Incremental-index delete-scope bug (store/chunks.py):** the DELETE
  keyed on `chunks_full.corpus` = `LOWER(works.author)` while the insert
  filter keys on the JSONL slug — mismatched for hebrew_mt/kjv/
  luther_1545/luther_1912/marcus_aurelius/new_testament/presocratic, so
  changed chunks were re-inserted BESIDE stale ones (3,373 dup MT verses
  on the first re-ingest). Fixed via `_author_labels_for_scope` JSONL
  pre-scan; regression tests in `tests/test_incremental_index.py`.

Verify used: parse-vs-DB count parity per book, 0 dup sections/ids,
0 ASCII in Hebrew text, famous-passage spot checks (Job 1:21, Prov 8:22,
Wis 2:23, Song 1:2, Lam 2:5), 100% embed coverage, 0 broken xref
targets (scripture cites are locator-resolved). Hermetic fixtures:
`tests/test_tei_lxx.py`, note-exclusion test in `tests/test_hebrew_mt.py`.

<details><summary>Original playbook (for reference)</summary>

Critical-text apparatus (`<note>`, `<app>`/`<rdg>`/`<lem>`) is being pulled into
verse bodies by `itertext()`, so a Hebrew/Greek verse string contains editorial
sigla. Unlike literary footnotes (which we *recovered* as `note` chunks), scripture
apparatus is text-critical noise that should simply be **excluded from the verse
text** — no `block_type` needed.

- **Files:** `src/minerva/sources/hebrew_mt.py:60` (`_verse_text` → `verse.itertext()`)
  and `src/minerva/sources/tei_lxx.py:35` (`_text_of` → `elem.itertext()`).
- **Fix:** before joining `itertext()`, drop `<note>`/`<app>` subtrees. Reuse the
  pattern from `tei.py` (`_text_excluding_notes`) — walk children, skip apparatus
  elements, keep `<w>`/`<seg>`/text/tail. Confirm the exact apparatus element names
  in the actual OSIS (MT) and TEI (LXX/Swete) files first.
- **Scope / churn:** ~2,736 MT verses + ~1,575 LXX verses; verse text changes ⇒
  `chunk_id` churn ⇒ re-embed those two corpora only.
- **Source ids:** check `registry.py` for the MT + LXX ingest source ids (pass both
  siblings if a corpus has more than one).
- **Verify:** apparatus sigla gone from sampled verses; verse *count* unchanged
  (we're cleaning text, not adding/removing chunks); diff a known apparatus-heavy
  verse before/after. See [[septuagint-ingestion]], [[bcv-canon-table]].
- **No refs rebuild needed** unless verse chunk_ids feeding scripture-cite xrefs
  churn — they will, so re-bind: scripture targets are mostly locator-resolved
  (NULL `target_chunk_id`), so likely fine, but check broken-target count after.
  See [[scripture-cite-rules]].

</details>

#### 4. Aquinas *disputatio* (Mode 2 — merged)

The scholastic article structure — objection(s) → *sed contra* → *corpus* (body) →
replies — is inline as `[arg. 1]` / `[s.c.]` / `[co.]` / `[ad 1]` markers but never
split, so a whole article is one chunk and the dialectic is unsearchable.

- **Files:** `corpus/split_aquinas.py` (locator `aquinas`, 6 works in
  `authors/aquinas_works.py`). Background survey: `docs/aquinas_cite_survey.md`.
  Source structure: [[corpus-thomisticum-anchors]].
- **Decision needed (assess step):** taxonomy for objections/replies. They are
  Aquinas's *own* dialectic (positions he raises then answers), so attribution is to
  Aquinas — but they aren't "remark"-style elaboration either. Options: (a) split
  into separate citable units, all `body`; (b) add `objection`/`reply` to the
  taxonomy. Lean (a) first (the win is *splitting*, locators like `ST I, q2, a3, ad 1`);
  add types only if the reader benefits.
- **Verify:** article counts; every `[co.]` present; spot-check the Five Ways
  (ST I, q2, a3) split into obj/sc/co/replies.

#### 5. Descartes Objections & Replies — ✅ DONE 2026-07-01 (PR #32)

**Assess confirmed a re-source job**: the Latin `meditationes.txt` holds only
the six Meditations. Re-sourced Clerselier's 1647 French translation from
fr.wikisource (Cousin 1824 ed.) — ten Parsoid-HTML pages committed raw,
fetched by `perseus/download_descartes_objections.py`.

**What shipped:** new `corpus/split_descartes_objections.py` (locator
`descartes_objections`): one work "Objections et Réponses", 537 chunks (276
objections + 261 Descartes paragraphs). Objector-voice paragraphs are
`block_type='objection'` with the objector (Caterus/Mersenne/Hobbes/Arnauld/
Gassendi/divers) in `chunks.speaker`; `retrieve.format_locator` cites
"… — objection (Hobbes)", never Descartes. Voice tracked from printed
headings (Hobbes's interleaved OBJECTION/RÉPONSE pairs; "ADDITION DE
DESCARTES" inside the Sixth set). Reader: `BlockType` union + `data-speaker`
voice tag + double-rule styling.

**Gap (future re-source, needs AT VII Latin OCR):** *Réponses aux cinquièmes*
(Descartes's reply to Gassendi), the entire *Septièmes* set (Bourdin) + the
letter to Clerselier — none transcribed on fr.wikisource.

#### 6. Kant Anmerkungen — ✅ DONE 2026-07-01 (PR #33)

The German sources are zeno.org HTML → `split_zeno_pages`; Kant's standalone
"Anmerkung" / "Anmerkung I" / "Allgemeine Anmerkung zur …" head lines came out
as tiny untyped chunks with the remark bodies indistinguishable from the main
argument. New `_type_kant_remarks` post-pass (Kant-gated, in
`corpus/split_zeno.py`): head + following paragraphs typed
`block_type='remark'` until the next structural head (Beweis / Folgerung /
Lehrsatz / Kasuistische Fragen / enumerated sub-heads) or page end. **Typing
only — 0 chunk_id churn, embeddings/lemmas/xrefs all survived the re-ingest
untouched.** 474 remarks across 7 works (MAN 126, KrV 101, KU 86, Religion 78
— the parerga, KpV 44, MS 24, Prolegomena 15).

**Gap:** the English Gregor PDFs render "Remark" as run-in heads inside
paragraphs (no standalone head lines), so the English side stays untyped —
would need text-level splitting with chunk churn; deferred.

#### 7. Marx · Nietzsche — ✅ ASSESSED 2026-07-01, no parser fix needed

The audit's "MED — untyped set-apart matter" rating was precautionary; the
assess step found nothing to type:

- **Marx (clean works):** the marxists.org-derived texts ship with **zero
  footnote markers** (0 standalone `Anmerkung`/`Fußnote` heads across the
  corpus) — Marx's apparatus was dropped upstream at the source, not merged
  by our parser. Nothing to recover without a re-source.
- **Nietzsche (zeno):** aphorism-level chunking is already correct
  (GS 1,162, MAM 1,535 …); the verse matter (GS *Scherz, List und Rache*
  prelude + *Lieder des Prinzen Vogelfrei*, JGB *Aus hohen Bergen*) is
  already sectioned under its own headings; the eKGWB Nachlass apparatus is
  intentionally stripped ([[ekgwb-nachlass-ingest]]). 0 footnote heads.
- **What the assess DID find:** *Das Kapital* Bd. I–III are **55 OCR
  mega-chunks** (85–582 KB each!) from a Google-Books scan of the 1867
  first edition, heavy OCR noise, chapter-level only. Moved to item 8 —
  it's the Hobbes failure mode, needs a re-source (mlwerke.de carries clean
  MEW text). Also noted: title-page junk chunks (e.g. GM ¶1–3 "Friedrich
  Nietzsche" / "Eine Streitschrift") → corpus-quality-audit backlog.

#### 8. Hobbes + Marx Kapital (data quality — re-source project)

The issue is OCR **mega-chunks**, a data-quality problem, *not* a block-type
parser fix. Needs re-chunking / re-source, not this template. See the
corpus-quality audit work ([[corpus-quality-audit-lessons]]). Scope: Hobbes
(Leviathan et al. OCR) + Marx Kapital I–III (re-source from mlwerke.de /
MEW; the current scan is the 1867 6-chapter first edition — decide edition
before sourcing). Plan as its own project (Spinoza-re-source precedent).

---

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

> Live status lives in the **Execution tracker** table at the top of this doc;
> this list is the original prioritization, annotated.

1. ✅ **TEI.2 note/cast capture** — one parser fix recovered ~8,456 dropped
   footnotes across Plato/Aristotle/Homer/Epictetus (emits `block_type='note'`/
   `'cast'` instead of dropping at `tei.py`). PRs #22–#23.
2. ✅ **Spinoza** dedicated splitter (Demonstratio / Scholium / Corollarium) —
   re-sourced structured Latin; 307→925 chunks, 162 remarks. PR #27.
3. ✅ **Scripture apparatus filtering** — `<note>` subtrees excluded in
   `hebrew_mt.py` + `tei_lxx.py`; grew to recover the LXX poetic books
   (Job/Prov/Wis/Song were 100% missing) and fix the incremental-index
   delete-scope slug/label mismatch. PR #29.
4. ✅ **Aquinas (#30), Descartes (#32), Kant (#33)** dedicated splitters
   (Descartes shipped with objector-attribution via `block_type='objection'`
   + `speaker`; Kant via the zeno remark post-pass, 0 id churn).
5. ✅ **Marx, Nietzsche — assessed 2026-07-01, no parser fix needed** (source
   texts carry no untyped set-apart matter; see playbook 7). Remaining: ⬜
   **Hobbes + Marx Kapital I–III** OCR mega-chunk re-source (data quality,
   its own project — playbook 8). ← NEXT
