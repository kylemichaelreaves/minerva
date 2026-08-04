# Term-glossary YAML specs

One YAML file per author per language. The curator authors a file
here; `minerva terms import` reads it and populates `terms`,
`term_renderings`, `term_relations`, and `term_occurrences` rows.

## Files

- `aristotle.grc.yaml` — Aristotle, Ancient Greek.
- `plato.grc.yaml` — Plato, Ancient Greek (add when curating).
- `hegel.deu.yaml` — Hegel, German (add when curating).
- `kant.deu.yaml` — Kant, German (add when curating).

Subdirectories of this folder are NOT auto-loaded by
`scripts/seed_terms.py`, so a `data/glossary/_drafts/` is a safe
place to stash work-in-progress files.

## Workflow — adding terms for a new work

The unit of curator effort is one work. Steps:

```bash
# 1. One-time per edition: populate the lemma cache for the work's
#    chunks. Run once for each new edition; later runs skip chunks
#    already cached.
uv run minerva terms lemmatize --lang deu --edition-id 84

# 2. Edit the author's YAML. Add a new term entry, or extend an
#    existing term's `apply_to:` with the new work + edition.

# 3. Dry-run to see counts.
uv run minerva terms import data/glossary/hegel.deu.yaml \
    --dry-run --only-work "Phänomenologie des Geistes"

# 4. Commit.
uv run minerva terms import data/glossary/hegel.deu.yaml

# 5. Open the Reader and click a marked term.
```

## Schema

```yaml
version: 1                       # currently 1
language: deu                    # ISO 639-3 source language
author: Hegel
terms:
  - lemma: Geist                 # primary match key (lemma-cache join for deu)
    source_form: Geist           # canonical surface for display (defaults to lemma)
    transliteration: Geist       # optional
    short_gloss: spirit; mind
    long_description: |
      Multi-line markdown. Keep it factual; the TermCard
      surfaces this verbatim.

    # When set, the importer uses these exact strings instead of the
    # lemma cache. Required for Greek today (no Greek lemmatizer on
    # Python 3.14 yet) and useful for German verbs whose separable
    # prefix trips spaCy's lemmatizer.
    search_forms:
      - Geistes                  # add genitive / dative if relevant
      - Geiste

    apply_to:
      - work: Phänomenologie des Geistes
        edition: Suhrkamp          # editions.name — the natural key
        edition_year: 1986         # only when one name repeats across years
        translations:
          - translator: Terry Pinkard   # translations.translator_name
            rendering: spirit
            note: optional translator note (markdown)
          - translator: Michael Inwood
            rendering: spirit
      # A term in multiple works repeats only the apply_to entries —
      # the term metadata above stays authoritative.

    related:
      - lemma: Bewusstsein
        relation_kind: contains   # free text
```

## Anchoring: use names, not ids

`edition:` and `translator:` are **natural keys** — they match
`editions.name` and `translations.translator_name`, and the importer
resolves them to ids at import time.

Do not anchor on `edition_id:` / `id:`. Those are surrogate keys handed
out by insertion order, and `minerva index --reset` reshuffles them: the
one spec in this directory used to say `edition_id: 58`, which by the
time anyone tried to re-import it named Homer's Iliad (#193). A rotted
`edition_id` at least fails validation, because the importer cross-checks
the edition against the `work:` you named. A rotted translation `id:`
does not — nothing cross-checks it, so it imports silently as the wrong
translator's rendering.

The numeric forms are still accepted, for rows a name genuinely cannot
separate. Give exactly one of the two per anchor; supplying both is an
error rather than a precedence rule.

Two disambiguators, needed only when a name is not unique:

- `edition_year:` — `editions` is UNIQUE (work_id, name, year), so one
  name can repeat across years.
- `translator:`'s sibling keys `work:` and `year:` — one translator
  often renders several works for the same author (H. Rackham covers
  three in the Aristotle corpus). Resolution searches the apply_to
  entry's work first, then falls back to author-wide, which is what
  finds translations that ingest filed under their own `works` row
  (work "Phenomenology of Spirit (Pinkard)" beside "Phänomenologie des
  Geistes"). An ambiguous match is reported with its candidates, never
  guessed.

## Matching strategy

| Language | Default                        | Backend                  | When to override with `search_forms:`              |
| -------- | ------------------------------ | ------------------------ | -------------------------------------------------- |
| `deu`    | Lemma cache via `chunk_lemmas` | spaCy `de_core_news_sm`  | Separable-prefix verbs (`aufheben` → `hebt … auf`) |
| `grc`    | Lemma cache via `chunk_lemmas` | Stanza `grc` (PROIEL)    | All-caps chapter openers like `ὉΜΩΝΥΜΑ` (the lemmatizer leaves capitals unchanged), or rare inflections Stanza misclassifies |

When a term defines `search_forms:`, the importer skips the lemma
cache for that term entirely and uses the listed surface strings.
Drop `search_forms:` to switch back to lemma-cache matching.

Both languages require the lemmatizer cache to be populated first:

```bash
uv run minerva terms lemmatize --lang grc           # Aristotle + Plato
uv run minerva terms lemmatize --lang deu           # Hegel + Kant
```

Or scope to a single edition via `--edition-id N`.

## Idempotency

Importing the same spec twice is safe: each occurrence is keyed on
`(term_id, source_chunk_id, source_start, source_end,
source_form_snapshot)` and a duplicate is silently skipped. Renderings
and term rows are upserted, so editing the YAML and re-importing
updates the existing rows in place.

## Cross-author term identity

Plato's ψυχή and Aristotle's ψυχή live in *separate* `terms` rows
right now — one per (source_form, source_language, AUTHOR-scoped
spec file). The schema supports linking them via `term_relations` if
that distinction matters later, but the importer doesn't auto-link.
