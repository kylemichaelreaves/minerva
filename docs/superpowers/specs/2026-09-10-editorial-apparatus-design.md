# Editorial apparatus: mark it, cap it, collapse it

**Status:** approved 2026-09-10
**Issues:** #533 (footnotes spliced into body text), #534 (front/back matter
indexed as Hegel, and the OCR-defeated filter), #535 (De Cive — **out of scope**,
see below)
**Related:** #165 (the apparatus share cap), #291 (paratext types), #401
(Google Books watermark inside 9 chunks)

A reader reported that the editorial material in *Lectures on the Philosophy of
World History* was misleading. It is, in three different ways, and the
predicate meant to prevent it has been silently failing corpus-wide.

## Problem

Work 712 (`Hegel`, `eng`, 477 chunks) is extracted from a 2011 OUP PDF. The
extractor walked each page in reading order and concatenated
`[running head] [body] [footnote block] [page number]` into one chunk.

| Defect | Count | Share |
|---|---|---|
| Chunks with a trailing numbered-note block | 279 | 58% |
| Chunks ending in a bare page number | 391 | 82% |
| Chunks carrying a running head | 216 | 45% |
| Editors' prose inside Hegel's body text | ~101,000 chars | **7.6%** |
| Chunks that are apparatus end to end | 14 | 3% |

Chunk `3b24cff49c5d197df172` (ord 79) truncates Hegel mid-thought and appends
an editor's note to the same paragraph:

> …and Caesar's Commentaries, belong here too.**4** I But original historians
> of 7 this kind arc found in our own day as well… In particular. **4. On
> Herodotus, Thucvdides, Xenophon, and Caesar, see the IntroductorY Fragment C
> 182!. 1828), nn. 4, 10, 11, 13. 135**

Three more splice a note *mid-sentence* rather than at the tail —
`3043a5e0e344e1d78c5c` interrupts "the War of the Spanish [Succession]" with
note 61.

The 14 whole-chunk items are the OUP title page, the copyright boilerplate
(`OXFORD \1NI'f'BUITI' ...... Great Clamtdoo Street`), the table of contents,
Hodgson and Brown's editorial introduction (ords 8–10), and the bibliography
(ords 474–476).

### Why the existing filter did not stop it

`heading_clean._is_editorial_heading()` already carries
`"editorialintroduction"` and `"bibliography"` in `_EDITORIAL_PHRASES`, and
`hegel_works.py:227` already sets `skip_headings=("Preface",)` for this work.
The intent was implemented. It does not fire:

```
True   'Editorial Introduction'
True   'Editorial Intr O Duction'      ← the docstring's own example
False  'Editorial Introouctjon'        ← work 712, ord 10
False  "EDITORIAL INTRODUCTIOI'o<"     ← work 712, ord 9
True   'Bibliography'
False  'Bjbljography'                  ← work 712, ord 475
False  'Secondary Works in German and French'
False  'Sources Used or Alluded to by Hegel'
```

`_EDITORIAL_NORM_RE` is `[^a-z]`: it strips non-letters and lowercases. That
survives **spacing and punctuation** damage — which is what the docstring's
example demonstrates — but not **letter substitution**, which is what OCR
actually does. The last two lines fail even spelled correctly; those are
simply missing phrases.

This is a corpus-wide fault. Every OCR'd edition is exposed to it, and the
failure is silent in both directions.

### The second, larger policy problem

`split_paragraphic.py:361` states the current policy:

> Editorial / front-matter labels … **drop BOTH the label AND the body** so
> this material doesn't get attributed to Hegel downstream.

So today, apparatus that matches is *deleted*, invisibly. Fixing the matcher
without changing this would silently delete more. The reader's requirement —
mark it, demote it, collapse it — is strictly better: it keeps real
scholarship, attributes it correctly, and is reversible.

## Design

### 1. `heading_clean`: match through OCR, and tag instead of dropping

Two changes to one predicate.

- **Bounded edit distance on the whole normalised label**, ≤2, against
  phrases of length ≥12 only. The existing exact-substring rule stays for
  everything; the fuzzy pass is additive.

  *Revised 2026-09-10 after measuring — the spec previously proposed folding
  confusion classes (`i/j/l/1`, `u/w`, `c/e`, `o/0`). That is over-engineering
  for the damage that actually exists.* Across all **94,424** distinct heading
  labels in the corpus, only four are near-misses to a phrase, and the rule
  above catches exactly the two real ones with **zero false positives**:

  ```
  newly matched by whole-label fuzzy (len>=12, d<=2): 2
     Bjbljography              ~ bibliography
     Editorial Introouctjon    ~ editorialintroduction
  ```

  The two constraints are what make it safe, and both are load-bearing:

  - **Whole-label, not substring.** Windowed substring matching was measured
    and is also too slow to probe at corpus scale.
  - **Length ≥12.** `_EDITORIAL_PHRASES` contains short entries — `contents`,
    `glossary`, `foreword`, `dedication` — matched today by *substring*.
    Letting those match fuzzily would fire on ordinary chapter titles.

  The other two near-misses, `Editoria L Int` and `Edit Introducti O N`, are
  *truncation*, not substitution, and are deliberately not matched: they are
  too short to distinguish from real headings.

  **Caveat on the measurement:** headings the filter already matches are
  *dropped* at ingest, so they never reach `chunks.section` and cannot appear
  in this survey. It measures what leaks through, which is the direction we
  care about, but it cannot be read as "the filter only ever matched once".
- **Add the two missing phrases**: `sourcesusedoralludedtoby`, `secondaryworks`.

Then change the call site from *drop* to *tag*: `_split_chapter_block` gains an
`editorial: bool`, and `_emit` sets `block_type='editorial'` rather than the
caller skipping the body.

### 2. A new `block_type`: `editorial`

Joins `note` / `remark` / `addition` / `objection` / `cast`. `chunks.block_type`
is free-form `TEXT` with no CHECK constraint, but the `BlockType` union in
`web/src/api/types/reader.ts` and the `check_api_types` gate keep Python and
the frontend in step — both must be updated together or `make check` fails.

`editorial` is distinct from `note` on purpose: `note` is footnote-shaped and
`format_locator` reattributes it as "editorial note", which is wrong wording
for a 3,000-character editors' essay.

Note that `retrieve.py:689` already reads
`_APPARATUS_LABEL.get(block_type, "editorial")` — the *fallback* label is
already the string `editorial`, so a new `editorial` type would be labelled
correctly by accident. Add it to `_APPARATUS_LABEL` explicitly anyway; a
behaviour that depends on a default happening to match is one refactor away
from being wrong.

### 3. Page-furniture surgery in the extractor

Per chunk, in order:

1. Strip the leading running head (four known strings, OCR-tolerant).
2. Split the trailing numbered-note block into its own sibling chunk with
   `block_type='note'` — the value that already exists and is already capped.
3. Drop the trailing bare page number.

**The note number gives us a correctness check rather than a blind regex.** A
note block opening `4. ` is only a note if marker `4` appears glued to a word
upstream (`too.4`). Where the marker is absent, leave the text alone and count
it — an unverified split is worse than a missed one, because it silently
deletes Hegel.

Sibling chunks are numbered `¶N.note`, never by renumbering `¶`: `section` is
an input to `_make_chunk_id`, so renumbering would churn every chunk after the
insertion (`section` feeds `chunk_id` — 17 stripped once churned 745).

### 4. Search: inherit the existing cap

Add `editorial` to `_APPARATUS_TYPES` in `retrieve.py`. The policy and its
reasoning already exist, argued for Plato's notes at `retrieve.py:172-186`:

> A cap rather than a score penalty: a penalty is a magic number tuned to
> whichever query it was derived from, while a cap states the actual policy —
> apparatus supports the text, so it may not crowd it out.

`_APPARATUS_MAX_SHARE = 1/3`. "Always prefer the actual author over the
editorial information" becomes exactly this cap: apparatus stays reachable,
and can never take more than a third of a result set.

### 5. Reader: the first collapsible block

`Lines.tsx` already emits `data-block`; today `data-block` only *styles*.
`editorial` renders as a closed disclosure:

```
┌────────────────────────────────────────┐
│ ▸ Editorial Introduction               │   ← closed by default
│   Hodgson & Brown · 3 sections         │
└────────────────────────────────────────┘
```

Expanding reveals the chunks, styled in the existing subordinate visual
language (left rule, `0.93em`, `--r-ink-soft`) that `remark`, `addition` and
`objection` already share. Open/closed state is per-viewer UI state, not
persisted corpus state.

### 6. Landing it

The churn was measured by simulating the cleanup over all 477 chunks:

| | |
|---|---|
| `chunk_id` would change (first 120 chars differ) | **187** |
| text changes, `chunk_id` survives (tail-only edit) | **259** |
| untouched | 31 |
| `cross_references` (source) on this work | 128 |
| `chunk_lemmas` rows on this work | 215,643 |
| `chunk_syntax` rows on this work | 0 |

**An in-place post-pass that preserves `chunk_id` was considered and rejected.**
The Kant Anmerkungen precedent achieved zero churn because it was
*typing only* — it changed no text. This changes text in **446** chunks, and an
embedding is an embedding *of the text*; `chunk_lemma_state` carries a
`text_hash` for exactly this reason. So all 446 need re-embedding and
re-lemmatising on either route. Preserving the id buys nothing but a
`chunk_id` that no longer reproduces from its own input — which churns at the
next re-ingest anyway. The id churn therefore costs only the 128
cross-references, on top of a re-derivation we owe regardless.

Order of operations:

1. `scripts/snapshot-db.sh editorial-apparatus` before anything mutating.
2. Re-ingest work 712 per the operator playbook. `ingest --only` replaces
   `chunks.jsonl` **per corpus**, so every Hegel source must be passed
   together, not just the one file.
3. `index --incremental --corpora hegel`, then `embed` (incremental by
   default), then re-lemmatise.
4. `refs build`, then repair the 128 cross-references, then embed-verify and
   llm-verify — `refs build` alone is not sufficient.
5. `make generate-authors` and commit both snapshots: the chunk count moves
   (sibling note chunks are added) and per-work granularity changes.

## Testing

- `heading_clean`: table-driven over the eight strings above, asserting both
  directions. The false-positive direction is the one that matters — assert
  that a sample of real chapter headings from the corpus still returns `False`.
- The note-splitting rule: fixtures for marker-present (split), marker-absent
  (leave alone, count), and note-mid-sentence (the `3043a5e0e344e1d78c5c`
  shape).
- Retrieval: a query that today returns mostly apparatus returns at most ⅓
  after the change. The cap already has coverage to extend rather than invent
  — `tests/test_retrieve.py:206`
  (`test_default_fetch_pool_still_finds_primary_text_past_a_dominant_apparatus_share`)
  and the `note1` fixture at :298. Neither names `_APPARATUS_MAX_SHARE`
  directly, so grepping the constant finds nothing; the tests are there.
- Reader: the disclosure is closed on first render, opens on click, and
  `editorial` chunks are absent from the reading flow when closed.
- Coverage: SonarCloud gates new code at 80% **including branches**; a guard
  whose false branch is untested scores 3/4.

## Corrections to the record

Both go in the implementing PR, per the "don't trust a stated cause" rule.

1. `_is_editorial_heading`'s docstring claims OCR tolerance it does not have.
   Its example, `"Editorial Intr O Duction"`, is drawn from the one damage
   class the code handles.
2. `scripts/clean-hobbes-latin.py` reports the long-s residue as "10 chunks —
   already low". It is low because the detection heuristic gates `lang` to
   `{eng, fra, deu}` and therefore **excludes `lat`**, the only affected
   language. The number measures the languages that do not have the problem.

## Out of scope

- **#535, De Cive.** Its 18 Latin chunks are unusable long-s OCR and are one
  chunk per chapter (up to 71,878 chars). That is a re-source, not a cleanup —
  a different job with a different risk profile, and the precedents
  (Kapital MEW, Theognis, Spinoza) all replaced the file rather than repairing
  it.
- **The corpus-wide sweep.** Fixing the predicate makes other works' apparatus
  detectable for the first time; how much there is, and in which works, is
  unmeasured. Worth a follow-up issue once the predicate lands, so the sweep
  measures against a filter that works.
