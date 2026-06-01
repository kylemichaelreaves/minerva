# Term-glossary YAML specs

One YAML file per author per language. The curator authors a file
here; `poietes terms import` reads it and populates `terms`,
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
uv run poietes terms lemmatize --lang deu --edition-id 84

# 2. Edit the author's YAML. Add a new term entry, or extend an
#    existing term's `apply_to:` with the new work + edition.

# 3. Dry-run to see counts.
uv run poietes terms import data/glossary/hegel.deu.yaml \
    --dry-run --only-work "Phänomenologie des Geistes"

# 4. Commit.
uv run poietes terms import data/glossary/hegel.deu.yaml

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
        edition_id: 84
        translations:
          - id: 89                # Pinkard
            rendering: spirit
            note: optional translator note (markdown)
          - id: 90                # Inwood
            rendering: spirit
      # A term in multiple works repeats only the apply_to entries —
      # the term metadata above stays authoritative.

    related:
      - lemma: Bewusstsein
        relation_kind: contains   # free text
```

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
uv run poietes terms lemmatize --lang grc           # Aristotle + Plato
uv run poietes terms lemmatize --lang deu           # Hegel + Kant
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
