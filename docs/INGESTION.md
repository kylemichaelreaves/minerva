# Adding an author to the minerva corpus

End-to-end checklist for ingesting a new author and making them usable
in **retrieval, chat, and the Reader** — not just present in
`index.sqlite`. Each step has known patterns to mirror from existing
authors (Plato, Aristotle, Augustine, Aquinas, Descartes, Spinoza,
Kant, Hegel, Hobbes, Marx, Nietzsche, Cicero, …). Skim the generic
process first, then jump to the author-specific notes at the bottom.

**There is no model training step.** Minerva is retrieval-grounded RAG:
after ingest you run `index` (+ optional `embed`). The LLM is not
fine-tuned on new text. If chat “doesn't know” an ingested author, the
bug is almost always retrieval config (especially `--lang`), missing
`AUTHOR_KEYWORDS`, or stale prompts — see **§14**.

Visual checklist: [Author Ingest Wave (FigJam)](https://www.figma.com/board/uaeZ5hqmEClhmBQf4Gv0xA).
Operator rules: [`MEMORY.md`](MEMORY.md).

## What "an ingest" means — the required steps at a glance

A new author is not ingested until **every** step below has run. Cross-
reference rules and the verification passes are not follow-up work —
they're inside the ingest. Skipping them produces a corpus island.

| # | Step | Owner |
|---|------|-------|
| 0 | `scripts/snapshot-db.sh pre-<author>-ingest` | §Pre-flight |
| 1 | Downloader (`perseus/download_<author>_<lang>.py`) | §1 |
| 2 | Citation system (`paragraph` unless author-specific scheme) | §2 |
| 3 | Works module (`<author>_works.py`) if needed | §3 |
| 4 | Parser registration in `ingest/registry.py` | §4 |
| 5 | Author manifest + codegen (`data/authors/manifest.yaml`) | §5 |
| 6 | Run `minerva ingest && minerva index && minerva embed` | §6 |
| 7 | Re-run `minerva terms lemmatize` per affected language | §7 |
| 8 | Update `AUTHOR_ORDINAL` + restart backend | §8 |
| 9 | **Write `refs/rules/<author>.py` (outgoing)** | §9 |
| 9b | **Bidirectional audit — update existing rules to target the new author** | §9b |
| 9c | **`refs build --strategy rules`, then `embed-verify`, then `llm-verify`** | §9c |
| 14 | Verify chat retrieval surfaces the new author | §14 |

Steps 9 / 9b / 9c are bold because they're the ones most commonly
skipped, and they're the ones whose absence is hardest to detect — the
new author works in Reader and Concordance fine, but the cross-
reference graph is silently broken. The MEMORY entries
[`refs_rules_mandatory_for_new_authors`](MEMORY.md), [`refs_rules_bidirectional_audit`](MEMORY.md),
and [`refs_verify_required`](MEMORY.md) exist because each of those
gaps caused a regression caught later.

## Pre-flight

```sh
scripts/snapshot-db.sh pre-<author>-ingest
```

Snapshots the live DB to `data/snapshots/<timestamp>-pre-<author>-ingest/`.
Every step below mutates `data/index.sqlite`; if anything goes wrong,
the snapshot is a one-`cp` recovery point. See [`MEMORY.md`](MEMORY.md#snapshot-before-destructive-ops)
for the workflow rule that makes this binding.

Identify the canonical source — usually a TEI XML edition (Perseus,
First1KGreek), a scholarly HTML edition (zeno.org, corpusthomisticum,
la.wikisource), or a structured plain-text edition (SBLGNT, Project
Gutenberg). Note the citation convention the source uses (Stephanus
letters, Bekker numbers, book:chapter:verse, KrV A/B-page, etc.).

## 1. Downloader

File: `perseus/download_<author>_<lang>.py`

Per-author script that fetches raw text from the canonical source and
writes to `data/<author>/raw_<lang>/`. Two well-tested patterns:

- **Perseus TEI XML.** Mirror `perseus/download_perseus_aristotle.py`.
  The harvester walks each work's TEI structure (`<div type="textpart">`
  etc.) emitting the section/book metadata the splitter needs. Greek
  authors with Perseus coverage (Plato, Aristotle, Plutarch, Homer,
  the LXX, the NT) all go this route.
- **HTML scholarly edition.** Mirror `perseus/download_kant_de.py`
  (zeno.org) or `perseus/download_aquinas.py` (corpusthomisticum). Each
  source has its own structural anchors and citation-prefix conventions;
  the downloader emits a flat `.txt` file with bracketed section
  markers (e.g. `[ST.1.84.7]` for Summa Theologiae I, q. 84, a. 7) for
  the splitter to consume.

Retry-with-backoff on transient network errors is mandatory — every
existing downloader has it. Polite inter-request delay (~1s) keeps
academic sources happy.

New downloaders should import from `perseus/_download.py` instead of
hand-rolling the retry / sleep / UA boilerplate:

```python
from _download import RateLimiter, fetch_parallel, fetch_with_retry

def fetch(url):
    return fetch_with_retry(url, encoding="iso-8859-1")  # or utf-8
```

The shared module exports `USER_AGENT`, `fetch_with_retry`,
`RateLimiter` (per-host token bucket), and `fetch_parallel`
(threaded). For BFS-style crawlers (Kant, Hegel), a `--jobs N` flag
that batches each BFS level through `fetch_parallel(... limiter=
RateLimiter(min_interval=delay))` gives a real speedup without
exceeding the source's good-graces rate. Cap at 2-3 jobs for
zeno.org; archive.org / Gallica tolerate more.

## 2. Citation system (migration if novel)

File: `src/minerva/migrations/00NN_<author>_citation_system.py`

The `works.citation_system` column is `CHECK`-constrained to a finite
set. Currently valid: `stephanus`, `bekker`, `kant_ab`, `sz_marginal`,
`paragraph`, `augustine`, `aquinas`. If your author's citation
convention is well-served by one of these (most are), skip this step
and just set `citation_system='paragraph'` or whichever fits.

Add a new value only when:

- The locator format is genuinely novel (e.g., book:chapter:verse is
  not modeled today — needs `bcv` or similar).
- A `locations.py` validator would be useful for downstream tooling.

Pattern: mirror `0010_augustine_citation_system.py` or
`0011_aquinas_citation_system.py`. The PRAGMA dance
(`foreign_keys=OFF` + `legacy_alter_table=ON`) is required because
the `chunks_full` view blocks the rename.

After writing the migration, run `minerva index` once to apply it —
or just wait, since it runs automatically on the next index pass.

## 3. Works module

File: `src/minerva/authors/<author>_works.py` (top-level `minerva.<author>_works` shims remain for compatibility)

A tuple of `Work(...)` records, one per ingested work. Each record
binds:

| field | what it is |
|---|---|
| `code` | snake_case slug (becomes filename + chunk-id input) |
| `title` | display title (matches `reference_targets.canonical_work`) |
| `translator` | translator name; `"(Original)"` for source-language editions |
| `edition_year` | year string |
| `filenames` | tuple of source files to ingest (the splitter consumes these) |
| `fmt` | `"txt"` / `"xml"` / `"html"` etc. — tells the splitter the format |
| `locator` | the splitter name (see step 4) |
| `lang` | ISO 639-3 (`grc`, `lat`, `eng`, `deu`, `fra`) |
| `corpus` | author slug for filtering (`plato`, `aquinas`, `nietzsche`) |
| `author` | display author name (matches `reference_targets.canonical_author`) |
| `citation_system` | one of the values from step 2 |

Then add a `find_work(filename: str) -> Work | None` helper so the
ingest router can dispatch by filename. Mirror any existing
`<author>_works.py`.

## 4. Splitter

File: `src/minerva/corpus/split_<author>.py` — **only if a new
format**.

The splitter parses raw text into `Chunk` objects (the DB row shape).
Reuse an existing splitter if its `locator` value already matches your
format:

- `perseus_xml` — TEI XML with `<div>` section structure (Plato,
  Aristotle, and reusable for Homer/LXX/NT if Perseus-hosted).
- `kant_zeno` — zeno.org's HTML scaffolding (reusable for Nietzsche).
- `aquinas` — Corpus Thomisticum's `[NNNN] <citation>` anchors
  (reusable for opuscula).
- `augustine` — la.wikisource's `[Lib.Cap.Para]` markers.
- `hegel`, `spinoza_la`, etc. — author-specific.

New splitters mirror the body of any existing one. Key invariants:

- One `Chunk` per natural reader unit (verse / paragraph / article /
  lectio). Granularity decisions matter for retrieval recall; err
  smaller.
- `chunk_id` is **content-derived** via `_make_chunk_id(...)`. This is
  load-bearing — the re-ingest rebind in `store.py` only works
  because chunk_ids are stable across re-ingest as long as the
  source text doesn't change.
- Emit `section` (the user-visible citation locator: "Gen 1:1", "Il.
  1.1", "JGB §43") and `book` (the major-division grouping for the
  reader index: "Genesis", "Iliad", "Jenseits von Gut und Böse").

## 4b. Ingest registry

File: [`src/minerva/ingest/registry.py`](../src/minerva/ingest/registry.py)

Add an `IngestSource(...)` entry (id, default path, parser factory). The
registry is the router for `minerva ingest`; CLI flags are derived from
each source's `argparse_flag` / `kwarg_name`. Run
`scripts/check_author_ingest.py --corpus <id>` after wiring.

## 5. Author manifest (metadata)

File: [`data/authors/manifest.yaml`](../data/authors/manifest.yaml)

Single source of truth for:

- `corpus_registry.CORPORA` (slug, lang, citation system, dominant glyph, chat keywords)
- `author_ordering.AUTHOR_ORDINAL` (sidebar chronological order)
- `web/src/Landing/atlasData.ts` `ATLAS_AUTHORS` (landing timeline)

After adding or editing an author entry:

```sh
make generate-authors    # write marked regions in the three targets
make check-authors       # codegen --check + ingest wiring validator
```

Run `pytest tests/test_author_manifest_sync.py` if you change ordinals or
corpus slugs. Optional `rules_module` in the manifest overrides the default
`author.lower().replace(" ", "_")` mapping for xref rule files.

## 6. Run the pipeline

```sh
.venv/bin/minerva ingest    # writes data/chunks.jsonl
.venv/bin/minerva index     # writes index.sqlite; auto-snapshots, rebinds xrefs
.venv/bin/minerva embed --lang any   # computes embeddings for new chunks only
```

The auto-snapshot in `cmd_index` is a fallback; the manual snapshot
from step 0 is the primary recovery point. `embed` skips chunks that
already have an embedding row under the same `--model`, so re-running
it just fills in the new ones (~10s/1000 new chunks on M-series). Pass
`--all` to force a full re-encode — necessary after switching models
or recovering from a corrupted `embeddings` table.

The auto-snapshot also preserves `chunk_lemmas` across `index --reset`:
chunk_ids are content-hashed, so a content-stable re-ingest restores
every lemma keyed by the surviving chunk_id and skips re-lemmatization
entirely (saving ~10 minutes of grc+lat LatinCy work per reingest). The
orphan sweep in `cmd_index` drops lemma rows whose chunk_id changed,
preserving FK integrity. Only chunks whose text actually changed need
re-lemmatizing.

### When to use full vs partial reingest

| Situation | Command |
|-----------|---------|
| Parser/schema change affecting many sources | `make reingest` (full `ingest` + `index --reset`) |
| One corpus / source id while iterating | `make reingest-only ONLY=<id>` |
| Fresh machine / corrupted index | `minerva index --reset` after full `ingest` |

### Parser-development cycle

When iterating on one corpus's parser (e.g. fixing a `tei_p5` bug for
Origen), use the partial-ingest + incremental-index path so the other
~40 corpora don't get re-parsed or re-indexed every loop:

```sh
# Manual two-step
.venv/bin/minerva ingest --only origen_grc,origen_eng --timing
.venv/bin/minerva index --incremental --from-ingest-only --timing

# Or use the wrapper:
make reingest-only ONLY=origen_grc,origen_eng
```

`--only` re-parses just the named sources; their chunks REPLACE every
existing row for the same corpus in `chunks.jsonl` (corpus-level — not
chunk-id-keyed, because content-hashed chunk_ids change when text is
cleaned and chunk-id overlay would leave stale rows orphaned).
`--incremental --from-ingest-only` reads `meta.ingest.only` (written by
the prior `ingest --only` run) and re-indexes just those corpora —
~10× faster than `index --reset` for a single-corpus edit (1.5s vs 16s
on theognis). Every other corpus's chunks, lemmas, embeddings, and
cross-references are preserved.

`--timing` prints per-source and per-stage wall times to stderr, and
persists the overall ingest/index/embed durations to `meta.timing.*`.
Inspect via `minerva stats` — the `timing` block in the JSON output
shows the last-run wall time per stage. Valid source ids are listed
when an unknown id is passed; they're also the keys of the
`IngestSource` entries in `src/minerva/ingest/registry.py`.

### Parallel ingest

`--jobs N` parallelizes per-source parsing across N worker processes.
Each worker re-imports the registry and parses one source, writing a
shard JSONL; the orchestrator merges shards in registry order so the
final `chunks.jsonl` is byte-identical to `--jobs 1`. Measured on
the full 344K-chunk corpus: **54s → 28s with `--jobs 4`** (~1.9×).

```sh
.venv/bin/minerva ingest --jobs 4 --timing       # full ingest
.venv/bin/minerva ingest --jobs 4 --only hegel,kant --timing   # partial
```

PDF-heavy sources (Hegel/Kant) hold the most RAM per worker; start
with `--jobs 4` on a 16 GB machine and scale up cautiously. Worker
failures are isolated — a bad parser logs to stderr and the run
continues; re-run with `--only <bad_source>` after fixing.

### LLM-verify resume

`refs build --strategy llm-verify` is naturally idempotent: its
candidate query excludes `source_method LIKE '%llm%'`, so already-
verified rows are skipped on a plain re-run.

For a faster resume after `--max-llm-calls` is exhausted, pass
`--resume`: it reads `meta.refs.llm_verify.last_row_id` (written
after every committed batch) and adds `WHERE xr.id > <last>` to
the eligible-rows query, so the verifier skips straight to the
tail instead of re-scanning the filtered candidate set. An
interrupted run wastes at most one batch's worth of rows.

```sh
.venv/bin/minerva refs build --strategy llm-verify --resume \
    --llm-backend anthropic --max-llm-calls 700
```

**Indexing alone does not make the author chat-ready.** Before you
treat the ingest as done, complete **§14 (Chat & retrieval
integration)** and the chat smoke tests in **§13**.

## 7. Lemmatization (Greek and modern languages)

Only needed for the term-glossary word-click feature in the reader.
Install the `[lemma]` extras (`uv pip install -e '.[lemma]'`) — that
pulls LatinCy spaCy wheels for `grc`/`lat` plus `de_core_news_sm` /
`fr_core_news_sm` / `en_core_web_sm`. Stanza remains as fallback for
Greek/Latin when LatinCy is missing, and as the primary backend for
`heb` / `ara`.

```sh
.venv/bin/minerva terms lemmatize --lang grc --n-process 4
.venv/bin/minerva terms lemmatize --lang lat --n-process 4
.venv/bin/minerva terms lemmatize --lang deu --n-process 4
.venv/bin/minerva terms lemmatize --lang fra
```

The CLI prints `lemmatize: backend=spacy model=grc_dep_web_sm` (or
`backend=stanza`) on startup so you can confirm LatinCy loaded.
`--n-process` applies to spaCy backends only; it is ignored on Stanza
paths.

This populates `chunk_lemmas`, which the `/api/words/lookup` endpoint
queries when the user clicks a word. A content-stable
`make reingest-only` preserves existing lemma rows for unchanged
chunk_ids (see the parser-development cycle above); only re-run
lemmatize for languages where chunk text actually changed.

## 8. Reader sidebar author order

Edit the new author's `ordinal` (and optional `year` / atlas fields) in
[`data/authors/manifest.yaml`](../data/authors/manifest.yaml), then
`make generate-authors`. The generated `AUTHOR_ORDINAL` block in
[`author_ordering.py`](../src/minerva/author_ordering.py) drives the Read
tab and `/api/works` list (not an alphabetical fallback in the frontend).
Insert the new author chronologically by lifespan. Approximate dates
for each existing entry:

```
Plato        428–348 BC
Aristotle    384–322 BC
Septuagint   3rd c. BC (compilation)
Homer        8th c. BC (composition)
New Testament 1st c. AD (compilation)
Vulgate      ~400 AD (Jerome's translation)
Augustine    354–430 AD
Aquinas      1225–1274
Descartes    1596–1650
Spinoza      1632–1677
Kant         1724–1804
Hegel        1770–1831
Nietzsche    1844–1900
```

Authors not in `AUTHOR_ORDINAL` sort to the end (`DEFAULT_AUTHOR_ORDINAL`);
always add the entry. Run `pytest tests/test_author_ordering.py` if
you renumber ordinals.

Within an author / work, `LANG_ORDINAL` orders editions: Greek → Latin →
German → French → English. **`heb` and `ara` are not in `LANG_ORDINAL`**
today — they fall through to `DEFAULT_LANG_ORDINAL` and sort last within
a work. A code change is needed if Hebrew MT / Quran editions should sit
ahead of translations.

## 9. Cross-reference rules (required)

Files: `src/minerva/refs/rules/specs/<author>.yaml` (mention-only) or
`src/minerva/refs/rules/<author>.py` (structural / locator rules).

**This step is not optional.** Every new-author ingest must ship at
least Phase 1 rules covering the author's principal interlocutors
(typically ≥3 named authors they engage with most heavily). Without
rules per author, the new corpus shows up as an island disconnected
from the rest — and the cross-references are what make a multi-author
minerva corpus thread together (Plato citing earlier figures, Aquinas
citing Aristotle / Augustine, Hobbes citing Aristotle / "the
schoolmen" / Cicero). Ship rules in the same round, not as a
follow-up.

For authors who only need name-mention rules, add
`refs/rules/specs/<module>.yaml` (see `gobineau.yaml`, `renan.yaml`).
The loader also attaches scripture-cite rules for 19th-c. philosophers.
Mirror `aquinas.py` for a heavy structural author or `hegel.py` for a
modern philosopher who engages predecessors by name. Two rule
classes available:

- `AuthorMentionRule` — fires on configured surface forms. Weak by
  default (`source_method='rule_weak'`, confidence ~0.4–0.7). For
  each name the author mentions, list every declension/inflection.
  Latin/Greek require oblique cases (Plato/Platonis/Platonem/Platone);
  German requires adjective forms (Kantisch/Kantischen).
- `StrongMentionRule` — same shape, defaults to `rule_strong` /
  confidence 0.95. Use only for unambiguous corpus-internal
  conventions: Aquinas's "Philosophus" = Aristotle; Spinoza's
  "Cartesius" = Descartes. Not every "frequently cited" relationship
  qualifies — the convention has to be definitionally consistent.
- Structural commentary rules (custom dataclass mirroring
  `aquinas.py`'s `StructuralCommentaryRule`) — for cases where a
  work IS a commentary on another (Aquinas-on-Aristotle pattern).

After writing rules, register the module by import — the runner
auto-discovers any `src/minerva/refs/rules/<author>.py` whose name
lowercase-matches the chunk's author.

### 9b. Bidirectional rule audit (also required)

Step 9 only covers OUTGOING references (mentions of older authors
inside the NEW author's text). The reverse — existing later-in-time
authors whose rules need a new entry for the NEW author — must be
audited explicitly, or those incoming cross-references silently
never get created.

Example: when Hobbes (1588–1679) was added, every existing author
in the corpus who lived after Hobbes (Spinoza, Locke, Hume, Kant,
Hegel, Marx, Nietzsche) is a candidate for an
`X→Hobbes` rule in `refs/rules/x.py`. Without this step, Hegel's
`Lectures on the History of Philosophy` Vol III chunks contain
"Hobbes" but produce 0 cross-references to him.

**Audit procedure** for every new author N:

```bash
# 1. Identify candidate sources — authors with AUTHOR_ORDINAL > N's.
#    Concretely: every author whose lifetime overlaps or post-dates N.

# 2. For each candidate X, check whether their rules already target N.
grep -l "target_author=\"$N\"" src/minerva/refs/rules/x.py

# 3. If not, grep X's chunks for N's name (case-sensitive on the
#    proper noun to avoid common-noun collisions):
sqlite3 data/index.sqlite \
  "SELECT COUNT(*) FROM chunks_full WHERE author='X' AND text GLOB '*$N*'"

# 4. If the count is > 0 and inspection confirms scholarly mentions,
#    add a rule to refs/rules/x.py with the appropriate surface forms
#    (German declined: Hobbessche/Hobbesschen; Latin oblique:
#    Hobbesius/Hobbesii; English: Hobbes/Hobbesian/Hobbist).

# 5. Re-run `minerva refs build` to materialize the new xrefs.
#    Incremental — only new candidate rows land.
```

When this audit is skipped (it was, repeatedly, through the early-
modern rounds), the corpus has dozens-to-hundreds of latent
cross-references waiting to exist. The Marx+Nietzsche followup
round produced 468 new xrefs by running this audit retroactively
across 6 rule modules.

### 9c. Verification stages (also required)

The `rules` strategy produces `rule_weak` and `rule_strong` rows.
These are unverified — they're the regex match dump, not yet
sanity-checked semantically. Two further stages clean the graph
up; **both are required** as part of every new-author ingest,
not optional.

The rules pass keeps a `refs_scan_state(chunk_id, text_hash)`
cache: chunks whose current `sha1(text)` matches a prior scan are
skipped (the rule output would be identical and get deduped
anyway). Pass `--rescan-all` after editing a rules module so the
previously-unmatched chunks get a fresh pass — the cache is a
content-hash skip, not a "this chunk has been seen" skip, so it
can't catch new rules matching old text.

```sh
.venv/bin/minerva refs build --strategy rules --rescan-all
```

**Stage 1 — embed-verify (free, local)**:

```bash
uv run minerva refs build --strategy embed-verify
```

Uses the sentence-transformer embeddings (already computed via
`minerva embed`) to do two sweeps:

* **Pass A (quoted-phrase verifier)** — for any candidate whose
  source text contains a quoted phrase, compares the phrase's
  embedding against candidate target chunks. Promotes high-cosine
  matches to `source_method='rule+embed'`, rejects low-cosine ones
  to `curator_status='rejected'`.
* **Pass B (allusion sweep)** — for each source chunk, finds
  embedding-similar target-author chunks and emits new `alludes`
  rows (`source_method='embed_only'`). Surfaces relationships
  the regex rules missed entirely.

Cost: zero API calls. Wall time: 1-5 min on the standard machine.

**Stage 2 — llm-verify (Anthropic / OpenAI)**:

```bash
uv run minerva refs build --strategy llm-verify \
    --llm-backend anthropic --llm-model claude-sonnet-4-6 \
    --max-llm-calls 700  # bump if many candidates
```

LLM judges batches of candidates (default 10/call) and writes the
verdict to `source_method='rule+embed+llm'` for kept rows,
`curator_status='rejected'` for dismissed ones.

Cost: roughly $0.01–0.05 per LLM call on Sonnet → $5–30 for a
typical post-ingest run of a single author. Cap via `--max-llm-calls`.

**Verification coverage audit** — periodically check which authors
have escaped verification:

```bash
sqlite3 data/index.sqlite "
SELECT w.author, xr.source_method, COUNT(*) FROM cross_references xr
JOIN chunks c ON c.chunk_id = xr.source_chunk_id
JOIN editions e ON e.id = c.edition_id
JOIN works w ON w.id = e.work_id
GROUP BY w.author, xr.source_method
ORDER BY w.author, 3 DESC"
```

Look for any author whose rows are all `rule_weak` / `rule_strong`
with no `rule+embed+llm`. That's the verification gap. Any new
author or any old author whose corpus has been re-ingested needs
both stages run.

## 10. Reference-targets seed

The `reference_targets` table seeds canonical out-of-corpus authors
in migration 0012 (Cicero, Plotinus, Vergil, Boethius, Avicenna,
Averroes, Maimonides, Ambrose, Porphyry). When your new author cites
figures NOT in that seed, two options:

- **Lazy** (preferred for most cases): `ensure_target` auto-creates a
  `reference_targets` row on first use. Fine for one-off citations.
- **Eager seed**: add a YAML file under `data/glossary/refs/` whose
  rows pre-create the targets. Better when many references point at
  the same out-of-corpus figure (Nietzsche → Schopenhauer is the
  archetype — every JGB passage would resolve faster with a
  pre-seeded target).

## 11. Hand-curated YAML seed

File: `data/glossary/refs/<author>.yaml`

5–10 canonical references the author scholar would say "must be
in the index." These become `curator_status='manual'` rows with
hand-written `curator_note` per row. Load via
`minerva refs load-spec data/glossary/refs/<author>.yaml`.

Format:

```yaml
- source:
    work: "Jenseits von Gut und Böse"
    section: "§11"
  target:
    author: Kant
    work: "Critique of Pure Reason"
  type: disputes
  note: "Nietzsche's critique of the synthetic-a-priori — the joke about Kant's 'faculty of faculties'."
```

This is also the only path that preserves your data through a
re-ingest (the LLM-verified auto rows are also preserved by the
shadow-address rebind in `store.py`, but manual YAML rows are
authoritative source-of-truth in git).

## 12. Run the detection pipeline

```sh
scripts/snapshot-db.sh pre-<author>-refs

.venv/bin/minerva refs build --strategy rules --source-author <NewAuthor>
.venv/bin/minerva refs build --strategy embed-verify
.venv/bin/minerva refs build --strategy llm-verify \
    --llm-backend anthropic --llm-model claude-sonnet-4-6 \
    --batch-size 20 --max-llm-calls 500
```

- `--source-author` filters the rules pass to only the new author —
  existing authors aren't re-scanned.
- embed-verify runs across the whole corpus so the new chunks find
  allusion partners in existing texts too.
- llm-verify is idempotent (skips rows whose `source_method` already
  contains `llm`), so only the new auto rows hit the LLM.

Cost guide at Sonnet 4.6 pricing (~$3/M input, $15/M output, prompt
caching on the system message):

| Author character | Approx new auto rows | LLM cost |
|---|---|---|
| Moderate Greek author (1 major work) | 500–1,500 | $2–5 |
| Heavy philosopher (Nietzsche) | 3,000–5,000 | $8–15 |
| Biblical corpus (LXX + Vulgate + NT) | 8,000–15,000 | $25–45 |

## 13. Verify

- Reader: open one of the new author's works. Confirm gutter markers
  on chunks the rules flagged. Click a marker → ReferenceCard opens →
  click "Open in reader →" → lands in the target work.
- /refs: filter source=NewAuthor. Sample 10 rows.
- /refs/review: triage the lowest-confidence auto rows; reject the
  noise, approve the clear hits.
- **Chat (required):** see §14 smoke tests — retrieval-only first,
  then one LLM turn if you use `serve` with a backend.

## 14. Chat & retrieval integration (required)

Ingest + index puts text in SQLite. The **chat agent** only sees what
retrieval returns under the current `serve` flags and what the system
prompt allows it to cite. This section was missing from early ingests
(e.g. Nietzsche indexed but invisible in chat because of `--lang eng`
and stale prompts). Treat it as mandatory, not polish.

### 14a. Corpus metadata (if new `corpus` slug)

File: `src/minerva/migrations/runtime_helpers.py`

When you introduce a new `Work.corpus` slug, add defaults if missing:

| map | purpose |
|-----|---------|
| `_CITATION_SYSTEM_BY_CORPUS` | default `works.citation_system` on first insert |
| `_ORIGINAL_LANG_BY_CORPUS` | original-language hint (`grc`, `lat`, `deu`, …) |

Mirror an author with the same citation shape (most modern prose →
`paragraph`). Biblical / surah-structured corpora have their own
entries already.

### 14b. Chat corpus auto-detection

File: `data/authors/manifest.yaml` — the corpus's `keywords:` list.
`AUTHOR_KEYWORDS` in `src/minerva/corpus_registry.py` is **generated**
from it; edit the manifest and run `make generate-authors`.

Maps **single-word** query tokens to `chunks_full.corpus` for
`detect_corpus()` (used by `/api/chat` when no corpus flag is set).
Add, for each author:

- the name, and common adjective forms — `nietzsche`, `nietzschean`;
- the name in **every language a reader is likely to ask in** —
  `platon` (de/fr), `aristote` (fr), `lukrez` (de), `epiktet` (de);
- the **German genitive**. English possessives need no entry, because
  `Plato's` tokenizes to `{plato, s}` and the bare name matches — but
  `Platons` is a single token, so without `platons` every German-phrased
  question misses its corpus outright (#169).

Multi-word keywords ("contra celsum", "vie de jésus") are matched as
phrases since #173, tolerant of case and of whatever separates the
words. Before that they were silently dead — `detect_corpus` looks up
one token at a time, and no token contains a space.

**Limits:** comparative queries ("Plato vs Aristotle") intentionally
return `None` (broad retrieval); a keyword that is also the title of
*another* corpus's work ("Plato's Phaedrus") does not, since #170 —
that case is resolved against the index rather than refused.

### 14b-bis. Corpus authors (required when the id isn't the author)

Retrieval filters on `LOWER(works.author)` — that is literally what the
`chunks_full.corpus` column is — while the CLI, `detect_corpus` and this
manifest all speak in corpus **ids**. When the two differ, declare the
mapping:

```yaml
- id: marcus_aurelius
  authors:
  - Marcus Aurelius
```

Omit `authors:` and the id is used as the author name, which is correct
for the 33 corpora named after their author. For the other seven it was
not, and the filter matched *nothing*: naming Marcus Aurelius or the
Torah in chat scoped retrieval to zero chunks and the agent abstained,
across 126,480 chunks — 30% of the corpus (#174).

`presocratic` shows why this is a list rather than a rename: one corpus,
nine authors.

`scripts/check_author_ingest.py` now fails when a `works.author` belongs
to no corpus, or a declared author matches no work — so the next corpus
whose id isn't its author name is caught at ingest instead of going
quietly dark.

Add a row in `tests/test_agent.py` under `test_detect_corpus_*`.

**Work detection.** Once the corpus is resolved, `detect_work` narrows to a
work named in the query, matching `works.title` and the per-language
`title_local` values. A title whose only significant token is an ordinary
word (`Laws`, `Lovers`, `Acts`, `Der Staat`) is trusted only when the query
capitalises it, so that running prose does not silently scope to it (#168).
That list is measured from the index, not hand-written — if the ingest added
works, regenerate it:

```bash
uv run python scripts/derive_common_title_tokens.py   # paste over
                                # _COMMON_TITLE_TOKENS in agent/detect.py
```

A token the list omits is trusted, so skipping this over-scopes rather than
breaking detection — but do it, or the next author's *Politics* is a
retrieval trap.

**Audit:** after any bulk ingest, grep ingested `corpus=` slugs against
`AUTHOR_KEYWORDS` values — several modern authors were added to the
index before this map was kept in sync.

### 14c. LLM prompts (keep generic)

File: `src/minerva/agent.py`

- `_SYSTEM_PROMPT_TEMPLATE` — must **not** hard-code a short author list
  (e.g. "Plato, Aristotle, Hegel, and Kant only"). The model obeys
  "use only &lt;PASSAGES&gt;"; if retrieval returns no chunks from the
  asked author, it may incorrectly claim the whole product excludes them.
- `REWRITE_PROMPT` — same: describe the corpus generically, not as four
  philosophers.

When you add authors, prefer updating keywords (§14b) over expanding a
fixed prompt list.

### 14d. Retrieval language default

File: `src/minerva/cli/_shared.py` — `--lang` defaults to **`any`**
(every language in the index). For a long time the default was
`eng`, which silently excluded German Nietzsche/Marx, Latin Cicero/
Spinoza/Augustine/Aquinas/Vulgate/Hobbes-Latin, Greek primary texts,
and Hebrew MT from chat retrieval — the chat would answer "X is not
in the corpus" even though X's chunks were sitting in the index.
The May 2026 multilingual-chat-retrieval fix corrected this:

* **`src/minerva/cli/_shared.py`** — `RETRIEVAL_LANG_CHOICES`
  (`any | eng | grc | deu | lat | fra | heb | ara`) and
  `RETRIEVAL_CORPUS_CHOICES` (every key in
  `runtime_helpers._ORIGINAL_LANG_BY_CORPUS` + `any`) are the
  argparse choice lists. They auto-extend when new corpora land in
  the runtime map — no more 8-author tuple to forget to update.
* **`Makefile`** — `LANG ?= any` and `make run` / `make start`
  pass `--lang $(LANG)` to `minerva serve`. Override for English-
  only experiments: `make run LANG=eng`.

```sh
# Default (any) — finds everything
.venv/bin/minerva serve

# Narrow to one language
.venv/bin/minerva serve --lang deu

# Smoke-test retrieval per language tier
.venv/bin/minerva ask --llm none --lang deu --corpus nietzsche "Mißratenen"
.venv/bin/minerva ask --llm none --lang lat --corpus cicero "res publica"
.venv/bin/minerva ask --llm none --lang grc --corpus plato "δικαιοσύνη"
.venv/bin/minerva ask --llm none --lang any "Nietzsche Genealogie"
```

If you add a new author, also add their slug to
`runtime_helpers._ORIGINAL_LANG_BY_CORPUS` (corpus → ISO 639-3
original language). The CLI choice list reads from there, so an
omission silently rejects `--corpus <slug>` at argparse time even
though the chunks exist in the index. This was the root cause of
the multilingual-chat-retrieval bug for `nietzsche`, `marx`,
`cicero`, `hume`, `locke`, `pascal`, `rousseau`, and `hebrew_mt`
(all of which had chunks but no map entry).

Hybrid search: run `embed --lang any` after index (step 6) if you
use `--use-vectors`.

**Known follow-ups (out of scope for the lang/corpus fix):**

* **FTS5 + Hebrew niqqud / Greek polytonic.** The default
  `tokenize='unicode61'` makes niqqud and te'amim part of the
  token, so a query without diacritics doesn't match indexed text
  with them. `tokenize='unicode61 remove_diacritics 2'` would help
  but needs evaluation — Greek accents disambiguate words too.
  Vector search bypasses this; lexical Hebrew/Greek queries today
  need the diacritics to match the indexed form.
* **Vector search at scale.** `retrieve._vector_search` hits
  SQLite's `too many SQL variables` limit on large indexes for some
  queries — pre-existing bug, surfaces on Hebrew Bible's 23k chunks.

### 14e. Optional UI / packaging touchpoints

| File | When to touch |
|------|----------------|
| `src/minerva/http/handlers/citations.py` — `_CORPUS_TO_DOMINANT` | Only if you want a new gutter glyph (Π/Α/Η/Κ today). Unknown corpora fall back to `P`. |
| `pyproject.toml` / `src/minerva/cli/__init__.py` | One-line project descriptions; cosmetic. |
| `src/minerva/eval_data/gold.jsonl` | If you maintain locator-eval coverage for the author. |
| `docs/dashboard_aggregates.json` | Regenerate via [`scripts/dashboard_aggregates.py`](../scripts/dashboard_aggregates.py) — see [`SCRIPTS.md`](SCRIPTS.md). |

### 14f. Smoke tests (chat-ready)

```sh
# 1. Author present in index
.venv/bin/minerva stats | grep -i "<Author>"

# 2. Retrieval hits (adjust --lang / --corpus)
.venv/bin/minerva ask --llm none --lang <orig-lang> --corpus <slug> "<typical phrase>"

# 3. Auto-detect scopes corpus when author name appears in query
.venv/bin/minerva ask --llm none --lang any "What does <Author> say about <topic>"

# 4. LLM turn (same flags as production serve)
.venv/bin/minerva ask --llm anthropic --lang any "<question>"
```

Pass criteria: step 2 returns chunks with correct locators; step 3's
top hits are mostly the target author; step 4 cites those passages and
does **not** claim the author is outside the corpus.

### 14g. Full touchpoint checklist (audit)

Use this when onboarding an author or auditing a bulk ingest:

| # | Area | File(s) |
|---|------|---------|
| 0 | Snapshot | `scripts/snapshot-db.sh` |
| 1 | Downloader | `perseus/download_<author>_*.py` |
| 2 | Citation migration | `migrations/00NN_*.py` (if novel) |
| 3 | Works table | `src/minerva/authors/<author>_works.py` |
| 4 | Splitter | `src/minerva/corpus/split_*.py` or reuse locator |
| 5 | Author manifest | `data/authors/manifest.yaml` → `make generate-authors` |
| 5b | Ingest registry | `ingest/registry.py` |
| 6 | Index + embed | `minerva ingest` / `index` / `embed` |
| 7 | Lemmatize | `minerva terms lemmatize --lang …` |
| 8 | Sidebar order | manifest `ordinal` → `author_ordering.py` |
| 9 | Outgoing xref rules | `refs/rules/specs/<author>.yaml` or `.py` |
| 9b | Incoming xref audit | other `refs/rules/*.py` |
| 10–12 | xref build / YAML / verify | `minerva refs …` |
| **14a** | Runtime corpus maps | `migrations/runtime_helpers.py` |
| **14b** | Chat keyword routing | `data/authors/manifest.yaml` `keywords:` |
| **14c** | Chat prompts | `agent.py` prompts |
| **14d** | Serve `--lang` | deploy / `Makefile` |
| 13 | Reader + refs + **chat** smoke | manual + commands above |

---

# Author-specific notes

Per-author ingest quirks and source choices. Corpus slugs and metadata
are authored in [`data/authors/manifest.yaml`](../data/authors/manifest.yaml)
and generated into [`corpus_registry.py`](../src/minerva/corpus_registry.py).

## Septuagint (Greek Old Testament)

**Status:** implemented (as of 2026-05).

- **Sources.** Perseus's First1KGreek hosts a Rahlfs-based LXX. SBL's
  STEPBible-Data on GitHub is an alternative (tagged, public-domain).
  Recommendation: **First1KGreek** if it covers your target books;
  it integrates cleanly with the existing `perseus_xml` splitter and
  the Greek lemmatizer already handles it.
- **Citation system.** Book:chapter:verse — novel for the corpus.
  Two options: (a) reuse `paragraph` and write the locator as a
  plain string like "Gen 1:1"; (b) add a new `bcv` value with a
  `locations.py` validator. Recommendation: **(a) for now**, upgrade
  to (b) later if cross-Bible queries need parsing.
- **Author / works.** Convention: `author="Septuagint"`, one Work
  per book (Genesis, Exodus, …, plus deuterocanonical). Sidebar
  position: between Aristotle and Augustine (3rd c. BC compilation).
- **Cross-references.** Heavy incoming traffic from Augustine,
  Aquinas, Aristotle (where Aristotle's not engaging Plato). Rules
  module would be sparse — the LXX cites its own internal references
  (the Pentateuch quotes itself) but mostly is a target, not a
  source. Skip writing `refs/rules/septuagint.py`; let the inbound
  rules from existing authors do the work.
- **Cost estimate.** ~30K chunks at one-verse-per-chunk granularity.
  Embeddings: ~5 min. LLM-verify: skipped (no source rules).

## Vulgate (Latin Bible — Old + New Testament)

**Status:** implemented (as of 2026-05).

- **Source.** vulsearch.sourceforge.net or unbound.biola.edu. The
  Clementine Vulgate is the standard for cross-reference work with
  Aquinas; the Stuttgart Vulgate (Weber-Gryson) is the
  modern-critical edition.
- **Citation system.** Same as Septuagint — book:chapter:verse.
- **Author / works.** `author="Vulgate"`, one Work per book. 73 books
  in the Catholic canon (including the deuterocanonicals Aquinas
  cites). Sidebar: between Aristotle/LXX and Augustine.
- **Cross-references.** Same posture as LXX — mostly a target.
  Aquinas → Vulgate will become the single largest cross-reference
  bucket once you ingest it; every ST/SCG question that quotes
  scripture (most of them) becomes a real link.
- **Important sequencing note.** After ingesting the Vulgate,
  re-run rules + LLM-verify on Aquinas so the scripture citations
  he makes ("ut dicit Apostolus", "Augustinus contra Iulianum, lib.
  IV") get bound to actual chunk targets. Otherwise his cites stay
  as work-or-section-level references.

## New Testament (Greek)

**Status:** implemented (as of 2026-05).

- **Source.** SBLGNT (Society of Biblical Literature Greek New
  Testament) on GitHub — public domain, USFM/XML formatted, used
  as the basis for many translations. Or Perseus's First1KGreek
  which has Tischendorf and other editions.
- **Citation system.** Same book:chapter:verse as the OTs.
- **Author / works.** `author="New Testament"` (or `"NT"`), one Work
  per book — 27 in the standard canon. Sidebar: after Aristotle and
  Septuagint, before Vulgate (1st c. AD composition).
- **Cross-references.** Outgoing references are minimal (the NT
  quotes the LXX heavily; Matthew alone has ~50 OT citations). A
  short `refs/rules/new_testament.py` could match common OT-quotation
  formulae (καθὼς γέγραπται, λέγει ὁ προφήτης, etc.) → target=Septuagint
  for embed-verify to localize. Incoming traffic from Augustine and
  Aquinas will dwarf this.

## Homer (Greek)

**Status:** implemented (as of 2026-05).

- **Source.** Perseus has Iliad + Odyssey in TEI XML with line-numbered
  text. The existing `perseus_xml` splitter handles this format.
- **Citation system.** Book.line (e.g., "Il. 1.1", "Od. 24.534").
  Closest existing fit: `paragraph` with the locator as a plain
  string. Alternatively add a `homer_book_line` value with a
  validator if you want clean book/line range queries.
- **Author / works.** `author="Homer"`, 2 works (`code=iliad`,
  `code=odyssey`). Sidebar: before Plato (8th c. BC composition).
- **Cross-references.** Plato cites Homer constantly (Republic,
  Ion). Aristotle in the Poetics. Augustine cites him via Cicero/
  Vergil. Once Homer is ingested, a rule sweep across existing
  authors (with `--source-author Plato` etc.) will bind those
  citations to chunk-level targets. **Heaviest pre-existing
  rule beneficiary:** Aristotle's Poetics chunks → Iliad book
  locations.
- **Outbound rules** for Homer himself: minimal. He's the source,
  not the citer.

## Early modern batch (Hobbes, Pascal, Hume, Locke, Rousseau)

**Status:** implemented (as of 2026-05).

Landed via `perseus/download_early_modern.py` + `*_works.py` tables.
All use the generic **`chapter`** splitter on Project Gutenberg plain
text — no new citation-system migration.

| Author   | Works ingested | Lang | PG IDs |
|----------|----------------|------|--------|
| Hobbes   | *Leviathan* (eng + lat), *De Cive* (eng + lat), *Human Nature* (eng), *De Corpore Politico* (eng) | eng, lat | 3207, 73906, 74236 + IA `leviathansivedem00hobb`, `gri_elementaphilos00ho` |
| Pascal   | *Pensées* | fra | 24499 |
| Hume     | *Enquiry*; *Treatise* | eng | 9662, 4705 |
| Locke    | *Essay*; *Second Treatise* | eng | 10615, 7370 |
| Rousseau | *Du contrat social* | fra | 4636 |

```sh
uv run python perseus/download_early_modern.py   # or --author hobbes
uv run python perseus/download_hobbes_la.py      # Hobbes Latin via IA OCR
.venv/bin/minerva ingest
.venv/bin/minerva index
.venv/bin/minerva embed --lang any   # optional
```

Cross-reference rule modules: `refs/rules/{hobbes,pascal,hume,locke,rousseau}.py`.
These are required (step 9) — they ship with the ingest, not as a
follow-up. Re-run `minerva refs build` on existing authors after
ingest so Kant/Spinoza mentions of Hume/Locke bind to chunk targets.

Hobbes Latin uses Internet Archive OCR (no clean Wikisource source)
and a dedicated state-machine parser (`src/minerva/hobbes_la.py`)
that detects CAPVT chapter headings in the 1668 Leviathan and
tracks page-running-head transitions in the 1642 De Cive.

## Nietzsche (German)

**Status:** implemented (as of 2026-05).

- **Source.** Two candidates:
  - **zeno.org** (recommended). Same HTML scaffolding as their Kant
    edition, so `download_kant_de.py` is the template — the
    structural anchors mostly match. Nietzsche's Werke, KSA-derived,
    public domain. Sections are §-numbered which slots straight
    into the `paragraph` citation system.
  - **nietzschesource.org / Digital Critical Edition (eKGWB)**. The
    academic gold standard but harder to scrape (JavaScript-rendered).
    Defer unless you specifically need critical apparatus.
- **Citation system.** `paragraph` — Nietzsche's §-numbered works
  (FW, JGB, GM, GD, EH, AC) read cleanly as `JGB §43`. The exceptions
  (GT, Z) use Roman-numeraled parts → still expressible as plain
  strings.
- **Author / works.** `author="Nietzsche"`. Recommended ingest set:
  GT (Die Geburt der Tragödie), MA (Menschliches, Allzumenschliches),
  M (Morgenröte), FW (Die fröhliche Wissenschaft), Z (Also sprach
  Zarathustra), JGB (Jenseits von Gut und Böse), GM (Zur Genealogie
  der Moral), GD (Götzen-Dämmerung), EH (Ecce Homo), AC (Der
  Antichrist), NW (Nietzsche contra Wagner). Add KSA Nachlaß
  fragments later — they have their own ingestion challenges (KSA
  volume:page citations, not §-numbered).
- **Cross-reference rules** (`src/minerva/refs/rules/nietzsche.py`).
  The high-value surface forms:

  | target | forms |
  |---|---|
  | Kant | `Kant`, `Kants`, `Kantische`, `Kantischen`, `Kritik der reinen Vernunft` |
  | Hegel | `Hegel`, `Hegels`, `Hegelsche`, `Hegelschen` |
  | Plato | `Plato`, `Platon`, `Platons`, `platonisch`, `platonischen`, `Platoniker` |
  | Aristotle | `Aristoteles`, `aristotelisch` |
  | Schopenhauer | `Schopenhauer`, `Schopenhauers`, `schopenhauer'sch` |
  | Augustine | `Augustin`, `Augustins`, `Augustinus` |
  | Wagner | `Wagner`, `Wagners`, `Wagnerianer` (out-of-corpus) |
  | Spinoza | `Spinoza`, `Spinozas`, `spinozistisch` |
  | Descartes | `Descartes`, `Cartesius`, `cartesianisch` |
  | Goethe | (out-of-corpus, add to ref-targets seed) |

  Confidence 0.65–0.75 for the modern targets, lower for the ancients.
  Nietzsche's mention frequency is high enough that even rule_weak
  has good signal; the LLM stage filters effectively.
- **Sidebar.** After Hegel, before any later additions (1844–1900).

## Hebrew Bible (Masoretic Text)

**Status:** implemented (as of 2026-05).

- **Downloader:** `perseus/download_hebrew_mt.py` → `data/hebrew_mt/raw/`.
- **Works:** `src/minerva/hebrew_mt_works.py`; corpus slug `hebrew_mt`.
- **Citation:** `bcv` (book:chapter:verse). Reader uses RTL layout and
  transliteration hover (`web/src/lib/hebrew.ts`).
- **Chat:** `AUTHOR_KEYWORDS` includes `tanakh`, `torah`, `masoretic`
  (see `corpus_registry.py`). Serve with `--lang any` (default).
- **FTS caveat:** niqqud/te'amim are part of the indexed token — lexical
  queries without diacritics may miss (§14d). Vector search bypasses this.

## Quran (Arabic)

**Status:** implemented (as of 2026-05).

- **Downloader:** `perseus/download_quran.py` (Uthmani XML).
- **Works:** `src/minerva/quran_works.py`; citation system `surah_ayah`.
- **Reader:** RTL + Arabic transliteration (`web/src/lib/arabic.ts`).
- **Chat:** keywords `quran`, `koran`, `surah`, `quranic`, etc.

## Marx, Cicero, and Stoics (brief)

**Status:** implemented (as of 2026-05).

| Corpus | Downloader(s) | Rules module |
|--------|---------------|--------------|
| `marx` | `download_marx_zeno.py`, `download_marx_wikisource.py`, … | `refs/rules/marx.py` |
| `cicero` | `download_cicero_wikisource.py` | `refs/rules/cicero.py` |
| `lucretius` | `download_ancient_pg.py` / Perseus | `refs/rules/lucretius.py` |
| `epictetus` | `download_perseus_epictetus.py` | (incoming xrefs from later authors) |
| `marcus_aurelius` | `download_marcus_aurelius.py` | `refs/rules/marcus_aurelius.py` |

Wire `corpus_registry` + §14 smoke tests for any new slug; Marx and
Nietzsche both need `deu` retrieval (`--lang any` or `--lang deu`).

---

# Common pitfalls

- **Re-ingest wipes chunk_lemmas.** Always re-run
  `minerva terms lemmatize --lang <lang>` after `minerva index`.
  (see [MEMORY.md#reingest-wipes-lemmas](MEMORY.md#reingest-wipes-lemmas)).
- **Re-ingest USED to wipe cross_references.** Fixed by migration
  0013 + the rebind step in `store.py`, but the rule is enforced by
  the auto-snapshot in `cmd_index` and the manual
  `scripts/snapshot-db.sh` discipline. (see
  [MEMORY.md#reingest-wipes-cross-references](MEMORY.md#reingest-wipes-cross-references),
  [MEMORY.md#snapshot-before-destructive-ops](MEMORY.md#snapshot-before-destructive-ops)).
- **Multi-statement SQL cleanups.** Always wrap in
  `BEGIN; ... SELECT verify; ROLLBACK;` first, commit only after
  the verification looks right. (see
  [MEMORY.md#transactional-preview-for-multistatement-sql](MEMORY.md#transactional-preview-for-multistatement-sql)).
- **LLM verify connection resets.** `src/minerva/llm.py` retries
  with exponential backoff on `ConnectionResetError` / `socket.timeout`
  / 429 / 5xx. If the verifier crashes anyway, just re-run — the
  idempotence filter (`source_method NOT LIKE '%llm%'`) skips
  already-verified rows.
- **Chunk-id stability.** If your splitter's hashing changes (you
  rename a section, alter the `text[:120]` prefix used in
  `_make_chunk_id`), chunks will get NEW ids and the rebind step
  will treat them as orphans. Don't touch existing splitter logic
  when adding a new author; only add new splitter modules.

---

# Historical: bulk expansion order (2025–2026)

These authors are **landed** in the repo today. The sequence below is
kept as reference when adding another biblical or modern batch.

If you're ingesting Homer + LXX + Vulgate + NT + Nietzsche from scratch,
the dependency-ordered sequence was:

1. **Homer first.** Smallest scope, fastest validation of the
   Perseus-XML reuse path. Bindings to Plato/Aristotle's Homer
   citations are immediate value.
2. **Septuagint + NT** together (both Greek, same `perseus_xml`
   splitter, same `bcv` citation convention). One ingest pass, one
   embed pass, one lemmatize pass.
3. **Vulgate.** Latin, separate source, but same citation convention.
   Re-run rules + LLM on Aquinas after — every "ut dicit Apostolus"
   suddenly resolves to a real Vulgate chunk.
4. **Nietzsche last.** Most modern, highest outbound-cite density,
   benefits from having all the older authors (especially Plato,
   Augustine, Schopenhauer's stand-in) already in the corpus as
   target candidates.

Estimate: ~2–3 sessions per author for the careful approach
(downloader + splitter + verification). Nietzsche alone is probably
1 session; the biblical texts together are probably 2 because of
the canon-coverage decisions and the post-ingest re-detection on
Aquinas.
